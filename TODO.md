# TODO

## Security Fixes (Manual)

### HIGH-003: Implement AI Safety Module
- **Severity:** HIGH
- **Where:** `admin-panel/app/ai/safety/` (directory does not exist)
- **What:** The base AI provider (`admin-panel/app/ai/providers/base.py`) imports from `app.ai.safety` and gracefully degrades when the module is missing. All safety controls (prompt sanitization, PII masking, output validation, error sanitization) are currently disabled no-ops.
- **Action required:** Create `admin-panel/app/ai/safety/` with four modules:
  - `sanitize.py` -- `sanitize_prompt_input()` strips injection patterns, wraps in `<user_input>` tags
  - `validate.py` -- `validate_agent_output()` validates structured responses against schema + value ranges
  - `pii_masker.py` -- `mask_pii()` / `unmask_pii()` for PII before AI submission
  - `errors.py` -- `sanitize_ai_error()` maps provider errors to safe client messages
- **Reference:** `~/.claude/make-it/references/guardrails.md` AI Operational Safety Controls section
