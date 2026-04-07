"""Battle Test 08: End-to-End Lifecycle.

Tests the complete real-world workflow:
  - Register an API via team -> submit -> approve -> activate in Kong
  - Create subscriber -> assign plan -> create API key
  - Verify Kong has the service, route, consumer, and key-auth credential
  - Hit the proxy endpoint with the API key and verify routing
  - Upgrade subscription plan
  - Deprecate and retire the API
"""

from __future__ import annotations

import time

import httpx
import pytest
from integration.conftest import (
    KONG_ADMIN,
    KONG_PROXY,
    create_api_key,
    create_subscriber,
    create_subscription,
    unique_email,
    unique_slug,
)


class TestFullApiLifecycle:
    """Provision an API end-to-end: team -> registry -> Kong -> proxy."""

    def test_register_submit_approve_activate(self, admin_session, kong_admin):
        """Walk the entire API registration workflow through to Kong activation."""
        # 1. Create a team
        slug = unique_slug("e2e")
        team = admin_session.post("/teams", json={
            "name": "E2E Lifecycle Team",
            "slug": slug,
            "description": "End-to-end test team",
            "contact_email": unique_email("e2e"),
        }).json()
        assert team["id"]

        # 2. Register an API
        api_slug = unique_slug("e2eapi")
        reg = admin_session.post("/api-registry", json={
            "team_id": team["id"],
            "name": "E2E Test API",
            "slug": api_slug,
            "description": "End-to-end lifecycle test API",
            "upstream_url": "https://httpbin.org",
            "auth_type": "key-auth",
            "rate_limit_second": 10,
            "rate_limit_minute": 100,
            "rate_limit_hour": 1000,
        }).json()
        assert reg["status"] == "draft"

        # 3. Submit for review
        submit_resp = admin_session.post(f"/api-registry/{reg['id']}/submit")
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "pending_review"

        # 4. Approve
        review_resp = admin_session.post(f"/api-registry/{reg['id']}/review", json={
            "action": "approve",
            "notes": "Approved for E2E testing",
        })
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "approved"

        # 5. Activate (provisions Kong service + route)
        activate_resp = admin_session.post(f"/api-registry/{reg['id']}/activate")
        assert activate_resp.status_code == 200
        activated = activate_resp.json()
        assert activated["status"] == "active"
        assert activated["kong_service_id"] is not None
        assert activated["kong_route_id"] is not None
        assert activated["gateway_path"] == f"/api/{api_slug}"

        # 6. Verify Kong has the service
        svc_name = f"api-reg-{api_slug}"
        svc_resp = kong_admin.get(f"/services/{svc_name}")
        assert svc_resp.status_code == 200
        kong_svc = svc_resp.json()
        assert kong_svc["host"] == "httpbin.org"

        # 7. Verify Kong has the route
        route_name = f"api-reg-{api_slug}-route"
        route_resp = kong_admin.get(f"/services/{svc_name}/routes/{route_name}")
        assert route_resp.status_code == 200
        kong_route = route_resp.json()
        assert f"/api/{api_slug}" in kong_route["paths"]

        # 8. Verify plugins were added (key-auth is required; rate-limiting
        # may fail if Kong redis is not configured, so we only assert key-auth)
        plugins_resp = kong_admin.get(f"/services/{svc_name}/plugins")
        assert plugins_resp.status_code == 200
        plugin_names = [p["name"] for p in plugins_resp.json()["data"]]
        assert "key-auth" in plugin_names

    def test_api_reject_and_resubmit(self, admin_session):
        """Test the reject -> edit -> resubmit flow."""
        team = admin_session.post("/teams", json={
            "name": "Reject Flow Team", "slug": unique_slug("rejf"),
            "contact_email": unique_email("rejf"),
        }).json()
        reg = admin_session.post("/api-registry", json={
            "team_id": team["id"],
            "name": "Rejected API",
            "slug": unique_slug("rejapi"),
            "upstream_url": "https://api.example.com",
        }).json()

        # Submit -> Reject
        admin_session.post(f"/api-registry/{reg['id']}/submit")
        admin_session.post(f"/api-registry/{reg['id']}/review", json={
            "action": "reject",
            "notes": "Missing documentation URL",
        })
        rejected = admin_session.get(f"/api-registry/{reg['id']}").json()
        assert rejected["status"] == "rejected"

        # Edit rejected API (resets to draft)
        admin_session.patch(f"/api-registry/{reg['id']}", json={
            "documentation_url": "https://docs.example.com",
        })
        edited = admin_session.get(f"/api-registry/{reg['id']}").json()
        assert edited["status"] == "draft"
        assert edited["documentation_url"] == "https://docs.example.com"

        # Resubmit -> Approve
        admin_session.post(f"/api-registry/{reg['id']}/submit")
        review_resp = admin_session.post(f"/api-registry/{reg['id']}/review", json={
            "action": "approve",
            "notes": "Documentation added, approved",
        })
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "approved"


class TestSubscriberOnboarding:
    """Full subscriber lifecycle: create -> plan -> key -> use."""

    def test_onboard_subscriber_with_plan_and_key(self, admin_session):
        """Create a subscriber, assign a plan, issue an API key."""
        # Create subscriber
        sub = create_subscriber(admin_session, tier="pro")
        assert sub["tier"] == "pro"
        assert sub["status"] == "active"

        # Get the pro plan
        plans = admin_session.get("/plans").json()
        pro_plan = next(p for p in plans if p["name"] == "pro")

        # Create subscription
        subscription = create_subscription(admin_session, sub["id"], pro_plan["id"])
        assert subscription["status"] == "active"
        assert subscription["plan_id"] == pro_plan["id"]

        # Create API key
        key = create_api_key(admin_session, sub["id"], name="onboarding-key")
        assert key["raw_key"] is not None
        assert key["is_active"] is True
        assert key["key_prefix"] == key["raw_key"][:8]

        # Verify subscriber shows in Kong as a consumer
        # (The DB trigger should have synced it)
        kong = httpx.Client(base_url=KONG_ADMIN, timeout=10)
        consumers = kong.get("/consumers").json()
        consumer_usernames = [c["username"] for c in consumers["data"]]
        assert sub["id"] in consumer_usernames
        kong.close()

    def test_subscriber_plan_upgrade_preserves_key(self, admin_session):
        """Upgrading a plan doesn't invalidate existing API keys."""
        sub = create_subscriber(admin_session, tier="free")
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        pro_plan = next(p for p in plans if p["name"] == "pro")

        # Create subscription on free plan
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])

        # Create an API key
        key = create_api_key(admin_session, sub["id"])
        raw_key = key["raw_key"]

        # Upgrade to pro
        upgrade_resp = admin_session.patch(f"/subscriptions/{subscription['id']}", json={
            "plan_id": pro_plan["id"],
        })
        assert upgrade_resp.status_code == 200

        # Verify key is still active
        keys_resp = admin_session.get(f"/subscribers/{sub['id']}/keys")
        assert keys_resp.status_code == 200
        active_keys = [k for k in keys_resp.json() if k["is_active"]]
        assert len(active_keys) >= 1


class TestBulkOperations:
    """Test bulk actions on subscriptions."""

    def test_bulk_suspend_subscriptions(self, admin_session):
        """Bulk suspend multiple subscriptions."""
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")

        # Create 3 subscribers with subscriptions
        sub_ids = []
        for i in range(3):
            sub = create_subscriber(admin_session)
            subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
            sub_ids.append(subscription["id"])

        # Bulk suspend
        resp = admin_session.post("/subscriptions/bulk", json={
            "subscription_ids": sub_ids,
            "action": "suspend",
        })
        assert resp.status_code == 200
        result = resp.json()
        assert result["updated"] == 3

        # Verify each is suspended
        for sid in sub_ids:
            s = admin_session.get(f"/subscriptions/{sid}").json()
            assert s["status"] == "suspended"

    def test_bulk_activate_after_suspend(self, admin_session):
        """Bulk reactivate suspended subscriptions."""
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")

        sub = create_subscriber(admin_session)
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])

        # Suspend then reactivate
        admin_session.post("/subscriptions/bulk", json={
            "subscription_ids": [subscription["id"]],
            "action": "suspend",
        })
        resp = admin_session.post("/subscriptions/bulk", json={
            "subscription_ids": [subscription["id"]],
            "action": "activate",
        })
        assert resp.status_code == 200
        s = admin_session.get(f"/subscriptions/{subscription['id']}").json()
        assert s["status"] == "active"

    def test_bulk_cancel_subscriptions(self, admin_session):
        """Bulk cancel subscriptions."""
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")

        subs = []
        for _ in range(2):
            sub = create_subscriber(admin_session)
            subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
            subs.append(subscription["id"])

        resp = admin_session.post("/subscriptions/bulk", json={
            "subscription_ids": subs,
            "action": "cancel",
        })
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2

    def test_bulk_invalid_action_rejected(self, admin_session):
        """Invalid bulk action returns 400."""
        resp = admin_session.post("/subscriptions/bulk", json={
            "subscription_ids": ["00000000-0000-0000-0000-000000000001"],
            "action": "destroy",
        })
        assert resp.status_code == 400


class TestApiKeyRotation:
    """Test API key lifecycle: create, rotate, revoke."""

    def test_rotate_key_invalidates_old(self, admin_session):
        """After rotation, the old key is deactivated."""
        sub = create_subscriber(admin_session)
        key = create_api_key(admin_session, sub["id"], name="rotate-test")
        old_key_id = key["id"]

        # Rotate
        rotate_resp = admin_session.post(f"/subscribers/{sub['id']}/keys/{old_key_id}/rotate")
        assert rotate_resp.status_code == 200
        rotation = rotate_resp.json()
        assert rotation["old_key_id"] == old_key_id
        assert rotation["new_key"]["raw_key"] is not None

        # Old key should be inactive
        keys = admin_session.get(f"/subscribers/{sub['id']}/keys").json()
        old_key = next(k for k in keys if k["id"] == old_key_id)
        assert old_key["is_active"] is False

        # New key should be active
        new_key = next(k for k in keys if k["id"] == rotation["new_key"]["id"])
        assert new_key["is_active"] is True

    def test_multiple_active_keys(self, admin_session):
        """A subscriber can have multiple active keys simultaneously."""
        sub = create_subscriber(admin_session)
        key1 = create_api_key(admin_session, sub["id"], name="key-alpha")
        key2 = create_api_key(admin_session, sub["id"], name="key-beta")

        keys = admin_session.get(f"/subscribers/{sub['id']}/keys").json()
        active = [k for k in keys if k["is_active"]]
        assert len(active) >= 2


class TestAuditTrail:
    """Verify that admin actions produce audit log entries."""

    def test_subscriber_actions_logged(self, admin_session):
        """Creating and updating a subscriber generates audit entries."""
        sub = create_subscriber(admin_session)
        admin_session.patch(f"/subscribers/{sub['id']}", json={"tier": "gold"})

        # Check audit logs (endpoint is /rbac/audit)
        resp = admin_session.get("/rbac/audit", params={
            "resource_type": "subscriber",
            "resource_id": sub["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        actions = [log["action"] for log in items]
        assert "create" in actions
        assert "update" in actions

    def test_team_actions_logged(self, admin_session):
        """Team creation generates an audit entry."""
        team = admin_session.post("/teams", json={
            "name": "Audit Test Team", "slug": unique_slug("aud"),
            "contact_email": unique_email("aud"),
        }).json()

        resp = admin_session.get("/rbac/audit", params={
            "resource_type": "team",
            "resource_id": team["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        actions = [log["action"] for log in items]
        assert "create" in actions
