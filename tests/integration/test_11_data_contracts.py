"""Battle Test 11: Data Contracts.

Tests data contract fields on API registrations:
  - Setting contract fields at creation time
  - Updating contracts on active APIs (no approval needed)
  - Public catalog endpoint (unauthenticated)
  - Kong request-size-limiting enforcement
  - Validation of SLA and contact fields
  - Contract defaults
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
        "name": "Contract Test Team",
        "slug": unique_slug("ct"),
        "contact_email": unique_email("ct"),
    }).json()


def _create_api(session, team_id: str, **overrides) -> dict:
    payload = {
        "team_id": team_id,
        "name": "Contract Test API",
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


# ---------------------------------------------------------------------------
# Contract CRUD
# ---------------------------------------------------------------------------

class TestContractCRUD:
    """Creating and updating data contract fields."""

    def test_create_api_with_contract_fields(self, admin_session):
        """Contract fields can be set at registration time."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            contact_primary_email="oncall@example.com",
            contact_escalation_email="escalation@example.com",
            contact_slack_channel="#api-alerts",
            sla_uptime_target=99.95,
            sla_latency_p50_ms=50,
            sla_latency_p95_ms=200,
            sla_latency_p99_ms=500,
            sla_error_budget_pct=0.05,
            sla_support_hours="24/7",
            deprecation_notice_days=60,
            breaking_change_policy="semver",
            openapi_spec_url="https://docs.example.com/openapi.json",
            max_request_size_kb=512,
        )
        assert api["contact_primary_email"] == "oncall@example.com"
        assert api["contact_slack_channel"] == "#api-alerts"
        assert float(api["sla_uptime_target"]) == 99.95
        assert api["sla_latency_p50_ms"] == 50
        assert api["sla_latency_p99_ms"] == 500
        assert api["deprecation_notice_days"] == 60
        assert api["max_request_size_kb"] == 512
        assert api["openapi_spec_url"] == "https://docs.example.com/openapi.json"

    def test_contract_defaults(self, admin_session):
        """APIs created without contract fields get sensible defaults."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        assert api["contact_primary_email"] is None
        assert api["sla_uptime_target"] is None
        assert api["deprecation_notice_days"] == 90
        assert api["breaking_change_policy"] == "semver"
        assert api["versioning_scheme"] == "url-path"
        assert api["max_request_size_kb"] == 128

    def test_update_contract_on_draft(self, admin_session):
        """Contract fields can be updated on a draft API via /contract endpoint."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "contact_primary_email": "team@example.com",
            "sla_uptime_target": 99.9,
            "sla_latency_p99_ms": 300,
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["contact_primary_email"] == "team@example.com"
        assert float(updated["sla_uptime_target"]) == 99.9
        assert updated["sla_latency_p99_ms"] == 300

    def test_update_contract_on_active_api(self, admin_session):
        """Contract fields can be updated on an ACTIVE API without re-approval."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        _activate_api(admin_session, api["id"])

        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "contact_escalation_email": "escalation@example.com",
            "sla_support_hours": "business-hours-cst",
            "changelog_url": "https://changelog.example.com",
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["status"] == "active"  # Status unchanged
        assert updated["contact_escalation_email"] == "escalation@example.com"
        assert updated["sla_support_hours"] == "business-hours-cst"
        assert updated["changelog_url"] == "https://changelog.example.com"

    def test_partial_contract_update(self, admin_session):
        """Only specified fields are updated; others remain unchanged."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            contact_primary_email="original@example.com",
            sla_uptime_target=99.9,
        )
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "contact_slack_channel": "#new-channel",
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["contact_primary_email"] == "original@example.com"  # unchanged
        assert float(updated["sla_uptime_target"]) == 99.9  # unchanged
        assert updated["contact_slack_channel"] == "#new-channel"  # new

    def test_contract_validation_uptime_out_of_range(self, admin_session):
        """SLA uptime target > 100 is rejected."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "sla_uptime_target": 150,
        })
        assert resp.status_code == 422

    def test_contract_validation_negative_latency(self, admin_session):
        """Negative latency values are rejected."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "sla_latency_p99_ms": -1,
        })
        assert resp.status_code == 422

    def test_contract_validation_invalid_policy(self, admin_session):
        """Invalid breaking_change_policy is rejected."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "breaking_change_policy": "yolo",
        })
        assert resp.status_code == 422

    def test_contract_validation_invalid_versioning(self, admin_session):
        """Invalid versioning_scheme is rejected."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "versioning_scheme": "random",
        })
        assert resp.status_code == 422

    def test_contract_in_get_registration(self, admin_session):
        """GET /{id} includes all contract fields."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            contact_primary_email="get-test@example.com",
            sla_uptime_target=99.5,
        )
        resp = admin_session.get(f"/api-registry/{api['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["contact_primary_email"] == "get-test@example.com"
        assert float(data["sla_uptime_target"]) == 99.5
        assert "deprecation_notice_days" in data
        assert "max_request_size_kb" in data


# ---------------------------------------------------------------------------
# Public Catalog
# ---------------------------------------------------------------------------

class TestPublicCatalog:
    """Public API catalog — unauthenticated access for subscribers."""

    def test_public_catalog_no_auth_required(self):
        """The public catalog works without any authentication."""
        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get("/public/api-catalog")
        assert resp.status_code == 200
        assert "items" in resp.json()
        client.close()

    def test_public_catalog_lists_active_only(self, admin_session):
        """Only active APIs appear in the public catalog."""
        team = _create_team(admin_session)
        # Draft API — should NOT appear
        draft_api = _create_api(admin_session, team["id"])
        # Active API — should appear
        active_api = _create_api(admin_session, team["id"])
        _activate_api(admin_session, active_api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get("/public/api-catalog", params={"page_size": 100})
        assert resp.status_code == 200
        slugs = [item["slug"] for item in resp.json()["items"]]
        assert active_api["slug"] in slugs
        assert draft_api["slug"] not in slugs
        client.close()

    def test_public_catalog_by_slug(self, admin_session):
        """GET by slug returns the API's contract."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            contact_primary_email="catalog@example.com",
            sla_uptime_target=99.99,
        )
        activated = _activate_api(admin_session, api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == api["slug"]
        assert data["contact_primary_email"] == "catalog@example.com"
        assert float(data["sla_uptime_target"]) == 99.99
        client.close()

    def test_public_catalog_excludes_internal_fields(self, admin_session):
        """Internal fields (upstream URL, Kong IDs, reviewer) are not exposed."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        _activate_api(admin_session, api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}")
        assert resp.status_code == 200
        data = resp.json()
        # These internal fields must NOT be present
        assert "upstream_url" not in data
        assert "kong_service_id" not in data
        assert "kong_route_id" not in data
        assert "reviewed_by" not in data
        assert "team_id" not in data
        client.close()

    def test_public_catalog_404_for_draft(self, admin_session):
        """Looking up a draft API by slug returns 404."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}")
        assert resp.status_code == 404
        client.close()

    def test_public_catalog_search(self, admin_session):
        """Search filters catalog by name/slug."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"], name="Weather Forecast API")
        _activate_api(admin_session, api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get("/public/api-catalog", params={"search": "Weather"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any("Weather" in item["name"] for item in items)
        client.close()


# ---------------------------------------------------------------------------
# Kong Enforcement
# ---------------------------------------------------------------------------

class TestKongEnforcement:
    """Kong request-size-limiting plugin synced from data contract."""

    def test_request_size_plugin_on_activation(self, admin_session, kong_admin):
        """Activating an API with max_request_size_kb creates the Kong plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"], max_request_size_kb=512)
        _activate_api(admin_session, api["id"])

        svc_name = f"api-reg-{api['slug']}"
        plugins_resp = kong_admin.get(f"/services/{svc_name}/plugins")
        assert plugins_resp.status_code == 200
        plugins = plugins_resp.json()["data"]
        size_plugins = [p for p in plugins if p["name"] == "request-size-limiting"]
        assert len(size_plugins) == 1
        assert size_plugins[0]["config"]["allowed_payload_size"] == 512

    def test_request_size_plugin_update_via_contract(self, admin_session, kong_admin):
        """Updating max_request_size_kb on an active API updates the Kong plugin."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"], max_request_size_kb=128)
        _activate_api(admin_session, api["id"])

        # Update contract with new size limit
        resp = admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "max_request_size_kb": 1024,
        })
        assert resp.status_code == 200

        # Verify Kong plugin was updated
        svc_name = f"api-reg-{api['slug']}"
        plugins_resp = kong_admin.get(f"/services/{svc_name}/plugins")
        plugins = plugins_resp.json()["data"]
        size_plugins = [p for p in plugins if p["name"] == "request-size-limiting"]
        assert len(size_plugins) == 1
        assert size_plugins[0]["config"]["allowed_payload_size"] == 1024


# ---------------------------------------------------------------------------
# RBAC on Contract Endpoint
# ---------------------------------------------------------------------------

class TestContractRBAC:
    """Verify that contract updates respect RBAC."""

    def test_viewer_cannot_update_contract(self, viewer_session, admin_session):
        """Viewers (read-only) cannot update data contracts."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        resp = viewer_session.patch(f"/api-registry/{api['id']}/contract", json={
            "contact_primary_email": "hacker@evil.com",
        })
        assert resp.status_code == 403

    def test_unauthenticated_cannot_update_contract(self, admin_session):
        """Unauthenticated users cannot update contracts."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.patch(f"/api-registry/{api['id']}/contract", json={
            "contact_primary_email": "anon@evil.com",
        })
        assert resp.status_code in (401, 403)
        client.close()


# ---------------------------------------------------------------------------
# Audit Trail
# ---------------------------------------------------------------------------

class TestContractAudit:
    """Contract updates produce audit log entries."""

    def test_contract_update_logged(self, admin_session):
        """Updating a contract generates an audit entry with action=update_contract."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        admin_session.patch(f"/api-registry/{api['id']}/contract", json={
            "sla_uptime_target": 99.9,
        })

        resp = admin_session.get("/rbac/audit", params={
            "resource_type": "api_registration",
            "resource_id": api["id"],
        })
        assert resp.status_code == 200
        items = resp.json().get("items", resp.json())
        actions = [log["action"] for log in items]
        assert "update_contract" in actions


# ---------------------------------------------------------------------------
# Developer Portal (Try It)
# ---------------------------------------------------------------------------

class TestDeveloperPortal:
    """Swagger UI developer portal for active APIs with OpenAPI specs."""

    def test_try_it_returns_html(self, admin_session):
        """Active API with openapi_spec_url returns a Swagger UI HTML page."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            openapi_spec_url="https://petstore3.swagger.io/api/v3/openapi.json",
        )
        _activate_api(admin_session, api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}/try-it")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        body = resp.text
        assert "swagger-ui" in body
        assert "petstore3.swagger.io" in body
        assert api["name"] in body
        client.close()

    def test_try_it_no_spec_returns_404(self, admin_session):
        """Active API without openapi_spec_url returns 404."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"])
        _activate_api(admin_session, api["id"])

        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}/try-it")
        assert resp.status_code == 404
        client.close()

    def test_try_it_inactive_api_returns_404(self, admin_session):
        """Draft API returns 404 for try-it."""
        team = _create_team(admin_session)
        api = _create_api(admin_session, team["id"],
            openapi_spec_url="https://example.com/openapi.json",
        )
        # Do NOT activate — stays in draft
        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get(f"/public/api-catalog/{api['slug']}/try-it")
        assert resp.status_code == 404
        client.close()

    def test_try_it_nonexistent_slug_returns_404(self):
        """Non-existent slug returns 404."""
        client = httpx.Client(base_url=ADMIN_API, timeout=10)
        resp = client.get("/public/api-catalog/does-not-exist-xyz/try-it")
        assert resp.status_code == 404
        client.close()
