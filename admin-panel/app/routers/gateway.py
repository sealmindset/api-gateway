"""Kong Gateway management routes: services, routes, plugins, consumers, health."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.middleware.rbac import require_permission
from app.models.database import User
from app.models.schemas import (
    KongConsumerRead,
    KongHealthResponse,
    KongPluginRead,
    KongRouteRead,
    KongServiceRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway", tags=["gateway"])


# ---------------------------------------------------------------------------
# Kong HTTP client helper
# ---------------------------------------------------------------------------

async def _kong_request(
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
) -> Any:
    """Send a request to the Kong Admin API and return the parsed JSON response."""
    settings = get_settings()
    headers: dict[str, str] = {"Accept": "application/json"}
    if settings.kong_admin_token:
        headers["Authorization"] = f"Bearer {settings.kong_admin_token}"

    async with httpx.AsyncClient(base_url=settings.kong_admin_url, headers=headers, timeout=15) as client:
        resp = await client.request(method, path, json=json_body)

    if resp.status_code >= 400:
        logger.error("Kong API error: %s %s -> %s %s", method, path, resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Kong Admin API returned {resp.status_code}: {resp.text[:500]}",
        )
    if resp.status_code == 204:
        return None
    return resp.json()


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@router.get("/services", response_model=list[KongServiceRead])
async def list_services(
    _auth: User = Depends(require_permission("gateway:read")),
):
    """List all services registered in Kong."""
    data = await _kong_request("GET", "/services")
    return data.get("data", [])


@router.get("/services/{service_id}", response_model=KongServiceRead)
async def get_service(
    service_id: str,
    _auth: User = Depends(require_permission("gateway:read")),
):
    """Get a specific Kong service."""
    return await _kong_request("GET", f"/services/{service_id}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/routes", response_model=list[KongRouteRead])
async def list_routes(
    _auth: User = Depends(require_permission("gateway:read")),
):
    """List all routes registered in Kong."""
    data = await _kong_request("GET", "/routes")
    return data.get("data", [])


@router.get("/routes/{route_id}", response_model=KongRouteRead)
async def get_route(
    route_id: str,
    _auth: User = Depends(require_permission("gateway:read")),
):
    """Get a specific Kong route."""
    return await _kong_request("GET", f"/routes/{route_id}")


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------

@router.get("/plugins", response_model=list[KongPluginRead])
async def list_plugins(
    _auth: User = Depends(require_permission("gateway:read")),
):
    """List all plugins registered in Kong."""
    data = await _kong_request("GET", "/plugins")
    return data.get("data", [])


@router.post("/plugins", response_model=KongPluginRead, status_code=201)
async def create_plugin(
    body: dict,
    _auth: User = Depends(require_permission("gateway:write")),
):
    """Add a new plugin to Kong."""
    return await _kong_request("POST", "/plugins", json_body=body)


@router.patch("/plugins/{plugin_id}", response_model=KongPluginRead)
async def update_plugin(
    plugin_id: str,
    body: dict,
    _auth: User = Depends(require_permission("gateway:write")),
):
    """Update plugin configuration."""
    return await _kong_request("PATCH", f"/plugins/{plugin_id}", json_body=body)


@router.delete("/plugins/{plugin_id}", status_code=204)
async def delete_plugin(
    plugin_id: str,
    _auth: User = Depends(require_permission("gateway:write")),
):
    """Remove a plugin from Kong."""
    await _kong_request("DELETE", f"/plugins/{plugin_id}")


# ---------------------------------------------------------------------------
# Consumers
# ---------------------------------------------------------------------------

@router.get("/consumers", response_model=list[KongConsumerRead])
async def list_consumers(
    _auth: User = Depends(require_permission("gateway:read")),
):
    """List all consumers in Kong."""
    data = await _kong_request("GET", "/consumers")
    return data.get("data", [])


@router.get("/consumers/{consumer_id}", response_model=KongConsumerRead)
async def get_consumer(
    consumer_id: str,
    _auth: User = Depends(require_permission("gateway:read")),
):
    """Get a specific Kong consumer."""
    return await _kong_request("GET", f"/consumers/{consumer_id}")


@router.post("/consumers", response_model=KongConsumerRead, status_code=201)
async def create_consumer(
    body: dict,
    _auth: User = Depends(require_permission("gateway:write")),
):
    """Create a new consumer in Kong."""
    return await _kong_request("POST", "/consumers", json_body=body)


@router.delete("/consumers/{consumer_id}", status_code=204)
async def delete_consumer(
    consumer_id: str,
    _auth: User = Depends(require_permission("gateway:write")),
):
    """Remove a consumer from Kong."""
    await _kong_request("DELETE", f"/consumers/{consumer_id}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=KongHealthResponse)
async def kong_health(
    _auth: User = Depends(require_permission("gateway:read")),
):
    """Return Kong node status and database connectivity info."""
    node_status = await _kong_request("GET", "/status")
    return KongHealthResponse(
        database=node_status.get("database", {}),
        server=node_status.get("server", {}),
    )
