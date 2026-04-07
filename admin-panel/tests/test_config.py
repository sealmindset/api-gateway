"""Tests for app.config -- settings loading and computed properties.

Note: Inside Docker, env vars from docker-compose override defaults.
Tests that check defaults must pass explicit values to avoid env leakage.
"""

import os
from unittest.mock import patch

import pytest

from app.config import Settings


class TestSettings:
    def test_app_name_default(self):
        s = Settings(_env_file=None)
        assert s.app_name == "API Gateway Admin Panel"

    def test_cors_origins_list_single(self):
        s = Settings(_env_file=None, cors_origins="http://localhost:3000")
        assert s.cors_origins_list == ["http://localhost:3000"]

    def test_cors_origins_list_multiple(self):
        s = Settings(
            _env_file=None,
            cors_origins="http://localhost:3000,http://localhost:8080",
        )
        assert s.cors_origins_list == ["http://localhost:3000", "http://localhost:8080"]

    def test_cors_origins_list_strips_whitespace(self):
        s = Settings(
            _env_file=None,
            cors_origins="http://a.com , http://b.com",
        )
        assert s.cors_origins_list == ["http://a.com", "http://b.com"]

    def test_entra_authority(self):
        s = Settings(_env_file=None, entra_tenant_id="my-tenant")
        assert s.entra_authority == "https://login.microsoftonline.com/my-tenant"

    def test_entra_openid_config_url_with_tenant(self):
        s = Settings(_env_file=None, entra_tenant_id="my-tenant", oidc_discovery_url=None)
        assert "my-tenant" in s.entra_openid_config_url
        assert ".well-known/openid-configuration" in s.entra_openid_config_url

    def test_entra_openid_config_url_override(self):
        s = Settings(
            _env_file=None,
            oidc_discovery_url="http://mock-oidc:8080/.well-known/openid-configuration",
        )
        assert s.entra_openid_config_url == "http://mock-oidc:8080/.well-known/openid-configuration"

    def test_rate_limit_explicit_values(self):
        s = Settings(
            _env_file=None,
            rate_limit_free_second=1,
            rate_limit_free_minute=30,
            rate_limit_enterprise_hour=100000,
        )
        assert s.rate_limit_free_second == 1
        assert s.rate_limit_free_minute == 30
        assert s.rate_limit_enterprise_hour == 100000

    def test_ai_explicit_values(self):
        s = Settings(
            _env_file=None,
            ai_provider="anthropic_foundry",
            ai_max_cost_per_analysis=0.50,
            ai_sampling_rate=0.1,
        )
        assert s.ai_provider == "anthropic_foundry"
        assert s.ai_max_cost_per_analysis == 0.50
        assert s.ai_sampling_rate == 0.1
