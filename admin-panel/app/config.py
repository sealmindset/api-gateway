"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the API Gateway Admin Panel.

    All values are read from environment variables or a .env file.
    """

    # --- Application ---
    app_name: str = "API Gateway Admin Panel"
    app_secret_key: str = Field(..., description="Secret key for session signing and CSRF")
    debug: bool = False

    # --- Database (PostgreSQL + asyncpg) ---
    database_url: str = Field(
        ...,
        description="PostgreSQL DSN, e.g. postgresql+asyncpg://user:pass@host:5432/dbname",
    )
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20
    db_echo: bool = False

    # --- Microsoft Entra ID (Azure AD) OIDC ---
    entra_tenant_id: str = Field(..., description="Azure AD tenant ID")
    entra_client_id: str = Field(..., description="Application (client) ID")
    entra_client_secret: str = Field(..., description="Client secret value")
    entra_redirect_uri: str = Field(
        "http://localhost:8000/auth/callback",
        description="OAuth2 redirect URI registered in Entra ID",
    )

    @property
    def entra_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"

    @property
    def entra_openid_config_url(self) -> str:
        return f"{self.entra_authority}/v2.0/.well-known/openid-configuration"

    @property
    def entra_jwks_uri(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/discovery/v2.0/keys"

    # --- Kong Admin API ---
    kong_admin_url: str = Field(
        "http://localhost:8001",
        description="Base URL for the Kong Admin API",
    )
    kong_admin_token: Optional[str] = Field(
        None, description="Optional bearer token for Kong Admin API"
    )

    # --- Redis ---
    redis_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis URL for session storage and caching",
    )

    # --- Rate-limit tier defaults (requests per window) ---
    rate_limit_free_second: int = 1
    rate_limit_free_minute: int = 30
    rate_limit_free_hour: int = 500

    rate_limit_basic_second: int = 5
    rate_limit_basic_minute: int = 100
    rate_limit_basic_hour: int = 3000

    rate_limit_pro_second: int = 20
    rate_limit_pro_minute: int = 500
    rate_limit_pro_hour: int = 15000

    rate_limit_enterprise_second: int = 100
    rate_limit_enterprise_minute: int = 3000
    rate_limit_enterprise_hour: int = 100000

    # --- Cribl ---
    cribl_endpoint: str = Field(
        "http://localhost:9514",
        description="Cribl Stream / Edge endpoint for log forwarding",
    )
    cribl_token: Optional[str] = None

    # --- AI / Claude ---
    ai_provider: str = Field(
        "anthropic_foundry",
        description="AI provider: anthropic_foundry (default) or claude",
    )
    anthropic_api_key: Optional[str] = Field(
        None, description="Anthropic API key (used by both claude and foundry providers)"
    )
    anthropic_model: str = Field(
        "cogdep-aifoundry-dev-eus2-claude-sonnet-4-5",
        description="Model / deployment name to use",
    )
    azure_ai_foundry_endpoint: Optional[str] = Field(
        None, description="Azure AI Foundry endpoint URL"
    )
    azure_ai_foundry_api_key: Optional[str] = Field(
        None,
        description="Optional separate API key for Azure AI Foundry "
                    "(falls back to ANTHROPIC_API_KEY if not set)",
    )
    ai_max_cost_per_analysis: float = Field(
        0.50, description="Max cost budget per AI analysis in USD"
    )
    ai_sampling_rate: float = Field(
        0.1, description="Fraction of requests to analyze (0.0-1.0)"
    )

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
