from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, engine, Base
from app.routers import bank, transactions, receipts, totals
from app.auth import hash_password, generate_totp_secret, verify_password, verify_totp, create_access_token
from app.models import User
from app.schemas import UserCreate, UserLogin, Token
from fastapi import HTTPException
import logging
import os

logging.basicConfig(level=logging.INFO)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="BizTrack Receipts API",
    version="1.0.0",
    description="Financial tracking tool with Plaid bank integration and Zelle detection",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bank.router)
app.include_router(transactions.router)
app.include_router(receipts.router)
app.include_router(totals.router)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Create receipts directory
    os.makedirs("./receipts", exist_ok=True)

@app.post("/auth/register", tags=["Auth"])
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == user_data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    totp_secret = generate_totp_secret()
    user = User(
        email=user_data.email,
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
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.totp_secret and credentials.totp_code:
        if not verify_totp(user.totp_secret, credentials.totp_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "BizTrack Receipts API", "version": "1.0.0"}
