"""
Statement Parser router — /orgs/{org_id}/statements/

POST /parse    — Upload PDF or ZIP → returns extracted transactions as preview JSON (not saved)
POST /import   — Accept parsed transaction list → save to DB → return count
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import require_org_role
from app.config import settings
from app.database import get_db
from app.models import BankAccount, OrgRole, Transaction, TransactionType
from app.schemas import ParsedTransaction, StatementImportRequest
from app.services.statement_parser import parse_pdf_bytes, parse_zip_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs/{org_id}/statements", tags=["Statements"])

# Max upload size: 50 MB
_MAX_BYTES = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helper: get or create a virtual "Statement Import" bank account for the org
# ---------------------------------------------------------------------------
async def _get_statement_account(
    org_id: str,
    user_id: str,
    db: AsyncSession,
) -> BankAccount:
    """
    Return the org's dedicated statement-import bank account, creating it if needed.
    This satisfies the NOT NULL FK constraint on transactions.account_id.
    """
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.org_id == uuid.UUID(org_id),
            BankAccount.plaid_item_id == "statement_import",
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        account = BankAccount(
            user_id=uuid.UUID(user_id),
            org_id=uuid.UUID(org_id),
            plaid_access_token="statement_import",
            plaid_item_id="statement_import",
            account_id=f"stmt_{org_id}",
            account_name="Statement Import",
            account_type="checking",
            institution_name="Uploaded Statement",
        )
        db.add(account)
        await db.flush()

    return account


# ---------------------------------------------------------------------------
# POST /orgs/{org_id}/statements/parse
# ---------------------------------------------------------------------------
@router.post("/parse")
async def parse_statement(
    org_id: str,
    file: UploadFile = File(...),
    auth=Depends(require_org_role(OrgRole.ADMIN)),
) -> dict[str, Any]:
    """
    Upload a PDF (or ZIP of PDFs) bank statement.
    Returns extracted transactions as a JSON preview — nothing is saved to the DB yet.

    - Accepts: application/pdf, application/zip, application/x-zip-compressed
    - Max size: 50 MB
    """
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured. Add it to your .env file.",
        )

    content_type = file.content_type or ""
    filename = file.filename or "upload"
    raw_bytes = await file.read()

    if len(raw_bytes) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB).")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    is_zip = (
        content_type in ("application/zip", "application/x-zip-compressed")
        or filename.lower().endswith(".zip")
    )
    is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

    if is_zip:
        transactions = await parse_zip_bytes(raw_bytes, client)
    elif is_pdf:
        transactions = await parse_pdf_bytes(raw_bytes, filename, client)
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PDF or a ZIP of PDFs.",
        )

    return {
        "transaction_count": len(transactions),
        "transactions": transactions,
        "source_file": filename,
    }


# ---------------------------------------------------------------------------
# POST /orgs/{org_id}/statements/import
# ---------------------------------------------------------------------------
@router.post("/import")
async def import_statement_transactions(
    org_id: str,
    body: StatementImportRequest,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Persist a list of parsed transactions (from /parse) into the database.
    Skips duplicates by synthetic plaid_transaction_id.
    Returns the count of newly inserted transactions.
    """
    current_user, _ = auth
    account = await _get_statement_account(org_id, str(current_user.id), db)

    inserted = 0
    skipped = 0

    for tx in body.transactions:
        # Parse date
        try:
            tx_date = datetime.fromisoformat(tx.date).replace(tzinfo=None)
        except ValueError:
            logger.warning(f"Skipping transaction with invalid date: {tx.date!r}")
            skipped += 1
            continue

        # Generate a stable synthetic Plaid-style ID so re-imports don't duplicate
        # Uses date + name + amount so the same transaction always hashes the same
        stable_key = f"stmt_{uuid.uuid5(uuid.NAMESPACE_URL, f'{tx.date}|{tx.name}|{tx.amount}|{org_id}').hex}"

        # Check for duplicate
        existing = await db.execute(
            select(Transaction).where(Transaction.plaid_transaction_id == stable_key)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        tx_type = (
            TransactionType.CREDIT
            if tx.transaction_type == "credit"
            else TransactionType.DEBIT
        )

        record = Transaction(
            user_id=current_user.id,
            org_id=uuid.UUID(org_id),
            account_id=account.id,
            plaid_transaction_id=stable_key,
            amount=abs(tx.amount),
            date=tx_date,
            name=tx.name,
            category=tx.category,
            transaction_type=tx_type,
            is_zelle=tx.is_zelle,
            zelle_counterparty=tx.zelle_counterparty,
            zelle_direction=tx.zelle_direction,
            assigned_user=tx.assigned_user,
            source="statement_import",
        )
        db.add(record)
        inserted += 1

    await db.commit()
    logger.info(f"Statement import: {inserted} inserted, {skipped} skipped (org {org_id})")

    return {
        "inserted": inserted,
        "skipped": skipped,
        "message": f"Imported {inserted} transaction(s). {skipped} duplicate(s) skipped.",
    }
