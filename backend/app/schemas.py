from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models import OrgRole, LoanStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str
    institution_name: Optional[str] = None


class TransactionOut(BaseModel):
    id: UUID
    plaid_transaction_id: str
    amount: float
    date: datetime
    name: Optional[str]
    category: Optional[str]
    transaction_type: str
    is_zelle: bool
    zelle_counterparty: Optional[str]
    zelle_direction: Optional[str]
    receipt_path: Optional[str]
    assigned_user: Optional[str] = None
    source: str = "plaid"
    repayment_loan_id: Optional[UUID] = None
    business_purpose: Optional[str] = None
    purpose_source: Optional[str] = None

    class Config:
        from_attributes = True


# --- Statement Parser schemas ---

class ParsedTransaction(BaseModel):
    """A single transaction extracted from a PDF statement by AI."""
    date: str                          # "YYYY-MM-DD"
    name: str
    amount: float
    transaction_type: str              # "credit" | "debit"
    is_zelle: bool = False
    zelle_counterparty: Optional[str] = None
    zelle_direction: Optional[str] = None
    category: Optional[str] = None
    assigned_user: Optional[str] = None  # Resolved by TBK attribution logic
    statement_file: Optional[str] = None
    statement_period: Optional[str] = None
    account_label: Optional[str] = None


class StatementImportRequest(BaseModel):
    """Body for the /statements/import endpoint — list of parsed transactions."""
    transactions: List[ParsedTransaction]


class TransactionUpdate(BaseModel):
    assigned_user: Optional[str] = None  # "Kenny" | "Bright" | "Tony" | None
    business_purpose: Optional[str] = None


class BulkDeleteRequest(BaseModel):
    ids: List[str]


class TotalsResponse(BaseModel):
    total_deposits: float
    total_withdrawals: float
    zelle_sent: float
    zelle_received: float
    net_balance: float
    transaction_count: int
    period_start: datetime
    period_end: datetime


# --- Organization schemas ---

class OrgCreate(BaseModel):
    name: str


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: str
    owner_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class OrgMemberOut(BaseModel):
    user_id: UUID
    email: str
    full_name: Optional[str]
    role: OrgRole
    joined_at: datetime

    class Config:
        from_attributes = True


class UserOrgOut(BaseModel):
    org: OrgOut
    role: OrgRole
    member_count: int


class InviteCreate(BaseModel):
    role: OrgRole = OrgRole.VIEWER
    expires_hours: int = 168  # 7 days


class InviteOut(BaseModel):
    id: UUID
    org_id: UUID
    token: str
    role: OrgRole
    expires_at: datetime
    used_by: Optional[UUID]
    is_active: bool

    class Config:
        from_attributes = True


class InvitePreview(BaseModel):
    org_name: str
    org_id: UUID
    role: OrgRole
    expires_at: datetime


# --- Loan schemas ---

class LoanCreate(BaseModel):
    borrower_name: str
    principal: float
    date_issued: datetime
    notes: Optional[str] = None


class LoanUpdate(BaseModel):
    borrower_name: Optional[str] = None
    principal: Optional[float] = None
    date_issued: Optional[datetime] = None
    notes: Optional[str] = None
    status: Optional[LoanStatus] = None


class RepaymentCreate(BaseModel):
    amount: float
    date: datetime
    notes: Optional[str] = None
    transaction_id: Optional[str] = None  # UUID string, links to a dashboard transaction


class RepaymentOut(BaseModel):
    id: UUID
    loan_id: UUID
    amount: float
    date: datetime
    notes: Optional[str]
    transaction_id: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class LoanOut(BaseModel):
    id: UUID
    org_id: UUID
    borrower_name: str
    principal: float
    date_issued: datetime
    notes: Optional[str]
    status: LoanStatus
    created_at: datetime
    outstanding_balance: float
    repayments: List[RepaymentOut] = []

    class Config:
        from_attributes = True


# --- Manual P&L entry schemas ---

class PnlEntryCreate(BaseModel):
    label: str
    amount: float
    entry_type: str                    # "revenue" | "expense"
    recurrence: str = "monthly"        # "monthly" | "once"
    start_date: datetime
    end_date: Optional[datetime] = None
    notes: Optional[str] = None


class PnlEntryUpdate(BaseModel):
    label: Optional[str] = None
    amount: Optional[float] = None
    entry_type: Optional[str] = None
    recurrence: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PnlEntryOut(BaseModel):
    id: UUID
    org_id: UUID
    label: str
    amount: float
    entry_type: str
    recurrence: str
    start_date: datetime
    end_date: Optional[datetime]
    notes: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Org people schemas ---

class OrgPersonCreate(BaseModel):
    name: str
    aliases: Optional[str] = None


class OrgPersonUpdate(BaseModel):
    aliases: Optional[str] = None


class OrgPersonOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    aliases: Optional[str] = None

    class Config:
        from_attributes = True


class LoanSummaryOut(BaseModel):
    total_loaned: float
    total_repaid: float
    total_outstanding: float
    active_loan_count: int
