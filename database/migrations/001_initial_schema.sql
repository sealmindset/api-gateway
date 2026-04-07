-- =============================================================================
-- Migration 001: Initial Schema
-- =============================================================================
-- Creates the complete database schema for the API Gateway admin panel.
-- Includes all tables, indexes, default data, triggers, and audit logging.
--
-- This schema matches the SQLAlchemy ORM models in admin-panel/app/models/database.py.
-- Users are authenticated via Microsoft Entra ID (OIDC), not local passwords.
--
-- Run against the 'api_gateway_admin' database.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- Cryptographic functions

-- ---------------------------------------------------------------------------
-- Helper: Auto-update updated_at timestamp trigger function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Helper: Audit log trigger function
-- Records all INSERT, UPDATE, DELETE operations on tracked tables.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION audit_log_trigger_fn()
RETURNS TRIGGER AS $$
DECLARE
    audit_user_id UUID;
    change_details JSONB;
BEGIN
    -- Try to get the current user from session variable (set by the app)
    BEGIN
        audit_user_id := current_setting('app.current_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        audit_user_id := NULL;
    END;

    IF TG_OP = 'DELETE' THEN
        change_details := jsonb_build_object('old', to_jsonb(OLD));
    ELSIF TG_OP = 'INSERT' THEN
        change_details := jsonb_build_object('new', to_jsonb(NEW));
    ELSE  -- UPDATE
        change_details := jsonb_build_object('old', to_jsonb(OLD), 'new', to_jsonb(NEW));
    END IF;

    INSERT INTO audit_logs (
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        ip_address
    ) VALUES (
        audit_user_id,
        TG_OP,
        TG_TABLE_NAME,
        CASE
            WHEN TG_OP = 'DELETE' THEN OLD.id::TEXT
            ELSE NEW.id::TEXT
        END,
        change_details,
        current_setting('app.client_ip', true)
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Tables
-- =============================================================================

-- ---------------------------------------------------------------------------
-- roles: RBAC role definitions with JSON permissions
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(64) NOT NULL UNIQUE,
    description TEXT,
    permissions JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_roles_name ON roles (name);

-- ---------------------------------------------------------------------------
-- users: Admin panel users, synced from Microsoft Entra ID (OIDC)
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(320) NOT NULL UNIQUE,
    name        VARCHAR(256) NOT NULL,
    entra_oid   VARCHAR(128) NOT NULL UNIQUE,
    roles       JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login  TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_entra_oid ON users (entra_oid);

-- ---------------------------------------------------------------------------
-- user_roles: Many-to-many relationship between users and roles
-- ---------------------------------------------------------------------------
CREATE TABLE user_roles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, role_id)
);

CREATE INDEX ix_user_roles_user_role ON user_roles (user_id, role_id);

-- ---------------------------------------------------------------------------
-- plans: Subscription plans with rate limits
-- ---------------------------------------------------------------------------
CREATE TABLE plans (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                VARCHAR(64) NOT NULL UNIQUE,
    description         TEXT,
    rate_limit_second   INTEGER NOT NULL DEFAULT 1,
    rate_limit_minute   INTEGER NOT NULL DEFAULT 30,
    rate_limit_hour     INTEGER NOT NULL DEFAULT 500,
    max_api_keys        INTEGER NOT NULL DEFAULT 2,
    allowed_endpoints   JSONB DEFAULT '[]',
    price_cents         INTEGER NOT NULL DEFAULT 0,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- subscribers: External API consumers / organizations
-- ---------------------------------------------------------------------------
CREATE TABLE subscribers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(256) NOT NULL,
    email           VARCHAR(320) NOT NULL,
    organization    VARCHAR(256),
    tier            VARCHAR(32) NOT NULL DEFAULT 'free',
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscribers_email ON subscribers (email);

-- ---------------------------------------------------------------------------
-- subscriptions: Links subscribers to plans
-- ---------------------------------------------------------------------------
CREATE TABLE subscriptions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscriber_id           UUID NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    plan_id                 UUID NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    status                  VARCHAR(32) NOT NULL DEFAULT 'active',
    starts_at               TIMESTAMPTZ NOT NULL,
    expires_at              TIMESTAMPTZ,
    rate_limit_per_second   INTEGER,
    rate_limit_per_minute   INTEGER,
    rate_limit_per_hour     INTEGER,
    allowed_endpoints       JSONB DEFAULT '[]',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_subscriber_id ON subscriptions (subscriber_id);
CREATE INDEX idx_subscriptions_plan_id ON subscriptions (plan_id);

-- ---------------------------------------------------------------------------
-- api_keys: API keys issued to subscribers for authentication
-- ---------------------------------------------------------------------------
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscriber_id   UUID NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    key_hash        VARCHAR(128) NOT NULL UNIQUE,
    key_prefix      VARCHAR(12) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    scopes          JSONB DEFAULT '[]',
    rate_limit      INTEGER,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ
);

CREATE INDEX idx_api_keys_subscriber_id ON api_keys (subscriber_id);
CREATE INDEX ix_api_keys_prefix ON api_keys (key_prefix);

-- ---------------------------------------------------------------------------
-- audit_logs: Immutable audit trail of all changes
-- ---------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(64) NOT NULL,
    resource_type   VARCHAR(64) NOT NULL,
    resource_id     VARCHAR(128),
    details         JSONB,
    ip_address      VARCHAR(45),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX ix_audit_logs_resource ON audit_logs (resource_type, resource_id);

-- =============================================================================
-- Triggers: updated_at auto-update
-- =============================================================================
CREATE TRIGGER trg_subscribers_updated_at
    BEFORE UPDATE ON subscribers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Triggers: Audit logging on key tables
-- =============================================================================
CREATE TRIGGER trg_users_audit
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_log_trigger_fn();

CREATE TRIGGER trg_subscribers_audit
    AFTER INSERT OR UPDATE OR DELETE ON subscribers
    FOR EACH ROW EXECUTE FUNCTION audit_log_trigger_fn();

CREATE TRIGGER trg_subscriptions_audit
    AFTER INSERT OR UPDATE OR DELETE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION audit_log_trigger_fn();

CREATE TRIGGER trg_api_keys_audit
    AFTER INSERT OR UPDATE OR DELETE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION audit_log_trigger_fn();

CREATE TRIGGER trg_plans_audit
    AFTER INSERT OR UPDATE OR DELETE ON plans
    FOR EACH ROW EXECUTE FUNCTION audit_log_trigger_fn();

-- =============================================================================
-- Default Data: Roles
-- =============================================================================
-- Permissions use the format "resource:action" matching the RBAC middleware.
-- The middleware checks for exact key matches in the permissions dict.
-- =============================================================================
INSERT INTO roles (name, description, permissions) VALUES
(
    'super_admin',
    'Full system access including role management.',
    '{
        "subscribers:read": true, "subscribers:write": true, "subscribers:delete": true,
        "subscriptions:read": true, "subscriptions:write": true, "subscriptions:delete": true,
        "api_keys:read": true, "api_keys:write": true, "api_keys:delete": true,
        "roles:read": true, "roles:write": true, "roles:delete": true,
        "users:read": true, "users:write": true,
        "gateway:read": true, "gateway:write": true,
        "audit:read": true,
        "ai:read": true, "ai:analyze": true, "ai:rate-limit": true, "ai:route": true,
        "ai:transform": true, "ai:documentation": true,
        "teams:read": true, "teams:write": true, "teams:delete": true,
        "api_registry:read": true, "api_registry:write": true,
        "api_registry:delete": true, "api_registry:approve": true
    }'
),
(
    'admin',
    'Administrative access. Manages subscribers, API keys, and subscriptions.',
    '{
        "subscribers:read": true, "subscribers:write": true, "subscribers:delete": true,
        "subscriptions:read": true, "subscriptions:write": true,
        "api_keys:read": true, "api_keys:write": true, "api_keys:delete": true,
        "roles:read": true,
        "users:read": true,
        "gateway:read": true,
        "audit:read": true,
        "ai:read": true, "ai:analyze": true, "ai:rate-limit": true,
        "teams:read": true, "teams:write": true,
        "api_registry:read": true, "api_registry:write": true, "api_registry:approve": true
    }'
),
(
    'operator',
    'Operational access. Can manage subscribers and view configurations.',
    '{
        "subscribers:read": true, "subscribers:write": true,
        "subscriptions:read": true, "subscriptions:write": true,
        "api_keys:read": true, "api_keys:write": true,
        "roles:read": true,
        "users:read": true,
        "gateway:read": true,
        "audit:read": true,
        "ai:read": true,
        "teams:read": true, "teams:write": true,
        "api_registry:read": true, "api_registry:write": true
    }'
),
(
    'viewer',
    'Read-only access to all resources.',
    '{
        "subscribers:read": true,
        "subscriptions:read": true,
        "api_keys:read": true,
        "roles:read": true,
        "users:read": true,
        "gateway:read": true,
        "audit:read": true,
        "ai:read": true,
        "teams:read": true,
        "api_registry:read": true
    }'
);

-- =============================================================================
-- Default Data: Plans (matching the config.py rate limit tiers)
-- =============================================================================
INSERT INTO plans (name, description, rate_limit_second, rate_limit_minute, rate_limit_hour, max_api_keys, price_cents) VALUES
('free',       'Free tier for evaluation and development.',              1,   30,    500,    2, 0),
('basic',      'Basic tier for light production workloads.',             5,   100,   3000,   5, 2999),
('pro',        'Pro tier for moderate production workloads.',            20,  500,   15000,  10, 9999),
('enterprise', 'Enterprise tier with highest limits. Contact sales.',   100, 3000,  100000, 50, 49999);

COMMIT;
