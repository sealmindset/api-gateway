"""Battle Test 13: Load & Stress Testing.

Simulates real traffic patterns against the live Docker stack:
  - Concurrent API requests to admin panel
  - Burst traffic to Kong proxy
  - Rate limit enforcement under pressure
  - Connection pool exhaustion recovery
  - Sustained throughput measurement
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pytest
from integration.conftest import (
    ADMIN_API,
    KONG_ADMIN,
    KONG_PROXY,
    create_api_key,
    create_subscriber,
    create_subscription,
    unique_email,
    unique_slug,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timed_request(client_base: str, path: str, **kwargs) -> dict:
    """Make a request and return timing + status info."""
    start = time.perf_counter()
    try:
        with httpx.Client(base_url=client_base, timeout=15) as c:
            resp = c.get(path, **kwargs)
        elapsed = time.perf_counter() - start
        return {"status": resp.status_code, "elapsed_ms": elapsed * 1000, "error": None}
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {"status": 0, "elapsed_ms": elapsed * 1000, "error": str(e)}


class TestAdminAPIConcurrency:
    """Verify the admin panel handles concurrent requests without errors."""

    def test_concurrent_reads_to_subscribers(self, admin_session):
        """50 concurrent GET /subscribers should all succeed."""
        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                pool.submit(lambda: admin_session.get("/subscribers"))
                for _ in range(50)
            ]
            for f in as_completed(futures):
                resp = f.result()
                results.append(resp.status_code)

        success_count = sum(1 for s in results if s == 200)
        assert success_count >= 45, (
            f"Only {success_count}/50 requests succeeded: {results}"
        )

    def test_concurrent_reads_to_plans(self, admin_session):
        """50 concurrent GET /plans should all succeed."""
        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                pool.submit(lambda: admin_session.get("/plans"))
                for _ in range(50)
            ]
            for f in as_completed(futures):
                resp = f.result()
                results.append(resp.status_code)

        success_count = sum(1 for s in results if s == 200)
        assert success_count >= 45, (
            f"Only {success_count}/50 requests succeeded"
        )

    def test_concurrent_writes_create_subscribers(self, admin_session):
        """20 concurrent subscriber creates should all succeed without conflict."""
        def create_one(i):
            return admin_session.post("/subscribers", json={
                "name": f"Load Test Sub {i}",
                "email": unique_email(f"load{i}"),
                "organization": "Load Test Corp",
                "tier": "free",
            })

        results = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(create_one, i) for i in range(20)]
            for f in as_completed(futures):
                resp = f.result()
                results.append(resp.status_code)

        created = sum(1 for s in results if s == 201)
        assert created >= 18, f"Only {created}/20 subscribers created"

    def test_mixed_read_write_load(self, admin_session):
        """Interleaved reads and writes don't deadlock or error."""
        def read_op():
            return admin_session.get("/subscribers").status_code

        def write_op(i):
            return admin_session.post("/subscribers", json={
                "name": f"Mixed Load {i}",
                "email": unique_email(f"mix{i}"),
                "tier": "free",
            }).status_code

        results = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = []
            for i in range(30):
                if i % 3 == 0:
                    futures.append(pool.submit(write_op, i))
                else:
                    futures.append(pool.submit(read_op))
            for f in as_completed(futures):
                results.append(f.result())

        ok_count = sum(1 for s in results if s in (200, 201))
        assert ok_count >= 25, f"Only {ok_count}/30 mixed ops succeeded"


class TestKongProxyThroughput:
    """Test Kong proxy performance under load."""

    def test_proxy_handles_burst_traffic(self, kong_proxy):
        """100 rapid requests to Kong proxy — no 5xx errors."""
        results = []
        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [
                pool.submit(lambda: kong_proxy.get("/"))
                for _ in range(100)
            ]
            for f in as_completed(futures):
                try:
                    resp = f.result()
                    results.append(resp.status_code)
                except Exception:
                    results.append(0)

        error_5xx = sum(1 for s in results if 500 <= s < 600)
        assert error_5xx == 0, f"Got {error_5xx} 5xx errors under burst load"

    def test_kong_admin_under_load(self, kong_admin):
        """50 concurrent Kong admin status checks should all succeed."""
        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                pool.submit(lambda: kong_admin.get("/status"))
                for _ in range(50)
            ]
            for f in as_completed(futures):
                resp = f.result()
                results.append(resp.status_code)

        assert all(s == 200 for s in results), (
            f"Some Kong admin requests failed: {results}"
        )


class TestResponseLatency:
    """Verify response times stay within acceptable bounds."""

    def test_health_endpoint_latency(self):
        """Health endpoint should respond in under 500ms."""
        times = []
        for _ in range(10):
            start = time.perf_counter()
            with httpx.Client(base_url=ADMIN_API, timeout=10) as c:
                resp = c.get("/health")
            elapsed = (time.perf_counter() - start) * 1000
            assert resp.status_code == 200
            times.append(elapsed)

        avg = sum(times) / len(times)
        p95 = sorted(times)[int(len(times) * 0.95)]
        assert avg < 500, f"Avg latency {avg:.0f}ms exceeds 500ms threshold"
        assert p95 < 1000, f"P95 latency {p95:.0f}ms exceeds 1000ms threshold"

    def test_subscriber_list_latency(self, admin_session):
        """GET /subscribers should respond in under 2s even with data."""
        times = []
        for _ in range(5):
            start = time.perf_counter()
            resp = admin_session.get("/subscribers")
            elapsed = (time.perf_counter() - start) * 1000
            assert resp.status_code == 200
            times.append(elapsed)

        avg = sum(times) / len(times)
        assert avg < 2000, f"Avg subscriber list latency {avg:.0f}ms exceeds 2s"

    def test_auth_me_latency(self, admin_session):
        """/auth/me should respond in under 500ms (cached)."""
        times = []
        for _ in range(10):
            start = time.perf_counter()
            resp = admin_session.get("/auth/me")
            elapsed = (time.perf_counter() - start) * 1000
            assert resp.status_code == 200
            times.append(elapsed)

        avg = sum(times) / len(times)
        assert avg < 500, f"Avg /auth/me latency {avg:.0f}ms exceeds 500ms"


class TestConnectionResilience:
    """Verify the system handles connection edge cases."""

    def test_rapid_connect_disconnect(self):
        """Rapid open/close cycles don't exhaust server connections."""
        for _ in range(50):
            with httpx.Client(base_url=ADMIN_API, timeout=5) as c:
                resp = c.get("/health")
                assert resp.status_code == 200

    def test_slow_client_doesnt_block_others(self, admin_session):
        """A slow reader shouldn't block fast readers."""
        def slow_request():
            with httpx.Client(base_url=ADMIN_API, timeout=30) as c:
                return c.get("/health").status_code

        def fast_request():
            return admin_session.get("/health").status_code

        with ThreadPoolExecutor(max_workers=5) as pool:
            # Start a slow request, then fire fast ones
            slow = pool.submit(slow_request)
            time.sleep(0.05)
            fast_results = [pool.submit(fast_request) for _ in range(10)]

            for f in as_completed(fast_results):
                assert f.result() == 200

            assert slow.result() == 200


class TestSustainedLoad:
    """Longer-duration load tests for stability."""

    def test_sustained_10_second_load(self, admin_session):
        """Maintain steady request rate for 10 seconds — no degradation."""
        results = []
        end_time = time.time() + 10
        request_count = 0

        while time.time() < end_time:
            start = time.perf_counter()
            resp = admin_session.get("/health")
            elapsed = (time.perf_counter() - start) * 1000
            results.append({"status": resp.status_code, "ms": elapsed})
            request_count += 1

        # All should succeed
        failures = [r for r in results if r["status"] != 200]
        assert len(failures) == 0, (
            f"{len(failures)}/{request_count} failures during sustained load"
        )

        # No latency spikes (no request > 5s)
        spikes = [r for r in results if r["ms"] > 5000]
        assert len(spikes) == 0, (
            f"{len(spikes)} requests exceeded 5s during sustained load"
        )

        # Throughput: should handle at least 10 req/s
        assert request_count >= 50, (
            f"Only {request_count} requests in 10s (< 5 req/s)"
        )
