from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID

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
