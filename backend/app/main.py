from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database import get_db, engine, Base, AsyncSessionLocal
from app.routers import bank, transactions, receipts, totals
from app.routers import orgs, invites, statements, chat, loans, reports
from app.auth import hash_password, generate_totp_secret, verify_password, verify_totp, create_access_token
from app.services.attribution import assign_user
from app.models import User, Organization, OrgMember, OrgRole, BankAccount, Loan, LoanRepayment
from app.schemas import UserCreate, UserLogin, Token
from fastapi import HTTPException
import logging
import os
import re
import secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Clerq API",
    version="1.0.0",
    description="Business financial tracking with Plaid bank integration and Zelle detection",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://0.0.0.0:3000,http://host.docker.internal:3000",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bank.router)
app.include_router(bank.legacy_router)
app.include_router(transactions.router)
app.include_router(transactions.legacy_router)
app.include_router(receipts.router)
app.include_router(receipts.legacy_router)
app.include_router(totals.router)
app.include_router(totals.legacy_router)
app.include_router(orgs.router)
app.include_router(invites.router)
app.include_router(statements.router)
app.include_router(chat.router)
app.include_router(loans.router)
app.include_router(reports.router)


def _make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


async def _migrate_user_to_org(db: AsyncSession, user: User) -> None:
    """Create a default org for a user and migrate their existing data into it."""
    # Check if user already has an org they own (idempotency guard)
    existing_org = await db.execute(
        select(Organization).where(Organization.owner_id == user.id)
    )
    org = existing_org.scalar_one_or_none()

    if not org:
        org_name = f"{user.full_name or user.email}'s Business"
        base_slug = _make_slug(org_name)
        slug = base_slug
        suffix = 2
        while True:
            conflict = await db.execute(select(Organization).where(Organization.slug == slug))
            if not conflict.scalar_one_or_none():
                break
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        org = Organization(name=org_name, slug=slug, owner_id=user.id)
        db.add(org)
        await db.flush()  # get org.id without committing

        member = OrgMember(org_id=org.id, user_id=user.id, role=OrgRole.ADMIN)
        db.add(member)
        await db.flush()

    # Backfill bank_accounts
    await db.execute(
        text("UPDATE bank_accounts SET org_id = :org_id WHERE user_id = :user_id AND org_id IS NULL"),
        {"org_id": str(org.id), "user_id": str(user.id)},
    )
    # Backfill transactions
    await db.execute(
        text("UPDATE transactions SET org_id = :org_id WHERE user_id = :user_id AND org_id IS NULL"),
        {"org_id": str(org.id), "user_id": str(user.id)},
    )
    await db.commit()


async def run_org_migration() -> None:
    """Idempotent startup migration: move all un-migrated user data into orgs."""
    async with AsyncSessionLocal() as db:
        # Find users who have bank accounts not yet assigned to an org
        result = await db.execute(
            select(User).where(
                User.id.in_(
                    select(BankAccount.user_id).where(BankAccount.org_id.is_(None))
                )
            )
        )
        users_to_migrate = result.scalars().all()
        for user in users_to_migrate:
            try:
                await _migrate_user_to_org(db, user)
                logger.info(f"Migrated user {user.email} to default org")
            except Exception as e:
                logger.error(f"Failed to migrate user {user.email}: {e}")
                await db.rollback()


async def backfill_assigned_users() -> None:
    """One-time idempotent: assign users to all transactions that have assigned_user = NULL."""
    from app.models import Transaction as TxModel
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TxModel).where(TxModel.assigned_user.is_(None))
        )
        txns = result.scalars().all()
        updated = 0
        for tx in txns:
            tx_type_str = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
            user = assign_user(tx.name or "", tx_type_str, tx.is_zelle, tx.zelle_counterparty)
            if user:
                tx.assigned_user = user
                updated += 1
        if updated:
            await db.commit()
            logger.info(f"Backfilled assigned_user for {updated} transactions")


async def recategorize_priority_rules() -> None:
    """Idempotent: re-apply PRIORITY_RULES to transactions already in the DB.

    The bank's own label is too coarse for these — it calls the CMCI payroll
    deposit "Deposit" and the mortgage "Payment". Rows imported before those
    rules existed still carry the coarse category, so the P&L would misfile
    them. Only rows a priority rule actually matches are touched.
    """
    from app.models import Transaction as TxModel
    from app.services.categorizer import PRIORITY_RULES
    from app.services.owner_transfers import CATEGORY_DRAW, CATEGORY_CONTRIBUTION

    # A description rule must never override an owner classification. Paying
    # Mimi matches the childcare rule, but once she is a personal payee those
    # rows are draws — and this task runs on every boot, so without the guard
    # it would quietly undo that each restart.
    protected = {CATEGORY_DRAW, CATEGORY_CONTRIBUTION}

    async with AsyncSessionLocal() as db:
        txns = (await db.execute(select(TxModel))).scalars().all()
        updated = 0
        for tx in txns:
            if tx.category in protected:
                continue
            text = f"{tx.name or ''} {tx.description or ''} {tx.zelle_counterparty or ''}"
            for pattern, category in PRIORITY_RULES:
                if pattern.search(text):
                    if tx.category != category:
                        tx.category = category
                        updated += 1
                    break
        if updated:
            await db.commit()
            logger.info(f"Recategorized {updated} transaction(s) via priority rules")


async def seed_org_people() -> None:
    """Idempotent: give every org a people list derived from its own data.

    Seeds from the distinct assigned_user values already on that org's
    transactions, so each org starts with exactly the names it actually uses
    rather than the old global Kenny/Bright/Tony list. Only runs for orgs that
    have no people yet, so edits made in settings are never overwritten.
    """
    from app.models import Transaction as TxModel, OrgPerson

    async with AsyncSessionLocal() as db:
        orgs = (await db.execute(select(Organization))).scalars().all()
        added = 0
        for org in orgs:
            existing = (await db.execute(
                select(OrgPerson).where(OrgPerson.org_id == org.id)
            )).scalars().all()
            if existing:
                continue

            names = (await db.execute(
                select(TxModel.assigned_user)
                .where(TxModel.org_id == org.id, TxModel.assigned_user.isnot(None))
                .distinct()
            )).scalars().all()
            for name in sorted({n.strip() for n in names if n and n.strip()}):
                db.add(OrgPerson(org_id=org.id, name=name))
                added += 1
        if added:
            await db.commit()
            logger.info(f"Seeded {added} org people row(s)")


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add org_id columns to existing tables if they don't exist yet
        await conn.execute(text(
            "ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS "
            "org_id UUID REFERENCES organizations(id) ON DELETE CASCADE"
        ))
        await conn.execute(text(
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS "
            "org_id UUID REFERENCES organizations(id) ON DELETE CASCADE"
        ))
        await conn.execute(text(
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS "
            "assigned_user VARCHAR"
        ))
        await conn.execute(text(
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS "
            "source VARCHAR NOT NULL DEFAULT 'plaid'"
        ))
        for _col in ("statement_file", "statement_period", "account_label",
                     "business_purpose", "purpose_source"):
            await conn.execute(text(
                f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {_col} VARCHAR"
            ))
        await conn.execute(text(
            "ALTER TABLE org_people ADD COLUMN IF NOT EXISTS aliases VARCHAR"
        ))
        await conn.execute(text(
            "ALTER TABLE org_people ADD COLUMN IF NOT EXISTS "
            "kind VARCHAR NOT NULL DEFAULT 'owner'"
        ))
        # Loan tables are created by create_all above; no ALTER TABLE needed for new installs
    os.makedirs("./receipts", exist_ok=True)
    await run_org_migration()
    await backfill_assigned_users()
    await seed_org_people()
    await recategorize_priority_rules()


@app.post("/auth/register", tags=["Auth"])
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    normalized_email = user_data.email.strip().lower()
    existing = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    totp_secret = generate_totp_secret()
    user = User(
        email=normalized_email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        totp_secret=totp_secret,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "user_id": str(user.id),
        "email": user.email,
        "totp_secret": totp_secret,
        "message": "Save the totp_secret and scan it in Google Authenticator to enable 2FA"
    }


@app.post("/auth/login", response_model=Token, tags=["Auth"])
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    normalized_email = credentials.email.strip().lower()
    result = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    totp_code = credentials.totp_code.strip() if credentials.totp_code else None
    if user.totp_secret and totp_code:
        if not verify_totp(user.totp_secret, totp_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "Clerq API", "version": "1.0.0"}
