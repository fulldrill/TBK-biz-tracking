from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db, AsyncSessionLocal
from app.models import User, BankAccount, Transaction, TransactionType, OrgRole
from app.schemas import TransactionOut, TransactionUpdate, BulkDeleteRequest
from app.auth import get_current_user, require_org_role
from app.services.plaid_service import fetch_transactions
from app.services.zelle_parser import parse_zelle
from app.services.categorizer import categorize_transaction
from app.services.attribution import assign_user
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
    return result.scalars().all()


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
