"""Role-Based Access Control middleware and decorators."""

from __future__ import annotations

import functools
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.middleware.auth import get_current_user
from app.models.database import AuditLog, Role, User, UserRole, get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default role definitions
# ---------------------------------------------------------------------------

DEFAULT_ROLES: dict[str, dict] = {
    "super_admin": {
        "description": "Full system access including role management",
        "permissions": {
            "subscribers:read": True,
            "subscribers:write": True,
            "subscribers:delete": True,
            "subscriptions:read": True,
            "subscriptions:write": True,
            "subscriptions:delete": True,
            "api_keys:read": True,
            "api_keys:write": True,
            "api_keys:delete": True,
            "roles:read": True,
            "roles:write": True,
            "roles:delete": True,
            "users:read": True,
            "users:write": True,
            "gateway:read": True,
            "gateway:write": True,
            "audit:read": True,
            "ai:read": True,
            "ai:analyze": True,
            "ai:rate-limit": True,
            "ai:route": True,
            "ai:transform": True,
            "ai:documentation": True,
        },
    },
    "admin": {
        "description": "Manage subscribers, subscriptions, and API keys",
        "permissions": {
            "subscribers:read": True,
            "subscribers:write": True,
            "subscribers:delete": True,
            "subscriptions:read": True,
            "subscriptions:write": True,
            "subscriptions:delete": True,
            "api_keys:read": True,
            "api_keys:write": True,
            "api_keys:delete": True,
            "roles:read": True,
            "users:read": True,
            "gateway:read": True,
            "gateway:write": True,
            "audit:read": True,
            "ai:read": True,
            "ai:analyze": True,
            "ai:rate-limit": True,
            "ai:route": True,
            "ai:transform": True,
            "ai:documentation": True,
        },
    },
    "operator": {
        "description": "Day-to-day operations: manage subscribers and keys",
        "permissions": {
            "subscribers:read": True,
            "subscribers:write": True,
            "subscriptions:read": True,
            "subscriptions:write": True,
            "api_keys:read": True,
            "api_keys:write": True,
            "roles:read": True,
            "users:read": True,
            "gateway:read": True,
            "audit:read": True,
            "ai:read": True,
            "ai:analyze": True,
            "ai:rate-limit": True,
        },
    },
    "viewer": {
        "description": "Read-only access to all resources",
        "permissions": {
            "subscribers:read": True,
            "subscriptions:read": True,
            "api_keys:read": True,
            "roles:read": True,
            "users:read": True,
            "gateway:read": True,
            "audit:read": True,
            "ai:read": True,
        },
    },
}

# ---------------------------------------------------------------------------
# Redis cache helpers
# ---------------------------------------------------------------------------

_redis: Optional[aioredis.Redis] = None
ROLE_CACHE_TTL = 300  # 5 minutes


async def get_redis() -> aioredis.Redis:
    """Return a shared Redis connection (lazy-initialised)."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


def _cache_key(user_id: uuid.UUID) -> str:
    return f"rbac:permissions:{user_id}"


async def _get_cached_permissions(user_id: uuid.UUID) -> Optional[dict[str, bool]]:
    """Retrieve merged permission map from Redis cache."""
    try:
        r = await get_redis()
        data = await r.get(_cache_key(user_id))
        if data:
            return json.loads(data)
    except Exception:
        logger.warning("Redis cache read failed for user %s", user_id, exc_info=True)
    return None


async def _set_cached_permissions(user_id: uuid.UUID, permissions: dict[str, bool]) -> None:
    """Store merged permission map in Redis cache."""
    try:
        r = await get_redis()
        await r.set(_cache_key(user_id), json.dumps(permissions), ex=ROLE_CACHE_TTL)
    except Exception:
        logger.warning("Redis cache write failed for user %s", user_id, exc_info=True)


async def invalidate_user_permissions(user_id: uuid.UUID) -> None:
    """Remove cached permissions for a user (call after role changes)."""
    try:
        r = await get_redis()
        await r.delete(_cache_key(user_id))
    except Exception:
        logger.warning("Redis cache delete failed for user %s", user_id, exc_info=True)


# ---------------------------------------------------------------------------
# Permission resolution
# ---------------------------------------------------------------------------

async def get_user_permissions(
    user: User,
    db: AsyncSession,
) -> dict[str, bool]:
    """Return the merged permission map for a user across all assigned roles.

    Results are cached in Redis for ROLE_CACHE_TTL seconds.
    """
    cached = await _get_cached_permissions(user.id)
    if cached is not None:
        return cached

    result = await db.execute(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .options(selectinload(UserRole.role))
    )
    user_roles = result.scalars().all()

    merged: dict[str, bool] = {}
    for ur in user_roles:
        if ur.role and ur.role.permissions:
            for perm, granted in ur.role.permissions.items():
                if granted:
                    merged[perm] = True

    await _set_cached_permissions(user.id, merged)
    return merged


async def get_user_role_names(
    user: User,
    db: AsyncSession,
) -> list[str]:
    """Return list of role names assigned to a user."""
    result = await db.execute(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .options(selectinload(UserRole.role))
    )
    return [ur.role.name for ur in result.scalars().all() if ur.role]


# ---------------------------------------------------------------------------
# Audit logging helper
# ---------------------------------------------------------------------------

async def log_access(
    db: AsyncSession,
    *,
    user: Optional[User],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Write an entry to the audit log."""
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()


# ---------------------------------------------------------------------------
# Dependency factories (decorators)
# ---------------------------------------------------------------------------

def require_permission(permission: str) -> Callable:
    """FastAPI dependency that asserts the current user holds *permission*.

    Usage::

        @router.get("/secret")
        async def secret(
            _auth=Depends(require_permission("subscribers:read")),
        ):
            ...
    """

    async def _checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db_session),
    ) -> User:
        permissions = await get_user_permissions(user, db)
        ip = request.client.host if request.client else None

        if not permissions.get(permission):
            await log_access(
                db,
                user=user,
                action="access_denied",
                resource_type=permission,
                details={"required_permission": permission},
                ip_address=ip,
            )
            logger.warning(
                "Permission denied: user=%s perm=%s ip=%s",
                user.email, permission, ip,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required.",
            )

        await log_access(
            db,
            user=user,
            action="access_granted",
            resource_type=permission,
            ip_address=ip,
        )
        return user

    return _checker


def require_role(role_name: str) -> Callable:
    """FastAPI dependency that asserts the current user is assigned *role_name*.

    Usage::

        @router.post("/admin-only")
        async def admin_only(
            _auth=Depends(require_role("admin")),
        ):
            ...
    """

    async def _checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db_session),
    ) -> User:
        role_names = await get_user_role_names(user, db)
        ip = request.client.host if request.client else None

        if role_name not in role_names:
            await log_access(
                db,
                user=user,
                action="access_denied",
                resource_type="role_check",
                details={"required_role": role_name, "user_roles": role_names},
                ip_address=ip,
            )
            logger.warning(
                "Role denied: user=%s required=%s has=%s ip=%s",
                user.email, role_name, role_names, ip,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' required.",
            )

        await log_access(
            db,
            user=user,
            action="access_granted",
            resource_type="role_check",
            details={"role": role_name},
            ip_address=ip,
        )
        return user

    return _checker


# ---------------------------------------------------------------------------
# Seed default roles
# ---------------------------------------------------------------------------

async def seed_default_roles(db: AsyncSession) -> None:
    """Insert default roles if they do not already exist."""
    for name, meta in DEFAULT_ROLES.items():
        result = await db.execute(select(Role).where(Role.name == name))
        if result.scalar_one_or_none() is None:
            db.add(
                Role(
                    name=name,
                    description=meta["description"],
                    permissions=meta["permissions"],
                )
            )
            logger.info("Seeded default role: %s", name)
    await db.commit()
