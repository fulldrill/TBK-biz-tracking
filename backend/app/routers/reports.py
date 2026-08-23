from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database import get_db
from app.models import Transaction, Organization, OrgRole, PnlEntry, PnlExclusion
from app.schemas import PnlEntryCreate, PnlEntryUpdate, PnlEntryOut
from app.auth import require_org_role
from app.services.pnl import build_pnl
from app.services.pdf_generator import generate_pnl_pdf
from app.config import settings
from datetime import datetime, timedelta
from typing import Optional, List
import os
import uuid

router = APIRouter(prefix="/orgs/{org_id}/reports", tags=["Reports"])

# Deferred revenue lands the month after it is earned, so a deposit dated just
# past period_end still belongs inside the period. Query wider than the window
# and let build_pnl filter on effective date.
_LOOKAHEAD = timedelta(days=45)


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
            Transaction.date <= end + _LOOKAHEAD,
        ))
        .order_by(Transaction.date)
    )
    return result.scalars().all()


async def _load_excluded(db: AsyncSession, org_id: str) -> list[str]:
    result = await db.execute(
        select(PnlExclusion.line_label).where(PnlExclusion.org_id == org_id)
    )
    return list(result.scalars().all())


async def _load_manual(db: AsyncSession, org_id: str):
    result = await db.execute(
        select(PnlEntry).where(and_(
            PnlEntry.org_id == org_id,
            PnlEntry.is_active.is_(True),
        ))
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
    manual = await _load_manual(db, org_id)
    removed = await _load_excluded(db, org_id)
    return build_pnl(
        transactions, start, end, manual_entries=manual, excluded_labels=removed
    )


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
    manual = await _load_manual(db, org_id)
    removed = await _load_excluded(db, org_id)
    pnl = build_pnl(
        transactions, start, end, manual_entries=manual, excluded_labels=removed
    )

    if not pnl["transaction_count"] and not pnl["manual_entry_count"]:
        raise HTTPException(status_code=404, detail="No transactions found for that period")

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


# ---------------------------------------------------------------------------
# Manual P&L entries — costs and income that never touched the bank account
# ---------------------------------------------------------------------------

def _validate(entry_type: str, recurrence: str) -> None:
    if entry_type not in ("revenue", "expense"):
        raise HTTPException(status_code=422, detail="entry_type must be 'revenue' or 'expense'")
    if recurrence not in ("monthly", "once"):
        raise HTTPException(status_code=422, detail="recurrence must be 'monthly' or 'once'")


@router.get("/entries", response_model=List[PnlEntryOut])
async def list_entries(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PnlEntry).where(PnlEntry.org_id == org_id).order_by(PnlEntry.created_at.desc())
    )
    return result.scalars().all()


@router.post("/entries", response_model=PnlEntryOut, status_code=201)
async def create_entry(
    org_id: str,
    body: PnlEntryCreate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    _validate(body.entry_type, body.recurrence)
    if body.end_date and body.end_date < body.start_date:
        raise HTTPException(status_code=422, detail="end_date cannot be before start_date")

    entry = PnlEntry(
        org_id=uuid.UUID(org_id),
        label=body.label.strip(),
        amount=body.amount,   # signed: a negative entry subtracts
        entry_type=body.entry_type,
        recurrence=body.recurrence,
        start_date=body.start_date,
        end_date=body.end_date,
        notes=body.notes,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.patch("/entries/{entry_id}", response_model=PnlEntryOut)
async def update_entry(
    org_id: str,
    entry_id: str,
    body: PnlEntryUpdate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    entry = (await db.execute(
        select(PnlEntry).where(and_(PnlEntry.id == entry_id, PnlEntry.org_id == org_id))
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    data = body.model_dump(exclude_unset=True)
    _validate(
        data.get("entry_type", entry.entry_type),
        data.get("recurrence", entry.recurrence),
    )
    for field, value in data.items():
        setattr(entry, field, value)

    if entry.end_date and entry.end_date < entry.start_date:
        raise HTTPException(status_code=422, detail="end_date cannot be before start_date")

    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    org_id: str,
    entry_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    entry = (await db.execute(
        select(PnlEntry).where(and_(PnlEntry.id == entry_id, PnlEntry.org_id == org_id))
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(entry)
    await db.commit()


# ---------------------------------------------------------------------------
# Line exclusions — lines the user chooses to keep off the statement
# ---------------------------------------------------------------------------

@router.get("/exclusions")
async def list_exclusions(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PnlExclusion).where(PnlExclusion.org_id == org_id).order_by(PnlExclusion.line_label)
    )
    return [
        {"id": str(e.id), "line_label": e.line_label}
        for e in result.scalars().all()
    ]


@router.post("/exclusions", status_code=201)
async def add_exclusion(
    org_id: str,
    body: dict,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    label = (body.get("line_label") or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="line_label is required")

    existing = await db.execute(
        select(PnlExclusion).where(and_(
            PnlExclusion.org_id == org_id,
            PnlExclusion.line_label == label,
        ))
    )
    row = existing.scalar_one_or_none()
    if row:
        return {"id": str(row.id), "line_label": row.line_label}

    row = PnlExclusion(org_id=uuid.UUID(org_id), line_label=label)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": str(row.id), "line_label": row.line_label}


@router.delete("/exclusions", status_code=200)
async def remove_exclusion(
    org_id: str,
    line_label: str = Query(..., description="The line to put back on the statement"),
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PnlExclusion).where(and_(
            PnlExclusion.org_id == org_id,
            PnlExclusion.line_label == line_label,
        ))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="That line is not excluded")
    await db.delete(row)
    await db.commit()
    return {"status": "restored", "line_label": line_label}
