"""
Prompt input sanitization for AI safety.

Strips known injection patterns and wraps user-supplied text in delimiter
tags so the AI model treats it as untrusted data rather than instructions.
"""

from __future__ import annotations

import base64
import codecs
import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable limits (importable for testing)
# ---------------------------------------------------------------------------

MAX_PROMPT_CHARS: int = 100_000

# ---------------------------------------------------------------------------
# Injection patterns
# ---------------------------------------------------------------------------

# Plain-text instruction-override attempts
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(above|previous|prior)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"(?:new|updated?)\s+system\s*(?:prompt|instruction)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+", re.IGNORECASE),
    re.compile(r"override\s+(system|safety|instructions?)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(the\s+)?(system|above|previous)", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+(are|were)\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if|though)\s+you", re.IGNORECASE),
]

# Role-marker injections (attempting to forge message boundaries)
_ROLE_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"###?\s*(System|Human|Assistant|User)\s*:", re.IGNORECASE),
    re.compile(r"<\|?(system|user|assistant)\|?>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contains_encoded_instructions(text: str) -> bool:
    """Detect base64 or ROT13-encoded injection attempts."""
    # Look for base64-encoded strings (minimum 20 chars to reduce false positives)
    b64_candidates = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", text)
    for candidate in b64_candidates:
        try:
            decoded = base64.b64decode(candidate, validate=True).decode("utf-8", errors="ignore")
            decoded_lower = decoded.lower()
            if any(kw in decoded_lower for kw in ("ignore previous", "system:", "you are now")):
                return True
        except Exception:
            continue

    # Check for ROT13-encoded instructions
    try:
        rot13_decoded = codecs.decode(text, "rot_13").lower()
        if any(kw in rot13_decoded for kw in ("ignore previous", "disregard above", "you are now")):
            # Only flag if the original text does NOT contain the phrase
            # (i.e. the phrase only appears after ROT13 decoding)
            text_lower = text.lower()
            if not any(kw in text_lower for kw in ("ignore previous", "disregard above", "you are now")):
                return True
    except Exception:
        pass

    return False


def _strip_role_markers(text: str) -> str:
    """Remove role-marker injections that attempt to forge message boundaries."""
    result = text
    for pattern in _ROLE_MARKERS:
        result = pattern.sub("[role-marker-removed]", result)
    return result


def _strip_injection_patterns(text: str) -> str:
    """Remove known prompt injection phrases."""
    result = text
    for pattern in _INJECTION_PATTERNS:
        result = pattern.sub("[injection-attempt-removed]", result)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_prompt_input(text: str) -> str:
    """
    Sanitize user-supplied text before embedding in an AI prompt.

    1. Enforces size limit (MAX_PROMPT_CHARS).
    2. Strips known injection patterns and role markers.
    3. Detects encoded injection attempts.
    4. Wraps the result in ``<user_input>`` delimiter tags.

    Returns:
        The sanitized and wrapped text, safe to embed in a prompt template.
    """
    if not text:
        return "<user_input></user_input>"

    # 1. Enforce size limit
    if len(text) > MAX_PROMPT_CHARS:
        logger.warning(
            "Prompt input truncated from %d to %d characters",
            len(text),
            MAX_PROMPT_CHARS,
        )
        text = text[:MAX_PROMPT_CHARS]

    # 2. Strip injection patterns and role markers
    sanitized = _strip_injection_patterns(text)
    sanitized = _strip_role_markers(sanitized)

    # 3. Detect encoded instructions
    if _contains_encoded_instructions(sanitized):
        logger.warning("Encoded injection attempt detected in prompt input")
        # Remove the base64-looking segments rather than rejecting entirely
        sanitized = re.sub(r"[A-Za-z0-9+/]{20,}={0,2}", "[encoded-content-removed]", sanitized)

    # 4. Wrap in delimiter tags
    return f"<user_input>{sanitized}</user_input>"
