"""API Gateway Admin Panel -- FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.middleware.auth import configure_oauth
from app.middleware.rbac import close_redis, seed_default_roles
from app.models.database import async_session_factory, close_db, init_db
from app.routers import ai, api_registry, auth, gateway, public_catalog, rbac, subscribers, subscriptions, teams

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown resources."""
    settings = get_settings()

    # Startup
    logger.info("Starting %s ...", settings.app_name)
    await init_db()
    configure_oauth(settings)

    # Seed default RBAC roles
    if async_session_factory is not None:
        async with async_session_factory() as session:
            await seed_default_roles(session)

    logger.info("Startup complete.")
    yield

    # Shutdown
    logger.info("Shutting down ...")
    await close_db()
    await close_redis()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # -- Middleware ----------------------------------------------------------
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="admin_session",
        max_age=3600,  # 1 hour
        same_site="lax",
        https_only=not settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Security headers middleware ----------------------------------------
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["server"] = ""
        return response

    # -- Routers ------------------------------------------------------------
    app.include_router(auth.router)
    app.include_router(subscribers.router)
    app.include_router(subscriptions.plan_router)
    app.include_router(subscriptions.sub_router)
    app.include_router(rbac.router)
    app.include_router(gateway.router)
    app.include_router(teams.router)
    app.include_router(api_registry.router)
    app.include_router(public_catalog.router)
    app.include_router(ai.router)

    # -- Static files -------------------------------------------------------
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # -- Health / readiness -------------------------------------------------
    @app.get("/health", tags=["ops"])
    async def health():
        """Liveness probe -- always returns 200 if the process is running."""
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    async def readiness():
        """Readiness probe -- verifies database connectivity."""
        from app.models.database import engine

        if engine is None:
            return JSONResponse(status_code=503, content={"status": "not_ready", "detail": "DB engine not initialised"})
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text("SELECT 1")
                )
            return {"status": "ready"}
        except Exception as exc:
            logger.error("Readiness check failed: %s", exc)
            return JSONResponse(status_code=503, content={"status": "not_ready", "detail": str(exc)})

    return app


app = create_app()
