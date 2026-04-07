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
# Team
# ---------------------------------------------------------------------------

class TeamBase(BaseModel):
    name: str = Field(..., max_length=256)
    slug: str = Field(..., max_length=128, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    description: Optional[str] = None
    contact_email: EmailStr
    metadata: Optional[dict] = None


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase, OrmModel):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    metadata: Optional[dict] = None
    is_active: Optional[bool] = None


class TeamDetail(TeamRead):
    """Team with member count and API count."""
    member_count: int = 0
    api_count: int = 0


# ---------------------------------------------------------------------------
# Team Member
# ---------------------------------------------------------------------------

class TeamMemberAdd(BaseModel):
    user_id: uuid.UUID
    role: str = Field("member", pattern=r"^(owner|admin|member|viewer)$")


class TeamMemberRead(OrmModel):
    id: uuid.UUID
    team_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None


class TeamMemberUpdate(BaseModel):
    role: str = Field(..., pattern=r"^(owner|admin|member|viewer)$")


# ---------------------------------------------------------------------------
# API Registration
# ---------------------------------------------------------------------------

class ApiRegistrationBase(BaseModel):
    name: str = Field(..., max_length=256)
    slug: str = Field(..., max_length=128, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    description: Optional[str] = None
    version: str = Field("v1", max_length=32)
    api_type: str = Field("rest", pattern=r"^(rest|graphql|grpc|websocket)$")
    documentation_url: Optional[str] = None
    tags: Optional[list[str]] = None
    upstream_url: str
    upstream_protocol: str = Field("https", pattern=r"^(http|https|grpc|grpcs)$")
    health_check_path: Optional[str] = "/health"
    gateway_path: Optional[str] = None
    rate_limit_second: int = Field(5, ge=0)
    rate_limit_minute: int = Field(100, ge=0)
    rate_limit_hour: int = Field(3000, ge=0)
    auth_type: str = Field("key-auth", pattern=r"^(key-auth|oauth2|jwt|none)$")
    requires_approval: bool = True


class ApiRegistrationCreate(ApiRegistrationBase):
    team_id: uuid.UUID


class ApiRegistrationRead(ApiRegistrationBase, OrmModel):
    id: uuid.UUID
    team_id: uuid.UUID
    kong_service_id: Optional[str] = None
    kong_route_id: Optional[str] = None
    status: str
    submitted_at: Optional[datetime] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ApiRegistrationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=32)
    documentation_url: Optional[str] = None
    tags: Optional[list[str]] = None
    upstream_url: Optional[str] = None
    upstream_protocol: Optional[str] = None
    health_check_path: Optional[str] = None
    gateway_path: Optional[str] = None
    rate_limit_second: Optional[int] = Field(None, ge=0)
    rate_limit_minute: Optional[int] = Field(None, ge=0)
    rate_limit_hour: Optional[int] = Field(None, ge=0)
    auth_type: Optional[str] = None
    requires_approval: Optional[bool] = None


class ApiRegistrationReview(BaseModel):
    action: str = Field(..., pattern=r"^(approve|reject)$")
    notes: Optional[str] = None


class ApiRegistrationStatusChange(BaseModel):
    status: str = Field(..., pattern=r"^(active|deprecated|retired)$")


# ---------------------------------------------------------------------------
# AI Prompts
# ---------------------------------------------------------------------------

class AIPromptBase(BaseModel):
    slug: str = Field(..., max_length=100, description="URL-safe unique identifier")
    name: str = Field(..., max_length=255, description="Human-friendly display name")
    category: str = Field(..., description="anomaly, rate_limit, routing, transform, documentation")
    system_prompt: str = Field(..., description="System prompt template text")
    model: Optional[str] = Field(None, max_length=100, description="Optional model override")
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, ge=1, le=128000)
    is_active: bool = True


class AIPromptCreate(AIPromptBase):
    pass


class AIPromptRead(AIPromptBase, OrmModel):
    id: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class AIPromptUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    system_prompt: Optional[str] = None
    model: Optional[str] = Field(None, max_length=100)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=128000)
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Forward-ref resolution
# ---------------------------------------------------------------------------
CurrentUser.model_rebuild()
