"""Battle Test 02: RBAC Enforcement.

Tests role-based access control across all permission levels:
  - super_admin: full access
  - operator: read/write subscribers, subscriptions, keys, teams, registry
  - viewer: read-only access
  - developer (no roles): denied everything
  - newuser (no roles): denied everything
"""

from __future__ import annotations

import pytest
from integration.conftest import unique_email


class TestSuperAdminAccess:
    """super_admin should have full access to everything."""

    def test_can_read_subscribers(self, admin_session):
        assert admin_session.get("/subscribers").status_code == 200

    def test_can_create_subscriber(self, admin_session):
        resp = admin_session.post("/subscribers", json={
            "name": "RBAC Test Sub", "email": unique_email("rbac"),
            "organization": "Test", "tier": "free",
        })
        assert resp.status_code == 201

    def test_can_read_plans(self, admin_session):
        assert admin_session.get("/plans").status_code == 200

    def test_can_create_plan(self, admin_session):
        resp = admin_session.post("/plans", json={
            "name": f"rbac-test-plan-{unique_email('x')[:8]}",
            "description": "RBAC test", "rate_limit_second": 1,
            "rate_limit_minute": 10, "rate_limit_hour": 100,
            "max_api_keys": 1, "price_cents": 0, "is_active": True,
        })
        assert resp.status_code == 201

    def test_can_read_roles(self, admin_session):
        resp = admin_session.get("/rbac/roles")
        assert resp.status_code == 200
        roles = resp.json()
        assert len(roles) >= 4  # super_admin, admin, operator, viewer

    def test_can_read_users(self, admin_session):
        resp = admin_session.get("/rbac/users")
        assert resp.status_code == 200

    def test_can_read_teams(self, admin_session):
        assert admin_session.get("/teams").status_code == 200

    def test_can_read_gateway(self, admin_session):
        resp = admin_session.get("/gateway/health")
        assert resp.status_code == 200

    def test_can_read_audit(self, admin_session):
        resp = admin_session.get("/rbac/audit")
        assert resp.status_code == 200


class TestOperatorAccess:
    """operator can read/write subscribers but not manage roles."""

    def test_can_read_subscribers(self, operator_session):
        assert operator_session.get("/subscribers").status_code == 200

    def test_can_create_subscriber(self, operator_session):
        resp = operator_session.post("/subscribers", json={
            "name": "Operator Test Sub", "email": unique_email("op"),
            "organization": "Test", "tier": "free",
        })
        assert resp.status_code == 201

    def test_can_read_plans(self, operator_session):
        assert operator_session.get("/plans").status_code == 200

    def test_cannot_delete_subscriber(self, operator_session, admin_session):
        """Operators don't have subscribers:delete permission."""
        # Create a subscriber first as admin
        sub = admin_session.post("/subscribers", json={
            "name": "Delete Test", "email": unique_email("del"),
            "organization": "Test", "tier": "free",
        }).json()
        resp = operator_session.delete(f"/subscribers/{sub['id']}")
        assert resp.status_code == 403

    def test_can_read_teams(self, operator_session):
        assert operator_session.get("/teams").status_code == 200


class TestViewerAccess:
    """viewer should only have read access."""

    def test_can_read_subscribers(self, viewer_session):
        assert viewer_session.get("/subscribers").status_code == 200

    def test_cannot_create_subscriber(self, viewer_session):
        resp = viewer_session.post("/subscribers", json={
            "name": "Viewer Test", "email": unique_email("view"),
            "organization": "Test", "tier": "free",
        })
        assert resp.status_code == 403

    def test_can_read_plans(self, viewer_session):
        assert viewer_session.get("/plans").status_code == 200

    def test_cannot_create_plan(self, viewer_session):
        resp = viewer_session.post("/plans", json={
            "name": "viewer-plan", "description": "should fail",
            "rate_limit_second": 1, "rate_limit_minute": 10,
            "rate_limit_hour": 100, "max_api_keys": 1, "price_cents": 0,
        })
        assert resp.status_code == 403

    def test_can_read_teams(self, viewer_session):
        assert viewer_session.get("/teams").status_code == 200

    def test_cannot_create_team(self, viewer_session):
        resp = viewer_session.post("/teams", json={
            "name": "viewer-team", "slug": "viewer-team",
            "contact_email": unique_email("team"),
        })
        assert resp.status_code == 403


class TestNoRoleAccess:
    """Users with no roles should be denied write AND read operations."""

    def test_developer_cannot_read_subscribers(self, developer_session):
        resp = developer_session.get("/subscribers")
        assert resp.status_code == 403

    def test_developer_cannot_create_subscriber(self, developer_session):
        resp = developer_session.post("/subscribers", json={
            "name": "Dev Test", "email": unique_email("dev"),
            "organization": "Test", "tier": "free",
        })
        assert resp.status_code == 403

    def test_newuser_cannot_read_subscribers(self, newuser_session):
        resp = newuser_session.get("/subscribers")
        assert resp.status_code == 403

    def test_newuser_cannot_read_plans(self, newuser_session):
        resp = newuser_session.get("/plans")
        assert resp.status_code == 403
