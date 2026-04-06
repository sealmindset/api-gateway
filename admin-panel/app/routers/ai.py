"""AI-powered API gateway endpoints: anomaly detection, smart routing, transforms, docs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from sqlalchemy import select

from app.middleware.rbac import require_permission
from app.models.database import AIPrompt, User, get_db_session
from app.models.schemas import AIPromptCreate, AIPromptRead, AIPromptUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Pydantic models -- Request payloads
# ---------------------------------------------------------------------------

class RequestData(BaseModel):
    """Incoming HTTP request data to be analyzed."""
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="Request path")
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    source_ip: Optional[str] = None
    timestamp: Optional[datetime] = None
    consumer_id: Optional[str] = None


class RequestMetrics(BaseModel):
    """Accompanying metrics for anomaly detection."""
    request_rate: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    payload_size_bytes: Optional[int] = None
    unique_endpoints_hit: Optional[int] = None
    requests_last_minute: Optional[int] = None
    requests_last_hour: Optional[int] = None


class BaselineProfile(BaseModel):
    """Baseline behavioural profile for a consumer / route."""
    avg_request_rate: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    typical_error_rate: Optional[float] = None
    common_paths: list[str] = Field(default_factory=list)
    common_methods: list[str] = Field(default_factory=list)
    typical_payload_size: Optional[int] = None


class AnalyzeRequest(BaseModel):
    """POST /api/ai/analyze body."""
    request_data: RequestData
    metrics: RequestMetrics = Field(default_factory=RequestMetrics)
    baseline: Optional[BaselineProfile] = None


class RateLimitSuggestRequest(BaseModel):
    """POST /api/ai/rate-limit/suggest body."""
    consumer_id: str
    usage_history: list[dict[str, Any]] = Field(
        ..., description="List of usage records with timestamp, count, endpoint, etc."
    )
    current_limits: dict[str, int] = Field(
        default_factory=dict,
        description="Current rate limits, e.g. {'second': 5, 'minute': 100, 'hour': 3000}",
    )


class BackendInfo(BaseModel):
    """Describes an available backend for smart routing."""
    name: str
    url: str
    weight: Optional[float] = 1.0
    region: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)


class BackendHealth(BaseModel):
    """Health data for a single backend."""
    name: str
    healthy: bool = True
    latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    active_connections: Optional[int] = None
    cpu_usage: Optional[float] = None


class RouteRequest(BaseModel):
    """POST /api/ai/route body."""
    request_data: RequestData
    available_backends: list[BackendInfo]
    backend_health: list[BackendHealth] = Field(default_factory=list)


class TransformRequest(BaseModel):
    """POST /api/ai/transform/request and /transform/response body."""
    body: Any = Field(..., description="The request or response body to transform")
    content_type: str = Field("application/json", description="MIME type of the body")
    transformation_rules: str = Field(
        ..., description="Natural-language description of the desired transformation"
    )
    context: Optional[dict[str, Any]] = Field(
        None, description="Optional extra context (consumer info, route metadata, etc.)"
    )


class TrafficSample(BaseModel):
    """A single request/response pair used for documentation generation."""
    request: RequestData
    response_status: int
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: Optional[Any] = None


class DocumentationRequest(BaseModel):
    """POST /api/ai/documentation/generate body."""
    openapi_spec: Optional[dict[str, Any]] = Field(
        None, description="Existing OpenAPI spec to enhance"
    )
    traffic_samples: list[TrafficSample] = Field(
        default_factory=list, description="Observed request/response pairs"
    )
    title: Optional[str] = None
    description: Optional[str] = None


class BatchAnalyzeRequest(BaseModel):
    """POST /api/ai/anomaly/batch body."""
    requests: list[AnalyzeRequest] = Field(
        ..., description="List of requests to analyze in parallel"
    )


# ---------------------------------------------------------------------------
# Pydantic models -- Response payloads
# ---------------------------------------------------------------------------

class AnomalyDetectionResult(BaseModel):
    """Result of anomaly analysis."""
    analysis_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    is_anomalous: bool = False
    reasons: list[str] = Field(default_factory=list)
    recommended_action: str = Field("allow", description="allow | warn | block")
    details: dict[str, Any] = Field(default_factory=dict)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RateLimitSuggestion(BaseModel):
    """AI-suggested rate limits for a consumer."""
    consumer_id: str
    suggested_limits: dict[str, int] = Field(
        ..., description="e.g. {'second': 10, 'minute': 200, 'hour': 5000}"
    )
    reasoning: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    based_on_samples: int = 0


class RoutingDecision(BaseModel):
    """Smart routing decision from the AI layer."""
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    selected_backend: str
    reasoning: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    fallback_backend: Optional[str] = None
    headers_to_add: dict[str, str] = Field(default_factory=dict)


class TransformResult(BaseModel):
    """Result of an AI-powered request or response transformation."""
    transform_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transformed_body: Any
    content_type: str = "application/json"
    changes_summary: str = ""
    tokens_used: int = 0


class DocumentationResult(BaseModel):
    """Auto-generated API documentation."""
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    markdown: str
    openapi_spec: Optional[dict[str, Any]] = None
    endpoints_documented: int = 0
    tokens_used: int = 0


class AIHealthResponse(BaseModel):
    """AI provider health and status information."""
    provider: str
    model: str
    available: bool
    latency_ms: Optional[float] = None
    total_requests: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    capabilities: list[str] = Field(default_factory=list)


class AIConfigResponse(BaseModel):
    """Current AI configuration."""
    provider: str
    model: str
    capabilities: list[str] = Field(default_factory=list)
    max_tokens: int = 0
    temperature: float = 0.0
    rate_limit_rpm: Optional[int] = None


# ---------------------------------------------------------------------------
# AI Agent dependency
# ---------------------------------------------------------------------------

def _get_agent():
    """Lazy-import the AI agent to avoid startup failures when AI is not configured."""
    try:
        from app.ai.agent import agent
        return agent
    except Exception as exc:
        logger.error("Failed to load AI agent: %s", exc)
        return None


def _require_agent():
    """Return the agent or raise 503 if unavailable."""
    agent = _get_agent()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider is not available. Check configuration and connectivity.",
        )
    return agent


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/analyze",
    response_model=AnomalyDetectionResult,
    summary="Analyze a request for anomalies",
    description=(
        "Send request data and associated metrics to the AI provider for "
        "anomaly detection. Returns a score, classification, and recommended action."
    ),
)
async def analyze_request(
    payload: AnalyzeRequest,
    _auth: User = Depends(require_permission("ai:analyze")),
) -> AnomalyDetectionResult:
    """Analyze a single request for anomalous behaviour."""
    agent = _require_agent()
    try:
        logger.info(
            "Anomaly analysis requested: method=%s path=%s consumer=%s",
            payload.request_data.method,
            payload.request_data.path,
            payload.request_data.consumer_id,
        )
        result: AnomalyDetectionResult = await agent.detect_anomaly(
            request_data=payload.request_data.model_dump(),
            metrics=payload.metrics.model_dump(),
            baseline=payload.baseline.model_dump() if payload.baseline else None,
        )
        logger.info(
            "Anomaly analysis complete: analysis_id=%s score=%.3f anomalous=%s",
            result.analysis_id, result.anomaly_score, result.is_anomalous,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Anomaly analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI analysis unavailable: {exc}",
        )


@router.post(
    "/rate-limit/suggest",
    response_model=RateLimitSuggestion,
    summary="Get AI-suggested rate limits",
    description=(
        "Provide a consumer's usage history and current limits. "
        "The AI will suggest optimized rate limits based on observed patterns."
    ),
)
async def suggest_rate_limits(
    payload: RateLimitSuggestRequest,
    _auth: User = Depends(require_permission("ai:rate-limit")),
) -> RateLimitSuggestion:
    """Get AI-powered rate-limit recommendations for a consumer."""
    agent = _require_agent()
    try:
        logger.info(
            "Rate-limit suggestion requested: consumer_id=%s history_samples=%d",
            payload.consumer_id, len(payload.usage_history),
        )
        result: RateLimitSuggestion = await agent.suggest_rate_limits(
            consumer_id=payload.consumer_id,
            usage_history=payload.usage_history,
            current_limits=payload.current_limits,
        )
        logger.info(
            "Rate-limit suggestion complete: consumer_id=%s confidence=%.3f",
            result.consumer_id, result.confidence,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Rate-limit suggestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI rate-limit suggestion unavailable: {exc}",
        )


@router.post(
    "/route",
    response_model=RoutingDecision,
    summary="Get smart routing decision",
    description=(
        "Given a request, a list of available backends, and their health data, "
        "the AI will choose the optimal backend and explain its reasoning."
    ),
)
async def smart_route(
    payload: RouteRequest,
    _auth: User = Depends(require_permission("ai:route")),
) -> RoutingDecision:
    """Get an AI-powered routing decision."""
    agent = _require_agent()
    try:
        logger.info(
            "Smart routing requested: path=%s backends=%d",
            payload.request_data.path, len(payload.available_backends),
        )
        result: RoutingDecision = await agent.decide_route(
            request_data=payload.request_data.model_dump(),
            available_backends=[b.model_dump() for b in payload.available_backends],
            backend_health=[h.model_dump() for h in payload.backend_health],
        )
        logger.info(
            "Smart routing complete: decision_id=%s selected=%s confidence=%.3f",
            result.decision_id, result.selected_backend, result.confidence,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Smart routing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI routing unavailable: {exc}",
        )


@router.post(
    "/transform/request",
    response_model=TransformResult,
    summary="Transform a request using AI",
    description=(
        "Apply natural-language transformation rules to a request body. "
        "The AI will rewrite the body according to the specified rules."
    ),
)
async def transform_request(
    payload: TransformRequest,
    _auth: User = Depends(require_permission("ai:transform")),
) -> TransformResult:
    """Transform a request body using AI-powered rules."""
    agent = _require_agent()
    try:
        logger.info(
            "Request transform requested: content_type=%s rules_len=%d",
            payload.content_type, len(payload.transformation_rules),
        )
        result: TransformResult = await agent.transform_body(
            body=payload.body,
            content_type=payload.content_type,
            transformation_rules=payload.transformation_rules,
            context=payload.context,
            direction="request",
        )
        logger.info(
            "Request transform complete: transform_id=%s tokens=%d",
            result.transform_id, result.tokens_used,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Request transform failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI request transformation unavailable: {exc}",
        )


@router.post(
    "/transform/response",
    response_model=TransformResult,
    summary="Transform a response using AI",
    description=(
        "Apply natural-language transformation rules to a response body. "
        "The AI will rewrite the body according to the specified rules."
    ),
)
async def transform_response(
    payload: TransformRequest,
    _auth: User = Depends(require_permission("ai:transform")),
) -> TransformResult:
    """Transform a response body using AI-powered rules."""
    agent = _require_agent()
    try:
        logger.info(
            "Response transform requested: content_type=%s rules_len=%d",
            payload.content_type, len(payload.transformation_rules),
        )
        result: TransformResult = await agent.transform_body(
            body=payload.body,
            content_type=payload.content_type,
            transformation_rules=payload.transformation_rules,
            context=payload.context,
            direction="response",
        )
        logger.info(
            "Response transform complete: transform_id=%s tokens=%d",
            result.transform_id, result.tokens_used,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Response transform failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI response transformation unavailable: {exc}",
        )


@router.post(
    "/documentation/generate",
    response_model=DocumentationResult,
    summary="Auto-generate API documentation",
    description=(
        "Provide an existing OpenAPI spec and/or traffic samples (request/response pairs). "
        "The AI will generate comprehensive markdown documentation."
    ),
)
async def generate_documentation(
    payload: DocumentationRequest,
    _auth: User = Depends(require_permission("ai:documentation")),
) -> DocumentationResult:
    """Generate API documentation from specs or traffic samples."""
    agent = _require_agent()
    if not payload.openapi_spec and not payload.traffic_samples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of 'openapi_spec' or 'traffic_samples' must be provided.",
        )
    try:
        logger.info(
            "Documentation generation requested: has_spec=%s samples=%d",
            payload.openapi_spec is not None, len(payload.traffic_samples),
        )
        result: DocumentationResult = await agent.generate_documentation(
            openapi_spec=payload.openapi_spec,
            traffic_samples=[s.model_dump() for s in payload.traffic_samples],
            title=payload.title,
            description=payload.description,
        )
        logger.info(
            "Documentation generation complete: doc_id=%s endpoints=%d tokens=%d",
            result.doc_id, result.endpoints_documented, result.tokens_used,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Documentation generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI documentation generation unavailable: {exc}",
        )


@router.get(
    "/health",
    response_model=AIHealthResponse,
    summary="AI provider health and status",
    description="Returns AI provider availability, model info, and cost statistics. No auth required.",
)
async def ai_health() -> AIHealthResponse:
    """Check AI provider health and return status information."""
    agent = _get_agent()
    if agent is None:
        return AIHealthResponse(
            provider="none",
            model="none",
            available=False,
            capabilities=[],
        )
    try:
        health = await agent.health_check()
        return AIHealthResponse(**health)
    except Exception as exc:
        logger.warning("AI health check failed: %s", exc)
        return AIHealthResponse(
            provider=getattr(agent, "provider_name", "unknown"),
            model=getattr(agent, "model_name", "unknown"),
            available=False,
            capabilities=[],
        )


@router.get(
    "/config",
    response_model=AIConfigResponse,
    summary="Current AI configuration",
    description="Returns the active AI provider configuration and available capabilities.",
)
async def ai_config(
    _auth: User = Depends(require_permission("ai:read")),
) -> AIConfigResponse:
    """Return the current AI configuration."""
    agent = _require_agent()
    try:
        config = await agent.get_config()
        return AIConfigResponse(**config)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to retrieve AI config: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to retrieve AI configuration: {exc}",
        )


@router.post(
    "/anomaly/batch",
    response_model=list[AnomalyDetectionResult],
    summary="Batch analyze multiple requests",
    description=(
        "Submit multiple requests for parallel anomaly detection. "
        "Results are returned in the same order as the input list."
    ),
)
async def batch_analyze(
    payload: BatchAnalyzeRequest,
    _auth: User = Depends(require_permission("ai:analyze")),
) -> list[AnomalyDetectionResult]:
    """Batch-analyze multiple requests for anomalies using parallel processing."""
    agent = _require_agent()
    if not payload.requests:
        return []

    logger.info("Batch anomaly analysis requested: count=%d", len(payload.requests))

    async def _analyze_one(item: AnalyzeRequest) -> AnomalyDetectionResult:
        """Analyze a single request, returning a safe fallback on error."""
        try:
            return await agent.detect_anomaly(
                request_data=item.request_data.model_dump(),
                metrics=item.metrics.model_dump(),
                baseline=item.baseline.model_dump() if item.baseline else None,
            )
        except Exception as exc:
            logger.warning("Batch item analysis failed: %s", exc)
            return AnomalyDetectionResult(
                anomaly_score=0.0,
                is_anomalous=False,
                reasons=[f"Analysis failed: {exc}"],
                recommended_action="allow",
                details={"error": str(exc)},
            )

    try:
        results = await asyncio.gather(
            *[_analyze_one(item) for item in payload.requests]
        )
        logger.info(
            "Batch anomaly analysis complete: count=%d anomalous=%d",
            len(results),
            sum(1 for r in results if r.is_anomalous),
        )
        return list(results)
    except Exception as exc:
        logger.exception("Batch anomaly analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI batch analysis unavailable: {exc}",
        )


# ---------------------------------------------------------------------------
# Prompt Management CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/prompts",
    response_model=list[AIPromptRead],
    summary="List all AI prompts",
)
async def list_prompts(
    category: Optional[str] = None,
    session=Depends(get_db_session),
):
    """Return all prompt templates, optionally filtered by category."""
    stmt = select(AIPrompt).order_by(AIPrompt.category, AIPrompt.name)
    if category:
        stmt = stmt.where(AIPrompt.category == category)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get(
    "/prompts/{prompt_id}",
    response_model=AIPromptRead,
    summary="Get a single prompt",
)
async def get_prompt(
    prompt_id: uuid.UUID,
    session=Depends(get_db_session),
):
    """Return a single prompt by ID."""
    result = await session.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post(
    "/prompts",
    response_model=AIPromptRead,
    status_code=201,
    summary="Create a new prompt",
)
async def create_prompt(
    payload: AIPromptCreate,
    _auth: User = Depends(require_permission("ai:analyze")),
    session=Depends(get_db_session),
):
    """Create a new prompt template."""
    existing = await session.execute(select(AIPrompt).where(AIPrompt.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Prompt with slug '{payload.slug}' already exists")
    prompt = AIPrompt(**payload.model_dump())
    session.add(prompt)
    await session.flush()
    await session.refresh(prompt)
    return prompt


@router.put(
    "/prompts/{prompt_id}",
    response_model=AIPromptRead,
    summary="Update a prompt",
)
async def update_prompt(
    prompt_id: uuid.UUID,
    payload: AIPromptUpdate,
    _auth: User = Depends(require_permission("ai:analyze")),
    session=Depends(get_db_session),
):
    """Update an existing prompt template. Increments the version number."""
    result = await session.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)
    prompt.version += 1
    await session.flush()
    await session.refresh(prompt)
    return prompt


@router.delete(
    "/prompts/{prompt_id}",
    status_code=204,
    summary="Delete a prompt",
)
async def delete_prompt(
    prompt_id: uuid.UUID,
    _auth: User = Depends(require_permission("ai:analyze")),
    session=Depends(get_db_session),
):
    """Delete a prompt template."""
    result = await session.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    await session.delete(prompt)
