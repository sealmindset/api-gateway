"""API Registry routes: submission, review workflow, Kong provisioning, usage metrics."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.middleware.auth import get_current_user
from app.middleware.rbac import is_platform_admin, log_access, require_permission
from app.models.database import (
    ApiRegistration,
    Team,
    TeamMember,
    User,
    get_db_session,
)
from app.models.schemas import (
    ApiRegistrationCreate,
    ApiRegistrationRead,
    ApiRegistrationReview,
    ApiRegistrationStatusChange,
    ApiRegistrationUpdate,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-registry", tags=["api-registry"])

# Valid status transitions
STATUS_TRANSITIONS = {
    "draft": ["pending_review"],
    "pending_review": ["approved", "rejected"],
    "approved": ["active"],
    "rejected": ["draft"],
    "active": ["deprecated"],
    "deprecated": ["active", "retired"],
    "retired": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_registration_or_404(db: AsyncSession, reg_id: uuid.UUID) -> ApiRegistration:
    result = await db.execute(select(ApiRegistration).where(ApiRegistration.id == reg_id))
    reg = result.scalar_one_or_none()
    if reg is None:
        raise HTTPException(status_code=404, detail="API registration not found.")
    return reg


async def _check_team_member(db: AsyncSession, user: User, team_id: uuid.UUID, min_role: str = "member") -> None:
    """Verify user belongs to the team with at least the given role.

    Platform admins (super_admin, admin) bypass team membership checks.
    """
    if await is_platform_admin(user, db):
        return

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this team.")

    hierarchy = {"owner": 4, "admin": 3, "member": 2, "viewer": 1}
    if hierarchy.get(membership.role, 0) < hierarchy.get(min_role, 0):
        raise HTTPException(status_code=403, detail=f"Requires at least '{min_role}' role in this team.")


async def _kong_request(method: str, path: str, *, json_body: dict | None = None) -> dict | None:
    """Send a request to Kong Admin API."""
    settings = get_settings()
    headers: dict[str, str] = {"Accept": "application/json"}
    if settings.kong_admin_token:
        headers["Authorization"] = f"Bearer {settings.kong_admin_token}"

    async with httpx.AsyncClient(base_url=settings.kong_admin_url, headers=headers, timeout=15) as client:
        resp = await client.request(method, path, json=json_body)

    if resp.status_code >= 400:
        logger.error("Kong API error: %s %s -> %s %s", method, path, resp.status_code, resp.text)
        raise HTTPException(
            status_code=502,
            detail=f"Kong Admin API returned {resp.status_code}: {resp.text[:500]}",
        )
    if resp.status_code == 204:
        return None
    return resp.json()


async def _provision_kong_service(reg: ApiRegistration) -> tuple[str, str]:
    """Create a Kong service + route for an approved API registration.

    Returns (kong_service_id, kong_route_id).
    """
    parsed = urlparse(reg.upstream_url)
    host = parsed.hostname or parsed.netloc
    port = parsed.port or (443 if reg.upstream_protocol == "https" else 80)
    path = parsed.path or "/"

    service_name = f"api-reg-{reg.slug}"

    # Create or update the service
    service = await _kong_request("PUT", f"/services/{service_name}", json_body={
        "name": service_name,
        "protocol": reg.upstream_protocol,
        "host": host,
        "port": port,
        "path": path,
        "connect_timeout": 10000,
        "read_timeout": 60000,
        "write_timeout": 60000,
    })
    service_id = service["id"]

    # Create or update the route
    gateway_path = reg.gateway_path or f"/api/{reg.slug}"
    route_name = f"api-reg-{reg.slug}-route"
    route = await _kong_request("PUT", f"/services/{service_name}/routes/{route_name}", json_body={
        "name": route_name,
        "paths": [gateway_path],
        "strip_path": True,
        "preserve_host": False,
    })
    route_id = route["id"]

    # Add rate-limiting plugin
    try:
        await _kong_request("POST", f"/services/{service_name}/plugins", json_body={
            "name": "rate-limiting",
            "config": {
                "second": reg.rate_limit_second,
                "minute": reg.rate_limit_minute,
                "hour": reg.rate_limit_hour,
                "policy": "redis",
                "fault_tolerant": True,
            },
        })
    except HTTPException:
        logger.warning("Rate-limiting plugin may already exist for %s", service_name)

    # Add auth plugin if required
    if reg.auth_type != "none":
        try:
            await _kong_request("POST", f"/services/{service_name}/plugins", json_body={
                "name": reg.auth_type,
                "config": {},
            })
        except HTTPException:
            logger.warning("Auth plugin %s may already exist for %s", reg.auth_type, service_name)

    # Add prometheus plugin for usage metrics
    try:
        await _kong_request("POST", f"/services/{service_name}/plugins", json_body={
            "name": "prometheus",
            "config": {"per_consumer": True},
        })
    except HTTPException:
        logger.warning("Prometheus plugin may already exist for %s", service_name)

    return service_id, route_id


async def _deprovision_kong_service(reg: ApiRegistration) -> None:
    """Remove Kong service and route for a retired API."""
    if reg.kong_service_id:
        service_name = f"api-reg-{reg.slug}"
        try:
            route_name = f"api-reg-{reg.slug}-route"
            await _kong_request("DELETE", f"/services/{service_name}/routes/{route_name}")
        except HTTPException:
            logger.warning("Failed to delete Kong route for %s", reg.slug)
        try:
            await _kong_request("DELETE", f"/services/{service_name}")
        except HTTPException:
            logger.warning("Failed to delete Kong service for %s", reg.slug)


# ---------------------------------------------------------------------------
# API Registration CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_registrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    team_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    user: User = Depends(require_permission("api_registry:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List API registrations with filters."""
    query = select(ApiRegistration)
    count_query = select(func.count(ApiRegistration.id))

    if team_id:
        query = query.where(ApiRegistration.team_id == team_id)
        count_query = count_query.where(ApiRegistration.team_id == team_id)
    if status_filter:
        query = query.where(ApiRegistration.status == status_filter)
        count_query = count_query.where(ApiRegistration.status == status_filter)
    if search:
        like = f"%{search}%"
        query = query.where(
            ApiRegistration.name.ilike(like) | ApiRegistration.slug.ilike(like)
        )
        count_query = count_query.where(
            ApiRegistration.name.ilike(like) | ApiRegistration.slug.ilike(like)
        )

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(ApiRegistration.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [ApiRegistrationRead.model_validate(r) for r in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ApiRegistrationRead, status_code=201)
async def create_registration(
    body: ApiRegistrationCreate,
    request: Request,
    user: User = Depends(require_permission("api_registry:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new API. User must be a member of the specified team."""
    # Verify team membership
    await _check_team_member(db, user, body.team_id, min_role="member")

    # Check slug uniqueness
    existing = await db.execute(select(ApiRegistration).where(ApiRegistration.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"API slug '{body.slug}' already exists.")

    reg = ApiRegistration(**body.model_dump())
    db.add(reg)
    await db.flush()

    await log_access(
        db, user=user, action="create", resource_type="api_registration",
        resource_id=str(reg.id), details=body.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return ApiRegistrationRead.model_validate(reg)


@router.get("/{reg_id}", response_model=ApiRegistrationRead)
async def get_registration(
    reg_id: uuid.UUID,
    user: User = Depends(require_permission("api_registry:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a single API registration."""
    reg = await _get_registration_or_404(db, reg_id)
    return ApiRegistrationRead.model_validate(reg)


@router.patch("/{reg_id}", response_model=ApiRegistrationRead)
async def update_registration(
    reg_id: uuid.UUID,
    body: ApiRegistrationUpdate,
    request: Request,
    user: User = Depends(require_permission("api_registry:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Update an API registration. Only allowed in draft or rejected status."""
    reg = await _get_registration_or_404(db, reg_id)
    await _check_team_member(db, user, reg.team_id, min_role="member")

    if reg.status not in ("draft", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit an API in '{reg.status}' status. Only draft or rejected APIs can be edited.",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(reg, field, value)
    # Reset to draft if it was rejected
    if reg.status == "rejected":
        reg.status = "draft"
    await db.flush()

    await log_access(
        db, user=user, action="update", resource_type="api_registration",
        resource_id=str(reg_id), details=update_data,
        ip_address=request.client.host if request.client else None,
    )
    return ApiRegistrationRead.model_validate(reg)


@router.delete("/{reg_id}", status_code=204)
async def delete_registration(
    reg_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("api_registry:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete an API registration. Only allowed in draft status."""
    reg = await _get_registration_or_404(db, reg_id)
    await _check_team_member(db, user, reg.team_id, min_role="admin")

    if reg.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Can only delete draft or rejected registrations.")

    await db.delete(reg)
    await db.flush()

    await log_access(
        db, user=user, action="delete", resource_type="api_registration",
        resource_id=str(reg_id),
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# Submission & Review Workflow
# ---------------------------------------------------------------------------

@router.post("/{reg_id}/submit", response_model=ApiRegistrationRead)
async def submit_for_review(
    reg_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("api_registry:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Submit a draft API for review."""
    reg = await _get_registration_or_404(db, reg_id)
    await _check_team_member(db, user, reg.team_id, min_role="member")

    if reg.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft APIs can be submitted for review.")

    reg.status = "pending_review"
    reg.submitted_at = datetime.now(timezone.utc)
    await db.flush()

    await log_access(
        db, user=user, action="submit", resource_type="api_registration",
        resource_id=str(reg_id),
        ip_address=request.client.host if request.client else None,
    )
    return ApiRegistrationRead.model_validate(reg)


@router.post("/{reg_id}/review", response_model=ApiRegistrationRead)
async def review_registration(
    reg_id: uuid.UUID,
    body: ApiRegistrationReview,
    request: Request,
    user: User = Depends(require_permission("api_registry:approve")),
    db: AsyncSession = Depends(get_db_session),
):
    """Approve or reject a pending API registration. Requires approval permission."""
    reg = await _get_registration_or_404(db, reg_id)

    if reg.status != "pending_review":
        raise HTTPException(status_code=400, detail="Only pending APIs can be reviewed.")

    reg.reviewed_by = user.id
    reg.reviewed_at = datetime.now(timezone.utc)
    reg.review_notes = body.notes

    if body.action == "approve":
        reg.status = "approved"
    else:
        reg.status = "rejected"

    await db.flush()

    await log_access(
        db, user=user, action=f"review_{body.action}", resource_type="api_registration",
        resource_id=str(reg_id), details={"action": body.action, "notes": body.notes},
        ip_address=request.client.host if request.client else None,
    )
    return ApiRegistrationRead.model_validate(reg)


@router.post("/{reg_id}/activate", response_model=ApiRegistrationRead)
async def activate_registration(
    reg_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("api_registry:approve")),
    db: AsyncSession = Depends(get_db_session),
):
    """Activate an approved API: provisions Kong service + route."""
    reg = await _get_registration_or_404(db, reg_id)

    if reg.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved APIs can be activated.")

    # Provision in Kong
    service_id, route_id = await _provision_kong_service(reg)
    reg.kong_service_id = service_id
    reg.kong_route_id = route_id
    reg.gateway_path = reg.gateway_path or f"/api/{reg.slug}"
    reg.status = "active"
    reg.activated_at = datetime.now(timezone.utc)
    await db.flush()

    await log_access(
        db, user=user, action="activate", resource_type="api_registration",
        resource_id=str(reg_id),
        details={"kong_service_id": service_id, "kong_route_id": route_id},
        ip_address=request.client.host if request.client else None,
    )
    return ApiRegistrationRead.model_validate(reg)


@router.post("/{reg_id}/status", response_model=ApiRegistrationRead)
async def change_status(
    reg_id: uuid.UUID,
    body: ApiRegistrationStatusChange,
    request: Request,
    user: User = Depends(require_permission("api_registry:approve")),
    db: AsyncSession = Depends(get_db_session),
):
    """Change status of an active/deprecated API (deprecate, reactivate, retire)."""
    reg = await _get_registration_or_404(db, reg_id)

    allowed = STATUS_TRANSITIONS.get(reg.status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{reg.status}' to '{body.status}'. Allowed: {allowed}",
        )

    old_status = reg.status
    reg.status = body.status

    # If retiring, deprovision from Kong
    if body.status == "retired":
        await _deprovision_kong_service(reg)
        reg.kong_service_id = None
        reg.kong_route_id = None

    await db.flush()

    await log_access(
        db, user=user, action="change_status", resource_type="api_registration",
        resource_id=str(reg_id),
        details={"old_status": old_status, "new_status": body.status},
        ip_address=request.client.host if request.client else None,
    )
    return ApiRegistrationRead.model_validate(reg)


# ---------------------------------------------------------------------------
# Usage Metrics (fetched from Kong/Prometheus)
# ---------------------------------------------------------------------------

@router.get("/{reg_id}/usage")
async def get_usage_metrics(
    reg_id: uuid.UUID,
    user: User = Depends(require_permission("api_registry:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Get usage metrics for a registered API from Kong status API."""
    reg = await _get_registration_or_404(db, reg_id)

    if not reg.kong_service_id:
        return {
            "status": reg.status,
            "message": "API is not yet active in Kong.",
            "metrics": None,
        }

    settings = get_settings()
    service_name = f"api-reg-{reg.slug}"

    # Fetch service-level status from Kong
    try:
        service_data = await _kong_request("GET", f"/services/{service_name}")
    except HTTPException:
        service_data = None

    # Fetch route info
    try:
        route_name = f"api-reg-{reg.slug}-route"
        route_data = await _kong_request("GET", f"/services/{service_name}/routes/{route_name}")
    except HTTPException:
        route_data = None

    # Fetch plugins
    try:
        plugins_data = await _kong_request("GET", f"/services/{service_name}/plugins")
        plugins = plugins_data.get("data", []) if plugins_data else []
    except HTTPException:
        plugins = []

    return {
        "api_id": str(reg.id),
        "api_name": reg.name,
        "api_slug": reg.slug,
        "status": reg.status,
        "gateway_path": reg.gateway_path,
        "kong_service_id": reg.kong_service_id,
        "kong_route_id": reg.kong_route_id,
        "service": {
            "protocol": service_data.get("protocol") if service_data else None,
            "host": service_data.get("host") if service_data else None,
            "port": service_data.get("port") if service_data else None,
            "enabled": service_data.get("enabled") if service_data else None,
        },
        "route": {
            "paths": route_data.get("paths") if route_data else None,
            "methods": route_data.get("methods") if route_data else None,
            "protocols": route_data.get("protocols") if route_data else None,
        },
        "plugins": [
            {"name": p.get("name"), "enabled": p.get("enabled"), "config": p.get("config", {})}
            for p in plugins
        ],
        "rate_limits": {
            "second": reg.rate_limit_second,
            "minute": reg.rate_limit_minute,
            "hour": reg.rate_limit_hour,
        },
    }
