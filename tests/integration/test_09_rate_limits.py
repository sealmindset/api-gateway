"""Battle Test 09: Rate Limit Tier Validation.

Tests that subscription plans enforce correct rate limits:
  - Free, Pro, Enterprise tiers have different limits
  - Subscription-level overrides take precedence
  - Plan CRUD respects constraints
  - Subscription usage endpoint returns correct limit info
"""

from __future__ import annotations

import pytest
from integration.conftest import (
    create_subscriber,
    create_subscription,
    unique_slug,
)


class TestPlanTierLimits:
    """Verify seeded plans have correct rate limit configurations."""

    def test_free_plan_has_lowest_limits(self, admin_session):
        plans = admin_session.get("/plans").json()
        free = next(p for p in plans if p["name"] == "free")
        assert free["rate_limit_second"] <= 2
        assert free["rate_limit_minute"] <= 60
        assert free["rate_limit_hour"] <= 500
        assert free["max_api_keys"] <= 2
        assert free["price_cents"] == 0

    def test_pro_plan_has_higher_limits(self, admin_session):
        plans = admin_session.get("/plans").json()
        pro = next(p for p in plans if p["name"] == "pro")
        free = next(p for p in plans if p["name"] == "free")
        assert pro["rate_limit_second"] >= free["rate_limit_second"]
        assert pro["rate_limit_minute"] >= free["rate_limit_minute"]
        assert pro["rate_limit_hour"] >= free["rate_limit_hour"]
        assert pro["price_cents"] > free["price_cents"]

    def test_enterprise_plan_has_highest_limits(self, admin_session):
        plans = admin_session.get("/plans").json()
        enterprise = next(p for p in plans if p["name"] == "enterprise")
        pro = next(p for p in plans if p["name"] == "pro")
        assert enterprise["rate_limit_second"] >= pro["rate_limit_second"]
        assert enterprise["rate_limit_minute"] >= pro["rate_limit_minute"]
        assert enterprise["rate_limit_hour"] >= pro["rate_limit_hour"]
        assert enterprise["price_cents"] > pro["price_cents"]

    def test_plan_ordering_by_price(self, admin_session):
        """Plans should be returned ordered by price (ascending)."""
        plans = admin_session.get("/plans").json()
        prices = [p["price_cents"] for p in plans]
        assert prices == sorted(prices), "Plans should be ordered by price"


class TestSubscriptionRateLimits:
    """Subscription-level rate limit overrides and usage info."""

    def test_subscription_inherits_plan_limits(self, admin_session):
        """A new subscription without overrides uses the plan's limits."""
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        pro_plan = next(p for p in plans if p["name"] == "pro")

        subscription = create_subscription(admin_session, sub["id"], pro_plan["id"])
        # No explicit rate limits set -> should be null (inherit from plan)
        assert subscription["rate_limit_per_second"] is None
        assert subscription["rate_limit_per_minute"] is None
        assert subscription["rate_limit_per_hour"] is None

    def test_subscription_custom_rate_limits(self, admin_session):
        """Subscription can override plan-level rate limits."""
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")

        subscription = create_subscription(
            admin_session, sub["id"], free_plan["id"],
            rate_limit_per_second=50,
            rate_limit_per_minute=500,
            rate_limit_per_hour=10000,
        )
        assert subscription["rate_limit_per_second"] == 50
        assert subscription["rate_limit_per_minute"] == 500
        assert subscription["rate_limit_per_hour"] == 10000

    def test_subscription_usage_endpoint(self, admin_session):
        """The usage endpoint returns rate limit info."""
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        pro_plan = next(p for p in plans if p["name"] == "pro")
        subscription = create_subscription(admin_session, sub["id"], pro_plan["id"])

        resp = admin_session.get(f"/subscriptions/{subscription['id']}/usage")
        assert resp.status_code == 200
        usage = resp.json()
        assert usage["subscription_id"] == subscription["id"]
        assert "rate_limits" in usage

    def test_update_subscription_rate_limits(self, admin_session):
        """Rate limits can be modified on an existing subscription."""
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])

        resp = admin_session.patch(f"/subscriptions/{subscription['id']}", json={
            "rate_limit_per_second": 100,
        })
        assert resp.status_code == 200
        assert resp.json()["rate_limit_per_second"] == 100


class TestPlanCRUD:
    """Plan creation, modification, and deactivation."""

    def test_create_custom_plan(self, admin_session):
        plan_name = unique_slug("plan")
        resp = admin_session.post("/plans", json={
            "name": plan_name,
            "description": "Custom battle test plan",
            "rate_limit_second": 25,
            "rate_limit_minute": 250,
            "rate_limit_hour": 5000,
            "max_api_keys": 10,
            "price_cents": 4999,
        })
        assert resp.status_code == 201
        plan = resp.json()
        assert plan["name"] == plan_name
        assert plan["rate_limit_second"] == 25
        assert plan["price_cents"] == 4999

    def test_deactivate_plan(self, admin_session):
        plan_name = unique_slug("deact")
        plan = admin_session.post("/plans", json={
            "name": plan_name,
            "rate_limit_second": 1,
            "rate_limit_minute": 10,
            "rate_limit_hour": 100,
        }).json()

        resp = admin_session.delete(f"/plans/{plan['id']}")
        assert resp.status_code == 204

        # Verify it's deactivated (not hard-deleted)
        get_resp = admin_session.get(f"/plans/{plan['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_active"] is False

    def test_update_plan_limits(self, admin_session):
        plan_name = unique_slug("uplim")
        plan = admin_session.post("/plans", json={
            "name": plan_name,
            "rate_limit_second": 1,
            "rate_limit_minute": 10,
            "rate_limit_hour": 100,
        }).json()

        resp = admin_session.patch(f"/plans/{plan['id']}", json={
            "rate_limit_second": 50,
            "rate_limit_hour": 5000,
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["rate_limit_second"] == 50
        assert updated["rate_limit_hour"] == 5000
        # Minute should be unchanged
        assert updated["rate_limit_minute"] == 10

    def test_inactive_plans_filtered_by_default(self, admin_session):
        """Listing plans with active_only=True (default) hides inactive plans."""
        plan_name = unique_slug("inact")
        plan = admin_session.post("/plans", json={
            "name": plan_name,
            "rate_limit_second": 1,
            "rate_limit_minute": 10,
            "rate_limit_hour": 100,
        }).json()
        admin_session.delete(f"/plans/{plan['id']}")

        # Default listing should not include the deactivated plan
        plans = admin_session.get("/plans").json()
        plan_names = [p["name"] for p in plans]
        assert plan_name not in plan_names

        # Explicit active_only=false should include it
        all_plans = admin_session.get("/plans", params={"active_only": "false"}).json()
        all_names = [p["name"] for p in all_plans]
        assert plan_name in all_names


class TestSubscriptionFiltering:
    """Test subscription list filtering by status and subscriber."""

    def test_filter_by_status(self, admin_session):
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        subscription = create_subscription(admin_session, sub["id"], free_plan["id"])

        # Cancel it
        admin_session.patch(f"/subscriptions/{subscription['id']}", json={
            "status": "cancelled",
        })

        # Filter for cancelled
        resp = admin_session.get("/subscriptions", params={"status": "cancelled"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        statuses = {s["status"] for s in items}
        assert statuses == {"cancelled"}

    def test_filter_by_subscriber(self, admin_session):
        sub = create_subscriber(admin_session)
        plans = admin_session.get("/plans").json()
        free_plan = next(p for p in plans if p["name"] == "free")
        create_subscription(admin_session, sub["id"], free_plan["id"])

        resp = admin_session.get("/subscriptions", params={"subscriber_id": sub["id"]})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(s["subscriber_id"] == sub["id"] for s in items)
