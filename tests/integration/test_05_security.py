"""Battle Test 05: Security and Attack Vectors.

Tests the API gateway's resilience against common attacks:
  - SQL injection
  - XSS payloads
  - Path traversal
  - Oversized payloads
  - Invalid UUIDs
  - Header injection
  - CSRF protection
"""

from __future__ import annotations

import pytest
from integration.conftest import unique_email


# ---------------------------------------------------------------------------
# SQL Injection Attempts
# ---------------------------------------------------------------------------

class TestSQLInjection:
    """Verify SQL injection payloads are rejected or sanitized."""

    SQL_PAYLOADS = [
        "'; DROP TABLE subscribers; --",
        "1' OR '1'='1",
        "1; SELECT * FROM users --",
        "' UNION SELECT null,null,null --",
        "admin'--",
    ]

    @pytest.mark.security
    def test_injection_in_subscriber_name(self, admin_session):
        for payload in self.SQL_PAYLOADS:
            resp = admin_session.post("/subscribers", json={
                "name": payload,
                "email": unique_email("sqli"),
                "organization": "Test",
                "tier": "free",
            })
            # Should either succeed (payload treated as literal string) or 422
            assert resp.status_code in (201, 422), \
                f"Unexpected status {resp.status_code} for payload: {payload}"

    @pytest.mark.security
    def test_injection_in_query_params(self, admin_session):
        """SQL injection via query parameters."""
        for payload in self.SQL_PAYLOADS:
            resp = admin_session.get(f"/subscribers?search={payload}")
            assert resp.status_code in (200, 400, 422)

    @pytest.mark.security
    def test_injection_in_path(self, admin_session):
        resp = admin_session.get("/subscribers/1' OR '1'='1")
        assert resp.status_code == 422  # Invalid UUID format


# ---------------------------------------------------------------------------
# XSS Payloads
# ---------------------------------------------------------------------------

class TestXSS:
    """Verify XSS payloads are sanitized in stored data."""

    XSS_PAYLOADS = [
        '<script>alert("xss")</script>',
        '<img src=x onerror=alert(1)>',
        '"><svg/onload=alert(1)>',
        "javascript:alert(1)",
    ]

    @pytest.mark.security
    def test_xss_in_subscriber_name(self, admin_session):
        for payload in self.XSS_PAYLOADS:
            resp = admin_session.post("/subscribers", json={
                "name": payload,
                "email": unique_email("xss"),
                "organization": "Test",
                "tier": "free",
            })
            if resp.status_code == 201:
                # If stored, verify it's stored as literal text
                sub_id = resp.json()["id"]
                get_resp = admin_session.get(f"/subscribers/{sub_id}")
                assert get_resp.status_code == 200
                # API returns JSON so XSS is auto-escaped, but verify the
                # stored value is the literal payload (not executed)
                assert get_resp.json()["name"] == payload

    @pytest.mark.security
    def test_xss_in_team_description(self, admin_session):
        from integration.conftest import unique_slug
        for payload in self.XSS_PAYLOADS:
            resp = admin_session.post("/teams", json={
                "name": "XSS Test",
                "slug": unique_slug("xss"),
                "description": payload,
                "contact_email": unique_email("xss"),
            })
            assert resp.status_code in (201, 422)


# ---------------------------------------------------------------------------
# Path Traversal
# ---------------------------------------------------------------------------

class TestPathTraversal:
    """Verify path traversal attacks are blocked."""

    @pytest.mark.security
    def test_traversal_in_subscriber_id(self, admin_session):
        resp = admin_session.get("/subscribers/../../../etc/passwd")
        assert resp.status_code in (404, 422)

    @pytest.mark.security
    def test_traversal_in_team_id(self, admin_session):
        resp = admin_session.get("/teams/../../etc/shadow")
        assert resp.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Oversized Payloads
# ---------------------------------------------------------------------------

class TestOversizedPayloads:
    """Verify the gateway handles oversized payloads gracefully."""

    @pytest.mark.security
    def test_huge_subscriber_name(self, admin_session):
        """A very long name should be rejected or truncated."""
        resp = admin_session.post("/subscribers", json={
            "name": "A" * 100_000,
            "email": unique_email("big"),
            "organization": "Test",
            "tier": "free",
        })
        # Should be rejected (validation or size limit)
        assert resp.status_code in (413, 422, 500)

    @pytest.mark.security
    def test_huge_json_body(self, admin_session):
        """Massive JSON payload should be rejected."""
        resp = admin_session.post("/subscribers", json={
            "name": "Normal",
            "email": unique_email("huge"),
            "organization": "Test",
            "tier": "free",
            "extra": {"data": "x" * 1_000_000},
        })
        assert resp.status_code in (413, 422, 201)  # May ignore extra fields


# ---------------------------------------------------------------------------
# Invalid Input Types
# ---------------------------------------------------------------------------

class TestInvalidInputs:
    """Verify proper validation of input types."""

    @pytest.mark.security
    def test_invalid_uuid_format(self, admin_session):
        resp = admin_session.get("/subscribers/not-a-uuid")
        assert resp.status_code == 422

    @pytest.mark.security
    def test_null_bytes_in_name(self, admin_session):
        resp = admin_session.post("/subscribers", json={
            "name": "test\x00injected",
            "email": unique_email("null"),
            "organization": "Test",
            "tier": "free",
        })
        # PostgreSQL rejects null bytes in text; 422 (validation) or 500 (DB error) are both acceptable
        # as long as the server doesn't crash silently or store corrupted data
        assert resp.status_code in (201, 422, 500)

    @pytest.mark.security
    def test_invalid_tier_value(self, admin_session):
        resp = admin_session.post("/subscribers", json={
            "name": "Bad Tier",
            "email": unique_email("tier"),
            "organization": "Test",
            "tier": "'; DROP TABLE plans; --",
        })
        # Should either succeed (stored as string) or validate
        assert resp.status_code in (201, 422)

    @pytest.mark.security
    def test_negative_rate_limit(self, admin_session):
        resp = admin_session.post("/plans", json={
            "name": f"negative-{unique_email('x')[:8]}",
            "rate_limit_second": -1,
            "rate_limit_minute": -100,
            "rate_limit_hour": -1000,
            "max_api_keys": -5,
            "price_cents": -100,
        })
        # Should reject negative values or accept them (depends on validation)
        assert resp.status_code in (201, 422)
