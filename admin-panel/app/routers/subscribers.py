"""Subscriber management routes: CRUD, API keys, Kong sync."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.middleware.auth import get_current_user
from app.middleware.rbac import log_access, require_permission
from app.models.database import ApiKey, Subscriber, Subscription, User, get_db_session
from app.models.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    ApiKeyRotateResponse,
    PaginatedResponse,
    SubscriberCreate,
    SubscriberRead,
    SubscriberUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscribers", tags=["subscribers"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_api_key() -> tuple[str, str, str]:
    """Generate a random API key, returning (raw_key, key_hash, key_prefix)."""
    raw = f"gw_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:8]
    return raw, key_hash, prefix


async def _sync_consumer_to_kong(subscriber: Subscriber, api_key_raw: Optional[str] = None) -> None:
    """Create or update a Kong consumer and optionally attach a key-auth credential."""
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.kong_admin_token:
        headers["Authorization"] = f"Bearer {settings.kong_admin_token}"

    async with httpx.AsyncClient(base_url=settings.kong_admin_url, headers=headers, timeout=10) as client:
        # Upsert consumer
        resp = await client.put(
            f"/consumers/{subscriber.id}",
            json={
                "username": str(subscriber.id),
                "custom_id": subscriber.email,
            },
        )
        if resp.status_code not in (200, 201):
            logger.error("Kong consumer upsert failed: %s %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="Failed to sync consumer to Kong.")

        # Attach key-auth credential if a raw key was provided
        if api_key_raw:
            resp = await client.post(
                f"/consumers/{subscriber.id}/key-auth",
                json={"key": api_key_raw},
            )
            if resp.status_code not in (200, 201):
                logger.error("Kong key-auth creation failed: %s %s", resp.status_code, resp.text)
                raise HTTPException(status_code=502, detail="Failed to provision API key in Kong.")


# ---------------------------------------------------------------------------
# Subscriber CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_subscribers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    tier: Optional[str] = None,
    search: Optional[str] = None,
    _auth: User = Depends(require_permission("subscribers:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List subscribers with pagination and optional filters."""
    query = select(Subscriber)
    count_query = select(func.count(Subscriber.id))

    if status_filter:
        query = query.where(Subscriber.status == status_filter)
        count_query = count_query.where(Subscriber.status == status_filter)
    if tier:
        query = query.where(Subscriber.tier == tier)
        count_query = count_query.where(Subscriber.tier == tier)
    if search:
        like = f"%{search}%"
        query = query.where(
            Subscriber.name.ilike(like) | Subscriber.email.ilike(like) | Subscriber.organization.ilike(like)
        )
        count_query = count_query.where(
            Subscriber.name.ilike(like) | Subscriber.email.ilike(like) | Subscriber.organization.ilike(like)
        )

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(Subscriber.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [SubscriberRead.model_validate(s) for s in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=SubscriberRead, status_code=201)
async def create_subscriber(
    body: SubscriberCreate,
    request: Request,
    user: User = Depends(require_permission("subscribers:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new subscriber."""
    subscriber = Subscriber(**body.model_dump())
    db.add(subscriber)
    await db.flush()

    await log_access(
        db,
        user=user,
        action="create",
        resource_type="subscriber",
        resource_id=str(subscriber.id),
        details=body.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return SubscriberRead.model_validate(subscriber)


@router.get("/{subscriber_id}", response_model=SubscriberRead)
async def get_subscriber(
    subscriber_id: uuid.UUID,
    _auth: User = Depends(require_permission("subscribers:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a single subscriber by ID."""
    result = await db.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found.")
    return SubscriberRead.model_validate(subscriber)


@router.patch("/{subscriber_id}", response_model=SubscriberRead)
async def update_subscriber(
    subscriber_id: uuid.UUID,
    body: SubscriberUpdate,
    request: Request,
    user: User = Depends(require_permission("subscribers:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Update subscriber fields."""
    result = await db.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscriber, field, value)
    await db.flush()

    await log_access(
        db,
        user=user,
        action="update",
        resource_type="subscriber",
        resource_id=str(subscriber_id),
        details=update_data,
        ip_address=request.client.host if request.client else None,
    )
    return SubscriberRead.model_validate(subscriber)


@router.delete("/{subscriber_id}", status_code=204)
async def delete_subscriber(
    subscriber_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("subscribers:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Soft-delete a subscriber by setting status to 'deleted'."""
    result = await db.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    subscriber = result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found.")

    subscriber.status = "deleted"
    await db.flush()

    await log_access(
        db,
        user=user,
        action="delete",
        resource_type="subscriber",
        resource_id=str(subscriber_id),
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------

@router.get("/{subscriber_id}/keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    subscriber_id: uuid.UUID,
    _auth: User = Depends(require_permission("api_keys:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List all API keys for a subscriber."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.subscriber_id == subscriber_id).order_by(ApiKey.created_at.desc())
    )
    return [ApiKeyRead.model_validate(k) for k in result.scalars().all()]


@router.post("/{subscriber_id}/keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    subscriber_id: uuid.UUID,
    body: ApiKeyCreate,
    request: Request,
    user: User = Depends(require_permission("api_keys:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate a new API key for a subscriber and sync to Kong."""
    # Verify subscriber exists
    sub_result = await db.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    subscriber = sub_result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Subscriber not found.")

    raw_key, key_hash, prefix = _generate_api_key()
    api_key = ApiKey(
        subscriber_id=subscriber_id,
        key_hash=key_hash,
        key_prefix=prefix,
        name=body.name,
        scopes=body.scopes,
        rate_limit=body.rate_limit,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    await db.flush()

    # Sync to Kong
    try:
        await _sync_consumer_to_kong(subscriber, api_key_raw=raw_key)
    except HTTPException:
        logger.warning("Kong sync failed during key creation for subscriber %s", subscriber_id)

    await log_access(
        db,
        user=user,
        action="create",
        resource_type="api_key",
        resource_id=str(api_key.id),
        details={"subscriber_id": str(subscriber_id), "key_prefix": prefix, "name": body.name},
        ip_address=request.client.host if request.client else None,
    )

    result = ApiKeyCreated.model_validate(api_key)
    result.raw_key = raw_key
    return result


@router.post("/{subscriber_id}/keys/{key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_api_key(
    subscriber_id: uuid.UUID,
    key_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("api_keys:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Rotate an API key: revoke the old one and issue a new one with the same config."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.subscriber_id == subscriber_id)
    )
    old_key = result.scalar_one_or_none()
    if old_key is None:
        raise HTTPException(status_code=404, detail="API key not found.")

    # Deactivate old key
    old_key.is_active = False

    # Create new key with same config
    raw_key, key_hash, prefix = _generate_api_key()
    new_key = ApiKey(
        subscriber_id=subscriber_id,
        key_hash=key_hash,
        key_prefix=prefix,
        name=old_key.name,
        scopes=old_key.scopes,
        rate_limit=old_key.rate_limit,
        expires_at=old_key.expires_at,
    )
    db.add(new_key)
    await db.flush()

    # Sync new key to Kong
    sub_result = await db.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    subscriber = sub_result.scalar_one_or_none()
    if subscriber:
        try:
            await _sync_consumer_to_kong(subscriber, api_key_raw=raw_key)
        except HTTPException:
            logger.warning("Kong sync failed during key rotation for subscriber %s", subscriber_id)

    await log_access(
        db,
        user=user,
        action="rotate",
        resource_type="api_key",
        resource_id=str(key_id),
        details={"new_key_id": str(new_key.id), "subscriber_id": str(subscriber_id)},
        ip_address=request.client.host if request.client else None,
    )

    new_key_response = ApiKeyCreated.model_validate(new_key)
    new_key_response.raw_key = raw_key
    return ApiKeyRotateResponse(old_key_id=key_id, new_key=new_key_response)


@router.delete("/{subscriber_id}/keys/{key_id}", status_code=204)
async def revoke_api_key(
    subscriber_id: uuid.UUID,
    key_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("api_keys:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Revoke (deactivate) an API key."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.subscriber_id == subscriber_id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found.")

    api_key.is_active = False
    await db.flush()

    await log_access(
        db,
        user=user,
        action="revoke",
        resource_type="api_key",
        resource_id=str(key_id),
        details={"subscriber_id": str(subscriber_id)},
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# Rate-limit override
# ---------------------------------------------------------------------------

@router.put("/{subscriber_id}/rate-limit")
async def set_rate_limit_override(
    subscriber_id: uuid.UUID,
    rate_limit_per_second: Optional[int] = None,
    rate_limit_per_minute: Optional[int] = None,
    rate_limit_per_hour: Optional[int] = None,
    request: Request = None,
    user: User = Depends(require_permission("subscribers:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Set rate-limit overrides on the subscriber's active subscription."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.subscriber_id == subscriber_id,
            Subscription.status == "active",
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No active subscription found.")

    if rate_limit_per_second is not None:
        subscription.rate_limit_per_second = rate_limit_per_second
    if rate_limit_per_minute is not None:
        subscription.rate_limit_per_minute = rate_limit_per_minute
    if rate_limit_per_hour is not None:
        subscription.rate_limit_per_hour = rate_limit_per_hour
    await db.flush()

    await log_access(
        db,
        user=user,
        action="update_rate_limit",
        resource_type="subscription",
        resource_id=str(subscription.id),
        details={
            "subscriber_id": str(subscriber_id),
            "per_second": rate_limit_per_second,
            "per_minute": rate_limit_per_minute,
            "per_hour": rate_limit_per_hour,
        },
        ip_address=request.client.host if request and request.client else None,
    )
    return {"detail": "Rate limits updated.", "subscription_id": str(subscription.id)}
