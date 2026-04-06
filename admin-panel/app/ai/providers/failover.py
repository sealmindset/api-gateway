"""
Failover provider that wraps a primary and fallback AI provider.

On any exception from the primary, the call is transparently retried
against the fallback.  All failover events are logged.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import AIProvider

logger = logging.getLogger(__name__)


class FailoverProvider(AIProvider):
    """
    Wrapper provider implementing automatic failover between a primary
    and a fallback AI provider.

    Every abstract method from :class:`AIProvider` is delegated to the
    primary provider first.  If it raises any exception the call is
    retried on the fallback provider.  A ``primary_failed`` flag
    tracks whether the primary has experienced a failure so that
    subsequent calls skip it immediately (avoiding repeated timeouts).
    """

    def __init__(self, primary: AIProvider, fallback: AIProvider) -> None:
        # Initialise base with placeholder values -- costs are delegated
        super().__init__(api_key="failover", model="multi-model", max_tokens=0)
        self.primary = primary
        self.fallback = fallback
        self.primary_failed: bool = False

    # ------------------------------------------------------------------
    # Core failover mechanism
    # ------------------------------------------------------------------

    async def _execute_with_failover(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> Any:
        """
        Invoke *method_name* on the primary provider.  On failure, log
        the event and retry on the fallback.
        """
        if not self.primary_failed:
            try:
                method = getattr(self.primary, method_name)
                return await method(*args, **kwargs)
            except Exception as exc:
                logger.warning(
                    "Primary provider (%s) failed for %s: %s. "
                    "Switching to fallback (%s).",
                    self.primary.__class__.__name__,
                    method_name,
                    exc,
                    self.fallback.__class__.__name__,
                )
                self.primary_failed = True

        # Fallback execution
        try:
            method = getattr(self.fallback, method_name)
            return await method(*args, **kwargs)
        except Exception as exc:
            logger.error(
                "Fallback provider (%s) also failed for %s: %s",
                self.fallback.__class__.__name__,
                method_name,
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Delegated abstract methods
    # ------------------------------------------------------------------

    async def analyze_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        return await self._execute_with_failover("analyze_request", request_data)

    async def detect_anomaly(
        self,
        request_metrics: dict[str, Any],
        historical_baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            "detect_anomaly", request_metrics, historical_baseline
        )

    async def suggest_rate_limit(
        self,
        consumer_id: str,
        usage_history: list[dict[str, Any]],
        current_limits: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            "suggest_rate_limit", consumer_id, usage_history, current_limits
        )

    async def generate_routing_decision(
        self,
        request: dict[str, Any],
        available_backends: list[dict[str, Any]],
        backend_health: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            "generate_routing_decision", request, available_backends, backend_health
        )

    async def transform_request(
        self,
        request: dict[str, Any],
        transformation_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            "transform_request", request, transformation_rules
        )

    async def transform_response(
        self,
        response_data: dict[str, Any],
        transformation_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            "transform_response", response_data, transformation_rules
        )

    async def generate_documentation(
        self,
        openapi_spec_or_traffic_sample: dict[str, Any] | str,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            "generate_documentation", openapi_spec_or_traffic_sample
        )

    # ------------------------------------------------------------------
    # Cost / token tracking -- aggregate across both providers
    # ------------------------------------------------------------------

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        if not self.primary_failed:
            return self.primary.estimate_cost(input_tokens, output_tokens)
        return self.fallback.estimate_cost(input_tokens, output_tokens)

    def get_total_cost(self) -> float:
        return self.primary.get_total_cost() + self.fallback.get_total_cost()

    def get_total_tokens(self) -> int:
        return self.primary.get_total_tokens() + self.fallback.get_total_tokens()
