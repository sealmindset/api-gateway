# TODO

## Security Fixes (Manual)

### ~~HIGH-003: Implement AI Safety Module~~ DONE
- **Status:** Completed 2026-04-07
- **Modules created:**
  - `admin-panel/app/ai/safety/sanitize.py` -- prompt injection protection, size limits, delimiter wrapping
  - `admin-panel/app/ai/safety/validate.py` -- structured JSON validation + free-text XSS/leakage stripping
  - `admin-panel/app/ai/safety/pii_masker.py` -- PII masking (email, phone, SSN, credit card, IP, API keys) with reversible unmasking
  - `admin-panel/app/ai/safety/errors.py` -- provider error sanitization with safe client messages
- **Verification:** `AI_SAFETY_AVAILABLE = True` confirmed in base provider

### ~~MED-001: Dockerfile missing USER (dev stage)~~ DONE
- Added `USER node` to development stage of `frontend/Dockerfile`

### ~~MED-002: Kong Admin API on all interfaces~~ DONE
- Bound Kong admin port to `127.0.0.1` in docker-compose.yml

### ~~MED-003: Default credentials in docker-compose~~ DONE
- Created `scripts/validate-secrets.sh` — warns in dev, fatally exits in other environments
- Updated `.env.example` with safe placeholder for Grafana password

### ~~MED-004: Grafana default admin credentials~~ DONE
- Set unique generated password in `.env`
- Updated `.env.example` placeholder to `change_me_grafana`

### ~~LOW-001: Dockerfile missing HEALTHCHECK~~ DONE
- Added `HEALTHCHECK` to production stage of `frontend/Dockerfile`

## Known Issues

### ~~AI Prompts Auth Gap~~ DONE
- **Status:** Fixed 2026-04-07
- Added `require_permission("ai:read")` to GET `/ai/prompts` and GET `/ai/prompts/{prompt_id}`
- Removed xfail marker from test; now asserts 401/403 for unauthenticated access

## Completed (2026-04-07)

### Battle Test Suite
- 174 integration tests across 11 files, all passing
- Coverage: auth, RBAC, teams, API registry lifecycle, subscribers, security, E2E, rate limits, advanced security, data contracts

### Data Contracts Feature
- 18 new columns on `api_registrations` table (contacts, SLAs, change management, schema)
- `PATCH /api-registry/{id}/contract` endpoint for updating contracts without re-approval
- Public catalog at `/public/api-catalog` (unauthenticated)
- Kong `request-size-limiting` plugin auto-synced from `max_request_size_kb`
- Migration: `database/migrations/005_data_contracts.sql`

### Bug Fixes (Battle Testing)
- Fixed MissingGreenlet on API registry endpoints (added `db.refresh()` after `db.flush()`)
- Fixed UUID serialization in subscription PATCH (use `model_dump(mode="json")`)
- Fixed API review payload schema mismatch (`action` field instead of `approved`)

### Developer Portal
- `GET /public/api-catalog/{slug}/try-it` — embedded Swagger UI for interactive API testing
- Loads OpenAPI spec from data contract, pre-configures gateway URL
- Subscribers authenticate via API key in Swagger UI authorize dialog

### Per-API Caching Policies
- 6 new columns on `api_registrations` (cache_enabled, cache_ttl_seconds, cache_methods, cache_content_types, cache_vary_headers, cache_bypass_on_auth)
- Kong `proxy-cache` plugin synced on activation and contract update
- Safe defaults: disabled, memory strategy (Kong CE 3.9 limitation — Redis requires Enterprise)
- Migration: `database/migrations/006_caching.sql`

### Observability Comparison
- `docs/observability-comparison.md` — Azure Monitor feature-by-feature mapping
- Maps Application Insights, Log Analytics, Azure Alerts, Workbooks to Prometheus + Grafana + Cribl
- Cost comparison: $0 additional licensing vs APIM per-unit pricing
- Added to RFC-001 and README
