"""Tests for app.middleware.rbac -- RBAC middleware and permission logic."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.rbac import (
    DEFAULT_ROLES,
    PLATFORM_ADMIN_ROLES,
    _cache_key,
    get_user_permissions,
    get_user_role_names,
    is_platform_admin,
    seed_default_roles,
)
from app.models.database import Role, User, UserRole


# ---------------------------------------------------------------------------
# Default role definitions
# ---------------------------------------------------------------------------

class TestDefaultRoles:
    def test_four_roles_defined(self):
        assert set(DEFAULT_ROLES.keys()) == {"super_admin", "admin", "operator", "viewer"}

    def test_super_admin_has_all_permissions(self):
        perms = DEFAULT_ROLES["super_admin"]["permissions"]
        assert perms.get("roles:write") is True
        assert perms.get("roles:delete") is True
        assert perms.get("api_registry:approve") is True

    def test_viewer_is_read_only(self):
        perms = DEFAULT_ROLES["viewer"]["permissions"]
        # Viewer should have read but not write
        assert perms.get("subscribers:read") is True
        assert "subscribers:write" not in perms
        assert "subscribers:delete" not in perms

    def test_operator_cannot_delete(self):
        perms = DEFAULT_ROLES["operator"]["permissions"]
        assert perms.get("subscribers:read") is True
        assert perms.get("subscribers:write") is True
        assert "subscribers:delete" not in perms

    def test_platform_admin_roles_set(self):
        assert PLATFORM_ADMIN_ROLES == {"super_admin", "admin"}


# ---------------------------------------------------------------------------
# Seed default roles
# ---------------------------------------------------------------------------

class TestSeedDefaultRoles:
    @pytest.mark.asyncio
    async def test_seeds_roles_into_empty_db(self, db_session: AsyncSession):
        # Patch Redis to avoid connection attempts
        with patch("app.middleware.rbac.get_redis", new_callable=AsyncMock):
            await seed_default_roles(db_session)

        result = await db_session.execute(select(Role))
        roles = result.scalars().all()
        role_names = {r.name for r in roles}
        assert role_names == {"super_admin", "admin", "operator", "viewer"}

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db_session: AsyncSession):
        with patch("app.middleware.rbac.get_redis", new_callable=AsyncMock):
            await seed_default_roles(db_session)
            await seed_default_roles(db_session)  # second call

        result = await db_session.execute(select(Role))
        roles = result.scalars().all()
        assert len(roles) == 4  # still just 4, not 8


# ---------------------------------------------------------------------------
# Permission resolution
# ---------------------------------------------------------------------------

class TestGetUserPermissions:
    @pytest.mark.asyncio
    async def test_admin_has_write_permissions(self, db_session, admin_user, admin_role):
        with patch("app.middleware.rbac._get_cached_permissions", return_value=None), \
             patch("app.middleware.rbac._set_cached_permissions", new_callable=AsyncMock):
            perms = await get_user_permissions(admin_user, db_session)
        assert perms.get("subscribers:write") is True
        assert perms.get("subscribers:read") is True

    @pytest.mark.asyncio
    async def test_user_with_no_roles_has_no_permissions(self, db_session, test_user):
        with patch("app.middleware.rbac._get_cached_permissions", return_value=None), \
             patch("app.middleware.rbac._set_cached_permissions", new_callable=AsyncMock):
            perms = await get_user_permissions(test_user, db_session)
        assert perms == {}

    @pytest.mark.asyncio
    async def test_cached_permissions_returned(self, db_session, test_user):
        cached = {"subscribers:read": True, "special:cached": True}
        with patch("app.middleware.rbac._get_cached_permissions", return_value=cached):
            perms = await get_user_permissions(test_user, db_session)
        assert perms == cached


# ---------------------------------------------------------------------------
# Role name resolution
# ---------------------------------------------------------------------------

class TestGetUserRoleNames:
    @pytest.mark.asyncio
    async def test_admin_user_has_admin_role(self, db_session, admin_user):
        names = await get_user_role_names(admin_user, db_session)
        assert "admin" in names

    @pytest.mark.asyncio
    async def test_user_with_no_roles(self, db_session, test_user):
        names = await get_user_role_names(test_user, db_session)
        assert names == []


# ---------------------------------------------------------------------------
# Platform admin check
# ---------------------------------------------------------------------------

class TestIsPlatformAdmin:
    @pytest.mark.asyncio
    async def test_admin_is_platform_admin(self, db_session, admin_user):
        result = await is_platform_admin(admin_user, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_regular_user_is_not_platform_admin(self, db_session, test_user):
        result = await is_platform_admin(test_user, db_session)
        assert result is False


# ---------------------------------------------------------------------------
# Cache key format
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_cache_key_format(self):
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert _cache_key(uid) == "rbac:permissions:12345678-1234-5678-1234-567812345678"
