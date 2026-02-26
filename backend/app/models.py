from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from datetime import datetime
import uuid
import enum

class TransactionType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    totp_secret = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    accounts = relationship("BankAccount", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")

class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    plaid_access_token = Column(String, nullable=False)
    plaid_item_id = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    account_name = Column(String)
    account_type = Column(String)
    institution_name = Column(String)
    last_synced = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id"), nullable=False)
    plaid_transaction_id = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    name = Column(String)
    description = Column(Text, nullable=True)
    merchant_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    is_zelle = Column(Boolean, default=False)
    zelle_counterparty = Column(String, nullable=True)
    zelle_direction = Column(String, nullable=True)
    receipt_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="transactions")
    account = relationship("BankAccount", back_populates="transactions")
