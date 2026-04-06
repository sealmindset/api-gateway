"""Pydantic schemas for API request / response serialisation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Shared mixins
# ---------------------------------------------------------------------------

class TimestampMixin(BaseModel):
    created_at: datetime


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserBase(BaseModel):
    email: EmailStr
    name: str


class UserRead(UserBase, OrmModel):
    id: uuid.UUID
    entra_oid: str
    roles: Optional[dict] = None
    created_at: datetime
    last_login: Optional[datetime] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    roles: Optional[dict] = None


class CurrentUser(UserRead):
    """Extended user info returned from /auth/me."""
    assigned_roles: list[RoleRead] = []


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

class RoleBase(BaseModel):
    name: str = Field(..., max_length=64)
    description: Optional[str] = None
    permissions: dict = Field(default_factory=dict)


class RoleCreate(RoleBase):
    pass


class RoleRead(RoleBase, OrmModel):
    id: uuid.UUID
    created_at: datetime


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = None
    permissions: Optional[dict] = None


# ---------------------------------------------------------------------------
# UserRole
# ---------------------------------------------------------------------------

class UserRoleAssign(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID


class UserRoleRead(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    assigned_by: Optional[uuid.UUID] = None
    assigned_at: datetime


# ---------------------------------------------------------------------------
# Subscriber
# ---------------------------------------------------------------------------

class SubscriberBase(BaseModel):
    name: str = Field(..., max_length=256)
    email: EmailStr
    organization: Optional[str] = Field(None, max_length=256)
    tier: str = Field("free", max_length=32)


class SubscriberCreate(SubscriberBase):
    pass


class SubscriberRead(SubscriberBase, OrmModel):
    id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime


class SubscriberUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    email: Optional[EmailStr] = None
    organization: Optional[str] = Field(None, max_length=256)
    tier: Optional[str] = Field(None, max_length=32)
    status: Optional[str] = Field(None, max_length=32)


# ---------------------------------------------------------------------------
# API Key
# ---------------------------------------------------------------------------

class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=128)
    scopes: Optional[list[str]] = None
    rate_limit: Optional[int] = None
    expires_at: Optional[datetime] = None


class ApiKeyRead(OrmModel):
    id: uuid.UUID
    subscriber_id: uuid.UUID
    key_prefix: str
    name: str
    scopes: Optional[Any] = None
    rate_limit: Optional[int] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(ApiKeyRead):
    """Returned only on creation -- includes the raw key (shown once)."""
    raw_key: str


class ApiKeyRotateResponse(BaseModel):
    old_key_id: uuid.UUID
    new_key: ApiKeyCreated


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

class PlanBase(BaseModel):
    name: str = Field(..., max_length=64)
    description: Optional[str] = None
    rate_limit_second: int = 1
    rate_limit_minute: int = 30
    rate_limit_hour: int = 500
    max_api_keys: int = 2
    allowed_endpoints: Optional[list[str]] = None
    price_cents: int = 0
    is_active: bool = True


class PlanCreate(PlanBase):
    pass


class PlanRead(PlanBase, OrmModel):
    id: uuid.UUID
    created_at: datetime


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = None
    rate_limit_second: Optional[int] = None
    rate_limit_minute: Optional[int] = None
    rate_limit_hour: Optional[int] = None
    max_api_keys: Optional[int] = None
    allowed_endpoints: Optional[list[str]] = None
    price_cents: Optional[int] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

class SubscriptionBase(BaseModel):
    subscriber_id: uuid.UUID
    plan_id: uuid.UUID
    starts_at: datetime
    expires_at: Optional[datetime] = None
    rate_limit_per_second: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_hour: Optional[int] = None
    allowed_endpoints: Optional[list[str]] = None


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionRead(SubscriptionBase, OrmModel):
    id: uuid.UUID
    status: str
    created_at: datetime


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    rate_limit_per_second: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_hour: Optional[int] = None
    allowed_endpoints: Optional[list[str]] = None


class BulkSubscriptionAction(BaseModel):
    subscription_ids: list[uuid.UUID]
    action: str = Field(..., description="Action to perform: activate, suspend, cancel")


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLogRead(OrmModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime


class AuditLogFilter(BaseModel):
    user_id: Optional[uuid.UUID] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Gateway (Kong)
# ---------------------------------------------------------------------------

class KongServiceRead(BaseModel):
    id: str
    name: Optional[str] = None
    host: str
    port: int
    protocol: str
    path: Optional[str] = None
    enabled: bool = True


class KongRouteRead(BaseModel):
    id: str
    name: Optional[str] = None
    protocols: list[str] = []
    hosts: Optional[list[str]] = None
    paths: Optional[list[str]] = None
    methods: Optional[list[str]] = None


class KongPluginRead(BaseModel):
    id: str
    name: str
    service: Optional[dict] = None
    route: Optional[dict] = None
    consumer: Optional[dict] = None
    config: dict = {}
    enabled: bool = True


class KongConsumerRead(BaseModel):
    id: str
    username: Optional[str] = None
    custom_id: Optional[str] = None


class KongHealthResponse(BaseModel):
    database: dict
    server: dict


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Forward-ref resolution
# ---------------------------------------------------------------------------
CurrentUser.model_rebuild()
