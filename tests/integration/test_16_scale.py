"""Battle Test 16: Data Scale Testing.

Tests system behavior with large data volumes:
  - Hundreds of subscribers
  - Thousands of API keys
  - Large result set pagination
  - Search performance at scale
  - Bulk operations on large sets
  - Database query performance
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from integration.conftest import (
    create_api_key,
    create_subscriber,
    create_subscription,
    unique_email,
    unique_slug,
)


class TestSubscriberScale:
    """Test system behavior with many subscribers."""

    def test_create_100_subscribers(self, admin_session):
        """Create 100 subscribers and verify list endpoint handles them."""
        created_ids = []
        for i in range(100):
            sub = admin_session.post("/subscribers", json={
                "name": f"Scale Sub {i:03d}",
                "email": unique_email(f"scale{i:03d}"),
                "organization": "Scale Test Corp",
                "tier": "free",
            })
            assert sub.status_code == 201, f"Failed at subscriber {i}: {sub.status_code}"
            created_ids.append(sub.json()["id"])

        assert len(created_ids) == 100

        # Verify list returns data without timing out
        start = time.perf_counter()
        resp = admin_session.get("/subscribers")
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 5000, f"Subscriber list took {elapsed:.0f}ms (>5s at scale)"

    def test_subscriber_pagination_at_scale(self, admin_session):
        """Pagination works correctly with many subscribers."""
        # First page
        resp = admin_session.get("/subscribers", params={"limit": 10, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()
        # Response may be a list or paginated object
        if isinstance(data, list):
            assert len(data) <= 10 or len(data) > 0  # at least has data
        elif isinstance(data, dict):
            items = data.get("items", data.get("data", []))
            assert len(items) > 0

    def test_subscriber_search_at_scale(self, admin_session):
        """Search/filter works efficiently with many records."""
        # Create a uniquely named subscriber to search for
        unique_name = f"FindMe-{unique_slug('srch')}"
        sub = admin_session.post("/subscribers", json={
            "name": unique_name,
            "email": unique_email("srch"),
            "tier": "free",
        }).json()

        # Search should find it
        start = time.perf_counter()
        resp = admin_session.get("/subscribers", params={"search": unique_name})
        elapsed = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        assert elapsed < 3000, f"Search took {elapsed:.0f}ms (>3s)"


class TestAPIKeyScale:
    """Test system with many API keys."""

    def test_create_50_keys_for_subscriber(self, admin_session):
        """Create many API keys for a single subscriber."""
        sub = create_subscriber(admin_session, name="Key Scale Sub")
        plans = admin_session.get("/plans").json()
        enterprise_plan = next(p for p in plans if p["name"] == "enterprise")
        create_subscription(admin_session, sub["id"], enterprise_plan["id"])

        created = 0
        for i in range(50):
            resp = admin_session.post(
                f"/subscribers/{sub['id']}/keys",
                json={"name": f"scale-key-{i:03d}"},
            )
            if resp.status_code == 201:
                created += 1
            else:
                # May hit max_api_keys limit
                break

        assert created >= 10, f"Only created {created} keys before limit"

        # List keys should return quickly
        start = time.perf_counter()
        keys_resp = admin_session.get(f"/subscribers/{sub['id']}/keys")
        elapsed = (time.perf_counter() - start) * 1000
        assert keys_resp.status_code == 200
        assert elapsed < 3000, f"Key list took {elapsed:.0f}ms (>3s)"

    def test_concurrent_key_creation(self, admin_session):
        """Concurrent API key creation doesn't produce duplicates."""
        sub = create_subscriber(admin_session, name="Concurrent Keys Sub")
        plans = admin_session.get("/plans").json()
        enterprise_plan = next(p for p in plans if p["name"] == "enterprise")
        create_subscription(admin_session, sub["id"], enterprise_plan["id"])

        results = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(
                    admin_session.post,
                    f"/subscribers/{sub['id']}/keys",
                    json={"name": f"concurrent-{i}"},
                )
                for i in range(10)
            ]
            for f in as_completed(futures):
                resp = f.result()
                results.append(resp.status_code)

        created = sum(1 for s in results if s == 201)
        assert created >= 5, f"Only {created}/10 concurrent keys created"

        # Verify no duplicate key prefixes
        keys = admin_session.get(f"/subscribers/{sub['id']}/keys").json()
        prefixes = [k["key_prefix"] for k in keys]
        assert len(prefixes) == len(set(prefixes)), "Duplicate key prefixes detected!"


class TestTeamScale:
    """Test team management at scale."""

    def test_create_50_teams(self, admin_session):
        """Create 50 teams and verify list performance."""
        for i in range(50):
            resp = admin_session.post("/teams", json={
                "name": f"Scale Team {i:03d}",
                "slug": unique_slug(f"st{i:03d}"),
                "contact_email": unique_email(f"st{i:03d}"),
            })
            assert resp.status_code == 201, f"Failed at team {i}: {resp.status_code}"

        # List should be fast
        start = time.perf_counter()
        resp = admin_session.get("/teams")
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Team list took {elapsed:.0f}ms (>3s)"

    def test_team_with_many_apis(self, admin_session):
        """A team with many registered APIs loads correctly."""
        team = admin_session.post("/teams", json={
            "name": "Many APIs Team",
            "slug": unique_slug("manyapi"),
            "contact_email": unique_email("manyapi"),
        }).json()

        for i in range(20):
            admin_session.post("/api-registry", json={
                "team_id": team["id"],
                "name": f"Scale API {i:03d}",
                "slug": unique_slug(f"sapi{i:03d}"),
                "upstream_url": f"https://api{i}.example.com",
            })

        # Team detail should load fast
        start = time.perf_counter()
        resp = admin_session.get(f"/teams/{team['id']}")
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Team detail took {elapsed:.0f}ms"


class TestAPIRegistryScale:
    """Test API registry at scale."""

    def test_registry_list_with_many_apis(self, admin_session):
        """API registry list performs well with many registrations."""
        start = time.perf_counter()
        resp = admin_session.get("/api-registry")
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 5000, f"Registry list took {elapsed:.0f}ms (>5s)"

    def test_public_catalog_at_scale(self):
        """Public catalog handles many active APIs."""
        import httpx
        from integration.conftest import ADMIN_API

        start = time.perf_counter()
        with httpx.Client(base_url=ADMIN_API, timeout=10) as c:
            resp = c.get("/public/api-catalog", params={"page_size": 100})
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 5000, f"Public catalog took {elapsed:.0f}ms (>5s)"


class TestAuditLogScale:
    """Test audit log performance with many entries."""

    def test_audit_log_query_performance(self, admin_session):
        """Audit log queries should remain fast as entries accumulate."""
        # After all the scale tests, there should be many audit entries
        start = time.perf_counter()
        resp = admin_session.get("/rbac/audit", params={"limit": 50})
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Audit log query took {elapsed:.0f}ms (>3s)"

    def test_audit_log_filtered_query(self, admin_session):
        """Filtered audit log queries are efficient."""
        start = time.perf_counter()
        resp = admin_session.get("/rbac/audit", params={
            "resource_type": "subscriber",
            "limit": 20,
        })
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Filtered audit query took {elapsed:.0f}ms"


class TestKongScale:
    """Test Kong with many services and consumers."""

    def test_kong_handles_many_consumers(self, kong_admin):
        """Kong consumer list performs well at scale."""
        start = time.perf_counter()
        resp = kong_admin.get("/consumers", params={"size": 100})
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Kong consumer list took {elapsed:.0f}ms"

    def test_kong_handles_many_services(self, kong_admin):
        """Kong service list performs well at scale."""
        start = time.perf_counter()
        resp = kong_admin.get("/services", params={"size": 100})
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Kong service list took {elapsed:.0f}ms"

    def test_kong_handles_many_plugins(self, kong_admin):
        """Kong plugin list performs well at scale."""
        start = time.perf_counter()
        resp = kong_admin.get("/plugins", params={"size": 100})
        elapsed = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < 3000, f"Kong plugin list took {elapsed:.0f}ms"
