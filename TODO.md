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

## Remaining nemo-it Findings

### MED-001: Dockerfile missing USER (dev stage)
- Add `USER node` to development stage of `frontend/Dockerfile`

### MED-002: Kong Admin API on all interfaces
- Bind to `127.0.0.1` in docker-compose.yml

### MED-003: Default credentials in docker-compose
- Add startup validation script for non-dev environments

### MED-004: Grafana default admin credentials
- Override via `.env` in all non-local environments

### LOW-001: Dockerfile missing HEALTHCHECK
- Add `HEALTHCHECK` to production stage of `frontend/Dockerfile`
