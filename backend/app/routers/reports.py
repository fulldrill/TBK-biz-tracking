from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database import get_db
from app.models import Transaction, Organization, OrgRole
from app.auth import require_org_role
from app.services.pnl import build_pnl
from app.services.pdf_generator import generate_pnl_pdf
from app.config import settings
from datetime import datetime, timedelta
from typing import Optional
import os
import uuid

router = APIRouter(prefix="/orgs/{org_id}/reports", tags=["Reports"])


def _resolve_period(
    year: Optional[int],
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> tuple[datetime, datetime]:
    """`year` wins when supplied; otherwise use the explicit range, else last 12 months."""
    if year:
        return datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59)
    if start_date and end_date:
        return start_date, end_date
    end = end_date or datetime.utcnow()
    start = start_date or (end - timedelta(days=365))
    return start, end


async def _load(db: AsyncSession, org_id: str, start: datetime, end: datetime):
    result = await db.execute(
        select(Transaction)
        .where(and_(
            Transaction.org_id == org_id,
            Transaction.date >= start,
            Transaction.date <= end,
        ))
        .order_by(Transaction.date)
    )
    return result.scalars().all()


@router.get("/years")
async def available_years(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    """Years that actually have transactions, newest first — drives the year picker."""
    result = await db.execute(
        select(func.extract("year", Transaction.date))
        .where(Transaction.org_id == org_id)
        .distinct()
    )
    years = sorted({int(row[0]) for row in result.all() if row[0] is not None}, reverse=True)
    return {"years": years}


@router.get("/pnl")
async def get_pnl(
    org_id: str,
    year: Optional[int] = Query(None, description="Calendar year; overrides start/end"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    start, end = _resolve_period(year, start_date, end_date)
    transactions = await _load(db, org_id, start, end)
    return build_pnl(transactions, start, end)


@router.get("/pnl/pdf")
async def get_pnl_pdf(
    org_id: str,
    year: Optional[int] = Query(None, description="Calendar year; overrides start/end"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    start, end = _resolve_period(year, start_date, end_date)
    transactions = await _load(db, org_id, start, end)
    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions found for that period")

    pnl = build_pnl(transactions, start, end)

    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    org_name = org.name if org else "Clerq"

    report_id = str(uuid.uuid4())[:8]
    pdf_path = os.path.join(settings.RECEIPT_STORAGE_PATH, org_id, f"pnl_{report_id}.pdf")
    generate_pnl_pdf(pnl, pdf_path, org_name=org_name)

    label = str(year) if year else f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"profit-and-loss_{label}.pdf",
    )
