"""
AI Agent factory for the API gateway.

Reads configuration from environment variables and instantiates the
correct AI provider (with optional failover wrapping).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .providers.base import AIProvider
from .providers.claude import ClaudeProvider
from .providers.anthropic_foundry import AnthropicFoundryProvider
from .providers.failover import FailoverProvider

logger = logging.getLogger(__name__)


def create_ai_agent(
    settings: Optional[dict[str, Any]] = None,
) -> AIProvider:
    """
    Factory function that creates and returns a configured AI provider.

    Configuration sources (in priority order):
    1. Values passed in *settings* dict.
    2. Environment variables.

    Supported settings / env vars:
        AI_PROVIDER              -- "anthropic_foundry" (default) or "claude"
        ANTHROPIC_API_KEY        -- API key (used by both claude and foundry)
        AZURE_AI_FOUNDRY_ENDPOINT -- Endpoint URL for Azure AI Foundry
        AZURE_AI_FOUNDRY_API_KEY  -- Optional separate key for foundry
                                     (falls back to ANTHROPIC_API_KEY)
        ANTHROPIC_MODEL          -- Model name override
        AI_MAX_TOKENS            -- Max response tokens (default 4096)
        AI_MAX_COST_PER_ANALYSIS -- Budget ceiling in USD (default 0.50)
        AI_ENABLE_FAILOVER       -- "true" to enable failover wrapping
        AI_FAILOVER_PROVIDER     -- Provider for failover (default: claude)

    Args:
        settings: Optional dict of configuration overrides.

    Returns:
        A fully configured :class:`AIProvider` instance.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    cfg = settings or {}

    def _get(key: str, default: str | None = None) -> str | None:
        return cfg.get(key) or os.environ.get(key) or default

    provider_name = _get("AI_PROVIDER", "anthropic_foundry")

    # Resolve API key: AZURE_AI_FOUNDRY_API_KEY takes precedence for
    # the foundry provider, but falls back to ANTHROPIC_API_KEY so a
    # single key variable works for both providers.
    anthropic_key = _get("ANTHROPIC_API_KEY")
    azure_key = _get("AZURE_AI_FOUNDRY_API_KEY")
    api_key = azure_key or anthropic_key

    azure_endpoint = _get("AZURE_AI_FOUNDRY_ENDPOINT")
    model = _get("ANTHROPIC_MODEL")
    max_tokens = int(_get("AI_MAX_TOKENS", "4096"))  # type: ignore[arg-type]
    max_cost = float(_get("AI_MAX_COST_PER_ANALYSIS", "0.50"))  # type: ignore[arg-type]
    enable_failover = _get("AI_ENABLE_FAILOVER", "false").lower() == "true"
    failover_provider_name = _get("AI_FAILOVER_PROVIDER", "claude")

    # --- Build primary provider -------------------------------------------

    primary: AIProvider

    if provider_name == "anthropic_foundry":
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY (or AZURE_AI_FOUNDRY_API_KEY) required "
                "for anthropic_foundry provider"
            )
        if not azure_endpoint:
            raise ValueError(
                "AZURE_AI_FOUNDRY_ENDPOINT required for anthropic_foundry provider"
            )
        primary = AnthropicFoundryProvider(
            api_key=api_key,
            base_url=azure_endpoint,
            model=model or "cogdep-aifoundry-dev-eus2-claude-sonnet-4-5",
            max_tokens=max_tokens,
            max_cost_per_analysis=max_cost,
        )

    elif provider_name == "claude":
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for claude provider")
        primary = ClaudeProvider(
            api_key=api_key,
            model=model or "claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            max_cost_per_analysis=max_cost,
        )

    else:
        raise ValueError(f"Unsupported AI provider: {provider_name}")

    logger.info("Primary AI provider: %s (model=%s)", provider_name, primary.model)

    # --- Optional failover wrapping ---------------------------------------

    if enable_failover and failover_provider_name != provider_name:
        try:
            fallback = _build_fallback(
                failover_provider_name,
                api_key=api_key,
                azure_endpoint=azure_endpoint,
                max_tokens=max_tokens,
                max_cost=max_cost,
            )
            primary = FailoverProvider(primary=primary, fallback=fallback)
            logger.info(
                "Failover enabled: %s -> %s",
                provider_name,
                failover_provider_name,
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialise failover provider (%s): %s. "
                "Running without failover.",
                failover_provider_name,
                exc,
            )

    return primary


def _build_fallback(
    provider_name: str,
    *,
    api_key: str | None,
    azure_endpoint: str | None,
    max_tokens: int,
    max_cost: float,
) -> AIProvider:
    """Construct a fallback provider instance by name."""
    if provider_name == "claude":
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for claude fallback")
        return ClaudeProvider(
            api_key=api_key,
            max_tokens=max_tokens,
            max_cost_per_analysis=max_cost,
        )

    if provider_name == "anthropic_foundry":
        if not api_key or not azure_endpoint:
            raise ValueError(
                "ANTHROPIC_API_KEY and AZURE_AI_FOUNDRY_ENDPOINT required "
                "for anthropic_foundry fallback"
            )
        return AnthropicFoundryProvider(
            api_key=api_key,
            base_url=azure_endpoint,
            max_tokens=max_tokens,
            max_cost_per_analysis=max_cost,
        )

    raise ValueError(f"Unsupported fallback provider: {provider_name}")
