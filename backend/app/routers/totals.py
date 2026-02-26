from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models import User, Transaction, TransactionType
from app.schemas import TotalsResponse
from app.auth import get_current_user
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter(prefix="/totals", tags=["Totals"])

@router.get("/", response_model=TotalsResponse)
async def get_totals(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    base_filter = and_(
        Transaction.user_id == current_user.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
    )
    all_tx = await db.execute(select(Transaction).where(base_filter))
    transactions = all_tx.scalars().all()

    total_deposits = sum(abs(t.amount) for t in transactions if t.transaction_type == TransactionType.CREDIT)
    total_withdrawals = sum(abs(t.amount) for t in transactions if t.transaction_type == TransactionType.DEBIT)
    zelle_sent = sum(abs(t.amount) for t in transactions if t.is_zelle and t.zelle_direction == "sent")
    zelle_received = sum(abs(t.amount) for t in transactions if t.is_zelle and t.zelle_direction == "received")

    return TotalsResponse(
        total_deposits=total_deposits,
        total_withdrawals=total_withdrawals,
        zelle_sent=zelle_sent,
        zelle_received=zelle_received,
        net_balance=total_deposits - total_withdrawals,
        transaction_count=len(transactions),
        period_start=start_date,
        period_end=end_date,
    )

@router.get("/monthly")
async def get_monthly_breakdown(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.date)
    )
    transactions = result.scalars().all()
    monthly: dict = {}
    for tx in transactions:
        key = tx.date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"deposits": 0.0, "withdrawals": 0.0, "zelle_sent": 0.0, "zelle_received": 0.0, "count": 0}
        if tx.transaction_type == TransactionType.CREDIT:
            monthly[key]["deposits"] += abs(tx.amount)
        else:
            monthly[key]["withdrawals"] += abs(tx.amount)
        if tx.is_zelle:
            if tx.zelle_direction == "sent":
                monthly[key]["zelle_sent"] += abs(tx.amount)
            else:
                monthly[key]["zelle_received"] += abs(tx.amount)
        monthly[key]["count"] += 1
    return {"monthly_breakdown": monthly}
