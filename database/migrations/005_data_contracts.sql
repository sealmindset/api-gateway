-- =============================================================================
-- 005: Data Contracts for API Registry
-- =============================================================================
-- Adds data contract fields to api_registrations: contacts, SLAs,
-- change management policies, and schema metadata.
-- All columns are nullable or have safe defaults so existing rows are unaffected.
-- =============================================================================

BEGIN;

-- -------------------------------------------------------------------------
-- Contacts
-- -------------------------------------------------------------------------
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS contact_primary_email VARCHAR(320);
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS contact_escalation_email VARCHAR(320);
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS contact_slack_channel VARCHAR(128);
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS contact_pagerduty_service VARCHAR(256);
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS contact_support_url TEXT;

-- -------------------------------------------------------------------------
-- SLAs
-- -------------------------------------------------------------------------
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS sla_uptime_target NUMERIC(5,2);
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS sla_latency_p50_ms INTEGER;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS sla_latency_p95_ms INTEGER;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS sla_latency_p99_ms INTEGER;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS sla_error_budget_pct NUMERIC(5,2);
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS sla_support_hours VARCHAR(64);

-- -------------------------------------------------------------------------
-- Change Management
-- -------------------------------------------------------------------------
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS deprecation_notice_days INTEGER DEFAULT 90;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS breaking_change_policy VARCHAR(64) DEFAULT 'semver';
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS versioning_scheme VARCHAR(32) DEFAULT 'url-path';
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS changelog_url TEXT;

-- -------------------------------------------------------------------------
-- Schema
-- -------------------------------------------------------------------------
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS openapi_spec_url TEXT;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS max_request_size_kb INTEGER DEFAULT 128;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS max_response_size_kb INTEGER;

COMMIT;
