"""Battle Test 12: Per-API Caching Policies.

Tests caching configuration on API registrations:
  - Default values (cache disabled)
  - Kong proxy-cache plugin creation on activation
  - Enabling/disabling cache via contract update
  - Updating cache TTL on active API
  - Public catalog shows cache status
"""

from __future__ import annotations

import httpx
import pytest
from integration.conftest import (
    ADMIN_API,
    KONG_ADMIN,
    unique_email,
    unique_slug,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_team(session) -> dict:
    return session.post("/teams", json={
        "name": "Cache Test Team",
        "slug": unique_slug("cache"),
        "contact_email": unique_email("cache"),
    }).json()


def _create_api(session, team_id: str, **overrides) -> dict:
    payload = {
        "team_id": team_id,
        "name": "Cache Test API",
        "slug": unique_slug("capi"),
        "upstream_url": "https://httpbin.org",
    }
    payload.update(overrides)
    resp = session.post("/api-registry", json=payload)
    assert resp.status_code == 201, f"Create API failed: {resp.status_code} {resp.text}"
    return resp.json()


def _activate_api(session, reg_id: str) -> dict:
    """Submit -> approve -> activate an API registration."""
    session.post(f"/api-registry/{reg_id}/submit")
    session.post(f"/api-registry/{reg_id}/review", json={
        "action": "approve", "notes": "Auto-approved for testing",
    })
    resp = session.post(f"/api-registry/{reg_id}/activate")
    assert resp.status_code == 200, f"Activate failed: {resp.status_code} {resp.text}"
    return resp.json()


def _get_proxy_cache_plugins(kong_admin, slug: str) -> list:
    """Return proxy-cache plugins for a service."""
    svc_name = f"api-reg-{slug}"
    resp = kong_admin.get(f"/services/{svc_name}/plugins")
    assert resp.status_code == 200
    return [p for p in resp.json()["data"] if p["name"] == "proxy-cache"]


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestCachingDefaults:
    """APIs are created with caching disabled by default."""

    def test_cache_disabled_by_default(self, admin_session):
        """New APIs have cache_enabled=false."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        assert api["cache_enabled"] is False

    def test_cache_default_values(self, admin_session):
        """Default cache configuration values are sensible."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        assert api["cache_ttl_seconds"] == 300
        assert api["cache_methods"] == ["GET", "HEAD"]
        assert api["cache_content_types"] == ["application/json"]
        assert api["cache_vary_headers"] == ["Accept"]
        assert api["cache_bypass_on_auth"] is True


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

class TestCachingActivation:
    """Kong proxy-cache plugin creation on activation."""

    def test_activate_with_cache_enabled(self, admin_session, kong_admin):
        """Activating with cache_enabled=true creates proxy-cache plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"], cache_enabled=True, cache_ttl_seconds=60)
        _activate_api(admin_session, api["id"])

        plugins = _get_proxy_cache_plugins(kong_admin, api["slug"])
        assert len(plugins) == 1
        assert plugins[0]["config"]["cache_ttl"] == 60
        assert plugins[0]["config"]["strategy"] == "memory"

    def test_activate_without_cache(self, admin_session, kong_admin):
        """Activating with default (cache disabled) does not create proxy-cache plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        _activate_api(admin_session, api["id"])

        plugins = _get_proxy_cache_plugins(kong_admin, api["slug"])
        assert len(plugins) == 0

    def test_cache_content_types_in_plugin(self, admin_session, kong_admin):
        """Custom cache_content_types are passed to Kong plugin config."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            cache_enabled=True,
            cache_content_types=["application/json", "text/plain"],
        )
        _activate_api(admin_session, api["id"])

        plugins = _get_proxy_cache_plugins(kong_admin, api["slug"])
        assert len(plugins) == 1
        assert "text/plain" in plugins[0]["config"]["content_type"]


# ---------------------------------------------------------------------------
# Contract Update
# ---------------------------------------------------------------------------

class TestCachingContractUpdate:
    """Cache settings updated via the contract endpoint sync to Kong."""

    def test_enable_cache_on_active_api(self, admin_session, kong_admin):
        """Enabling cache on an active API creates the proxy-cache plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        _activate_api(admin_session, api["id"])

        # Verify no plugin initially
        assert len(_get_proxy_cache_plugins(kong_admin, api["slug"])) == 0

        # Enable via contract
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "cache_enabled": True,
            "cache_ttl_seconds": 120,
        })
        assert resp.status_code == 200

        plugins = _get_proxy_cache_plugins(kong_admin, api["slug"])
        assert len(plugins) == 1
        assert plugins[0]["config"]["cache_ttl"] == 120

    def test_disable_cache_on_active_api(self, admin_session, kong_admin):
        """Disabling cache on an active API removes the proxy-cache plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"], cache_enabled=True)
        _activate_api(admin_session, api["id"])

        # Verify plugin exists
        assert len(_get_proxy_cache_plugins(kong_admin, api["slug"])) == 1

        # Disable via contract
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "cache_enabled": False,
        })
        assert resp.status_code == 200

        plugins = _get_proxy_cache_plugins(kong_admin, api["slug"])
        assert len(plugins) == 0

    def test_update_cache_ttl_on_active_api(self, admin_session, kong_admin):
        """Updating cache TTL on an active API updates the Kong plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"], cache_enabled=True, cache_ttl_seconds=300)
        _activate_api(admin_session, api["id"])

        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "cache_ttl_seconds": 60,
        })
        assert resp.status_code == 200

        plugins = _get_proxy_cache_plugins(kong_admin, api["slug"])
        assert len(plugins) == 1
        assert plugins[0]["config"]["cache_ttl"] == 60

    def test_cache_fields_in_get_registration(self, admin_session):
        """GET /{id} includes cache fields."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            cache_enabled=True,
            cache_ttl_seconds=600,
        )
        resp = admin_session.get(f"/api-registry/{api['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_enabled"] is True
        assert data["cache_ttl_seconds"] == 600


# ---------------------------------------------------------------------------
# Public Catalog
# ---------------------------------------------------------------------------

class TestCachingPublicCatalog:
    """Public catalog includes cache status."""

    def test_public_catalog_shows_cache_status(self, admin_session):
        """Public catalog entry includes cache_enabled and cache_ttl_seconds."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            cache_enabled=True,
            cache_ttl_seconds=120,
        )
        _activate_api(admin_session, api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_enabled"] is True
        assert data["cache_ttl_seconds"] == 120
        client.close()
