"""
Abstract base class for AI providers in the API gateway.

Defines the interface that all AI providers must implement, along with
shared cost tracking, token budget enforcement, and AI safety utilities.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional AI safety module import (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from app.ai.safety.sanitize import sanitize_prompt_input
    from app.ai.safety.validate import validate_agent_output
    from app.ai.safety.pii_masker import mask_pii, unmask_pii
    from app.ai.safety.errors import sanitize_ai_error
    AI_SAFETY_AVAILABLE = True
except ImportError:
    AI_SAFETY_AVAILABLE = False
    logger.debug(
        "AI safety module not available -- providers will operate without safety controls"
    )


class AIProvider(ABC):
    """Abstract base class for all AI providers."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        max_cost_per_analysis: float = 0.50,
    ) -> None:
        """
        Initialise the AI provider.

        Args:
            api_key: API key / credential for the provider.
            model: Model identifier to use.
            max_tokens: Maximum tokens for each response.
            max_cost_per_analysis: Budget ceiling (USD) for a single analysis call.
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.max_cost_per_analysis = max_cost_per_analysis

        # Cumulative usage tracking
        self._total_cost: float = 0.0
        self._total_tokens: int = 0

    # ------------------------------------------------------------------
    # Abstract methods -- every provider must implement these
    # ------------------------------------------------------------------

    @abstractmethod
    async def analyze_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze an incoming API request for patterns and classify intent."""
        ...

    @abstractmethod
    async def detect_anomaly(
        self,
        request_metrics: dict[str, Any],
        historical_baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Detect anomalies in request metrics.

        Returns a dict with at least: score, anomaly_type, confidence,
        action, reasoning, details.
        """
        ...

    @abstractmethod
    async def suggest_rate_limit(
        self,
        consumer_id: str,
        usage_history: list[dict[str, Any]],
        current_limits: dict[str, Any],
    ) -> dict[str, Any]:
        """Return recommended rate limits based on usage patterns."""
        ...

    @abstractmethod
    async def generate_routing_decision(
        self,
        request: dict[str, Any],
        available_backends: list[dict[str, Any]],
        backend_health: dict[str, Any],
    ) -> dict[str, Any]:
        """Decide which backend should handle a given request."""
        ...

    @abstractmethod
    async def transform_request(
        self,
        request: dict[str, Any],
        transformation_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """AI-powered request transformation."""
        ...

    @abstractmethod
    async def transform_response(
        self,
        response: dict[str, Any],
        transformation_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """AI-powered response transformation."""
        ...

    @abstractmethod
    async def generate_documentation(
        self,
        openapi_spec_or_traffic_sample: dict[str, Any] | str,
    ) -> dict[str, Any]:
        """Auto-generate API documentation from an OpenAPI spec or traffic sample."""
        ...

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost of an API call in USD."""
        ...

    # ------------------------------------------------------------------
    # Cost / token tracking
    # ------------------------------------------------------------------

    def get_total_cost(self) -> float:
        """Return cumulative cost (USD) across all calls."""
        return self._total_cost

    def get_total_tokens(self) -> int:
        """Return cumulative token usage across all calls."""
        return self._total_tokens

    def _check_budget(self, estimated_cost: float) -> None:
        """
        Raise ``ValueError`` if the estimated cost for a single call
        exceeds ``max_cost_per_analysis``.
        """
        if estimated_cost > self.max_cost_per_analysis:
            raise ValueError(
                f"Estimated cost ${estimated_cost:.4f} exceeds budget "
                f"${self.max_cost_per_analysis:.2f} per analysis"
            )

    def _track_usage(self, input_tokens: int, output_tokens: int) -> float:
        """
        Record token usage and cost.  Returns the cost for this call.
        """
        cost = self.estimate_cost(input_tokens, output_tokens)
        self._total_cost += cost
        self._total_tokens += input_tokens + output_tokens
        return cost

    # ------------------------------------------------------------------
    # AI Safety utilities
    # ------------------------------------------------------------------

    def _sanitize_input(self, text: str) -> str:
        """Sanitize prompt input through AI safety module if available."""
        if AI_SAFETY_AVAILABLE:
            return sanitize_prompt_input(text)
        return text

    def _validate_output(self, text: str) -> str:
        """Validate AI output through safety module if available."""
        if AI_SAFETY_AVAILABLE:
            result = validate_agent_output(text)
            return result.get("sanitized_text", text)
        return text

    def _mask_pii(self, text: str) -> tuple[str, dict[str, str]]:
        """Mask PII in text before sending to AI provider."""
        if AI_SAFETY_AVAILABLE:
            return mask_pii(text)
        return text, {}

    def _unmask_pii(self, text: str, mappings: dict[str, str]) -> str:
        """Unmask PII in AI response."""
        if AI_SAFETY_AVAILABLE and mappings:
            return unmask_pii(text, mappings)
        return text

    def _sanitize_error(self, error: Exception) -> dict[str, Any]:
        """Sanitize AI provider error messages to avoid leaking secrets."""
        if AI_SAFETY_AVAILABLE:
            return sanitize_ai_error(error)
        return {"message": "An AI provider error occurred", "safe": True}

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove markdown code fences (```json ... ```) from model output."""
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove opening fence (with optional language tag)
            stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped, count=1)
            # Remove closing fence
            stripped = re.sub(r"\n?```\s*$", "", stripped, count=1)
        return stripped.strip()
