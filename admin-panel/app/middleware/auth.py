"""OIDC authentication middleware for Microsoft Entra ID."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.database import User, get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OAuth / OIDC client (module-level singleton, configured at startup)
# ---------------------------------------------------------------------------

oauth = OAuth()


def configure_oauth(settings: Settings) -> None:
    """Register the Entra ID OIDC provider with authlib.

    Must be called once during application startup.
    """
    oauth.register(
        name="entra",
        client_id=settings.entra_client_id,
        client_secret=settings.entra_client_secret,
        server_metadata_url=settings.entra_openid_config_url,
        client_kwargs={
            "scope": "openid email profile",
        },
    )


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _get_token_from_session(request: Request) -> Optional[dict]:
    """Extract the stored OIDC token dict from the session."""
    return request.session.get("token")


def _get_userinfo_from_session(request: Request) -> Optional[dict]:
    """Extract cached userinfo from the session."""
    return request.session.get("userinfo")


# ---------------------------------------------------------------------------
# User provisioning / sync
# ---------------------------------------------------------------------------

async def _provision_or_update_user(
    session: AsyncSession,
    userinfo: dict,
) -> User:
    """Create or update the local user record from Entra ID claims.

    On first login the user is auto-provisioned with no explicit roles;
    an admin must assign roles afterwards.
    """
    oid: str = userinfo.get("oid") or userinfo.get("sub", "")
    email: str = userinfo.get("email") or userinfo.get("preferred_username", "")
    name: str = userinfo.get("name", email)

    result = await session.execute(select(User).where(User.entra_oid == oid))
    user = result.scalar_one_or_none()

    if user is None:
        logger.info("Auto-provisioning new user: %s (%s)", email, oid)
        user = User(
            email=email,
            name=name,
            entra_oid=oid,
            roles={},
            last_login=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()
    else:
        user.email = email
        user.name = name
        user.last_login = datetime.now(timezone.utc)
        await session.flush()

    return user


# ---------------------------------------------------------------------------
# FastAPI dependency: get authenticated user
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Resolve the currently-authenticated user from the session.

    Raises 401 if the user is not logged in.
    """
    userinfo = _get_userinfo_from_session(request)
    if userinfo is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in via /auth/login.",
        )

    user = await _provision_or_update_user(db, userinfo)
    return user


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising."""
    userinfo = _get_userinfo_from_session(request)
    if userinfo is None:
        return None
    return await _provision_or_update_user(db, userinfo)
