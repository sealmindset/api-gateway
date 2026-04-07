-- Migration 006: Add caching policy columns to api_registrations
-- Per-API response caching configuration, synced to Kong's proxy-cache plugin.
-- All columns use safe defaults (caching disabled by default).

BEGIN;

ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS cache_enabled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS cache_ttl_seconds INTEGER NOT NULL DEFAULT 300;
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS cache_methods JSONB DEFAULT '["GET","HEAD"]';
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS cache_content_types JSONB DEFAULT '["application/json"]';
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS cache_vary_headers JSONB DEFAULT '["Accept"]';
ALTER TABLE api_registrations ADD COLUMN IF NOT EXISTS cache_bypass_on_auth BOOLEAN NOT NULL DEFAULT true;

COMMIT;
