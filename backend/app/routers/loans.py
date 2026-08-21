from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Loan, LoanRepayment, LoanStatus, OrgRole, Transaction
from app.schemas import LoanCreate, LoanUpdate, LoanOut, LoanSummaryOut, RepaymentCreate, RepaymentOut
from app.auth import require_org_role
from typing import List
from uuid import UUID

router = APIRouter(prefix="/orgs/{org_id}/loans", tags=["Loans"])


def _compute_balance(loan: Loan) -> float:
    paid = sum(r.amount for r in loan.repayments)
    return round(loan.principal - paid, 2)


def _to_loan_out(loan: Loan) -> LoanOut:
    balance = _compute_balance(loan)
    return LoanOut(
        id=loan.id,
        org_id=loan.org_id,
        borrower_name=loan.borrower_name,
        principal=loan.principal,
        date_issued=loan.date_issued,
        notes=loan.notes,
        status=loan.status,
        created_at=loan.created_at,
        outstanding_balance=balance,
        repayments=loan.repayments,
    )


@router.get("/", response_model=List[LoanOut])
async def list_loans(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Loan)
        .options(selectinload(Loan.repayments))
        .where(Loan.org_id == org_id)
        .order_by(Loan.date_issued.desc())
    )
    loans = result.scalars().unique().all()
    return [_to_loan_out(l) for l in loans]


@router.post("/", response_model=LoanOut)
async def create_loan(
    org_id: str,
    body: LoanCreate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    loan = Loan(
        org_id=org_id,
        borrower_name=body.borrower_name,
        principal=body.principal,
        date_issued=body.date_issued,
        notes=body.notes,
    )
    db.add(loan)
    await db.commit()
    # Re-fetch with repayments loaded
    res = await db.execute(
        select(Loan).options(selectinload(Loan.repayments)).where(Loan.id == loan.id)
    )
    loan = res.scalars().unique().scalar_one()
    return _to_loan_out(loan)


@router.get("/summary", response_model=LoanSummaryOut)
async def get_loan_summary(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Loan).options(selectinload(Loan.repayments)).where(Loan.org_id == org_id)
    )
    loans = result.scalars().unique().all()
    total_loaned = sum(l.principal for l in loans)
    total_repaid = sum(sum(r.amount for r in l.repayments) for l in loans)
    total_outstanding = sum(_compute_balance(l) for l in loans if l.status == LoanStatus.ACTIVE)
    active_count = sum(1 for l in loans if l.status == LoanStatus.ACTIVE)
    return LoanSummaryOut(
        total_loaned=round(total_loaned, 2),
        total_repaid=round(total_repaid, 2),
        total_outstanding=round(total_outstanding, 2),
        active_loan_count=active_count,
    )


@router.get("/{loan_id}", response_model=LoanOut)
async def get_loan(
    org_id: str,
    loan_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Loan)
        .options(selectinload(Loan.repayments))
        .where(and_(Loan.id == loan_id, Loan.org_id == org_id))
    )
    loan = result.scalars().unique().scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return _to_loan_out(loan)


@router.patch("/{loan_id}", response_model=LoanOut)
async def update_loan(
    org_id: str,
    loan_id: str,
    body: LoanUpdate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Loan)
        .options(selectinload(Loan.repayments))
        .where(and_(Loan.id == loan_id, Loan.org_id == org_id))
    )
    loan = result.scalars().unique().scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if body.borrower_name is not None:
        loan.borrower_name = body.borrower_name
    if body.principal is not None:
        loan.principal = body.principal
    if body.date_issued is not None:
        loan.date_issued = body.date_issued
    if body.notes is not None:
        loan.notes = body.notes
    if body.status is not None:
        loan.status = body.status
    await db.commit()
    await db.refresh(loan)
    # Re-fetch with repayments after update
    res = await db.execute(
        select(Loan).options(selectinload(Loan.repayments)).where(Loan.id == loan.id)
    )
    loan = res.scalars().unique().scalar_one()
    return _to_loan_out(loan)


@router.delete("/{loan_id}")
async def delete_loan(
    org_id: str,
    loan_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Loan).where(and_(Loan.id == loan_id, Loan.org_id == org_id))
    )
    loan = result.scalars().unique().scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    await db.delete(loan)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{loan_id}/repayments", response_model=RepaymentOut)
async def add_repayment(
    org_id: str,
    loan_id: str,
    body: RepaymentCreate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Loan).where(and_(Loan.id == loan_id, Loan.org_id == org_id))
    )
    loan = result.scalars().unique().scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Validate transaction_id belongs to this org if provided
    tx_id = None
    if body.transaction_id:
        tx_result = await db.execute(
            select(Transaction).where(
                and_(Transaction.id == body.transaction_id, Transaction.org_id == org_id)
            )
        )
        tx = tx_result.scalar_one_or_none()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found in this org")
        tx_id = tx.id

    repayment = LoanRepayment(
        loan_id=loan.id,
        amount=body.amount,
        date=body.date,
        notes=body.notes,
        transaction_id=tx_id,
    )
    db.add(repayment)
    await db.flush()

    # Auto-update loan status — recompute balance via DB query
    rep_result = await db.execute(
        select(LoanRepayment).where(LoanRepayment.loan_id == loan.id)
    )
    all_repayments = rep_result.scalars().all()
    total_paid = sum(r.amount for r in all_repayments)
    balance = round(loan.principal - total_paid, 2)
    if balance <= 0 and loan.status == LoanStatus.ACTIVE:
        loan.status = LoanStatus.PAID_OFF

    await db.commit()
    await db.refresh(repayment)
    return repayment


@router.delete("/{loan_id}/repayments/{repayment_id}")
async def delete_repayment(
    org_id: str,
    loan_id: str,
    repayment_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LoanRepayment).where(
            and_(LoanRepayment.id == repayment_id, LoanRepayment.loan_id == loan_id)
        )
    )
    repayment = result.scalar_one_or_none()
    if not repayment:
        raise HTTPException(status_code=404, detail="Repayment not found")

    # Re-fetch loan to check org
    loan_result = await db.execute(
        select(Loan).where(and_(Loan.id == loan_id, Loan.org_id == org_id))
    )
    loan = loan_result.scalars().unique().scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    await db.delete(repayment)
    await db.flush()

    # If loan was paid off, check if it should revert to active
    if loan.status == LoanStatus.PAID_OFF:
        rep_result = await db.execute(
            select(LoanRepayment).where(LoanRepayment.loan_id == loan.id)
        )
        remaining = rep_result.scalars().all()
        total_paid = sum(r.amount for r in remaining)
        balance = round(loan.principal - total_paid, 2)
        if balance > 0:
            loan.status = LoanStatus.ACTIVE

    await db.commit()
    return {"status": "deleted"}
