"""Battle Test 07: AI Endpoints.

Tests the AI-powered analysis layer:
  - AI health and config
  - Prompt management CRUD
  - Analysis endpoints (may return errors without AI provider)
"""

from __future__ import annotations

import pytest


class TestAIHealth:
    """Verify AI layer endpoints are accessible."""

    def test_ai_health(self, admin_session):
        resp = admin_session.get("/ai/health")
        assert resp.status_code == 200

    def test_ai_config(self, admin_session):
        resp = admin_session.get("/ai/config")
        # 200 if AI provider configured, 503 if not, 403 if missing permission
        assert resp.status_code in (200, 403, 503)


class TestPromptManagement:
    """Test AI prompt CRUD operations."""

    def test_list_prompts(self, admin_session):
        resp = admin_session.get("/ai/prompts")
        assert resp.status_code == 200
        prompts = resp.json()
        assert isinstance(prompts, list)
        # Should have seed prompts from migration
        assert len(prompts) >= 5

    def test_seeded_prompt_categories(self, admin_session):
        """Verify all expected prompt categories exist."""
        prompts = admin_session.get("/ai/prompts").json()
        slugs = [p["slug"] for p in prompts]
        assert "anomaly-detection" in slugs
        assert "rate-limit-advisor" in slugs
        assert "smart-routing" in slugs
        assert "api-documentation" in slugs

    def test_get_prompt_by_id(self, admin_session):
        prompts = admin_session.get("/ai/prompts").json()
        if prompts:
            resp = admin_session.get(f"/ai/prompts/{prompts[0]['id']}")
            assert resp.status_code == 200
            assert resp.json()["slug"] == prompts[0]["slug"]

    def test_create_prompt(self, admin_session):
        from integration.conftest import unique_slug
        slug = unique_slug("prompt")
        resp = admin_session.post("/ai/prompts", json={
            "slug": slug,
            "name": "Battle Test Prompt",
            "category": "anomaly",
            "system_prompt": "You are a test prompt.",
            "temperature": 0.5,
            "max_tokens": 1024,
        })
        assert resp.status_code == 201
        prompt = resp.json()
        assert prompt["slug"] == slug
        assert prompt["is_active"] is True

    def test_update_prompt(self, admin_session):
        from integration.conftest import unique_slug
        slug = unique_slug("upd")
        prompt = admin_session.post("/ai/prompts", json={
            "slug": slug, "name": "Update Me", "category": "rate_limit",
            "system_prompt": "Original prompt.",
        }).json()
        resp = admin_session.put(f"/ai/prompts/{prompt['id']}", json={
            "slug": slug, "name": "Updated", "category": "rate_limit",
            "system_prompt": "Updated prompt.",
            "temperature": 0.7,
        })
        assert resp.status_code == 200
        assert resp.json()["system_prompt"] == "Updated prompt."

    def test_delete_prompt(self, admin_session):
        from integration.conftest import unique_slug
        slug = unique_slug("del")
        prompt = admin_session.post("/ai/prompts", json={
            "slug": slug, "name": "Delete Me", "category": "routing",
            "system_prompt": "To be deleted.",
        }).json()
        resp = admin_session.delete(f"/ai/prompts/{prompt['id']}")
        assert resp.status_code == 204


class TestAIAnalysis:
    """Test AI analysis endpoints (expect graceful errors without AI provider)."""

    def test_analyze_endpoint_exists(self, admin_session):
        """The analyze endpoint should exist even if AI provider isn't configured."""
        resp = admin_session.post("/ai/analyze", json={
            "analysis_type": "anomaly",
            "data": {"test": True},
        })
        # 200 if configured, 503/422 if no AI provider
        assert resp.status_code in (200, 422, 500, 503)

    def test_anomaly_batch_endpoint_exists(self, admin_session):
        resp = admin_session.post("/ai/anomaly/batch", json={
            "requests": [],
        })
        assert resp.status_code in (200, 422, 500, 503)

    def test_rate_limit_suggest_endpoint_exists(self, admin_session):
        resp = admin_session.post("/ai/rate-limit/suggest", json={
            "consumer_id": "test-consumer",
        })
        assert resp.status_code in (200, 422, 500, 503)
