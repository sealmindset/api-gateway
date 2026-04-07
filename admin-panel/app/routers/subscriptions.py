"""Subscription and plan management routes."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.middleware.rbac import log_access, require_permission
from app.models.database import Plan, Subscriber, Subscription, User, get_db_session
from app.models.schemas import (
    BulkSubscriptionAction,
    PaginatedResponse,
    PlanCreate,
    PlanRead,
    PlanUpdate,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["subscriptions"])

# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

plan_router = APIRouter(prefix="/plans", tags=["plans"])


@plan_router.get("", response_model=list[PlanRead])
async def list_plans(
    active_only: bool = Query(True),
    _auth: User = Depends(require_permission("subscriptions:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List all subscription plans."""
    query = select(Plan).order_by(Plan.price_cents)
    if active_only:
        query = query.where(Plan.is_active.is_(True))
    result = await db.execute(query)
    return [PlanRead.model_validate(p) for p in result.scalars().all()]


@plan_router.post("", response_model=PlanRead, status_code=201)
async def create_plan(
    body: PlanCreate,
    request: Request,
    user: User = Depends(require_permission("subscriptions:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new subscription plan."""
    plan = Plan(**body.model_dump())
    db.add(plan)
    await db.flush()

    await log_access(
        db, user=user, action="create", resource_type="plan",
        resource_id=str(plan.id), details=body.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return PlanRead.model_validate(plan)


@plan_router.get("/{plan_id}", response_model=PlanRead)
async def get_plan(
    plan_id: uuid.UUID,
    _auth: User = Depends(require_permission("subscriptions:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a single plan by ID."""
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return PlanRead.model_validate(plan)


@plan_router.patch("/{plan_id}", response_model=PlanRead)
async def update_plan(
    plan_id: uuid.UUID,
    body: PlanUpdate,
    request: Request,
    user: User = Depends(require_permission("subscriptions:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Update plan fields."""
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)
    await db.flush()

    await log_access(
        db, user=user, action="update", resource_type="plan",
        resource_id=str(plan_id), details=update_data,
        ip_address=request.client.host if request.client else None,
    )
    return PlanRead.model_validate(plan)


@plan_router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("subscriptions:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Deactivate a plan (soft delete)."""
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")

    plan.is_active = False
    await db.flush()

    await log_access(
        db, user=user, action="deactivate", resource_type="plan",
        resource_id=str(plan_id),
        ip_address=request.client.host if request.client else None,
    )


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

sub_router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@sub_router.get("", response_model=PaginatedResponse)
async def list_subscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subscriber_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    _auth: User = Depends(require_permission("subscriptions:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """List subscriptions with optional filters."""
    query = select(Subscription)
    count_query = select(func.count(Subscription.id))

    if subscriber_id:
        query = query.where(Subscription.subscriber_id == subscriber_id)
        count_query = count_query.where(Subscription.subscriber_id == subscriber_id)
    if status_filter:
        query = query.where(Subscription.status == status_filter)
        count_query = count_query.where(Subscription.status == status_filter)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(Subscription.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [SubscriptionRead.model_validate(s) for s in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@sub_router.post("", response_model=SubscriptionRead, status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    request: Request,
    user: User = Depends(require_permission("subscriptions:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a subscription for a subscriber."""
    # Verify subscriber and plan exist
    sub_result = await db.execute(select(Subscriber).where(Subscriber.id == body.subscriber_id))
    if sub_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Subscriber not found.")

    plan_result = await db.execute(select(Plan).where(Plan.id == body.plan_id))
    if plan_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Plan not found.")

    subscription = Subscription(**body.model_dump())
    db.add(subscription)
    await db.flush()

    await log_access(
        db, user=user, action="create", resource_type="subscription",
        resource_id=str(subscription.id), details=body.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return SubscriptionRead.model_validate(subscription)


@sub_router.get("/{subscription_id}", response_model=SubscriptionRead)
async def get_subscription(
    subscription_id: uuid.UUID,
    _auth: User = Depends(require_permission("subscriptions:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a subscription by ID."""
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    return SubscriptionRead.model_validate(subscription)


@sub_router.patch("/{subscription_id}", response_model=SubscriptionRead)
async def update_subscription(
    subscription_id: uuid.UUID,
    body: SubscriptionUpdate,
    request: Request,
    user: User = Depends(require_permission("subscriptions:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Modify a subscription."""
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscription, field, value)
    await db.flush()
    await db.refresh(subscription)

    await log_access(
        db, user=user, action="update", resource_type="subscription",
        resource_id=str(subscription_id), details=body.model_dump(exclude_unset=True, mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    return SubscriptionRead.model_validate(subscription)


@sub_router.delete("/{subscription_id}", status_code=204)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("subscriptions:delete")),
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel a subscription."""
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")

    subscription.status = "cancelled"
    await db.flush()

    await log_access(
        db, user=user, action="cancel", resource_type="subscription",
        resource_id=str(subscription_id),
        ip_address=request.client.host if request.client else None,
    )


@sub_router.post("/bulk", response_model=dict)
async def bulk_subscription_action(
    body: BulkSubscriptionAction,
    request: Request,
    user: User = Depends(require_permission("subscriptions:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """Perform a bulk action on multiple subscriptions.

    Supported actions: activate, suspend, cancel.
    """
    valid_actions = {"activate": "active", "suspend": "suspended", "cancel": "cancelled"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {list(valid_actions.keys())}")

    new_status = valid_actions[body.action]
    updated = 0

    for sub_id in body.subscription_ids:
        result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
        subscription = result.scalar_one_or_none()
        if subscription is not None:
            subscription.status = new_status
            updated += 1

    await db.flush()

    await log_access(
        db, user=user, action=f"bulk_{body.action}", resource_type="subscription",
        details={"count": updated, "ids": [str(i) for i in body.subscription_ids]},
        ip_address=request.client.host if request.client else None,
    )
    return {"detail": f"Bulk {body.action} completed.", "updated": updated}


# ---------------------------------------------------------------------------
# Usage stats (placeholder)
# ---------------------------------------------------------------------------

@sub_router.get("/{subscription_id}/usage")
async def get_subscription_usage(
    subscription_id: uuid.UUID,
    _auth: User = Depends(require_permission("subscriptions:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """Return usage statistics for a subscription.

    In production this would query a metrics store (e.g., Prometheus, ClickHouse).
    """
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")

    return {
        "subscription_id": str(subscription_id),
        "status": subscription.status,
        "rate_limits": {
            "per_second": subscription.rate_limit_per_second,
            "per_minute": subscription.rate_limit_per_minute,
            "per_hour": subscription.rate_limit_per_hour,
        },
        "note": "Usage metrics integration pending.",
    }


# Combine both routers for inclusion by main app
router.include_router(plan_router)
router.include_router(sub_router)
