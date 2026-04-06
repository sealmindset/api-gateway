"""
Three-tier prompt resolution: Redis cache -> Database -> hardcoded seed fallback.

Usage:
    prompt_text = await resolve_prompt("anomaly-detection")
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Slug -> hardcoded prompt mapping (seed fallback)
_HARDCODED: dict[str, str] = {}


def _ensure_hardcoded() -> None:
    """Lazy-load the hardcoded prompts from prompts.py into the fallback map."""
    if _HARDCODED:
        return
    from .prompts import (
        ANOMALY_DETECTION_SYSTEM_PROMPT,
        RATE_LIMIT_ADVISOR_SYSTEM_PROMPT,
        SMART_ROUTING_SYSTEM_PROMPT,
        REQUEST_TRANSFORM_SYSTEM_PROMPT,
        DOCUMENTATION_SYSTEM_PROMPT,
        REQUEST_ANALYSIS_SYSTEM_PROMPT,
    )
    _HARDCODED.update({
        "anomaly-detection": ANOMALY_DETECTION_SYSTEM_PROMPT,
        "rate-limit-advisor": RATE_LIMIT_ADVISOR_SYSTEM_PROMPT,
        "smart-routing": SMART_ROUTING_SYSTEM_PROMPT,
        "request-transform": REQUEST_TRANSFORM_SYSTEM_PROMPT,
        "response-transform": REQUEST_TRANSFORM_SYSTEM_PROMPT,
        "api-documentation": DOCUMENTATION_SYSTEM_PROMPT,
        "request-analysis": REQUEST_ANALYSIS_SYSTEM_PROMPT,
    })


async def resolve_prompt(slug: str) -> Optional[str]:
    """
    Resolve a prompt template by slug using three-tier lookup:
      1. Database (ai_prompts table, is_active=True)
      2. Hardcoded seed fallback (prompts.py)

    Returns None if the slug is not found anywhere.
    """
    # Tier 1: Database
    try:
        from app.models.database import AIPrompt, async_session_factory
        from sqlalchemy import select

        if async_session_factory is not None:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(AIPrompt.system_prompt)
                    .where(AIPrompt.slug == slug, AIPrompt.is_active.is_(True))
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    logger.debug("Prompt '%s' resolved from database", slug)
                    return row
    except Exception as exc:
        logger.warning("DB prompt lookup failed for '%s': %s", slug, exc)

    # Tier 2: Hardcoded fallback
    _ensure_hardcoded()
    hardcoded = _HARDCODED.get(slug)
    if hardcoded:
        logger.debug("Prompt '%s' resolved from hardcoded fallback", slug)
        return hardcoded

    logger.warning("Prompt '%s' not found in any tier", slug)
    return None
