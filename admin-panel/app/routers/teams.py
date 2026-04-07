"""Team management routes: CRUD, member management, team-scoped access."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.middleware.auth import get_current_user
from app.middleware.rbac import is_platform_admin, log_access, require_permission
from app.models.database import (
    ApiRegistration,
    Team,
    TeamMember,
    User,
    get_db_session,
)
from app.models.schemas import (
    PaginatedResponse,
    TeamCreate,
    TeamDetail,
    TeamMemberAdd,
    TeamMemberRead,
    TeamMemberUpdate,
    TeamRead,
    TeamUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_team_or_404(db: AsyncSession, team_id: uuid.UUID) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")
    return team


async def _check_team_access(
    db: AsyncSession,
    user: User,
    team_id: uuid.UUID,
    min_role: str = "member",
) -> TeamMember | None:
    """Verify user is a member of the team with at least the given role.

    Platform admins (super_admin, admin) bypass team membership checks
    and can manage any team's resources.

    Role hierarchy: owner > admin > member > viewer
    """
    # Platform admins bypass team-scoped checks
    if await is_platform_admin(user, db):
        return None

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this team.")

    hierarchy = {"owner": 4, "admin": 3, "member": 2, "viewer": 1}
    if hierarchy.get(membership.role, 0) < hierarchy.get(min_role, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Requires at least '{min_role}' role in this team.",
        )
    return membership


async def _enrich_team(db: AsyncSession, team: Team) -> TeamDetail:
    """Add member_count and api_count to a team read."""
    member_count = (
        await db.execute(select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id))
    ).scalar_one()
    api_count = (
        await db.execute(select(func.count(ApiRegistration.id)).where(ApiRegistration.team_id == team.id))
    ).scalar_one()
    detail = TeamDetail.model_validate(team)
    detail.member_count = member_count
    detail.api_count = api_count
    return detail


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_teams(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    my_teams: bool = Query(False, description="Only show teams the current user belongs to"),
    user: User = Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List teams with optional filtering."""
    query = select(Team).where(Team.is_active == True)
    count_query = select(func.count(Team.id)).where(Team.is_active == True)

    if my_teams:
        my_team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        query = query.where(Team.id.in_(my_team_ids))
        count_query = count_query.where(Team.id.in_(my_team_ids))

    if search:
        like = f"%{search}%"
        query = query.where(Team.name.ilike(like) | Team.slug.ilike(like))
        count_query = count_query.where(Team.name.ilike(like) | Team.slug.ilike(like))

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(Team.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    teams = result.scalars().all()
    items = [await _enrich_team(db, t) for t in teams]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TeamDetail, status_code=201)
async def create_team(
    body: TeamCreate,
    request: Request,
    user: User = Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new team. The creating user becomes the owner."""
    # Check slug uniqueness
    existing = await db.execute(select(Team).where(Team.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Team slug '{body.slug}' already exists.")

    team_data = body.model_dump()
    meta = team_data.pop("metadata", None)
    team = Team(**team_data)
    if meta is not None:
        team.metadata_ = meta
    db.add(team)
    await db.flush()

    # Add creator as owner
    owner = TeamMember(team_id=team.id, user_id=user.id, role="owner")
    db.add(owner)
    await db.flush()

    await log_access(
        db, user=user, action="create", resource_type="team",
        resource_id=str(team.id), details=body.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return await _enrich_team(db, team)


@router.get("/{team_id}", response_model=TeamDetail)
async def get_team(
    team_id: uuid.UUID,
    user: User = Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a team by ID."""
    team = await _get_team_or_404(db, team_id)
    return await _enrich_team(db, team)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    request: Request,
    user: User = Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Update team details. Requires admin+ role in the team."""
    team = await _get_team_or_404(db, team_id)
    await _check_team_access(db, user, team_id, min_role="admin")

    update_data = body.model_dump(exclude_unset=True)
    meta = update_data.pop("metadata", None)
    for field, value in update_data.items():
        setattr(team, field, value)
    if meta is not None:
        team.metadata_ = meta
    await db.flush()
    await db.refresh(team)

    await log_access(
        db, user=user, action="update", resource_type="team",
        resource_id=str(team_id), details=update_data,
        ip_address=request.client.host if request.client else None,
    )
    return TeamRead.model_validate(team)


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("teams:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Deactivate a team. Requires owner role."""
    team = await _get_team_or_404(db, team_id)
    await _check_team_access(db, user, team_id, min_role="owner")

    team.is_active = False
    await db.flush()

    await log_access(
        db, user=user, action="delete", resource_type="team",
        resource_id=str(team_id),
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# Team Members
# ---------------------------------------------------------------------------

@router.get("/{team_id}/members", response_model=list[TeamMemberRead])
async def list_team_members(
    team_id: uuid.UUID,
    user: User = Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List members of a team."""
    await _get_team_or_404(db, team_id)

    result = await db.execute(
        select(TeamMember)
        .where(TeamMember.team_id == team_id)
        .options(selectinload(TeamMember.user))
        .order_by(TeamMember.joined_at)
    )
    members = result.scalars().all()
    items = []
    for m in members:
        read = TeamMemberRead.model_validate(m)
        if m.user:
            read.user_name = m.user.name
            read.user_email = m.user.email
        items.append(read)
    return items


@router.post("/{team_id}/members", response_model=TeamMemberRead, status_code=201)
async def add_team_member(
    team_id: uuid.UUID,
    body: TeamMemberAdd,
    request: Request,
    user: User = Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Add a user to a team. Requires admin+ role in the team."""
    await _get_team_or_404(db, team_id)
    await _check_team_access(db, user, team_id, min_role="admin")

    # Verify target user exists
    target = await db.execute(select(User).where(User.id == body.user_id))
    target_user = target.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Check not already a member
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member of this team.")

    member = TeamMember(team_id=team_id, user_id=body.user_id, role=body.role)
    db.add(member)
    await db.flush()

    await log_access(
        db, user=user, action="add_member", resource_type="team",
        resource_id=str(team_id),
        details={"user_id": str(body.user_id), "role": body.role},
        ip_address=request.client.host if request.client else None,
    )

    read = TeamMemberRead.model_validate(member)
    read.user_name = target_user.name
    read.user_email = target_user.email
    return read


@router.patch("/{team_id}/members/{member_id}", response_model=TeamMemberRead)
async def update_team_member(
    team_id: uuid.UUID,
    member_id: uuid.UUID,
    body: TeamMemberUpdate,
    request: Request,
    user: User = Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Change a member's role. Requires admin+ role."""
    await _check_team_access(db, user, team_id, min_role="admin")

    result = await db.execute(
        select(TeamMember)
        .where(TeamMember.id == member_id, TeamMember.team_id == team_id)
        .options(selectinload(TeamMember.user))
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found.")

    member.role = body.role
    await db.flush()

    await log_access(
        db, user=user, action="update_member", resource_type="team",
        resource_id=str(team_id),
        details={"member_id": str(member_id), "new_role": body.role},
        ip_address=request.client.host if request.client else None,
    )

    read = TeamMemberRead.model_validate(member)
    if member.user:
        read.user_name = member.user.name
        read.user_email = member.user.email
    return read


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_team_member(
    team_id: uuid.UUID,
    member_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Remove a member from a team. Requires admin+ role."""
    await _check_team_access(db, user, team_id, min_role="admin")

    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.team_id == team_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found.")

    if member.role == "owner":
        # Check there's at least one other owner
        owner_count = (
            await db.execute(
                select(func.count(TeamMember.id)).where(
                    TeamMember.team_id == team_id,
                    TeamMember.role == "owner",
                )
            )
        ).scalar_one()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner.")

    await db.delete(member)
    await db.flush()

    await log_access(
        db, user=user, action="remove_member", resource_type="team",
        resource_id=str(team_id),
        details={"member_id": str(member_id)},
        ip_address=request.client.host if request.client else None,
    )
