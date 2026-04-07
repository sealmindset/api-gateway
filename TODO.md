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
