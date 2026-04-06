"""Authentication routes: Entra ID OIDC login / callback / logout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, get_optional_user, oauth
from app.middleware.rbac import get_user_role_names
from app.models.database import User, get_db_session
from app.models.schemas import CurrentUser, RoleRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirect the browser to the Entra ID authorization endpoint."""
    redirect_uri = request.url_for("auth_callback")
    return await oauth.entra.authorize_redirect(request, str(redirect_uri))


@router.get("/callback", name="auth_callback")
async def callback(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Handle the OIDC callback from Entra ID.

    Exchanges the authorization code for tokens, stores them in the
    session, and provisions the local user record if needed.
    """
    try:
        token = await oauth.entra.authorize_access_token(request)
    except Exception:
        logger.exception("Failed to exchange authorization code")
        return JSONResponse(
            status_code=400,
            content={"detail": "Authentication failed. Could not exchange code for token."},
        )

    userinfo = token.get("userinfo")
    if userinfo is None:
        userinfo = await oauth.entra.userinfo(token=token)

    request.session["token"] = dict(token)
    request.session["userinfo"] = dict(userinfo)

    logger.info("User authenticated: %s", userinfo.get("email") or userinfo.get("preferred_username"))
    return RedirectResponse(url="/")


@router.post("/logout")
async def logout(request: Request):
    """Clear the server-side session and log the user out."""
    email = (request.session.get("userinfo") or {}).get("email", "unknown")
    request.session.clear()
    logger.info("User logged out: %s", email)
    return {"detail": "Logged out successfully."}


@router.get("/me", response_model=CurrentUser)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Return the current user's profile including assigned roles."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.database import UserRole

    result = await db.execute(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .options(selectinload(UserRole.role))
    )
    user_roles = result.scalars().all()
    roles = [
        RoleRead.model_validate(ur.role) for ur in user_roles if ur.role
    ]

    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        entra_oid=user.entra_oid,
        roles=user.roles,
        created_at=user.created_at,
        last_login=user.last_login,
        assigned_roles=roles,
    )
