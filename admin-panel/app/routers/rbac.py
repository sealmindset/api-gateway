"""RBAC management routes: roles, user-role assignments, audit log."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.middleware.auth import get_current_user
from app.middleware.rbac import (
    DEFAULT_ROLES,
    invalidate_user_permissions,
    log_access,
    require_permission,
    require_role,
)
from app.models.database import AuditLog, Role, User, UserRole, get_db_session
from app.models.schemas import (
    AuditLogFilter,
    AuditLogRead,
    PaginatedResponse,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserRoleAssign,
    UserRoleRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rbac", tags=["rbac"])


# ---------------------------------------------------------------------------
# Roles CRUD
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleRead])
async def list_roles(
    _auth: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List all defined roles."""
    result = await db.execute(select(Role).order_by(Role.name))
    return [RoleRead.model_validate(r) for r in result.scalars().all()]


@router.post("/roles", response_model=RoleRead, status_code=201)
async def create_role(
    body: RoleCreate,
    request: Request,
    user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new role."""
    existing = await db.execute(select(Role).where(Role.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Role name already exists.")

    role = Role(**body.model_dump())
    db.add(role)
    await db.flush()

    await log_access(
        db, user=user, action="create", resource_type="role",
        resource_id=str(role.id), details=body.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return RoleRead.model_validate(role)


@router.get("/roles/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: uuid.UUID,
    _auth: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a role by ID."""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found.")
    return RoleRead.model_validate(role)


@router.patch("/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    request: Request,
    user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Update a role's metadata or permissions."""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(role, field, value)
    await db.flush()

    await log_access(
        db, user=user, action="update", resource_type="role",
        resource_id=str(role_id), details=update_data,
        ip_address=request.client.host if request.client else None,
    )
    return RoleRead.model_validate(role)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("roles:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a role (and cascade remove assignments)."""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found.")

    await db.delete(role)
    await db.flush()

    await log_access(
        db, user=user, action="delete", resource_type="role",
        resource_id=str(role_id),
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# User-Role assignments
# ---------------------------------------------------------------------------

@router.post("/assignments", response_model=UserRoleRead, status_code=201)
async def assign_role(
    body: UserRoleAssign,
    request: Request,
    user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Assign a role to a user."""
    # Verify both exist
    target_user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    target_role = (await db.execute(select(Role).where(Role.id == body.role_id))).scalar_one_or_none()
    if target_role is None:
        raise HTTPException(status_code=404, detail="Role not found.")

    # Check for duplicate
    existing = await db.execute(
        select(UserRole).where(UserRole.user_id == body.user_id, UserRole.role_id == body.role_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Role already assigned to this user.")

    assignment = UserRole(user_id=body.user_id, role_id=body.role_id, assigned_by=user.id)
    db.add(assignment)
    await db.flush()

    await invalidate_user_permissions(body.user_id)

    await log_access(
        db, user=user, action="assign_role", resource_type="user_role",
        resource_id=str(assignment.id),
        details={"target_user": str(body.user_id), "role": target_role.name},
        ip_address=request.client.host if request.client else None,
    )
    return UserRoleRead.model_validate(assignment)


@router.delete("/assignments/{user_id}/{role_id}", status_code=204)
async def revoke_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Revoke a role from a user."""
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Role assignment not found.")

    await db.delete(assignment)
    await db.flush()

    await invalidate_user_permissions(user_id)

    await log_access(
        db, user=user, action="revoke_role", resource_type="user_role",
        details={"target_user": str(user_id), "role_id": str(role_id)},
        ip_address=request.client.host if request.client else None,
    )


@router.get("/users/{user_id}/roles", response_model=list[RoleRead])
async def list_user_roles(
    user_id: uuid.UUID,
    _auth: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List roles assigned to a specific user."""
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id).options(selectinload(UserRole.role))
    )
    return [RoleRead.model_validate(ur.role) for ur in result.scalars().all() if ur.role]


# ---------------------------------------------------------------------------
# Users list (for admin assignment UI)
# ---------------------------------------------------------------------------

@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    _auth: User = Depends(require_permission("users:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List all users with their assigned roles."""
    query = select(User)
    count_query = select(func.count(User.id))

    if search:
        like = f"%{search}%"
        query = query.where(User.name.ilike(like) | User.email.ilike(like))
        count_query = count_query.where(User.name.ilike(like) | User.email.ilike(like))

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(User.name).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()

    # Enrich with role names
    items = []
    for u in users:
        roles_result = await db.execute(
            select(UserRole).where(UserRole.user_id == u.id).options(selectinload(UserRole.role))
        )
        role_names = [ur.role.name for ur in roles_result.scalars().all() if ur.role]
        items.append({
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "entra_oid": u.entra_oid,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "role_names": role_names,
        })

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Permissions reference
# ---------------------------------------------------------------------------

@router.get("/permissions")
async def list_permissions(
    _auth: User = Depends(require_permission("roles:read")),
):
    """Return the complete permission catalogue derived from default roles."""
    all_perms: set[str] = set()
    for role_def in DEFAULT_ROLES.values():
        all_perms.update(role_def["permissions"].keys())
    return {"permissions": sorted(all_perms)}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=PaginatedResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    _auth: User = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Query the audit log with optional filters."""
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [AuditLogRead.model_validate(a) for a in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
