"""Root conftest -- shared fixtures for all admin-panel tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.database import Base, User, Role, UserRole

# ---------------------------------------------------------------------------
# Make PostgreSQL JSONB columns work on SQLite by rendering them as JSON
# ---------------------------------------------------------------------------

from sqlalchemy.dialects import sqlite as sqlite_dialect

# Register JSONB → JSON adapter for SQLite's type compiler
@event.listens_for(Base.metadata, "before_create")
def _remap_jsonb_for_sqlite(target, connection, **kw):
    """No-op listener; the real fix is the type adapter below."""
    pass


# Monkey-patch SQLite type compiler to handle JSONB
_orig_get_colspec = sqlite_dialect.base.SQLiteTypeCompiler

if not hasattr(sqlite_dialect.base.SQLiteTypeCompiler, "visit_JSONB"):
    def _visit_jsonb(self, type_, **kw):
        return self.visit_JSON(type_, **kw)
    sqlite_dialect.base.SQLiteTypeCompiler.visit_JSONB = _visit_jsonb


# ---------------------------------------------------------------------------
# In-memory SQLite async engine for tests
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def db_engine():
    """Create an async in-memory SQLite engine and provision schema."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async session bound to the test engine."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Pre-built test data
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def test_user(db_session: AsyncSession) -> User:
    """Create and return a basic test user."""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="Test User",
        entra_oid="test-oid-001",
        roles={},
        last_login=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture()
async def admin_role(db_session: AsyncSession) -> Role:
    """Create and return an admin role with full permissions."""
    role = Role(
        id=uuid.uuid4(),
        name="admin",
        description="Full admin access",
        permissions={
            "subscribers:read": True,
            "subscribers:write": True,
            "subscribers:delete": True,
            "subscriptions:read": True,
            "subscriptions:write": True,
            "api_keys:read": True,
            "api_keys:write": True,
            "roles:read": True,
            "roles:write": True,
            "users:read": True,
            "gateway:read": True,
            "gateway:write": True,
            "audit:read": True,
            "ai:read": True,
            "ai:analyze": True,
            "teams:read": True,
            "teams:write": True,
            "teams:delete": True,
            "api_registry:read": True,
            "api_registry:write": True,
            "api_registry:approve": True,
        },
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture()
async def viewer_role(db_session: AsyncSession) -> Role:
    """Create and return a viewer role with read-only permissions."""
    role = Role(
        id=uuid.uuid4(),
        name="viewer",
        description="Read-only access",
        permissions={
            "subscribers:read": True,
            "subscriptions:read": True,
            "api_keys:read": True,
            "roles:read": True,
            "users:read": True,
            "gateway:read": True,
            "audit:read": True,
            "ai:read": True,
            "teams:read": True,
            "api_registry:read": True,
        },
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest_asyncio.fixture()
async def admin_user(db_session: AsyncSession, test_user: User, admin_role: Role) -> User:
    """A test user with the admin role assigned."""
    assignment = UserRole(
        user_id=test_user.id,
        role_id=admin_role.id,
    )
    db_session.add(assignment)
    await db_session.flush()
    return test_user


# ---------------------------------------------------------------------------
# FastAPI test client (with mocked DB and auth)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def app_client(db_session: AsyncSession, test_user: User):
    """
    Yield an httpx.AsyncClient wired to the FastAPI app with:
    - DB dependency overridden to use the test session
    - Auth dependency overridden to return test_user (always authenticated)
    - Redis mocked out
    """
    from app.main import create_app
    from app.models.database import get_db_session
    from app.middleware.auth import get_current_user

    app = create_app()

    # Override DB session
    async def _override_db():
        yield db_session

    # Override auth -- always return test_user
    async def _override_auth():
        return test_user

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_current_user] = _override_auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
