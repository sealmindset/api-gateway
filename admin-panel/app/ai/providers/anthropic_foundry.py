"""
Azure AI Foundry provider implementation.

Inherits from ClaudeProvider and overrides client initialisation to use
the Azure AI Foundry endpoint.  All inference methods are inherited unchanged
because the Anthropic Messages API is compatible across both endpoints.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    from anthropic import AsyncAnthropic, AnthropicFoundry  # noqa: F401
    ANTHROPIC_AVAILABLE = True
except ImportError:
    try:
        from anthropic import AsyncAnthropic
        AnthropicFoundry = None  # type: ignore[assignment,misc]
        ANTHROPIC_AVAILABLE = True
    except ImportError:
        ANTHROPIC_AVAILABLE = False
        AnthropicFoundry = None  # type: ignore[assignment,misc]

from .claude import ClaudeProvider

logger = logging.getLogger(__name__)


class AnthropicFoundryProvider(ClaudeProvider):
    """
    Azure AI Foundry variant of the Claude provider.

    Uses ``AsyncAnthropic`` pointed at the Azure AI Foundry endpoint so that
    all inherited inference methods work identically.
    """

    # Azure AI Foundry deployment name prefix
    AZURE_FOUNDRY_PREFIX = "cogdep-aifoundry-"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "cogdep-aifoundry-dev-eus2-claude-sonnet-4-5",
        max_tokens: int = 4096,
        max_cost_per_analysis: float = 0.50,
    ) -> None:
        """
        Initialise the Anthropic Foundry provider.

        Args:
            api_key: Azure AI Foundry API key.
            base_url: Azure AI Foundry endpoint URL.  If ``None``, read from
                      the ``AZURE_AI_FOUNDRY_ENDPOINT`` environment variable.
            model: Azure AI Foundry deployment name
                   (e.g. ``cogdep-aifoundry-dev-eus2-claude-sonnet-4-5``).
            max_tokens: Maximum tokens for responses.
            max_cost_per_analysis: Budget ceiling (USD) per analysis call.
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic library not installed.  Install with: pip install anthropic"
            )

        resolved_base_url = base_url or os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT")
        if not resolved_base_url:
            raise ValueError(
                "Azure AI Foundry endpoint required.  Pass base_url or set "
                "the AZURE_AI_FOUNDRY_ENDPOINT environment variable."
            )

        # Validate Azure-specific model name
        if not model.lower().startswith(self.AZURE_FOUNDRY_PREFIX):
            logger.warning(
                "Model '%s' does not start with expected Azure prefix '%s'.  "
                "It may not be a valid Azure AI Foundry deployment.",
                model,
                self.AZURE_FOUNDRY_PREFIX,
            )

        # Initialise the parent ClaudeProvider (creates self.client)
        super().__init__(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            max_cost_per_analysis=max_cost_per_analysis,
        )

        # Override the client to point at the Azure AI Foundry endpoint
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=resolved_base_url,
        )

        logger.info(
            "Initialised Anthropic Foundry provider with model: %s at %s",
            model,
            resolved_base_url,
        )
