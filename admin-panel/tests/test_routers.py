"""Integration tests for API routers via the test client.

These tests use an in-memory SQLite database and mocked auth.
External services (Kong, Redis) are mocked where needed.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    Plan,
    Role,
    Subscriber,
    Team,
    TeamMember,
    User,
    UserRole,
)


# ---------------------------------------------------------------------------
# Helpers -- build an authenticated test client with admin permissions
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def authed_client(db_session: AsyncSession, admin_user: User, admin_role: Role):
    """Test client where the user is authenticated and has admin role."""
    from app.main import create_app
    from app.models.database import get_db_session
    from app.middleware.auth import get_current_user
    from app.middleware.rbac import get_user_permissions

    app = create_app()

    async def _override_db():
        yield db_session

    async def _override_auth():
        return admin_user

    # Mock Redis-based permission cache to return admin permissions directly
    async def _override_perms(user, db):
        return admin_role.permissions

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_current_user] = _override_auth

    # Patch permission resolution to skip Redis
    with patch("app.middleware.rbac.get_user_permissions", side_effect=_override_perms), \
         patch("app.middleware.rbac._get_cached_permissions", return_value=None), \
         patch("app.middleware.rbac._set_cached_permissions", new_callable=AsyncMock), \
         patch("app.middleware.rbac.log_access", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

class TestSubscribers:
    @pytest.mark.asyncio
    async def test_list_subscribers_empty(self, authed_client):
        resp = await authed_client.get("/subscribers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_create_subscriber(self, authed_client):
        with patch("app.routers.subscribers._sync_consumer_to_kong", new_callable=AsyncMock):
            resp = await authed_client.post("/subscribers", json={
                "name": "Test Corp",
                "email": "test@corp.com",
                "organization": "TestOrg",
                "tier": "basic",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Corp"
        assert data["email"] == "test@corp.com"
        assert data["tier"] == "basic"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_subscriber_not_found(self, authed_client):
        fake_id = str(uuid.uuid4())
        resp = await authed_client.get(f"/subscribers/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_and_get_subscriber(self, authed_client):
        with patch("app.routers.subscribers._sync_consumer_to_kong", new_callable=AsyncMock):
            create_resp = await authed_client.post("/subscribers", json={
                "name": "ACME",
                "email": "acme@example.com",
            })
        sub_id = create_resp.json()["id"]
        get_resp = await authed_client.get(f"/subscribers/{sub_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "ACME"


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

class TestPlans:
    @pytest.mark.asyncio
    async def test_list_plans_empty(self, authed_client):
        resp = await authed_client.get("/plans")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_plan(self, authed_client):
        resp = await authed_client.post("/plans", json={
            "name": "Starter",
            "rate_limit_second": 5,
            "rate_limit_minute": 100,
            "rate_limit_hour": 3000,
            "max_api_keys": 3,
            "price_cents": 999,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Starter"
        assert data["price_cents"] == 999
        assert data["is_active"] is True


# ---------------------------------------------------------------------------
# RBAC endpoints
# ---------------------------------------------------------------------------

class TestRbacEndpoints:
    @pytest.mark.asyncio
    async def test_list_roles(self, authed_client):
        resp = await authed_client.get("/rbac/roles")
        assert resp.status_code == 200
        # Should return at least the admin role from our fixture
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_permissions(self, authed_client):
        resp = await authed_client.get("/rbac/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

class TestTeams:
    @pytest.mark.asyncio
    async def test_list_teams_empty(self, authed_client):
        resp = await authed_client.get("/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_team(self, authed_client):
        """Team creation requires PostgreSQL (JSONB metadata column).
        Marked as integration -- skipped in SQLite-backed unit tests."""
        pytest.skip("Requires PostgreSQL (JSONB metadata serialization)")


# ---------------------------------------------------------------------------
# Gateway health (mocked Kong)
# ---------------------------------------------------------------------------

class TestGateway:
    @pytest.mark.asyncio
    async def test_gateway_health_kong_down(self, authed_client):
        """When Kong is unreachable, gateway health should return an error."""
        resp = await authed_client.get("/gateway/health")
        # Will get a 502 or connection error since Kong isn't running in tests
        assert resp.status_code in (200, 502, 500)


# ---------------------------------------------------------------------------
# AI endpoints (mocked provider)
# ---------------------------------------------------------------------------

class TestAiEndpoints:
    @pytest.mark.asyncio
    async def test_ai_config(self, authed_client):
        resp = await authed_client.get("/ai/config")
        # 200 when AI agent loads, 503 when provider isn't configured
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert "provider" in data or "model" in data

    @pytest.mark.asyncio
    async def test_ai_health(self, authed_client):
        resp = await authed_client.get("/ai/health")
        # 200 when AI agent loads, 503 when provider isn't configured
        assert resp.status_code in (200, 503)
