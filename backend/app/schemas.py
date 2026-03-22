from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models import OrgRole


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

    class Config:
        from_attributes = True


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
