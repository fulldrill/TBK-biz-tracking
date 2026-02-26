from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models import User, Transaction
from app.auth import get_current_user
from app.services.pdf_generator import generate_receipt_pdf, generate_batch_receipt_pdf
from app.config import settings
from typing import Optional
from datetime import datetime
import os
import uuid

router = APIRouter(prefix="/receipts", tags=["Receipts"])

@router.get("/{transaction_id}")
async def get_single_receipt(
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

@router.post("/batch")
async def generate_batch_receipts(
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
