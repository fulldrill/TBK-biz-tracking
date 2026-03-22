from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import User, Organization, OrgMember, OrgRole
from app.schemas import OrgCreate, OrgOut, OrgMemberOut, UserOrgOut, InviteCreate, InviteOut
from app.auth import get_current_user, require_org_role, generate_invite_token
from app.models import OrgInvite
from datetime import datetime, timedelta
from typing import List, Tuple
import re
import logging

router = APIRouter(prefix="/orgs", tags=["Organizations"])
logger = logging.getLogger(__name__)


def _make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while True:
        conflict = await db.execute(select(Organization).where(Organization.slug == slug))
        if not conflict.scalar_one_or_none():
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


@router.post("/", response_model=OrgOut)
async def create_org(
    payload: OrgCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slug = await _unique_slug(db, _make_slug(payload.name))
    org = Organization(name=payload.name, slug=slug, owner_id=current_user.id)
    db.add(org)
    await db.flush()
    member = OrgMember(org_id=org.id, user_id=current_user.id, role=OrgRole.ADMIN)
    db.add(member)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/", response_model=List[UserOrgOut])
async def list_my_orgs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memberships = await db.execute(
        select(OrgMember).where(OrgMember.user_id == current_user.id)
    )
    memberships = memberships.scalars().all()

    result = []
    for m in memberships:
        org_result = await db.execute(select(Organization).where(Organization.id == m.org_id))
        org = org_result.scalar_one_or_none()
        if not org:
            continue
        count_result = await db.execute(
            select(func.count()).select_from(OrgMember).where(OrgMember.org_id == org.id)
        )
        member_count = count_result.scalar()
        result.append(UserOrgOut(
            org=OrgOut.model_validate(org),
            role=m.role,
            member_count=member_count,
        ))
    return result


@router.get("/{org_id}", response_model=OrgOut)
async def get_org(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.patch("/{org_id}", response_model=OrgOut)
async def update_org(
    org_id: str,
    payload: OrgCreate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.name = payload.name
    await db.commit()
    await db.refresh(org)
    return org


@router.delete("/{org_id}")
async def delete_org(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if str(org.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only the owner can delete this organization")
    await db.delete(org)
    await db.commit()
    return {"status": "deleted"}


# --- Members ---

@router.get("/{org_id}/members", response_model=List[OrgMemberOut])
async def list_members(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id)
    )
    memberships = result.scalars().all()
    out = []
    for m in memberships:
        user_result = await db.execute(select(User).where(User.id == m.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            out.append(OrgMemberOut(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=m.role,
                joined_at=m.joined_at,
            ))
    return out


@router.patch("/{org_id}/members/{member_user_id}")
async def update_member_role(
    org_id: str,
    member_user_id: str,
    payload: dict,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == member_user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")
    new_role = payload.get("role")
    if new_role not in [r.value for r in OrgRole]:
        raise HTTPException(status_code=422, detail="Invalid role")
    membership.role = OrgRole(new_role)
    await db.commit()
    return {"status": "updated", "role": new_role}


@router.delete("/{org_id}/members/{member_user_id}")
async def remove_member(
    org_id: str,
    member_user_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if str(org.owner_id) == member_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the organization owner")

    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == member_user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(membership)
    await db.commit()
    return {"status": "removed"}


# --- Invites ---

@router.post("/{org_id}/invites", response_model=InviteOut)
async def create_invite(
    org_id: str,
    payload: InviteCreate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    invite = OrgInvite(
        org_id=org_id,
        created_by=current_user.id,
        token=generate_invite_token(),
        role=payload.role,
        expires_at=datetime.utcnow() + timedelta(hours=payload.expires_hours),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


@router.get("/{org_id}/invites", response_model=List[InviteOut])
async def list_invites(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgInvite).where(OrgInvite.org_id == org_id, OrgInvite.is_active == True)
    )
    return result.scalars().all()


@router.delete("/{org_id}/invites/{invite_id}")
async def revoke_invite(
    org_id: str,
    invite_id: str,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgInvite).where(
            OrgInvite.id == invite_id,
            OrgInvite.org_id == org_id,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite.is_active = False
    await db.commit()
    return {"status": "revoked"}
