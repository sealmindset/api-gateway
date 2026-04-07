"""SQLAlchemy async models for the API Gateway Admin Panel."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


# ---------------------------------------------------------------------------
# Engine & session factory (initialised at app startup)
# ---------------------------------------------------------------------------

engine = None
async_session_factory: Optional[async_sessionmaker] = None


async def init_db() -> None:
    """Create the async engine and session factory."""
    global engine, async_session_factory
    settings = get_settings()
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(
        db_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_max_size,
        pool_pre_ping=True,
    )
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def close_db() -> None:
    """Dispose of the connection pool."""
    global engine
    if engine is not None:
        await engine.dispose()


async def get_db_session():
    """FastAPI dependency that yields an async database session."""
    if async_session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base with async attribute support."""
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    """Admin-panel user, synced from Microsoft Entra ID."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    entra_oid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    roles: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
        foreign_keys="[UserRole.user_id]",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class Role(Base):
    """RBAC role definition."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    """Many-to-many association between users and roles."""

    __tablename__ = "user_roles"
    __table_args__ = (
        Index("ix_user_roles_user_role", "user_id", "role_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="user_roles", foreign_keys=[user_id])
    role: Mapped["Role"] = relationship(back_populates="user_roles")


class Subscriber(Base):
    """External API subscriber / consumer."""

    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    organization: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="subscriber", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="subscriber", cascade="all, delete-orphan")


class ApiKey(Base):
    """API key issued to a subscriber."""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_prefix", "key_prefix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    rate_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    subscriber: Mapped["Subscriber"] = relationship(back_populates="api_keys")


class Plan(Base):
    """Subscription plan definition."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rate_limit_second: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rate_limit_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    rate_limit_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    max_api_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    allowed_endpoints: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")


class Subscription(Base):
    """A subscriber's subscription to a plan."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rate_limit_per_second: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_per_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowed_endpoints: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    subscriber: Mapped["Subscriber"] = relationship(back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship(back_populates="subscriptions")


class AuditLog(Base):
    """Immutable audit trail for admin actions."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")


class Team(Base):
    """Organizational unit that owns APIs."""

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")
    api_registrations: Mapped[list["ApiRegistration"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    """Maps users to teams with roles (owner, admin, member, viewer)."""

    __tablename__ = "team_members"
    __table_args__ = (
        Index("ix_team_members_team_user", "team_id", "user_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


class ApiRegistration(Base):
    """An API registered by a team for exposure through the Kong gateway."""

    __tablename__ = "api_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)

    # API metadata
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    api_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rest")
    documentation_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)

    # Upstream target
    upstream_url: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_protocol: Mapped[str] = mapped_column(String(10), nullable=False, default="https")
    health_check_path: Mapped[Optional[str]] = mapped_column(String(256), default="/health")

    # Kong integration
    kong_service_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kong_route_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    gateway_path: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Rate limits
    rate_limit_second: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rate_limit_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    rate_limit_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)

    # Auth
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="key-auth")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Workflow
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="api_registrations")
    reviewer: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by])


class AIPrompt(Base):
    """AI prompt template managed via the admin panel."""

    __tablename__ = "ai_prompts"
    __table_args__ = (
        Index("ix_ai_prompts_category", "category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    temperature: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False, default=Decimal("0.3"))
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
