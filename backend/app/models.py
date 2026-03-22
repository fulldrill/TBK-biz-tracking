from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from datetime import datetime
import uuid
import enum

class TransactionType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"

class OrgRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"

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
    org_memberships = relationship("OrgMember", back_populates="user", foreign_keys="OrgMember.user_id")

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("OrgMember", back_populates="org", cascade="all, delete-orphan")
    invites = relationship("OrgInvite", back_populates="org", cascade="all, delete-orphan")
    bank_accounts = relationship("BankAccount", back_populates="org", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="org", cascade="all, delete-orphan")

class OrgMember(Base):
    __tablename__ = "org_members"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(OrgRole), nullable=False, default=OrgRole.VIEWER)
    joined_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_member"),)
    org = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="org_memberships", foreign_keys=[user_id])

class OrgInvite(Base):
    __tablename__ = "org_invites"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    role = Column(Enum(OrgRole), nullable=False, default=OrgRole.VIEWER)
    expires_at = Column(DateTime, nullable=False)
    used_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    org = relationship("Organization", back_populates="invites")
    creator = relationship("User", foreign_keys=[created_by])
    redeemer = relationship("User", foreign_keys=[used_by])

class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    plaid_access_token = Column(String, nullable=False)
    plaid_item_id = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    account_name = Column(String)
    account_type = Column(String)
    institution_name = Column(String)
    last_synced = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="accounts")
    org = relationship("Organization", back_populates="bank_accounts")
    transactions = relationship("Transaction", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
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
    assigned_user = Column(String, nullable=True)       # "Kenny" | "Bright" | None
    source = Column(String, nullable=False, default="plaid")  # "plaid" | "statement_import"
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="transactions")
    org = relationship("Organization", back_populates="transactions")
    account = relationship("BankAccount", back_populates="transactions")
