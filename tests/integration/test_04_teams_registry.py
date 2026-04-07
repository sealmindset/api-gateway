"""Battle Test 04: Teams and API Registry.

Tests the team-based API registration workflow:
  - Create team
  - Add members
  - Register API
  - Submission and approval workflow
  - RBAC on team resources
"""

from __future__ import annotations

import pytest
from integration.conftest import unique_email, unique_slug


class TestTeamCRUD:
    """Team creation and management."""

    def test_create_team(self, admin_session):
        slug = unique_slug("team")
        resp = admin_session.post("/teams", json={
            "name": "Battle Test Team",
            "slug": slug,
            "description": "Integration test team",
            "contact_email": unique_email("team"),
        })
        assert resp.status_code == 201
        team = resp.json()
        assert team["slug"] == slug
        assert team["is_active"] is True

    def test_list_teams(self, admin_session):
        resp = admin_session.get("/teams")
        assert resp.status_code == 200

    def test_get_team_by_id(self, admin_session):
        slug = unique_slug("get")
        team = admin_session.post("/teams", json={
            "name": "Get Test", "slug": slug,
            "contact_email": unique_email("team"),
        }).json()
        resp = admin_session.get(f"/teams/{team['id']}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == slug

    def test_update_team(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "Update Test", "slug": unique_slug("upd"),
            "contact_email": unique_email("team"),
        }).json()
        resp = admin_session.patch(f"/teams/{team['id']}", json={
            "description": "Updated description",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_delete_team(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "Delete Test", "slug": unique_slug("del"),
            "contact_email": unique_email("team"),
        }).json()
        resp = admin_session.delete(f"/teams/{team['id']}")
        assert resp.status_code == 204


class TestTeamMembers:
    """Team member management."""

    def test_add_member_to_team(self, admin_session, operator_session):
        team = admin_session.post("/teams", json={
            "name": "Member Test", "slug": unique_slug("mem"),
            "contact_email": unique_email("team"),
        }).json()
        # Creator is auto-added as owner, so add a different user
        op_info = operator_session.user_info
        resp = admin_session.post(f"/teams/{team['id']}/members", json={
            "user_id": op_info["id"],
            "role": "member",
        })
        assert resp.status_code in (200, 201)

    def test_list_team_members(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "List Members", "slug": unique_slug("lm"),
            "contact_email": unique_email("team"),
        }).json()
        resp = admin_session.get(f"/teams/{team['id']}/members")
        assert resp.status_code == 200


class TestApiRegistry:
    """API registration and approval workflow."""

    def test_register_api(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "API Reg Team", "slug": unique_slug("api"),
            "contact_email": unique_email("team"),
        }).json()
        resp = admin_session.post("/api-registry", json={
            "team_id": team["id"],
            "name": "Weather API",
            "slug": unique_slug("weather"),
            "description": "Returns weather data",
            "upstream_url": "https://api.weather.example.com",
            "auth_type": "key-auth",
            "requires_approval": True,
        })
        assert resp.status_code == 201
        reg = resp.json()
        assert reg["status"] == "draft"

    def test_list_api_registrations(self, admin_session):
        resp = admin_session.get("/api-registry")
        assert resp.status_code == 200

    def test_submit_api_for_review(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "Submit Team", "slug": unique_slug("sub"),
            "contact_email": unique_email("team"),
        }).json()
        reg = admin_session.post("/api-registry", json={
            "team_id": team["id"],
            "name": "Submit Test API",
            "slug": unique_slug("submit"),
            "upstream_url": "https://api.example.com",
        }).json()
        resp = admin_session.post(f"/api-registry/{reg['id']}/submit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_review"

    def test_approve_api(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "Approve Team", "slug": unique_slug("apr"),
            "contact_email": unique_email("team"),
        }).json()
        reg = admin_session.post("/api-registry", json={
            "team_id": team["id"],
            "name": "Approve Test API",
            "slug": unique_slug("approve"),
            "upstream_url": "https://api.example.com",
        }).json()
        admin_session.post(f"/api-registry/{reg['id']}/submit")
        resp = admin_session.post(f"/api-registry/{reg['id']}/review", json={
            "action": "approve",
            "notes": "Looks good!",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_reject_api(self, admin_session):
        team = admin_session.post("/teams", json={
            "name": "Reject Team", "slug": unique_slug("rej"),
            "contact_email": unique_email("team"),
        }).json()
        reg = admin_session.post("/api-registry", json={
            "team_id": team["id"],
            "name": "Reject Test API",
            "slug": unique_slug("reject"),
            "upstream_url": "https://api.example.com",
        }).json()
        admin_session.post(f"/api-registry/{reg['id']}/submit")
        resp = admin_session.post(f"/api-registry/{reg['id']}/review", json={
            "action": "reject",
            "notes": "Needs documentation",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
