"""
Shared fixtures for API Gateway integration / battle tests.

These tests run against the LIVE Docker stack:
  - Admin Panel API: http://localhost:8880
  - Kong Proxy:      http://localhost:8800
  - Kong Admin:      http://127.0.0.1:8801
  - Mock OIDC:       http://localhost:8180

Prerequisite: docker compose up -d  (all services healthy)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import httpx
import pytest

# ---------------------------------------------------------------------------
# Service URLs (match docker-compose port mappings on this machine)
# ---------------------------------------------------------------------------

ADMIN_API = "http://localhost:8880"
KONG_PROXY = "http://localhost:8800"
KONG_ADMIN = "http://127.0.0.1:8801"
MOCK_OIDC = "http://localhost:8180"

# Internal docker hostname -> external host mapping
DOCKER_TO_HOST = {
    "mock-oidc:8080": "localhost:8180",
    "admin-panel:8080": "localhost:8880",
}

OIDC_TOKEN_URL = f"{MOCK_OIDC}/connect/token"
OIDC_USERINFO_URL = f"{MOCK_OIDC}/connect/userinfo"

CLIENT_ID = "api-gateway-local"
CLIENT_SECRET = "mock-client-secret"

# Mock OIDC test users
USERS = {
    "admin": {"username": "admin", "password": "admin", "oid": "admin-oid-001"},
    "operator": {"username": "operator", "password": "operator", "oid": "operator-oid-002"},
    "teamlead": {"username": "teamlead", "password": "teamlead", "oid": "teamlead-oid-003"},
    "developer": {"username": "developer", "password": "developer", "oid": "developer-oid-004"},
    "viewer": {"username": "viewer", "password": "viewer", "oid": "viewer-oid-005"},
    "newuser": {"username": "newuser", "password": "newuser", "oid": "newuser-oid-006"},
}


# ---------------------------------------------------------------------------
# URL rewriting: docker internal hostnames -> localhost
# ---------------------------------------------------------------------------

def rewrite_url(url: str) -> str:
    """Replace docker-internal hostnames with localhost equivalents."""
    for docker_host, local_host in DOCKER_TO_HOST.items():
        url = url.replace(f"http://{docker_host}", f"http://{local_host}")
    return url


# ---------------------------------------------------------------------------
# Admin API session — simulates a logged-in user via OIDC redirect chain
# ---------------------------------------------------------------------------

class AdminSession:
    """HTTP client pre-authenticated against the Admin Panel via OIDC flow."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.client = httpx.Client(base_url=ADMIN_API, timeout=30)
        self._authenticated = False

    def login(self) -> "AdminSession":
        """Walk through the full OIDC authorization code flow."""
        # Use a session client that stores cookies across requests
        c = httpx.Client(timeout=30, follow_redirects=False)

        # Step 1: GET /auth/login on admin panel -> redirect to OIDC authorize
        resp = c.get(f"{ADMIN_API}/auth/login")
        assert resp.status_code in (302, 307), f"/auth/login returned {resp.status_code}"
        authorize_url = rewrite_url(resp.headers["location"])

        # Step 2: GET OIDC authorize endpoint -> login page
        resp = c.get(authorize_url)

        if resp.status_code in (302, 307):
            # Redirect — may be to login page or directly to callback
            redirect_url = resp.headers["location"]
            if "/Account/Login" in redirect_url:
                # Need to go through login page
                login_page_url = redirect_url if redirect_url.startswith("http") else f"{MOCK_OIDC}{redirect_url}"
                resp = c.get(login_page_url)
                assert resp.status_code == 200, f"Login page returned {resp.status_code}"
                # Fall through to 200 handler below
            else:
                callback_url = rewrite_url(redirect_url)

        if resp.status_code == 200:
            # Login form — POST credentials
            # The oidc-server-mock uses Input.* field names
            body = resp.text
            return_url_match = re.search(
                r'name="Input\.ReturnUrl"\s+value="([^"]*)"', body
            ) or re.search(r'name="ReturnUrl"\s+value="([^"]*)"', body)
            csrf_match = re.search(
                r'name="__RequestVerificationToken"[^>]+value="([^"]*)"', body
            )
            return_url = return_url_match.group(1) if return_url_match else ""
            csrf_token = csrf_match.group(1) if csrf_match else ""

            # Unescape HTML entities in return URL
            return_url = return_url.replace("&amp;", "&")

            login_resp = c.post(
                f"{MOCK_OIDC}/Account/Login",
                data={
                    "Input.Username": self.username,
                    "Input.Password": self.password,
                    "Input.ReturnUrl": return_url,
                    "__RequestVerificationToken": csrf_token,
                    "Input.Button": "login",
                },
                follow_redirects=False,
            )
            assert login_resp.status_code in (302, 307), (
                f"Login POST returned {login_resp.status_code}"
            )

            # Follow redirects from login -> authorize -> callback
            next_url = login_resp.headers["location"]
            if next_url.startswith("/"):
                next_url = f"{MOCK_OIDC}{next_url}"
            else:
                next_url = rewrite_url(next_url)

            resp = c.get(next_url, follow_redirects=False)
            assert resp.status_code in (302, 307), (
                f"Post-login redirect returned {resp.status_code}"
            )
            callback_url = rewrite_url(resp.headers["location"])
        else:
            raise RuntimeError(f"OIDC authorize returned {resp.status_code}")

        # Step 3: Follow callback URL back to admin panel
        # This sets the session cookie
        resp = c.get(callback_url, follow_redirects=False)
        assert resp.status_code in (200, 302, 307), (
            f"Callback returned {resp.status_code}: {resp.text[:200]}"
        )

        # Transfer cookies from auth flow client to our session client
        # Use the cookie jar directly to avoid CookieConflict with duplicate names
        for cookie in c.cookies.jar:
            self.client.cookies.set(
                cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
            )

        # Verify we're authenticated
        me_resp = self.client.get("/auth/me")
        if me_resp.status_code == 200:
            self._authenticated = True
            self._user_info = me_resp.json()
        else:
            raise RuntimeError(
                f"/auth/me returned {me_resp.status_code} after login. "
                f"Cookies: {dict(self.client.cookies)}"
            )

        c.close()
        return self

    @property
    def user_info(self) -> dict:
        return self._user_info

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.client.get(path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.client.post(path, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self.client.patch(path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self.client.put(path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self.client.delete(path, **kwargs)

    def close(self):
        self.client.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def admin_session() -> AdminSession:
    """Logged-in session as the admin user (super_admin)."""
    s = AdminSession("admin", "admin").login()
    yield s
    s.close()


@pytest.fixture(scope="session")
def operator_session() -> AdminSession:
    """Logged-in session as the operator user."""
    s = AdminSession("operator", "operator").login()
    yield s
    s.close()


@pytest.fixture(scope="session")
def viewer_session() -> AdminSession:
    """Logged-in session as the viewer user (read-only)."""
    s = AdminSession("viewer", "viewer").login()
    yield s
    s.close()


@pytest.fixture(scope="session")
def developer_session() -> AdminSession:
    """Logged-in session as the developer user (no platform roles)."""
    s = AdminSession("developer", "developer").login()
    yield s
    s.close()


@pytest.fixture(scope="session")
def newuser_session() -> AdminSession:
    """Logged-in session as the newuser (auto-provisioned, no roles)."""
    s = AdminSession("newuser", "newuser").login()
    yield s
    s.close()


@pytest.fixture(scope="session")
def kong_admin() -> httpx.Client:
    """HTTP client for Kong Admin API."""
    client = httpx.Client(base_url=KONG_ADMIN, timeout=15)
    yield client
    client.close()


@pytest.fixture(scope="session")
def kong_proxy() -> httpx.Client:
    """HTTP client for Kong Proxy."""
    client = httpx.Client(base_url=KONG_PROXY, timeout=15)
    yield client
    client.close()


@pytest.fixture(scope="session", autouse=True)
def _seed_role_assignments(admin_session, operator_session, viewer_session):
    """Assign platform roles to test users via direct DB SQL.

    On a fresh DB, users are auto-provisioned on first OIDC login but have
    no role assignments.  This fixture runs INSERT ... ON CONFLICT DO NOTHING
    so it is safe to re-run on an existing DB.
    """
    import subprocess

    # Map: username email -> role name
    assignments = {
        admin_session.user_info["email"]: "super_admin",
        operator_session.user_info["email"]: "operator",
        viewer_session.user_info["email"]: "viewer",
    }
    for email, role_name in assignments.items():
        sql = (
            f"INSERT INTO user_roles (id, user_id, role_id, assigned_at) "
            f"SELECT gen_random_uuid(), u.id, r.id, NOW() "
            f"FROM users u, roles r "
            f"WHERE u.email = '{email}' AND r.name = '{role_name}' "
            f"ON CONFLICT DO NOTHING;"
        )
        subprocess.run(
            [
                "docker", "exec", "api-gw-postgres",
                "psql", "-U", "api_gateway_admin", "-d", "api_gateway_admin",
                "-c", sql,
            ],
            capture_output=True,
            text=True,
        )

    # Flush the Redis permission cache so the RBAC middleware picks up the
    # newly-inserted roles instead of serving stale "no permissions" entries.
    # Read password from the project .env file (same file docker compose uses).
    import os, pathlib
    env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
    redis_pw = "redis_local_dev"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REDIS_PASSWORD="):
                redis_pw = line.split("=", 1)[1].strip()
                break
    subprocess.run(
        [
            "docker", "exec", "api-gw-redis",
            "redis-cli", "-a", redis_pw, "FLUSHALL",
        ],
        capture_output=True,
        text=True,
    )

    yield


@pytest.fixture(scope="session")
def unauthenticated_client() -> httpx.Client:
    """HTTP client with NO auth for testing 401 responses."""
    client = httpx.Client(base_url=ADMIN_API, timeout=15)
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Helper functions for creating test data
# ---------------------------------------------------------------------------

def unique_email(prefix: str = "test") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@battletest.dev"


def unique_slug(prefix: str = "bt") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_subscriber(session: AdminSession, tier: str = "free", **overrides) -> dict:
    """Create a subscriber and return the response dict."""
    payload = {
        "name": f"Battle Test {tier.title()} Subscriber",
        "email": unique_email(f"sub-{tier}"),
        "organization": "Battle Test Corp",
        "tier": tier,
    }
    payload.update(overrides)
    resp = session.post("/subscribers", json=payload)
    assert resp.status_code == 201, f"Create subscriber failed: {resp.status_code} {resp.text}"
    return resp.json()


def create_plan(session: AdminSession, name: str, **overrides) -> dict:
    """Create a subscription plan and return the response dict."""
    payload = {
        "name": name,
        "description": f"Battle test plan: {name}",
        "rate_limit_second": 1,
        "rate_limit_minute": 30,
        "rate_limit_hour": 500,
        "max_api_keys": 5,
        "price_cents": 0,
        "is_active": True,
    }
    payload.update(overrides)
    resp = session.post("/plans", json=payload)
    assert resp.status_code == 201, f"Create plan failed: {resp.status_code} {resp.text}"
    return resp.json()


def create_subscription(session: AdminSession, subscriber_id: str, plan_id: str, **overrides) -> dict:
    """Create a subscription and return the response dict."""
    payload = {
        "subscriber_id": subscriber_id,
        "plan_id": plan_id,
        "starts_at": now_iso(),
    }
    payload.update(overrides)
    resp = session.post("/subscriptions", json=payload)
    assert resp.status_code == 201, f"Create subscription failed: {resp.status_code} {resp.text}"
    return resp.json()


def create_api_key(session: AdminSession, subscriber_id: str, name: str = "battle-key") -> dict:
    """Create an API key and return the response dict (includes raw_key)."""
    resp = session.post(
        f"/subscribers/{subscriber_id}/keys",
        json={"name": name},
    )
    assert resp.status_code == 201, f"Create API key failed: {resp.status_code} {resp.text}"
    return resp.json()
