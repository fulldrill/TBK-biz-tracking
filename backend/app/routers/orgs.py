from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import User, Organization, OrgMember, OrgRole, OrgPerson, Transaction
from app.schemas import (
    OrgCreate, OrgOut, OrgMemberOut, UserOrgOut, InviteCreate, InviteOut,
    OrgPersonCreate, OrgPersonOut, OrgPersonUpdate,
)
from app.auth import get_current_user, require_org_role, generate_invite_token
from app.models import OrgInvite
from datetime import datetime, timedelta
from typing import List, Tuple
import re
import uuid
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


# ---------------------------------------------------------------------------
# Org people — who a transaction can be attributed to.
#
# Orgs do not share owners, so this list is per-org rather than the global
# Kenny/Bright/Tony that used to be hardcoded in the frontend.
# ---------------------------------------------------------------------------

@router.get("/{org_id}/people", response_model=List[OrgPersonOut])
async def list_org_people(
    org_id: str,
    auth=Depends(require_org_role(OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgPerson).where(OrgPerson.org_id == org_id).order_by(OrgPerson.name)
    )
    return result.scalars().all()


@router.post("/{org_id}/people", response_model=OrgPersonOut, status_code=201)
async def add_org_person(
    org_id: str,
    body: OrgPersonCreate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")

    existing = await db.execute(
        select(OrgPerson).where(OrgPerson.org_id == org_id, OrgPerson.name == name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"{name} is already on this org")

    if body.kind not in ("owner", "personal"):
        raise HTTPException(status_code=422, detail="kind must be 'owner' or 'personal'")
    person = OrgPerson(
        org_id=uuid.UUID(org_id), name=name, aliases=body.aliases, kind=body.kind
    )
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/{org_id}/people/{person_id}", status_code=200)
async def remove_org_person(
    org_id: str,
    person_id: str,
    reassign_to: str | None = None,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Remove a person from the org.

    Transactions already attributed to them are not silently orphaned: pass
    `reassign_to` to move them to another name, otherwise they are cleared to
    unassigned. Either way the count is reported back.
    """
    result = await db.execute(
        select(OrgPerson).where(OrgPerson.id == person_id, OrgPerson.org_id == org_id)
    )
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    affected = await db.execute(
        select(Transaction).where(
            Transaction.org_id == org_id,
            Transaction.assigned_user == person.name,
        )
    )
    rows = affected.scalars().all()
    for tx in rows:
        tx.assigned_user = reassign_to or None

    await db.delete(person)
    await db.commit()
    return {
        "status": "removed",
        "name": person.name,
        "transactions_reassigned": len(rows),
        "reassigned_to": reassign_to,
    }


@router.patch("/{org_id}/people/{person_id}", response_model=OrgPersonOut)
async def update_org_person(
    org_id: str,
    person_id: str,
    body: OrgPersonUpdate,
    auth=Depends(require_org_role(OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Set the other names this person appears under on statements.

    Comma-separated. Needed wherever a first name cannot reach the printed
    name — "Kenny" never matches "Kenneth Manjo".
    """
    result = await db.execute(
        select(OrgPerson).where(OrgPerson.id == person_id, OrgPerson.org_id == org_id)
    )
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if body.aliases is not None:
        person.aliases = body.aliases.strip() or None
    if body.kind is not None:
        if body.kind not in ("owner", "personal"):
            raise HTTPException(status_code=422, detail="kind must be 'owner' or 'personal'")
        person.kind = body.kind
    await db.commit()
    await db.refresh(person)
    return person
