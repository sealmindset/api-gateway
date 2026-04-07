"""
AI output validation for safety.

Validates structured (JSON) and free-text AI responses before they reach
the database or the client.  Strips dangerous content like HTML/script tags,
detects system prompt leakage, and validates structured fields against
expected schemas and value ranges.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dangerous content patterns
# ---------------------------------------------------------------------------

# HTML/script tags that could cause XSS when rendered in a UI
_HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*(script|iframe|object|embed|form|input|link|meta|base)\b[^>]*>", re.IGNORECASE)

# Markdown injection that could break page layout
_MARKDOWN_INJECTION = re.compile(r"!\[.*?\]\(javascript:", re.IGNORECASE)

# System prompt leakage indicators
_SYSTEM_PROMPT_LEAKAGE = [
    "you are an ai",
    "you are a helpful",
    "your instructions are",
    "my system prompt",
    "as an ai assistant",
    "<system>",
    "</system>",
    "system prompt:",
]


# ---------------------------------------------------------------------------
# Structured output validation
# ---------------------------------------------------------------------------

# Expected ranges for common AI output fields
_FIELD_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "score": {"min": 0.0, "max": 1.0},
    "confidence": {"min": 0.0, "max": 1.0},
    "risk_score": {"min": 0.0, "max": 1.0},
    "anomaly_score": {"min": 0.0, "max": 1.0},
}

_ENUM_CONSTRAINTS: dict[str, set[str]] = {
    "action": {"allow", "throttle", "block", "alert"},
    "anomaly_type": {
        "none", "rate_spike", "payload_anomaly", "geo_anomaly",
        "auth_anomaly", "pattern_anomaly", "latency_anomaly",
        "error_rate_spike", "credential_stuffing", "enumeration",
        "data_exfiltration", "unknown",
    },
}


def _validate_structured(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and clamp structured AI output fields.

    - Numeric fields are clamped to their expected range.
    - Enum fields are replaced with a safe default if invalid.
    - Unknown fields are passed through unchanged.
    """
    validated = dict(data)

    for field, constraints in _FIELD_CONSTRAINTS.items():
        if field in validated:
            try:
                value = float(validated[field])
                validated[field] = max(constraints["min"], min(constraints["max"], value))
            except (TypeError, ValueError):
                validated[field] = constraints["min"]

    for field, allowed in _ENUM_CONSTRAINTS.items():
        if field in validated:
            if str(validated[field]).lower() not in allowed:
                logger.warning(
                    "AI output field '%s' had invalid value '%s', defaulting to first allowed",
                    field,
                    validated[field],
                )
                validated[field] = "unknown" if "unknown" in allowed else sorted(allowed)[0]

    return validated


# ---------------------------------------------------------------------------
# Free-text sanitization
# ---------------------------------------------------------------------------

def _sanitize_text(text: str) -> str:
    """Strip dangerous HTML tags, markdown injection, and prompt leakage from free text."""
    result = text

    # Strip dangerous HTML tags
    result = _HTML_TAG_PATTERN.sub("[html-removed]", result)

    # Strip markdown injection
    result = _MARKDOWN_INJECTION.sub("[md-injection-removed]", result)

    # Redact system prompt leakage
    text_lower = result.lower()
    for phrase in _SYSTEM_PROMPT_LEAKAGE:
        if phrase in text_lower:
            logger.warning("System prompt leakage detected in AI output")
            # Replace the line containing the leakage
            lines = result.split("\n")
            cleaned_lines = []
            for line in lines:
                if phrase in line.lower():
                    cleaned_lines.append("[system-prompt-content-redacted]")
                else:
                    cleaned_lines.append(line)
            result = "\n".join(cleaned_lines)
            break  # re-check not needed after line-level redaction

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_agent_output(text: str) -> dict[str, Any]:
    """
    Validate AI output before it reaches the database or client.

    For structured (JSON) responses:
    - Parses the JSON
    - Validates field values against expected ranges and enums
    - Sanitizes any string values within the structure
    - Returns ``{"sanitized_text": <re-serialized JSON>, "structured": True, "data": <dict>}``

    For free-text responses:
    - Strips dangerous HTML, markdown injection, and prompt leakage
    - Returns ``{"sanitized_text": <cleaned text>, "structured": False}``
    """
    if not text:
        return {"sanitized_text": "", "structured": False}

    # Try to parse as JSON first
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            validated = _validate_structured(data)

            # Sanitize string values recursively
            validated = _sanitize_dict_strings(validated)

            return {
                "sanitized_text": json.dumps(validated),
                "structured": True,
                "data": validated,
            }
        except (json.JSONDecodeError, TypeError):
            pass

    # Fall back to free-text sanitization
    sanitized = _sanitize_text(text)
    return {"sanitized_text": sanitized, "structured": False}


def _sanitize_dict_strings(obj: Any) -> Any:
    """Recursively sanitize string values in a dict/list structure."""
    if isinstance(obj, dict):
        return {k: _sanitize_dict_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_dict_strings(item) for item in obj]
    if isinstance(obj, str):
        return _sanitize_text(obj)
    return obj
