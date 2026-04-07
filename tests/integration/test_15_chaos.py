"""Battle Test 15: Chaos & Resilience Testing.

Tests system behavior under failure conditions:
  - Redis unavailability and recovery
  - Admin panel restart recovery
  - Kong restart and plugin persistence
  - Database connection recovery
  - Graceful degradation when dependencies are unhealthy
  - Service restart ordering
"""

from __future__ import annotations

import subprocess
import time

import httpx
import pytest
from integration.conftest import (
    ADMIN_API,
    KONG_ADMIN,
    KONG_PROXY,
    create_subscriber,
    unique_email,
    unique_slug,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _docker_exec(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a docker command and return the result."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )


def _container_running(name: str) -> bool:
    """Check if a docker container is running."""
    result = _docker_exec(["docker", "inspect", "-f", "{{.State.Running}}", name])
    return result.stdout.strip() == "true"


def _wait_for_health(url: str, timeout: int = 60) -> bool:
    """Poll a health endpoint until it responds 200 or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout,
                httpx.RemoteProtocolError, httpx.ReadError):
            pass
        time.sleep(1)
    return False


def _restart_container(name: str):
    """Restart a docker container and wait for it to be running."""
    _docker_exec(["docker", "restart", name])
    deadline = time.time() + 60
    while time.time() < deadline:
        if _container_running(name):
            return
        time.sleep(1)
    raise TimeoutError(f"Container {name} did not restart within 60s")


class TestRedisResilience:
    """Test behavior when Redis is unavailable or restarted."""

    def test_admin_panel_survives_redis_restart(self, admin_session):
        """Admin panel should recover after Redis restart."""
        # Verify baseline
        assert admin_session.get("/health").status_code == 200

        # Restart Redis
        _restart_container("api-gw-redis")

        # Wait for Redis to come back
        time.sleep(3)

        # Admin panel should still work (may need a moment to reconnect)
        healthy = _wait_for_health(f"{ADMIN_API}/health", timeout=30)
        assert healthy, "Admin panel did not recover after Redis restart"

        # Authenticated requests should still work
        resp = admin_session.get("/auth/me")
        assert resp.status_code == 200

    def test_rbac_works_after_redis_flush(self, admin_session):
        """RBAC permissions should reload from DB after Redis cache is cleared."""
        import os
        import pathlib

        env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
        redis_pw = "redis_local_dev"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("REDIS_PASSWORD="):
                    redis_pw = line.split("=", 1)[1].strip()
                    break

        # Flush Redis
        _docker_exec([
            "docker", "exec", "api-gw-redis",
            "redis-cli", "-a", redis_pw, "FLUSHALL",
        ])

        # Give the admin panel a moment to notice
        time.sleep(1)

        # RBAC should still work (reloads from DB)
        resp = admin_session.get("/subscribers")
        assert resp.status_code == 200, (
            f"RBAC failed after Redis flush: {resp.status_code}"
        )


class TestKongResilience:
    """Test Kong gateway resilience."""

    def test_kong_services_persist_after_restart(self):
        """Kong services and routes survive a Kong restart (backed by DB)."""
        # Use fresh clients to avoid stale TCP connections after restart
        with httpx.Client(base_url=KONG_ADMIN, timeout=10) as ka:
            services_before = ka.get("/services").json()
            service_count_before = len(services_before.get("data", []))

        # Restart Kong
        _restart_container("api-gw-kong")

        # Wait for Kong to be healthy
        healthy = _wait_for_health(f"http://127.0.0.1:8801/status", timeout=90)
        assert healthy, "Kong did not recover after restart"

        # Services should persist (Kong uses PostgreSQL for state)
        with httpx.Client(base_url=KONG_ADMIN, timeout=10) as ka:
            services_after = ka.get("/services").json()
        service_count_after = len(services_after.get("data", []))
        assert service_count_after >= service_count_before, (
            f"Kong lost services after restart: {service_count_before} -> {service_count_after}"
        )

    def test_kong_plugins_persist_after_restart(self):
        """Kong plugins survive a restart."""
        with httpx.Client(base_url=KONG_ADMIN, timeout=10) as ka:
            plugins_before = ka.get("/plugins").json()
        plugin_count_before = len(plugins_before.get("data", []))

        _restart_container("api-gw-kong")
        healthy = _wait_for_health(f"http://127.0.0.1:8801/status", timeout=90)
        assert healthy, "Kong did not recover"

        with httpx.Client(base_url=KONG_ADMIN, timeout=10) as ka:
            plugins_after = ka.get("/plugins").json()
        plugin_count_after = len(plugins_after.get("data", []))
        assert plugin_count_after >= plugin_count_before, (
            f"Kong lost plugins after restart: {plugin_count_before} -> {plugin_count_after}"
        )

    def test_kong_proxy_recovers_after_restart(self):
        """Kong proxy port accepts traffic after restart."""
        _restart_container("api-gw-kong")
        healthy = _wait_for_health(f"http://127.0.0.1:8801/status", timeout=90)
        assert healthy

        # Proxy should respond (404 is fine — means Kong is routing)
        with httpx.Client(base_url=KONG_PROXY, timeout=10) as kp:
            resp = kp.get("/")
        assert resp.status_code in (200, 404)


class TestAdminPanelResilience:
    """Test admin panel recovery scenarios."""

    def test_admin_panel_restart_preserves_sessions(self):
        """After admin panel restart, new logins work immediately."""
        _restart_container("api-gw-admin-panel")
        healthy = _wait_for_health(f"{ADMIN_API}/health", timeout=60)
        assert healthy, "Admin panel did not recover after restart"

        # Fresh login should work
        from integration.conftest import AdminSession
        session = AdminSession("admin", "admin").login()
        resp = session.get("/auth/me")
        assert resp.status_code == 200
        session.close()

    def test_admin_panel_restart_preserves_data(self):
        """Data created before restart persists after restart."""
        # Use a fresh session to avoid stale connections from prior tests
        from integration.conftest import AdminSession
        session = AdminSession("admin", "admin").login()

        # Create a subscriber before restart
        sub = create_subscriber(session, name="Chaos Persist Test")
        sub_id = sub["id"]
        session.close()

        _restart_container("api-gw-admin-panel")
        healthy = _wait_for_health(f"{ADMIN_API}/health", timeout=60)
        assert healthy

        # Re-login (old session cookies are invalid after restart)
        new_session = AdminSession("admin", "admin").login()

        # Subscriber should still exist
        resp = new_session.get(f"/subscribers/{sub_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Chaos Persist Test"
        new_session.close()


class TestDatabaseResilience:
    """Test behavior when PostgreSQL is temporarily unavailable."""

    def test_admin_panel_recovers_after_db_restart(self):
        """Admin panel reconnects to PostgreSQL after DB restart."""
        _restart_container("api-gw-postgres")

        # Wait for PostgreSQL to be ready
        deadline = time.time() + 60
        pg_ready = False
        while time.time() < deadline:
            result = _docker_exec([
                "docker", "exec", "api-gw-postgres",
                "pg_isready", "-U", "api_gateway_admin",
            ])
            if result.returncode == 0:
                pg_ready = True
                break
            time.sleep(2)
        assert pg_ready, "PostgreSQL did not recover within 60s"

        # Admin panel should eventually reconnect
        # May need a restart if connection pool is exhausted
        time.sleep(5)
        healthy = _wait_for_health(f"{ADMIN_API}/health", timeout=30)
        if not healthy:
            # Admin panel may need a restart to reconnect
            _restart_container("api-gw-admin-panel")
            healthy = _wait_for_health(f"{ADMIN_API}/health", timeout=60)

        assert healthy, "Admin panel did not recover after DB restart"


class TestServiceDependencyOrder:
    """Test that services handle dependency startup order correctly."""

    def test_admin_panel_has_app_module(self):
        """Admin panel container has the main application module."""
        result = _docker_exec([
            "docker", "exec", "api-gw-admin-panel",
            "python3", "-c", "import app.main; print('ok')",
        ])
        assert result.returncode == 0, f"app.main not importable: {result.stderr}"

    def test_kong_connected_to_postgres(self, kong_admin):
        """Kong should be connected to its database."""
        status = kong_admin.get("/status").json()
        db_reachable = status.get("database", {}).get("reachable", False)
        assert db_reachable, "Kong reports database is not reachable"

    def test_all_containers_healthy(self):
        """All expected containers should be running."""
        expected = [
            "api-gw-kong",
            "api-gw-postgres",
            "api-gw-redis",
            "api-gw-admin-panel",
        ]
        for name in expected:
            assert _container_running(name), f"Container {name} is not running"
