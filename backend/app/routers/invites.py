from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User, Organization, OrgMember, OrgInvite, OrgRole
from app.schemas import InvitePreview
from app.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/invites", tags=["Invites"])


@router.get("/{token}", response_model=InvitePreview)
async def preview_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — no auth required. Returns org name, role, and expiry."""
    result = await db.execute(select(OrgInvite).where(OrgInvite.token == token))
    invite = result.scalar_one_or_none()
    if not invite or not invite.is_active or invite.used_by is not None:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Invite has expired")

    org_result = await db.execute(select(Organization).where(Organization.id == invite.org_id))
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return InvitePreview(
        org_name=org.name,
        org_id=org.id,
        role=invite.role,
        expires_at=invite.expires_at,
    )


@router.post("/{token}/redeem")
async def redeem_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authenticated — creates org membership and marks invite as used."""
    result = await db.execute(select(OrgInvite).where(OrgInvite.token == token))
    invite = result.scalar_one_or_none()
    if not invite or not invite.is_active or invite.used_by is not None:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Invite has expired")

    # Check if user is already a member
    existing = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == invite.org_id,
            OrgMember.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already a member of this organization")

    member = OrgMember(org_id=invite.org_id, user_id=current_user.id, role=invite.role)
    db.add(member)

    invite.used_by = current_user.id
    invite.used_at = datetime.utcnow()

    await db.commit()

    org_result = await db.execute(select(Organization).where(Organization.id == invite.org_id))
    org = org_result.scalar_one_or_none()
    return {
        "status": "joined",
        "org_id": str(org.id),
        "org_name": org.name,
        "role": invite.role.value,
    }
