from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User, BankAccount
from app.schemas import LinkTokenResponse, ExchangeTokenRequest
from app.auth import get_current_user
from app.services.plaid_service import create_link_token, exchange_public_token, get_accounts
import logging

router = APIRouter(prefix="/bank", tags=["Bank"])
logger = logging.getLogger(__name__)

@router.get("/link-token", response_model=LinkTokenResponse)
async def get_link_token(current_user: User = Depends(get_current_user)):
    try:
        token = await create_link_token(str(current_user.id))
        return LinkTokenResponse(link_token=token)
    except Exception as e:
        logger.error(f"Link token error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create link token: {str(e)}")

@router.post("/connect")
async def connect_bank(
    payload: ExchangeTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tokens = await exchange_public_token(payload.public_token)
        access_token = tokens["access_token"]
        item_id = tokens["item_id"]
        accounts = await get_accounts(access_token)
        connected = []
        for acct in accounts:
            existing = await db.execute(
                select(BankAccount).where(BankAccount.account_id == acct["account_id"])
            )
            if existing.scalar_one_or_none():
                continue
            bank_acct = BankAccount(
                user_id=current_user.id,
                plaid_access_token=access_token,
                plaid_item_id=item_id,
                account_id=acct["account_id"],
                account_name=acct.get("name"),
                account_type=acct.get("subtype"),
                institution_name=payload.institution_name,
            )
            db.add(bank_acct)
            connected.append(acct.get("name"))
        await db.commit()
        return {"connected_accounts": connected, "status": "success"}
    except Exception as e:
        logger.error(f"Bank connect error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect bank account: {str(e)}")

@router.get("/accounts")
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BankAccount).where(BankAccount.user_id == current_user.id)
    )
    accounts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "account_name": a.account_name,
            "account_type": a.account_type,
            "institution_name": a.institution_name,
            "last_synced": a.last_synced,
        }
        for a in accounts
    ]
