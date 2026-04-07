"""Battle Test 06: Kong Gateway Integration.

Tests Kong proxy and admin API interactions:
  - Gateway health
  - Consumer management via admin panel
  - Route listing
  - Service listing
  - Plugin management
"""

from __future__ import annotations

import pytest


class TestGatewayHealth:
    """Verify Kong gateway is operational."""

    def test_kong_admin_reachable(self, kong_admin):
        resp = kong_admin.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "memory" in data

    def test_kong_proxy_reachable(self, kong_proxy):
        resp = kong_proxy.get("/")
        # Kong returns 404 when no routes match, which is expected
        assert resp.status_code in (200, 404)

    def test_gateway_health_via_admin_panel(self, admin_session):
        resp = admin_session.get("/gateway/health")
        assert resp.status_code == 200


class TestGatewayServices:
    """Verify Kong service management."""

    def test_list_services(self, admin_session):
        resp = admin_session.get("/gateway/services")
        assert resp.status_code == 200

    def test_list_routes(self, admin_session):
        resp = admin_session.get("/gateway/routes")
        assert resp.status_code == 200


class TestGatewayConsumers:
    """Verify Kong consumer management through admin panel."""

    def test_list_consumers(self, admin_session):
        resp = admin_session.get("/gateway/consumers")
        assert resp.status_code == 200


class TestGatewayPlugins:
    """Verify Kong plugin management through admin panel."""

    def test_list_plugins(self, admin_session):
        resp = admin_session.get("/gateway/plugins")
        assert resp.status_code == 200
