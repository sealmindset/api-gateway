"""
Pydantic models for AI provider inputs and outputs.

Defines structured data types for all AI-driven API gateway capabilities
including anomaly detection, rate limiting, routing, transformations,
and documentation generation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnomalyAction(str, Enum):
    """Recommended action when an anomaly is detected."""

    ALLOW = "allow"
    THROTTLE = "throttle"
    BLOCK = "block"
    ALERT = "alert"


class AnomalyType(str, Enum):
    """Classification of detected anomaly."""

    NONE = "none"
    RATE_SPIKE = "rate_spike"
    PAYLOAD_ANOMALY = "payload_anomaly"
    GEO_ANOMALY = "geo_anomaly"
    AUTH_ANOMALY = "auth_anomaly"
    PATTERN_ANOMALY = "pattern_anomaly"
    LATENCY_ANOMALY = "latency_anomaly"
    ERROR_RATE_SPIKE = "error_rate_spike"
    CREDENTIAL_STUFFING = "credential_stuffing"
    ENUMERATION = "enumeration"
    DATA_EXFILTRATION = "data_exfiltration"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------

class AnomalyDetectionRequest(BaseModel):
    """Input for anomaly detection analysis."""

    request_data: dict[str, Any] = Field(
        ..., description="The incoming API request data (headers, path, method, body snippet)"
    )
    metrics: dict[str, Any] = Field(
        ..., description="Current request metrics (rate, latency, error counts)"
    )
    baseline: dict[str, Any] | None = Field(
        default=None,
        description="Historical baseline metrics for comparison",
    )


class AnomalyDetectionResult(BaseModel):
    """Output from anomaly detection analysis."""

    score: float = Field(
        ..., ge=0.0, le=1.0, description="Anomaly score from 0 (normal) to 1 (highly anomalous)"
    )
    anomaly_type: str = Field(
        ..., description="Classification of the anomaly type"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the detection result"
    )
    action: str = Field(
        ..., description="Recommended action: allow, throttle, block, or alert"
    )
    reasoning: str = Field(
        ..., description="Human-readable explanation of the detection reasoning"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured details about the anomaly",
    )


# ---------------------------------------------------------------------------
# Rate Limit Suggestion
# ---------------------------------------------------------------------------

class RateLimitSuggestion(BaseModel):
    """AI-suggested rate limits for a consumer."""

    consumer_id: str = Field(..., description="Identifier of the API consumer")
    recommended_per_second: int = Field(
        ..., ge=0, description="Recommended requests per second"
    )
    recommended_per_minute: int = Field(
        ..., ge=0, description="Recommended requests per minute"
    )
    recommended_per_hour: int = Field(
        ..., ge=0, description="Recommended requests per hour"
    )
    reasoning: str = Field(
        ..., description="Explanation of why these limits are recommended"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the recommendation"
    )


# ---------------------------------------------------------------------------
# Routing Decision
# ---------------------------------------------------------------------------

class RoutingDecision(BaseModel):
    """AI-driven routing decision for an incoming request."""

    target_backend: str = Field(
        ..., description="Selected backend service to route the request to"
    )
    reasoning: str = Field(
        ..., description="Explanation of the routing decision"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the routing decision"
    )
    estimated_latency_ms: int = Field(
        ..., ge=0, description="Estimated response latency in milliseconds"
    )


# ---------------------------------------------------------------------------
# Transform Result
# ---------------------------------------------------------------------------

class TransformResult(BaseModel):
    """Result of an AI-powered request or response transformation."""

    transformed_data: dict[str, Any] = Field(
        ..., description="The transformed request or response data"
    )
    transformations_applied: list[str] = Field(
        default_factory=list,
        description="List of transformations that were applied",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings generated during transformation",
    )


# ---------------------------------------------------------------------------
# Documentation Result
# ---------------------------------------------------------------------------

class DocumentationResult(BaseModel):
    """Auto-generated API documentation."""

    title: str = Field(..., description="API documentation title")
    description: str = Field(..., description="High-level API description")
    endpoints: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of endpoint definitions with method, path, description, parameters",
    )
    schemas: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of data schemas / models referenced by the API",
    )
    markdown: str = Field(
        ..., description="Full documentation rendered as Markdown"
    )


# ---------------------------------------------------------------------------
# Health Status
# ---------------------------------------------------------------------------

class AIHealthStatus(BaseModel):
    """Health and usage status of an AI provider."""

    provider: str = Field(..., description="Provider name (e.g. claude, anthropic_foundry)")
    model: str = Field(..., description="Model identifier currently in use")
    available: bool = Field(..., description="Whether the provider is reachable and operational")
    total_cost: float = Field(
        default=0.0, ge=0.0, description="Cumulative cost in USD for this provider instance"
    )
    total_tokens: int = Field(
        default=0, ge=0, description="Cumulative tokens consumed by this provider instance"
    )
