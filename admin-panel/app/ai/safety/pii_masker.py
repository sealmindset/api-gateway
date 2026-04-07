"""
PII masking and unmasking for AI safety.

Replaces personally identifiable information with placeholders before
sending text to an external AI provider, and restores the original values
in the response.  This ensures PII never leaves the system boundary.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII patterns (order matters -- more specific patterns first)
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # US Social Security Numbers: 123-45-6789
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),

    # Credit card numbers (Visa, MC, Amex, Discover -- with or without separators)
    ("CREDIT_CARD", re.compile(
        r"\b(?:"
        r"4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"   # Visa
        r"|5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"  # Mastercard
        r"|3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}"           # Amex
        r"|6(?:011|5\d{2})[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"  # Discover
        r")\b"
    )),

    # Email addresses
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),

    # US phone numbers (various formats)
    ("PHONE", re.compile(
        r"\b(?:"
        r"\+?1[\s.-]?)?"
        r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"
    )),

    # IPv4 addresses (but not version numbers like 1.0.0 or 2.3.4)
    ("IP_ADDRESS", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),

    # AWS access key IDs
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),

    # Bearer tokens / API keys (long hex or base64 strings that look like credentials)
    ("API_KEY", re.compile(r"\b(?:sk-|pk_|rk_)[A-Za-z0-9]{20,}\b")),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mask_pii(text: str) -> tuple[str, dict[str, str]]:
    """
    Replace PII in *text* with numbered placeholders.

    Returns:
        A tuple of (masked_text, mappings) where *mappings* maps each
        placeholder back to the original value.  Pass both to
        :func:`unmask_pii` to restore the originals.

    Example::

        masked, m = mask_pii("Email me at rob@example.com")
        # masked  == "Email me at [EMAIL_1]"
        # m       == {"[EMAIL_1]": "rob@example.com"}
    """
    if not text:
        return text, {}

    mappings: dict[str, str] = {}
    counters: dict[str, int] = {}
    result = text

    for pii_type, pattern in _PII_PATTERNS:
        matches = list(pattern.finditer(result))
        # Process in reverse order so replacement indices stay valid
        for match in reversed(matches):
            original = match.group(0)

            # Skip if this exact value was already masked by a more specific pattern
            if any(original in v for v in mappings.values()):
                continue

            count = counters.get(pii_type, 0) + 1
            counters[pii_type] = count
            placeholder = f"[{pii_type}_{count}]"

            mappings[placeholder] = original
            result = result[:match.start()] + placeholder + result[match.end():]

    if mappings:
        logger.info("Masked %d PII item(s) across %d categories", len(mappings), len(counters))

    return result, mappings


def unmask_pii(text: str, mappings: dict[str, str]) -> str:
    """
    Restore PII placeholders to their original values.

    Args:
        text: Text containing ``[TYPE_N]`` placeholders.
        mappings: The mapping dict returned by :func:`mask_pii`.

    Returns:
        Text with all placeholders replaced by the original PII values.
    """
    if not text or not mappings:
        return text

    result = text
    for placeholder, original in mappings.items():
        result = result.replace(placeholder, original)

    return result
