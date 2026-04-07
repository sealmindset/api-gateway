"""Battle Test 03: Subscriber Lifecycle.

Full lifecycle testing of subscriber onboarding:
  - Create subscriber
  - Generate API keys
  - Create subscriptions at different tiers
  - Upgrade/downgrade plans
  - Revoke API keys
  - Delete subscriber (cascade)
"""

from __future__ import annotations

import pytest
from integration.conftest import (
    create_subscriber, create_api_key, create_subscription,
    unique_email, now_iso,
)


class TestSubscriberCRUD:
    """Basic subscriber CRUD operations."""

    def test_create_subscriber(self, admin_session):
        sub = create_subscriber(admin_session, tier="free")
        assert sub["id"]
        assert sub["tier"] == "free"
        assert sub["status"] == "active"

    def test_list_subscribers(self, admin_session):
        resp = admin_session.get("/subscribers")
        assert resp.status_code == 200
        data = resp.json()
        # Paginated response
        if isinstance(data, dict) and "items" in data:
            assert len(data["items"]) >= 1
        else:
            assert isinstance(data, list)
            assert len(data) >= 1

    def test_get_subscriber_by_id(self, admin_session):
        sub = create_subscriber(admin_session, tier="basic")
        resp = admin_session.get(f"/subscribers/{sub['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == sub["id"]

    def test_update_subscriber(self, admin_session):
        sub = create_subscriber(admin_session)
        resp = admin_session.patch(f"/subscribers/{sub['id']}", json={
            "organization": "Updated Corp",
            "tier": "pro",
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["organization"] == "Updated Corp"
        assert updated["tier"] == "pro"

    def test_delete_subscriber(self, admin_session):
        sub = create_subscriber(admin_session)
        resp = admin_session.delete(f"/subscribers/{sub['id']}")
        assert resp.status_code == 204
        # After delete, subscriber may be soft-deleted (status=deleted) or gone
        resp = admin_session.get(f"/subscribers/{sub['id']}")
        if resp.status_code == 200:
            assert resp.json()["status"] == "deleted"
        else:
            assert resp.status_code == 404

    def test_get_nonexistent_subscriber_404(self, admin_session):
        resp = admin_session.get("/subscribers/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_create_subscriber_validation(self, admin_session):
        """Missing required fields should return 422."""
        resp = admin_session.post("/subscribers", json={"name": "no email"})
        assert resp.status_code == 422


class TestApiKeys:
    """API key generation and management."""

    def test_create_api_key(self, admin_session):
        sub = create_subscriber(admin_session)
        key = create_api_key(admin_session, sub["id"])
        assert key["raw_key"].startswith("gw_")
        assert key["key_prefix"]
        assert key["is_active"] is True

    def test_create_multiple_keys(self, admin_session):
        sub = create_subscriber(admin_session)
        key1 = create_api_key(admin_session, sub["id"], name="key-1")
        key2 = create_api_key(admin_session, sub["id"], name="key-2")
        assert key1["id"] != key2["id"]
        assert key1["raw_key"] != key2["raw_key"]

    def test_list_subscriber_keys(self, admin_session):
        sub = create_subscriber(admin_session)
        create_api_key(admin_session, sub["id"], name="list-test")
        resp = admin_session.get(f"/subscribers/{sub['id']}/keys")
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) >= 1
        # Raw key should NOT be in the list response
        for k in keys:
            assert "raw_key" not in k

    def test_delete_api_key(self, admin_session):
        sub = create_subscriber(admin_session)
        key = create_api_key(admin_session, sub["id"])
        resp = admin_session.delete(f"/subscribers/{sub['id']}/keys/{key['id']}")
        assert resp.status_code == 204

    def test_rotate_api_key(self, admin_session):
        sub = create_subscriber(admin_session)
        key = create_api_key(admin_session, sub["id"])
        resp = admin_session.post(f"/subscribers/{sub['id']}/keys/{key['id']}/rotate")
        assert resp.status_code == 200
        rotated = resp.json()
        assert rotated["old_key_id"] == key["id"]
        assert rotated["new_key"]["raw_key"] != key["raw_key"]


class TestSubscriptions:
    """Subscription plan management."""

    def test_create_subscription(self, admin_session):
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
        assert subscription["status"] == "active"
        assert subscription["subscriber_id"] == sub["id"]
        assert subscription["plan_id"] == free_plan["id"]

    def test_list_subscriptions(self, admin_session):
        resp = admin_session.get("/subscriptions")
        assert resp.status_code == 200

    def test_get_subscription_by_id(self, admin_session):
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
        resp = admin_session.get(f"/subscriptions/{subscription['id']}")
        assert resp.status_code == 200

    def test_upgrade_subscription(self, admin_session):
        """Change a subscription from free to pro plan."""
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        pro_plan = next(p for p in plans if p["name"] == "pro")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
        resp = admin_session.patch(f"/subscriptions/{subscription['id']}", json={
            "plan_id": pro_plan["id"],
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["plan_id"] == pro_plan["id"]

    def test_cancel_subscription(self, admin_session):
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
        resp = admin_session.patch(f"/subscriptions/{subscription['id']}", json={
            "status": "cancelled",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_delete_subscription(self, admin_session):
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])
        resp = admin_session.delete(f"/subscriptions/{subscription['id']}")
        assert resp.status_code == 204


class TestPlans:
    """Subscription plan CRUD."""

    def test_list_seeded_plans(self, admin_session):
        resp = admin_session.get("/plans")
        plans = resp.json()
        names = [p["name"] for p in plans]
        assert "free" in names
        assert "basic" in names
        assert "pro" in names
        assert "enterprise" in names

    def test_free_plan_rate_limits(self, admin_session):
        plans = admin_session.get("/plans").json()
        free = next(p for p in plans if p["name"] == "free")
        assert free["rate_limit_second"] == 1
        assert free["rate_limit_minute"] == 30
        assert free["rate_limit_hour"] == 500
        assert free["max_api_keys"] == 2
        assert free["price_cents"] == 0

    def test_enterprise_plan_rate_limits(self, admin_session):
        plans = admin_session.get("/plans").json()
        ent = next(p for p in plans if p["name"] == "enterprise")
        assert ent["rate_limit_second"] == 100
        assert ent["rate_limit_minute"] == 3000
        assert ent["rate_limit_hour"] == 100000
        assert ent["max_api_keys"] == 50
        assert ent["price_cents"] == 49999
