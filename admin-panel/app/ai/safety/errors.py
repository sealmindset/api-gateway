"""
AI error sanitization for safety.

Maps provider-specific error messages to generic, safe messages that can
be returned to clients without leaking internal details such as provider
names, model identifiers, token counts, or API keys.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error classification patterns
# ---------------------------------------------------------------------------

_ERROR_MAP: list[tuple[re.Pattern[str], str, int]] = [
    # (pattern matching the raw error, safe client message, suggested HTTP status)

    # Rate limiting
    (re.compile(r"429|rate.?limit|too.?many.?requests|throttl", re.IGNORECASE),
     "AI service is temporarily busy. Please try again.",
     429),

    # Authentication / authorization
    (re.compile(r"401|403|auth|api.?key|unauthorized|forbidden|invalid.*key", re.IGNORECASE),
     "AI service configuration error. Contact your administrator.",
     503),

    # Timeout
    (re.compile(r"timeout|timed?.?out|deadline|connect.*error", re.IGNORECASE),
     "AI request timed out. Please try again with a shorter input.",
     504),

    # Content filter / safety
    (re.compile(r"content.?filter|safety|moderation|blocked|refus", re.IGNORECASE),
     "The AI could not process this request due to content restrictions.",
     422),

    # Model not found / invalid
    (re.compile(r"model.*not.?found|invalid.*model|not_found_error", re.IGNORECASE),
     "AI service configuration error. Contact your administrator.",
     503),

    # Overloaded
    (re.compile(r"overloaded|capacity|503|service.?unavailable", re.IGNORECASE),
     "AI service is temporarily unavailable. Please try again later.",
     503),

    # Token / context length exceeded
    (re.compile(r"token|context.?length|too.?long|max.*length|exceeded.*limit", re.IGNORECASE),
     "The input is too large for AI processing. Please reduce the size and try again.",
     413),
]

# Patterns that might leak sensitive info in error messages
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),          # API keys
    re.compile(r"AKIA[0-9A-Z]{16}"),              # AWS keys
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),  # Bearer tokens
    re.compile(r"https?://[^\s]+/v1/"),            # Provider API URLs
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_ai_error(error: Exception) -> dict[str, Any]:
    """
    Map an AI provider exception to a safe, client-facing error response.

    The full error is logged server-side for debugging. The returned dict
    contains only sanitized information safe to send to the client.

    Returns:
        A dict with keys:
        - ``message``: Safe, human-readable error message.
        - ``status_code``: Suggested HTTP status code.
        - ``safe``: Always ``True`` (indicates the message has been sanitized).
        - ``retry``: Whether the client should retry the request.
    """
    error_str = str(error)

    # Log the full error server-side (scrub sensitive tokens first)
    safe_log = error_str
    for pattern in _SENSITIVE_PATTERNS:
        safe_log = pattern.sub("[REDACTED]", safe_log)
    logger.error("AI provider error (sanitized for log): %s", safe_log)

    # Match against known error patterns
    for pattern, safe_message, status_code in _ERROR_MAP:
        if pattern.search(error_str):
            retry = status_code in (429, 503, 504)
            return {
                "message": safe_message,
                "status_code": status_code,
                "safe": True,
                "retry": retry,
            }

    # Fallback for unrecognised errors
    return {
        "message": "AI processing failed. Please try again.",
        "status_code": 500,
        "safe": True,
        "retry": True,
    }
