"""
AI provider layer for the API gateway.

Provides AI-driven capabilities including anomaly detection, adaptive rate
limiting, smart routing, request/response transformation, and automatic
documentation generation.
"""

from .agent import create_ai_agent
from .providers.base import AIProvider
from .providers.claude import ClaudeProvider
from .providers.anthropic_foundry import AnthropicFoundryProvider
from .providers.failover import FailoverProvider
from .schemas import (
    AnomalyDetectionRequest,
    AnomalyDetectionResult,
    RateLimitSuggestion,
    RoutingDecision,
    TransformResult,
    DocumentationResult,
    AIHealthStatus,
)

__all__ = [
    # Factory
    "create_ai_agent",
    # Providers
    "AIProvider",
    "ClaudeProvider",
    "AnthropicFoundryProvider",
    "FailoverProvider",
    # Schemas
    "AnomalyDetectionRequest",
    "AnomalyDetectionResult",
    "RateLimitSuggestion",
    "RoutingDecision",
    "TransformResult",
    "DocumentationResult",
    "AIHealthStatus",
]
