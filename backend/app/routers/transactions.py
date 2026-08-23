from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db, AsyncSessionLocal
from app.models import User, BankAccount, Transaction, TransactionType, OrgRole, LoanRepayment, Organization
from app.schemas import TransactionOut, TransactionUpdate, BulkDeleteRequest
from app.auth import get_current_user, require_org_role
from app.services.plaid_service import fetch_transactions
from app.services.zelle_parser import parse_zelle
from app.services.categorizer import categorize_transaction
from app.services.attribution import assign_user
from app.services.receipt_cache import invalidate_receipt_cache
from app.config import settings
from openai import AsyncOpenAI
from datetime import datetime
from typing import List, Optional
from uuid import UUID
import logging

router = APIRouter(prefix="/orgs/{org_id}/transactions", tags=["Transactions"])
legacy_router = APIRouter(prefix="/transactions", tags=["Transactions (legacy)"])
logger = logging.getLogger(__name__)


async def sync_transactions_for_account(account_id: str, org_id: str, user_id: str, days_back: int = 90):
    """Background task: opens its own DB session to avoid closed-session issues."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BankAccount).where(BankAccount.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            return
        raw_transactions = await fetch_transactions(account.plaid_access_token, days_back)
        for tx in raw_transactions:
            existing = await db.execute(
                select(Transaction).where(Transaction.plaid_transaction_id == tx["transaction_id"])
            )
            if existing.scalar_one_or_none():
                continue
            name = tx.get("name") or ""
            description = tx.get("original_description") or tx.get("name") or ""
            amount = tx.get("amount", 0)
            tx_type = TransactionType.DEBIT if amount > 0 else TransactionType.CREDIT
            plaid_cats = tx.get("category") or []
            plaid_category = " > ".join(plaid_cats) if plaid_cats else None
            category = categorize_transaction(name, description, plaid_category)
            is_zelle, counterparty, direction = parse_zelle(name, description, amount)
            tx_type_str = "debit" if tx_type == TransactionType.DEBIT else "credit"
            transaction = Transaction(
                user_id=user_id,
                org_id=org_id,
                account_id=account.id,
                plaid_transaction_id=tx["transaction_id"],
                amount=amount,
                date=datetime.strptime(tx["date"], "%Y-%m-%d"),
                name=name,
                description=description,
                merchant_name=tx.get("merchant_name"),
                category=category,
                transaction_type=tx_type,
                is_zelle=is_zelle,
                zelle_counterparty=counterparty,
                zelle_direction=direction,
                assigned_user=assign_user(name, tx_type_str, is_zelle, counterparty),
            )
            db.add(transaction)
        account.last_synced = datetime.utcnow()
        await db.commit()
        logger.info(f"Synced {len(raw_transactions)} transactions for account {account.account_name}")


@router.post("/sync")
async def sync_transactions(
    org_id: str,
    background_tasks: BackgroundTasks,
    days_back: int = Query(90, ge=1, le=730),
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    result = await db.execute(
        select(BankAccount).where(BankAccount.org_id == org_id)
    )
    accounts = result.scalars().all()
    if not accounts:
        raise HTTPException(status_code=404, detail="No connected bank accounts. Connect a bank first.")
    for account in accounts:
        background_tasks.add_task(
            sync_transactions_for_account,
            str(account.id),
            org_id,
            str(current_user.id),
            days_back,
        )
    return {"status": "sync started", "accounts": len(accounts)}


@router.get("/", response_model=List[TransactionOut])
async def get_transactions(
    org_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_zelle: Optional[bool] = None,
    transaction_type: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    filters = [Transaction.org_id == org_id]
    if start_date:
        filters.append(Transaction.date >= start_date)
    if end_date:
        filters.append(Transaction.date <= end_date)
    if is_zelle is not None:
        filters.append(Transaction.is_zelle == is_zelle)
    if transaction_type:
        filters.append(Transaction.transaction_type == transaction_type)
    if category:
        filters.append(Transaction.category.ilike(f"%{category}%"))
    if source:
        filters.append(Transaction.source == source)
    result = await db.execute(
        select(Transaction)
        .where(and_(*filters))
        .order_by(Transaction.date.desc())
        .limit(limit)
        .offset(offset)
    )
    txns = result.scalars().all()

    # Enrich with repayment_loan_id
    tx_ids = [tx.id for tx in txns]
    repayment_map: dict = {}
    if tx_ids:
        rep_result = await db.execute(
            select(LoanRepayment).where(LoanRepayment.transaction_id.in_(tx_ids))
        )
        for rep in rep_result.scalars().all():
            if rep.transaction_id:
                repayment_map[rep.transaction_id] = rep.loan_id

    out = []
    for tx in txns:
        tx_out = TransactionOut.model_validate(tx)
        tx_out.repayment_loan_id = repayment_map.get(tx.id)
        out.append(tx_out)
    return out


@router.patch("/{transaction_id}", response_model=TransactionOut)
async def update_transaction(
    org_id: str,
    transaction_id: str,
    body: TransactionUpdate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.org_id == org_id)
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if body.assigned_user is not None:
        tx.assigned_user = body.assigned_user if body.assigned_user != "" else None
    if body.business_purpose is not None:
        note = body.business_purpose.strip()
        tx.business_purpose = note or None
        # An owner-written note outranks anything generated, and clearing one
        # puts the row back in the "needs your note" queue rather than leaving
        # it silently blank.
        tx.purpose_source = "manual" if note else "needs_input"

    # Both fields print on the receipt, which is cached on disk. Without this
    # the next download would serve the PDF built before the edit.
    invalidate_receipt_cache(org_id, tx)

    await db.commit()
    await db.refresh(tx)
    return tx


@router.delete("/bulk")
async def bulk_delete_transactions(
    org_id: str,
    body: BulkDeleteRequest,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        sql_delete(Transaction).where(
            and_(
                Transaction.org_id == org_id,
                Transaction.id.in_([UUID(i) for i in body.ids]),
            )
        )
    )
    await db.commit()
    return {"deleted": result.rowcount}


@router.delete("/{transaction_id}")
async def delete_transaction(
    org_id: str,
    transaction_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.org_id == org_id)
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.delete(tx)
    await db.commit()
    return {"status": "deleted"}


# --- Legacy routes ---

async def _legacy_sync_for_account(account: BankAccount, db: AsyncSession, days_back: int = 90):
    raw_transactions = await fetch_transactions(account.plaid_access_token, days_back)
    for tx in raw_transactions:
        existing = await db.execute(
            select(Transaction).where(Transaction.plaid_transaction_id == tx["transaction_id"])
        )
        if existing.scalar_one_or_none():
            continue
        name = tx.get("name") or ""
        description = tx.get("original_description") or tx.get("name") or ""
        amount = tx.get("amount", 0)
        tx_type = TransactionType.DEBIT if amount > 0 else TransactionType.CREDIT
        plaid_cats = tx.get("category") or []
        plaid_category = " > ".join(plaid_cats) if plaid_cats else None
        category = categorize_transaction(name, description, plaid_category)
        is_zelle, counterparty, direction = parse_zelle(name, description, amount)
        tx_type_str = "debit" if tx_type == TransactionType.DEBIT else "credit"
        transaction = Transaction(
            user_id=account.user_id,
            org_id=account.org_id,
            account_id=account.id,
            plaid_transaction_id=tx["transaction_id"],
            amount=amount,
            date=datetime.strptime(tx["date"], "%Y-%m-%d"),
            name=name,
            description=description,
            merchant_name=tx.get("merchant_name"),
            category=category,
            transaction_type=tx_type,
            is_zelle=is_zelle,
            zelle_counterparty=counterparty,
            zelle_direction=direction,
            assigned_user=assign_user(name, tx_type_str, is_zelle, counterparty),
        )
        db.add(transaction)
    account.last_synced = datetime.utcnow()
    await db.commit()


@legacy_router.post("/sync")
async def legacy_sync_transactions(
    background_tasks: BackgroundTasks,
    days_back: int = Query(90, ge=1, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BankAccount).where(BankAccount.user_id == current_user.id)
    )
    accounts = result.scalars().all()
    if not accounts:
        raise HTTPException(status_code=404, detail="No connected bank accounts. Connect a bank first.")
    for account in accounts:
        background_tasks.add_task(_legacy_sync_for_account, account, db, days_back)
    return {"status": "sync started", "accounts": len(accounts)}


@legacy_router.get("/", response_model=List[TransactionOut])
async def legacy_get_transactions(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_zelle: Optional[bool] = None,
    transaction_type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [Transaction.user_id == current_user.id]
    if start_date:
        filters.append(Transaction.date >= start_date)
    if end_date:
        filters.append(Transaction.date <= end_date)
    if is_zelle is not None:
        filters.append(Transaction.is_zelle == is_zelle)
    if transaction_type:
        filters.append(Transaction.transaction_type == transaction_type)
    if category:
        filters.append(Transaction.category.ilike(f"%{category}%"))
    result = await db.execute(
        select(Transaction)
        .where(and_(*filters))
        .order_by(Transaction.date.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@legacy_router.delete("/{transaction_id}")
async def legacy_delete_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.delete(tx)
    await db.commit()
    return {"status": "deleted"}


@router.post("/generate-purposes")
async def generate_business_purposes(
    org_id: str,
    overwrite: bool = Query(False, description="Regenerate notes already generated"),
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Write a business-purpose note onto every transaction that lacks one.

    Notes an owner wrote are never touched, even with overwrite=true — those
    are an attestation, not something to regenerate.
    """
    from app.services.purpose_generator import (
        build_context, derive_purpose, ai_purposes,
        SOURCE_AI, SOURCE_NEEDS_INPUT, SOURCE_MANUAL,
    )

    all_rows = (await db.execute(
        select(Transaction).where(Transaction.org_id == org_id).order_by(Transaction.date)
    )).scalars().all()
    if not all_rows:
        return {"derived": 0, "ai": 0, "needs_input": 0, "skipped": 0}

    ctx = build_context(all_rows)

    targets = [
        tx for tx in all_rows
        if tx.purpose_source != SOURCE_MANUAL
        and (overwrite or not tx.business_purpose)
    ]
    skipped = len(all_rows) - len(targets)

    counts = {"derived": 0, "ai": 0, "needs_input": 0, "skipped": skipped}
    unresolved: list = []

    for tx in targets:
        note, source = derive_purpose(tx, ctx)
        if source and source != SOURCE_NEEDS_INPUT and note:
            tx.business_purpose = note
            tx.purpose_source = source
            invalidate_receipt_cache(org_id, tx)
            counts["derived"] += 1
        elif source == SOURCE_NEEDS_INPUT:
            tx.business_purpose = None
            tx.purpose_source = SOURCE_NEEDS_INPUT
            invalidate_receipt_cache(org_id, tx)
            counts["needs_input"] += 1
        else:
            unresolved.append(tx)

    # Anything no rule matched goes to the model, which restates the
    # description or returns null when it reveals nothing.
    if unresolved and settings.OPENAI_API_KEY:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        for start in range(0, len(unresolved), 40):
            chunk = unresolved[start:start + 40]
            notes = await ai_purposes(client, [(t.name or "") for t in chunk])
            for i, tx in enumerate(chunk):
                note = notes.get(i)
                if note:
                    tx.business_purpose = note
                    tx.purpose_source = SOURCE_AI
                    counts["ai"] += 1
                else:
                    tx.business_purpose = None
                    tx.purpose_source = SOURCE_NEEDS_INPUT
                    counts["needs_input"] += 1
                invalidate_receipt_cache(org_id, tx)
    else:
        for tx in unresolved:
            tx.business_purpose = None
            tx.purpose_source = SOURCE_NEEDS_INPUT
            invalidate_receipt_cache(org_id, tx)
            counts["needs_input"] += 1

    await db.commit()
    logger.info(f"Purpose generation for org {org_id}: {counts}")
    return counts


@router.post("/reclassify-owner-transfers")
async def reclassify_owner_transfers(
    org_id: str,
    dry_run: bool = Query(True, description="Preview without writing"),
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Recategorise Zelle to/from the org's own people as equity movement.

    Paying yourself by Zelle is indistinguishable from paying a supplier, so
    these land in operating expenses by default and understate profit. Money
    out becomes Owner's Draw, money in Owner's Contribution; both are excluded
    from the P&L and shown in its excluded section.

    Defaults to a dry run because it moves money between P&L sections — call
    with dry_run=false to apply.
    """
    from app.models import OrgPerson
    from app.services.owner_transfers import (
        owner_tokens, classify_owner_transfer, purpose_note, kind_of,
        CATEGORY_DRAW, CATEGORY_CONTRIBUTION,
    )

    people = (await db.execute(
        select(OrgPerson).where(OrgPerson.org_id == org_id)
    )).scalars().all()
    owners = owner_tokens(people)
    if not owners:
        raise HTTPException(
            status_code=400,
            detail="This organization has no people configured, so there is no "
                   "owner to match against. Add them in settings first.",
        )

    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    org_name = org.name if org else ""

    rows = (await db.execute(
        select(Transaction).where(
            and_(Transaction.org_id == org_id, Transaction.is_zelle.is_(True))
        ).order_by(Transaction.date)
    )).scalars().all()

    changes: list[dict] = []
    for tx in rows:
        tx_type = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
        category, owner = classify_owner_transfer(
            tx.is_zelle, tx.zelle_counterparty, tx.zelle_direction, tx_type, owners
        )
        if not category or tx.category == category:
            continue
        changes.append({
            "id": str(tx.id),
            "date": tx.date.strftime("%Y-%m-%d"),
            "counterparty": tx.zelle_counterparty,
            "amount": abs(tx.amount or 0.0),
            "from_category": tx.category,
            "to_category": category,
            "owner": owner,
        })
        if not dry_run:
            tx.category = category
            # An owner's own note is an attestation — never overwrite it.
            if tx.purpose_source != "manual":
                tx.business_purpose = purpose_note(
                    category, owner, org_name, kind_of(owners, owner)
                )
                tx.purpose_source = "derived"
            invalidate_receipt_cache(org_id, tx)

    if not dry_run and changes:
        await db.commit()

    draws = [c for c in changes if c["to_category"] == CATEGORY_DRAW]
    contribs = [c for c in changes if c["to_category"] == CATEGORY_CONTRIBUTION]
    return {
        "dry_run": dry_run,
        "matched_owners": sorted(owners.keys()),
        "draw_count": len(draws),
        "draw_total": round(sum(c["amount"] for c in draws), 2),
        "contribution_count": len(contribs),
        "contribution_total": round(sum(c["amount"] for c in contribs), 2),
        "changes": changes,
    }
