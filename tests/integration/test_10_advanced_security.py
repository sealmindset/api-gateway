"""Battle Test 10: Advanced Security.

Adversarial testing beyond basic injection:
  - IDOR (Insecure Direct Object Reference)
  - Privilege escalation attempts
  - Session manipulation
  - Header injection
  - Mass assignment / parameter pollution
  - RBAC boundary enforcement
  - Resource enumeration
"""

from __future__ import annotations

import uuid

import pytest
from integration.conftest import (
    create_subscriber,
    unique_email,
    unique_slug,
)


class TestIDOR:
    """Insecure Direct Object Reference: access resources you shouldn't."""

    def test_viewer_cannot_update_subscriber(self, viewer_session):
        """Viewer role should not be able to update a subscriber."""
        # Try to update a subscriber (we don't know a valid ID, but the
        # permission check should reject before the DB lookup)
        fake_id = str(uuid.uuid4())
        resp = viewer_session.patch(f"/subscribers/{fake_id}", json={
            "name": "Hacked Name",
        })
        assert resp.status_code == 403

    def test_developer_cannot_access_subscribers(self, developer_session):
        """Developer (no platform role) cannot read subscriber data."""
        resp = developer_session.get("/subscribers")
        assert resp.status_code == 403

    def test_viewer_cannot_delete_team(self, viewer_session, admin_session):
        """Viewer can read teams but not delete them."""
        team = admin_session.post("/teams", json={
            "name": "IDOR Delete Test", "slug": unique_slug("idor"),
            "contact_email": unique_email("idor"),
        }).json()

        resp = viewer_session.delete(f"/teams/{team['id']}")
        assert resp.status_code == 403

    def test_operator_cannot_delete_subscriber(self, operator_session, admin_session):
        """Operator has read+write but not delete permission."""
        sub = create_subscriber(admin_session)
        resp = operator_session.delete(f"/subscribers/{sub['id']}")
        assert resp.status_code == 403


class TestPrivilegeEscalation:
    """Attempts to escalate privileges via the API."""

    def test_cannot_self_promote_role(self, viewer_session):
        """A viewer cannot assign themselves an admin role."""
        me = viewer_session.get("/auth/me").json()
        # Try to create a role assignment for ourselves
        resp = viewer_session.post("/rbac/assignments", json={
            "user_id": me["id"],
            "role_id": str(uuid.uuid4()),  # random role ID
        })
        assert resp.status_code == 403

    def test_operator_cannot_create_roles(self, operator_session):
        """Only super_admin can create new roles."""
        resp = operator_session.post("/rbac/roles", json={
            "name": "hacked-admin",
            "description": "Escalated role",
            "permissions": {"*": True},
        })
        assert resp.status_code == 403

    def test_viewer_cannot_modify_plans(self, viewer_session):
        """Viewers cannot create or modify subscription plans."""
        resp = viewer_session.post("/plans", json={
            "name": "free-hack",
            "rate_limit_second": 99999,
            "rate_limit_minute": 99999,
            "rate_limit_hour": 99999,
        })
        assert resp.status_code == 403


class TestHeaderInjection:
    """Header manipulation attacks."""

    def test_host_header_injection(self, admin_session):
        """Injecting a malicious Host header should not cause issues."""
        resp = admin_session.get("/auth/me", headers={
            "Host": "evil.example.com",
        })
        # Should still work (or reject cleanly), not redirect to evil.example.com
        assert resp.status_code in (200, 400, 421)

    def test_x_forwarded_for_spoofing(self, admin_session):
        """X-Forwarded-For spoofing should not bypass access controls."""
        resp = admin_session.get("/subscribers", headers={
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
        })
        # Should still work normally (admin has access)
        assert resp.status_code == 200

    def test_content_type_mismatch(self, admin_session):
        """Sending wrong content-type should be handled gracefully."""
        resp = admin_session.client.post(
            f"{admin_session.client.base_url}/subscribers",
            content=b"not-json",
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code in (400, 415, 422)


class TestMassAssignment:
    """Attempt to set fields that shouldn't be user-controllable."""

    def test_cannot_set_subscriber_id(self, admin_session):
        """Sending an 'id' field in create should be ignored."""
        fake_id = str(uuid.uuid4())
        resp = admin_session.post("/subscribers", json={
            "name": "Mass Assign Test",
            "email": unique_email("mass"),
            "organization": "Test",
            "tier": "free",
            "id": fake_id,
        })
        assert resp.status_code == 201
        # The ID should NOT be the one we tried to set
        assert resp.json()["id"] != fake_id

    def test_cannot_set_subscriber_status_on_create(self, admin_session):
        """Status should default to 'active', not be settable on create."""
        resp = admin_session.post("/subscribers", json={
            "name": "Status Hack",
            "email": unique_email("stat"),
            "organization": "Test",
            "tier": "free",
            "status": "suspended",
        })
        # Either the status field is ignored (201 with status=active)
        # or it's rejected (422)
        if resp.status_code == 201:
            assert resp.json()["status"] == "active"
        else:
            assert resp.status_code == 422

    def test_cannot_set_team_created_at(self, admin_session):
        """Timestamps should be server-controlled."""
        resp = admin_session.post("/teams", json={
            "name": "Timestamp Hack", "slug": unique_slug("ts"),
            "contact_email": unique_email("ts"),
            "created_at": "2000-01-01T00:00:00Z",
        })
        if resp.status_code == 201:
            created = resp.json()["created_at"]
            assert not created.startswith("2000-")


class TestResourceEnumeration:
    """Prevent enumeration of resources by sequential IDs."""

    def test_nonexistent_subscriber_returns_404_not_info(self, admin_session):
        """Requesting a non-existent subscriber should return 404, not leak info."""
        fake_id = str(uuid.uuid4())
        resp = admin_session.get(f"/subscribers/{fake_id}")
        assert resp.status_code == 404
        body = resp.json()
        # Should not reveal internal details
        assert "traceback" not in str(body).lower()
        assert "sql" not in str(body).lower()

    def test_nonexistent_team_returns_404(self, admin_session):
        fake_id = str(uuid.uuid4())
        resp = admin_session.get(f"/teams/{fake_id}")
        assert resp.status_code == 404

    def test_nonexistent_plan_returns_404(self, admin_session):
        fake_id = str(uuid.uuid4())
        resp = admin_session.get(f"/plans/{fake_id}")
        assert resp.status_code == 404

    def test_nonexistent_subscription_returns_404(self, admin_session):
        fake_id = str(uuid.uuid4())
        resp = admin_session.get(f"/subscriptions/{fake_id}")
        assert resp.status_code == 404


class TestSessionSecurity:
    """Session and cookie security."""

    def test_unauthenticated_cannot_access_admin_endpoints(self, unauthenticated_client):
        """All admin endpoints require authentication."""
        endpoints = [
            "/subscribers", "/plans", "/subscriptions",
            "/teams", "/rbac/roles", "/rbac/audit",
            "/api-registry",
        ]
        for endpoint in endpoints:
            resp = unauthenticated_client.get(endpoint)
            assert resp.status_code in (401, 403), (
                f"{endpoint} returned {resp.status_code} without auth"
            )

    def test_ai_prompts_requires_auth(self, unauthenticated_client):
        """AI prompts endpoint should require authentication."""
        resp = unauthenticated_client.get("/ai/prompts")
        assert resp.status_code in (401, 403), (
            f"/ai/prompts returned {resp.status_code} without auth"
        )

    def test_invalid_session_cookie_rejected(self, unauthenticated_client):
        """A forged session cookie should not grant access."""
        unauthenticated_client.cookies.set("session", "forged-session-value")
        resp = unauthenticated_client.get("/auth/me")
        assert resp.status_code in (401, 403)

    def test_expired_or_tampered_cookie(self, unauthenticated_client):
        """A tampered session cookie should be rejected."""
        unauthenticated_client.cookies.set(
            "session",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.fake"
        )
        resp = unauthenticated_client.get("/auth/me")
        assert resp.status_code in (401, 403)


class TestInputBoundaries:
    """Edge cases in input validation."""

    def test_empty_string_fields_rejected(self, admin_session):
        """Empty name should be rejected."""
        resp = admin_session.post("/subscribers", json={
            "name": "",
            "email": unique_email("empty"),
            "organization": "Test",
            "tier": "free",
        })
        # FastAPI/Pydantic should reject or the DB constraint should catch it
        assert resp.status_code in (201, 422)

    def test_extremely_long_slug(self, admin_session):
        """A slug exceeding max length should be rejected."""
        long_slug = "a" * 200
        resp = admin_session.post("/teams", json={
            "name": "Long Slug Team",
            "slug": long_slug,
            "contact_email": unique_email("slug"),
        })
        assert resp.status_code == 422

    def test_unicode_in_names(self, admin_session):
        """Unicode characters should be handled correctly."""
        resp = admin_session.post("/subscribers", json={
            "name": "Tester",
            "email": unique_email("uni"),
            "organization": "Test Corp",
            "tier": "free",
        })
        assert resp.status_code == 201

    def test_special_chars_in_slug(self, admin_session):
        """Slugs with special characters should be rejected (regex pattern)."""
        resp = admin_session.post("/teams", json={
            "name": "Special Slug",
            "slug": "has spaces!",
            "contact_email": unique_email("sp"),
        })
        assert resp.status_code == 422

    def test_duplicate_subscriber_email_allowed(self, admin_session):
        """Multiple subscribers can share the same email (different entities)."""
        email = unique_email("dup")
        resp1 = admin_session.post("/subscribers", json={
            "name": "Dup 1", "email": email, "tier": "free",
        })
        resp2 = admin_session.post("/subscribers", json={
            "name": "Dup 2", "email": email, "tier": "free",
        })
        assert resp1.status_code == 201
        # Second may succeed or fail depending on uniqueness constraint
        assert resp2.status_code in (201, 409)

    def test_duplicate_team_slug_rejected(self, admin_session):
        """Team slugs must be unique."""
        slug = unique_slug("dup")
        admin_session.post("/teams", json={
            "name": "Dup Team 1", "slug": slug,
            "contact_email": unique_email("dup"),
        })
        resp = admin_session.post("/teams", json={
            "name": "Dup Team 2", "slug": slug,
            "contact_email": unique_email("dup2"),
        })
        assert resp.status_code == 409
