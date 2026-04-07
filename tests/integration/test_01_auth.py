"""Battle Test 01: OIDC Authentication Flow.

Tests the complete Entra ID / OIDC authentication lifecycle:
  - Login redirect chain
  - Session cookie persistence
  - /auth/me endpoint
  - Logout
  - Unauthenticated access rejection
  - User auto-provisioning
"""

from __future__ import annotations

import pytest
from integration.conftest import AdminSession, ADMIN_API


class TestOIDCLogin:
    """Verify the full OIDC authorization code flow."""

    def test_admin_login_succeeds(self, admin_session):
        """Admin user can log in and has a valid session."""
        info = admin_session.user_info
        assert info["email"] == "admin@sleepnumber.dev"
        assert info["entra_oid"] == "admin-oid-001"
        assert info["name"] == "Platform Admin"
        assert info["id"]  # UUID should be set

    def test_operator_login_succeeds(self, operator_session):
        info = operator_session.user_info
        assert info["email"] == "operator@sleepnumber.dev"
        assert info["entra_oid"] == "operator-oid-002"

    def test_viewer_login_succeeds(self, viewer_session):
        info = viewer_session.user_info
        assert info["email"] == "viewer@sleepnumber.dev"
        assert info["entra_oid"] == "viewer-oid-005"

    def test_developer_login_succeeds(self, developer_session):
        """Developer user (no roles) can still log in."""
        info = developer_session.user_info
        assert info["email"] == "developer@sleepnumber.dev"

    def test_newuser_auto_provisioned(self, newuser_session):
        """New user is auto-provisioned on first login."""
        info = newuser_session.user_info
        assert info["email"] == "newuser@sleepnumber.dev"
        assert info["assigned_roles"] == []  # No roles assigned


class TestAuthMe:
    """Test the /auth/me endpoint."""

    def test_me_returns_user_info(self, admin_session):
        resp = admin_session.get("/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@sleepnumber.dev"
        assert "id" in data
        assert "created_at" in data
        assert "last_login" in data

    def test_me_includes_assigned_roles(self, admin_session):
        resp = admin_session.get("/auth/me")
        data = resp.json()
        role_names = [r["name"] for r in data.get("assigned_roles", [])]
        assert "super_admin" in role_names


class TestUnauthenticated:
    """Verify that unauthenticated requests are rejected."""

    def test_me_returns_401(self, unauthenticated_client):
        resp = unauthenticated_client.get("/auth/me")
        assert resp.status_code == 401

    def test_subscribers_returns_401(self, unauthenticated_client):
        resp = unauthenticated_client.get("/subscribers")
        assert resp.status_code == 401

    def test_plans_returns_401(self, unauthenticated_client):
        resp = unauthenticated_client.get("/plans")
        assert resp.status_code == 401

    def test_teams_returns_401(self, unauthenticated_client):
        resp = unauthenticated_client.get("/teams")
        assert resp.status_code == 401

    def test_rbac_returns_401(self, unauthenticated_client):
        resp = unauthenticated_client.get("/rbac/roles")
        assert resp.status_code == 401


class TestLogout:
    """Test the logout flow."""

    def test_logout_clears_session(self):
        """After logout, /auth/me should return 401."""
        s = AdminSession("admin", "admin").login()
        # Verify logged in
        assert s.get("/auth/me").status_code == 200
        # Logout
        resp = s.post("/auth/logout")
        assert resp.status_code == 200
        # Session should be cleared
        resp = s.get("/auth/me")
        assert resp.status_code == 401
        s.close()
