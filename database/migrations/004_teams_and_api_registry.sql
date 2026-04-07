-- =============================================================================
-- Migration 004: Teams and API Registry
-- =============================================================================
-- Adds team-based API registration and management portal:
--   - teams: organizational units that own APIs
--   - team_members: maps users to teams with roles
--   - api_registrations: APIs submitted for registration in Kong gateway
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Ensure the update_updated_at function exists
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Teams
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(256)  NOT NULL,
    slug            VARCHAR(128)  NOT NULL UNIQUE,
    description     TEXT,
    contact_email   VARCHAR(320)  NOT NULL,
    metadata        JSONB         DEFAULT '{}'::jsonb,
    is_active       BOOLEAN       NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_teams_slug ON teams (slug);
CREATE INDEX IF NOT EXISTS ix_teams_created_at ON teams (created_at);

-- Auto-update updated_at
CREATE TRIGGER trg_teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------------------
-- Team Members
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_members (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id     UUID          NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id     UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(32)   NOT NULL DEFAULT 'member',  -- owner, admin, member, viewer
    joined_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_team_members UNIQUE (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_team_members_team ON team_members (team_id);
CREATE INDEX IF NOT EXISTS ix_team_members_user ON team_members (user_id);

-- ---------------------------------------------------------------------------
-- API Registrations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_registrations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id             UUID          NOT NULL REFERENCES teams(id) ON DELETE CASCADE,

    -- API metadata
    name                VARCHAR(256)  NOT NULL,
    slug                VARCHAR(128)  NOT NULL UNIQUE,
    description         TEXT,
    version             VARCHAR(32)   NOT NULL DEFAULT 'v1',
    api_type            VARCHAR(32)   NOT NULL DEFAULT 'rest',  -- rest, graphql, grpc, websocket
    documentation_url   TEXT,
    tags                JSONB         DEFAULT '[]'::jsonb,

    -- Upstream target (where the API actually lives)
    upstream_url        TEXT          NOT NULL,
    upstream_protocol   VARCHAR(10)   NOT NULL DEFAULT 'https',
    health_check_path   VARCHAR(256)  DEFAULT '/health',

    -- Kong integration
    kong_service_id     VARCHAR(64),
    kong_route_id       VARCHAR(64),
    gateway_path        VARCHAR(256),   -- e.g. /api/v1/weather

    -- Rate limiting defaults
    rate_limit_second   INTEGER       DEFAULT 5,
    rate_limit_minute   INTEGER       DEFAULT 100,
    rate_limit_hour     INTEGER       DEFAULT 3000,

    -- Auth requirements
    auth_type           VARCHAR(32)   NOT NULL DEFAULT 'key-auth',  -- key-auth, oauth2, jwt, none
    requires_approval   BOOLEAN       NOT NULL DEFAULT true,

    -- Workflow
    status              VARCHAR(32)   NOT NULL DEFAULT 'draft',
    -- draft -> pending_review -> approved -> active -> deprecated -> retired
    submitted_at        TIMESTAMPTZ,
    reviewed_by         UUID          REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at         TIMESTAMPTZ,
    review_notes        TEXT,
    activated_at        TIMESTAMPTZ,

    -- Timestamps
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_api_reg_team ON api_registrations (team_id);
CREATE INDEX IF NOT EXISTS ix_api_reg_slug ON api_registrations (slug);
CREATE INDEX IF NOT EXISTS ix_api_reg_status ON api_registrations (status);
CREATE INDEX IF NOT EXISTS ix_api_reg_created_at ON api_registrations (created_at);

-- Auto-update updated_at
CREATE TRIGGER trg_api_reg_updated_at
    BEFORE UPDATE ON api_registrations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMIT;
