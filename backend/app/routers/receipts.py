from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models import User, Transaction, Organization, OrgRole
from app.auth import get_current_user, require_org_role
from app.services.pdf_generator import (
    generate_receipt_pdf,
    generate_batch_receipt_pdf,
    generate_all_receipts_pdf,
)
from app.config import settings
from typing import Optional
from datetime import datetime
import os
import uuid

router = APIRouter(prefix="/orgs/{org_id}/receipts", tags=["Receipts"])
legacy_router = APIRouter(prefix="/receipts", tags=["Receipts (legacy)"])


def _receipt_data(tx, org_name: str = "") -> dict:
    """Shape one Transaction row into the dict the PDF generator expects."""
    return {
        "date": tx.date.strftime("%Y-%m-%d"),
        "name": tx.name,
        "transaction_type": tx.transaction_type.value,
        "amount": tx.amount,
        "category": tx.category,
        "is_zelle": tx.is_zelle,
        "zelle_direction": tx.zelle_direction,
        "zelle_counterparty": tx.zelle_counterparty,
        "assigned_user": tx.assigned_user,
        "account_label": tx.account_label,
        "statement_period": tx.statement_period,
        "statement_file": tx.statement_file,
        "reference": tx.plaid_transaction_id,
        "business_purpose": tx.business_purpose,
    }


# Declared before /{transaction_id} — a single-segment path parameter would
# otherwise capture "all" and look for a transaction with that id.
@router.get("/all")
async def download_all_receipts(
    org_id: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    transaction_type: Optional[str] = Query(None),
    is_zelle: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    assigned_user: Optional[str] = Query(None),
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    """Every matching receipt as one PDF, one per page, in date order.

    Takes the same filters as the transaction list so what you see on the
    dashboard is what you get in the file.
    """
    filters = [Transaction.org_id == org_id]
    if start_date:
        filters.append(Transaction.date >= start_date)
    if end_date:
        filters.append(Transaction.date <= end_date)
    if transaction_type:
        filters.append(Transaction.transaction_type == transaction_type)
    if is_zelle is not None:
        filters.append(Transaction.is_zelle.is_(is_zelle))
    if category:
        filters.append(Transaction.category.ilike(f"%{category}%"))
    if assigned_user:
        filters.append(Transaction.assigned_user == assigned_user)

    result = await db.execute(
        select(Transaction).where(and_(*filters)).order_by(Transaction.date)
    )
    transactions = result.scalars().all()
    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions match those filters")

    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    org_name = org.name if org else "Clerq"

    period_label = ""
    if start_date or end_date:
        lo = start_date.strftime("%Y-%m-%d") if start_date else "start"
        hi = end_date.strftime("%Y-%m-%d") if end_date else "today"
        period_label = f"{lo} to {hi}"

    batch_id = str(uuid.uuid4())[:8]
    pdf_path = os.path.join(settings.RECEIPT_STORAGE_PATH, org_id, f"receipts_{batch_id}.pdf")
    generate_all_receipts_pdf(
        [_receipt_data(t) for t in transactions],
        pdf_path,
        org_name=org_name,
        period_label=period_label,
    )
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"receipts_{len(transactions)}_{batch_id}.pdf",
    )


@router.get("/{transaction_id}")
async def get_single_receipt(
    org_id: str,
    transaction_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
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

    # The layout version is part of the filename: receipts are cached on disk,
    # so without it every transaction that already has a PDF would keep serving
    # the old format forever. Bump this whenever the receipt layout changes.
    pdf_path = os.path.join(
        settings.RECEIPT_STORAGE_PATH,
        org_id,
        f"{tx.plaid_transaction_id}_v2.pdf",
    )

    if not os.path.exists(pdf_path):
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        org = (await db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        generate_receipt_pdf(
            _receipt_data(tx),
            pdf_path,
            org_name=org.name if org else "Clerq",
        )
        tx.receipt_path = pdf_path
        await db.commit()

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"receipt_{tx.plaid_transaction_id}.pdf"
    )


@router.post("/batch")
async def generate_batch_receipts(
    org_id: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    filters = [Transaction.org_id == org_id]
    if start_date:
        filters.append(Transaction.date >= start_date)
    if end_date:
        filters.append(Transaction.date <= end_date)

    result = await db.execute(
        select(Transaction).where(and_(*filters)).order_by(Transaction.date.desc())
    )
    transactions = result.scalars().all()

    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions found for that period")

    deposits = sum(abs(t.amount) for t in transactions if t.transaction_type.value == "credit")
    withdrawals = sum(abs(t.amount) for t in transactions if t.transaction_type.value == "debit")
    zelle_sent = sum(abs(t.amount) for t in transactions if t.is_zelle and t.zelle_direction == "sent")
    zelle_received = sum(abs(t.amount) for t in transactions if t.is_zelle and t.zelle_direction == "received")

    totals = {
        "total_deposits": deposits,
        "total_withdrawals": withdrawals,
        "zelle_sent": zelle_sent,
        "zelle_received": zelle_received,
        "net_balance": deposits - withdrawals,
    }

    batch_id = str(uuid.uuid4())[:8]
    pdf_path = os.path.join(
        settings.RECEIPT_STORAGE_PATH,
        org_id,
        f"batch_{batch_id}.pdf",
    )
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    tx_dicts = [
        {
            "date": t.date,
            "name": t.name,
            "transaction_type": t.transaction_type.value,
            "amount": t.amount,
            "category": t.category,
            "is_zelle": t.is_zelle,
        }
        for t in transactions
    ]

    period_label = ""
    if start_date and end_date:
        period_label = f"({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"

    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    generate_batch_receipt_pdf(
        tx_dicts, totals, pdf_path,
        period_label=period_label,
        org_name=org.name if org else "Clerq",
    )
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"batch_receipt_{batch_id}.pdf"
    )


# --- Legacy routes ---

@legacy_router.get("/{transaction_id}")
async def legacy_get_single_receipt(
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

    pdf_path = os.path.join(
        settings.RECEIPT_STORAGE_PATH,
        str(current_user.id),
        f"{tx.plaid_transaction_id}.pdf",
    )

    if not os.path.exists(pdf_path):
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        generate_receipt_pdf(
            {
                "date": tx.date.strftime("%Y-%m-%d"),
                "name": tx.name,
                "transaction_type": tx.transaction_type.value,
                "amount": tx.amount,
                "category": tx.category,
                "is_zelle": tx.is_zelle,
                "zelle_direction": tx.zelle_direction,
                "zelle_counterparty": tx.zelle_counterparty,
            },
            pdf_path,
        )
        tx.receipt_path = pdf_path
        await db.commit()

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"receipt_{tx.plaid_transaction_id}.pdf"
    )


@legacy_router.post("/batch")
async def legacy_generate_batch_receipts(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [Transaction.user_id == current_user.id]
    if start_date:
        filters.append(Transaction.date >= start_date)
    if end_date:
        filters.append(Transaction.date <= end_date)

    result = await db.execute(
        select(Transaction).where(and_(*filters)).order_by(Transaction.date.desc())
    )
    transactions = result.scalars().all()

    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions found for that period")

    deposits = sum(abs(t.amount) for t in transactions if t.transaction_type.value == "credit")
    withdrawals = sum(abs(t.amount) for t in transactions if t.transaction_type.value == "debit")
    zelle_sent = sum(abs(t.amount) for t in transactions if t.is_zelle and t.zelle_direction == "sent")
    zelle_received = sum(abs(t.amount) for t in transactions if t.is_zelle and t.zelle_direction == "received")

    totals = {
        "total_deposits": deposits,
        "total_withdrawals": withdrawals,
        "zelle_sent": zelle_sent,
        "zelle_received": zelle_received,
        "net_balance": deposits - withdrawals,
    }

    batch_id = str(uuid.uuid4())[:8]
    pdf_path = os.path.join(
        settings.RECEIPT_STORAGE_PATH,
        str(current_user.id),
        f"batch_{batch_id}.pdf",
    )
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    tx_dicts = [
        {
            "date": t.date,
            "name": t.name,
            "transaction_type": t.transaction_type.value,
            "amount": t.amount,
            "category": t.category,
            "is_zelle": t.is_zelle,
        }
        for t in transactions
    ]

    period_label = ""
    if start_date and end_date:
        period_label = f"({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"

    generate_batch_receipt_pdf(tx_dicts, totals, pdf_path, period_label=period_label)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"batch_receipt_{batch_id}.pdf"
    )
