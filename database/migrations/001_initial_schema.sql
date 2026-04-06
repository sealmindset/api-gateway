-- =============================================================================
-- Migration 001: Initial Schema
-- =============================================================================
-- Creates the complete database schema for the API Gateway admin panel.
-- Includes all tables, indexes, default data, triggers, and audit logging.
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
    old_data JSONB;
    new_data JSONB;
BEGIN
    -- Try to get the current user from session variable (set by the app)
    BEGIN
        audit_user_id := current_setting('app.current_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        audit_user_id := NULL;
    END;

    IF TG_OP = 'DELETE' THEN
        old_data := to_jsonb(OLD);
        new_data := NULL;
    ELSIF TG_OP = 'INSERT' THEN
        old_data := NULL;
        new_data := to_jsonb(NEW);
    ELSE  -- UPDATE
        old_data := to_jsonb(OLD);
        new_data := to_jsonb(NEW);
    END IF;

    INSERT INTO audit_logs (
        user_id,
        action,
        resource_type,
        resource_id,
        old_value,
        new_value,
        ip_address
    ) VALUES (
        audit_user_id,
        TG_OP,
        TG_TABLE_NAME,
        CASE
            WHEN TG_OP = 'DELETE' THEN OLD.id::TEXT
            ELSE NEW.id::TEXT
        END,
        old_data,
        new_data,
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
-- roles: User roles with JSON permissions
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    permissions JSONB NOT NULL DEFAULT '{}',
    is_system   BOOLEAN NOT NULL DEFAULT FALSE,  -- System roles cannot be deleted
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_roles_name ON roles (name);

-- ---------------------------------------------------------------------------
-- users: Admin panel users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    username        VARCHAR(100) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_is_active ON users (is_active);

-- ---------------------------------------------------------------------------
-- user_roles: Many-to-many relationship between users and roles
-- ---------------------------------------------------------------------------
CREATE TABLE user_roles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    granted_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, role_id)
);

CREATE INDEX idx_user_roles_user_id ON user_roles (user_id);
CREATE INDEX idx_user_roles_role_id ON user_roles (role_id);

-- ---------------------------------------------------------------------------
-- plans: Subscription plans with rate limits
-- ---------------------------------------------------------------------------
CREATE TABLE plans (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                VARCHAR(100) NOT NULL UNIQUE,
    description         TEXT,
    -- Rate limiting
    rate_limit_per_second   INTEGER,
    rate_limit_per_minute   INTEGER,
    rate_limit_per_hour     INTEGER,
    rate_limit_per_day      INTEGER,
    rate_limit_per_month    INTEGER,
    -- Quotas
    monthly_quota       BIGINT,            -- Total requests per month
    max_request_size_kb INTEGER DEFAULT 256,
    -- Features
    allowed_endpoints   JSONB DEFAULT '["*"]',  -- List of allowed endpoint patterns
    features            JSONB DEFAULT '{}',      -- Additional feature flags
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_plans_name ON plans (name);
CREATE INDEX idx_plans_is_active ON plans (is_active);

-- ---------------------------------------------------------------------------
-- subscribers: API consumers / organizations
-- ---------------------------------------------------------------------------
CREATE TABLE subscribers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    organization    VARCHAR(255),
    email           VARCHAR(255) NOT NULL,
    phone           VARCHAR(50),
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata        JSONB DEFAULT '{}',
    -- Kong consumer reference
    kong_consumer_id    VARCHAR(255) UNIQUE,
    kong_consumer_name  VARCHAR(255) UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscribers_email ON subscribers (email);
CREATE INDEX idx_subscribers_organization ON subscribers (organization);
CREATE INDEX idx_subscribers_is_active ON subscribers (is_active);
CREATE INDEX idx_subscribers_kong_consumer_id ON subscribers (kong_consumer_id);

-- ---------------------------------------------------------------------------
-- subscriptions: Links subscribers to plans (a subscriber can change plans)
-- ---------------------------------------------------------------------------
CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscriber_id   UUID NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    plan_id         UUID NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'cancelled', 'expired')),
    starts_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    cancelled_at    TIMESTAMPTZ,
    cancelled_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_subscriber_id ON subscriptions (subscriber_id);
CREATE INDEX idx_subscriptions_plan_id ON subscriptions (plan_id);
CREATE INDEX idx_subscriptions_status ON subscriptions (status);
CREATE INDEX idx_subscriptions_expires_at ON subscriptions (expires_at);
-- Only one active subscription per subscriber
CREATE UNIQUE INDEX idx_subscriptions_active_unique
    ON subscriptions (subscriber_id) WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- api_keys: API keys issued to subscribers for authentication
-- ---------------------------------------------------------------------------
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscriber_id   UUID NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    -- The key itself (stored as hash; the plaintext is shown only once at creation)
    key_prefix      VARCHAR(8) NOT NULL,     -- First 8 chars for identification
    key_hash        VARCHAR(255) NOT NULL,    -- bcrypt hash of the full key
    name            VARCHAR(255) NOT NULL,    -- Human-readable label
    description     TEXT,
    -- Status
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at      TIMESTAMPTZ,
    revoked_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    expires_at      TIMESTAMPTZ,
    -- Usage tracking
    last_used_at    TIMESTAMPTZ,
    usage_count     BIGINT NOT NULL DEFAULT 0,
    -- Kong reference
    kong_key_id     VARCHAR(255) UNIQUE,
    -- Scopes and restrictions
    scopes          JSONB DEFAULT '["read"]',
    allowed_ips     JSONB DEFAULT '[]',       -- Empty = allow all
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_api_keys_subscriber_id ON api_keys (subscriber_id);
CREATE INDEX idx_api_keys_key_prefix ON api_keys (key_prefix);
CREATE INDEX idx_api_keys_is_active ON api_keys (is_active);
CREATE INDEX idx_api_keys_kong_key_id ON api_keys (kong_key_id);
CREATE INDEX idx_api_keys_expires_at ON api_keys (expires_at) WHERE expires_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- audit_logs: Immutable audit trail of all changes
-- ---------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(50) NOT NULL,    -- INSERT, UPDATE, DELETE, LOGIN, etc.
    resource_type   VARCHAR(100) NOT NULL,   -- Table name or resource type
    resource_id     TEXT,                     -- ID of the affected resource
    old_value       JSONB,
    new_value       JSONB,
    ip_address      VARCHAR(45),             -- IPv4 or IPv6
    user_agent      TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit logs are append-only; index for common queries
CREATE INDEX idx_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs (action);
CREATE INDEX idx_audit_logs_resource_type ON audit_logs (resource_type);
CREATE INDEX idx_audit_logs_resource_id ON audit_logs (resource_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at DESC);
-- Composite index for filtering by resource
CREATE INDEX idx_audit_logs_resource ON audit_logs (resource_type, resource_id);

-- =============================================================================
-- Triggers: updated_at auto-update
-- =============================================================================
CREATE TRIGGER trg_roles_updated_at
    BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_plans_updated_at
    BEFORE UPDATE ON plans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_subscribers_updated_at
    BEFORE UPDATE ON subscribers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_api_keys_updated_at
    BEFORE UPDATE ON api_keys
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
INSERT INTO roles (name, description, permissions, is_system) VALUES
(
    'super_admin',
    'Full system access. Can manage all resources including users and roles.',
    '{
        "users": ["create", "read", "update", "delete"],
        "roles": ["create", "read", "update", "delete"],
        "subscribers": ["create", "read", "update", "delete"],
        "api_keys": ["create", "read", "update", "delete", "revoke"],
        "plans": ["create", "read", "update", "delete"],
        "subscriptions": ["create", "read", "update", "delete"],
        "audit_logs": ["read"],
        "kong": ["read", "configure"],
        "settings": ["read", "update"]
    }',
    TRUE
),
(
    'admin',
    'Administrative access. Can manage subscribers, API keys, and subscriptions.',
    '{
        "users": ["read"],
        "roles": ["read"],
        "subscribers": ["create", "read", "update", "delete"],
        "api_keys": ["create", "read", "update", "delete", "revoke"],
        "plans": ["read"],
        "subscriptions": ["create", "read", "update"],
        "audit_logs": ["read"],
        "kong": ["read"],
        "settings": ["read"]
    }',
    TRUE
),
(
    'operator',
    'Operational access. Can manage subscribers and view configurations.',
    '{
        "users": ["read"],
        "subscribers": ["create", "read", "update"],
        "api_keys": ["create", "read", "revoke"],
        "plans": ["read"],
        "subscriptions": ["create", "read"],
        "audit_logs": ["read"],
        "kong": ["read"]
    }',
    TRUE
),
(
    'viewer',
    'Read-only access to all resources.',
    '{
        "users": ["read"],
        "subscribers": ["read"],
        "api_keys": ["read"],
        "plans": ["read"],
        "subscriptions": ["read"],
        "audit_logs": ["read"],
        "kong": ["read"]
    }',
    TRUE
);

-- =============================================================================
-- Default Data: Plans
-- =============================================================================
INSERT INTO plans (name, description, rate_limit_per_second, rate_limit_per_minute, rate_limit_per_hour, rate_limit_per_day, rate_limit_per_month, monthly_quota, max_request_size_kb, sort_order) VALUES
(
    'free',
    'Free tier with basic rate limits. Suitable for evaluation and development.',
    5,        -- 5 req/s
    100,      -- 100 req/min
    1000,     -- 1,000 req/hr
    10000,    -- 10,000 req/day
    100000,   -- 100,000 req/month
    100000,   -- 100K monthly quota
    256,      -- 256 KB max request
    1
),
(
    'standard',
    'Standard tier for moderate production workloads.',
    25,       -- 25 req/s
    500,      -- 500 req/min
    10000,    -- 10,000 req/hr
    100000,   -- 100,000 req/day
    2000000,  -- 2M req/month
    2000000,  -- 2M monthly quota
    512,      -- 512 KB max request
    2
),
(
    'premium',
    'Premium tier for high-throughput production workloads.',
    100,      -- 100 req/s
    2000,     -- 2,000 req/min
    50000,    -- 50,000 req/hr
    500000,   -- 500,000 req/day
    10000000, -- 10M req/month
    10000000, -- 10M monthly quota
    1024,     -- 1 MB max request
    3
),
(
    'enterprise',
    'Enterprise tier with custom limits. Contact sales for configuration.',
    500,      -- 500 req/s
    10000,    -- 10,000 req/min
    200000,   -- 200,000 req/hr
    2000000,  -- 2,000,000 req/day
    50000000, -- 50M req/month
    50000000, -- 50M monthly quota
    5120,     -- 5 MB max request
    4
);

COMMIT;
