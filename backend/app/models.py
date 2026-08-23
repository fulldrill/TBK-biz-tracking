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

class LoanStatus(str, enum.Enum):
    ACTIVE = "active"
    PAID_OFF = "paid_off"
    WRITTEN_OFF = "written_off"

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
    # Provenance — ties a receipt back to the primary document it came from.
    # Without these a receipt is a floating summary; with them it is a voucher.
    statement_file = Column(String, nullable=True)      # source PDF filename
    statement_period = Column(String, nullable=True)    # statement closing date, ISO
    account_label = Column(String, nullable=True)       # "TRUIST ... CHECKING ••••7218"
    # Why this transaction was a business cost. Empty with purpose_source
    # "needs_input" means the ledger cannot establish it and the owner must say.
    business_purpose = Column(Text, nullable=True)
    purpose_source = Column(String, nullable=True)      # derived | ai | manual | needs_input
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="transactions")
    org = relationship("Organization", back_populates="transactions")
    account = relationship("BankAccount", back_populates="transactions")
    loan_repayments = relationship("LoanRepayment", back_populates="transaction")


class PnlEntry(Base):
    """A manual line on the P&L that never hit the bank account.

    Covers things a bank feed cannot know about — the home-office rent the
    business owes, cash income, an adjustment the accountant asked for.
    `recurrence="monthly"` expands to one occurrence per month between
    start_date and end_date (open-ended when end_date is NULL).
    """
    __tablename__ = "pnl_entries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    label = Column(String, nullable=False)              # shown as the P&L line item
    amount = Column(Float, nullable=False)              # always positive
    entry_type = Column(String, nullable=False)         # "revenue" | "expense"
    recurrence = Column(String, nullable=False, default="monthly")  # "monthly" | "once"
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)          # NULL = ongoing
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    org = relationship("Organization")


class PnlExclusion(Base):
    """A P&L line the user has chosen to keep off the statement.

    Rule-based exclusions (transfers, mortgage) live in services/pnl.py because
    they are accounting facts. This table is the user's own judgement — a line
    that is real spending but not a business expense, say. Excluded lines still
    appear in their own section so the money never silently disappears.
    """
    __tablename__ = "pnl_exclusions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    line_label = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "line_label", name="uq_pnl_exclusion"),)
    org = relationship("Organization")


class OrgPerson(Base):
    """Someone a transaction can be attributed to, scoped to one org.

    Replaces the globally hardcoded Kenny/Bright/Tony list — orgs do not
    share owners, so the assignable set has to be per-org.
    """
    __tablename__ = "org_people"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    # Comma-separated other names this person appears under on statements —
    # "Kenny" never matches "Kenneth Manjo" on its own.
    aliases = Column(String, nullable=True)
    # "owner"    — a principal; money out is a draw, money in a contribution.
    # "personal" — someone the owner pays for family reasons (childcare,
    #              school). Money out is still a draw: it left the business for
    #              personal use, and who received it does not change that.
    kind = Column(String, nullable=False, default="owner")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_org_person"),)
    org = relationship("Organization")


class Loan(Base):
    __tablename__ = "loans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    borrower_name = Column(String, nullable=False)
    principal = Column(Float, nullable=False)
    date_issued = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(Enum(LoanStatus), nullable=False, default=LoanStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    repayments = relationship("LoanRepayment", back_populates="loan", cascade="all, delete-orphan")


class LoanRepayment(Base):
    __tablename__ = "loan_repayments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=True)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    loan = relationship("Loan", back_populates="repayments")
    transaction = relationship("Transaction", back_populates="loan_repayments")
