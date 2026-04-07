"""Public API catalog — unauthenticated read-only access to active API contracts."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import ApiRegistration, get_db_session
from app.models.schemas import PaginatedResponse, PublicApiCatalogEntry

router = APIRouter(prefix="/public/api-catalog", tags=["public-catalog"])


@router.get("", response_model=PaginatedResponse)
async def list_public_apis(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """List active APIs with their data contracts. No authentication required."""
    query = select(ApiRegistration).where(ApiRegistration.status == "active")
    count_query = select(func.count(ApiRegistration.id)).where(ApiRegistration.status == "active")

    if search:
        like = f"%{search}%"
        query = query.where(
            ApiRegistration.name.ilike(like) | ApiRegistration.slug.ilike(like)
        )
        count_query = count_query.where(
            ApiRegistration.name.ilike(like) | ApiRegistration.slug.ilike(like)
        )

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(ApiRegistration.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [PublicApiCatalogEntry.model_validate(r) for r in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{slug}", response_model=PublicApiCatalogEntry)
async def get_public_api(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get a single active API's data contract by slug. No authentication required."""
    result = await db.execute(
        select(ApiRegistration).where(
            ApiRegistration.slug == slug,
            ApiRegistration.status == "active",
        )
    )
    reg = result.scalar_one_or_none()
    if reg is None:
        raise HTTPException(status_code=404, detail="API not found or not active.")
    return PublicApiCatalogEntry.model_validate(reg)


@router.get("/{slug}/try-it", response_class=HTMLResponse)
async def try_api(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Interactive Swagger UI for an active API. Requires an OpenAPI spec URL."""
    result = await db.execute(
        select(ApiRegistration).where(
            ApiRegistration.slug == slug,
            ApiRegistration.status == "active",
        )
    )
    reg = result.scalar_one_or_none()
    if reg is None:
        raise HTTPException(status_code=404, detail="API not found or not active.")
    if not reg.openapi_spec_url:
        raise HTTPException(
            status_code=404,
            detail="This API does not have an OpenAPI specification URL configured.",
        )

    settings = get_settings()
    gateway_url = f"{settings.kong_proxy_url}{reg.gateway_path or f'/api/{reg.slug}'}"
    description = reg.description or ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{reg.name} — Try It</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    .portal-header {{
      background: #1a1a2e; color: #fff; padding: 24px 32px;
    }}
    .portal-header h1 {{ margin: 0 0 4px 0; font-size: 1.6rem; }}
    .portal-header .meta {{ opacity: 0.7; font-size: 0.9rem; }}
    .portal-header .desc {{ margin-top: 8px; font-size: 0.95rem; opacity: 0.85; }}
    .api-key-bar {{
      background: #f0f4f8; padding: 12px 32px; display: flex; align-items: center; gap: 12px;
      border-bottom: 1px solid #d0d7de;
    }}
    .api-key-bar input {{
      padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; width: 320px; font-size: 0.9rem;
    }}
    .api-key-bar button {{
      padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 4px;
      cursor: pointer; font-size: 0.9rem;
    }}
    .api-key-bar button:hover {{ background: #1d4ed8; }}
    .api-key-bar .hint {{ font-size: 0.8rem; color: #666; }}
  </style>
</head>
<body>
  <div class="portal-header">
    <h1>{reg.name}</h1>
    <div class="meta">Version {reg.version} &middot; {reg.api_type.upper()} &middot; Auth: {reg.auth_type}</div>
    <div class="desc">{description}</div>
  </div>
  <div class="api-key-bar">
    <label for="apiKeyInput"><strong>API Key:</strong></label>
    <input type="text" id="apiKeyInput" placeholder="Enter your API key to authorize requests" />
    <button onclick="applyKey()">Authorize</button>
    <span class="hint">Your key is sent as the <code>apikey</code> header with each request.</span>
  </div>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
  <script>
    const ui = SwaggerUIBundle({{
      url: "{reg.openapi_spec_url}",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
      layout: "StandaloneLayout",
      persistAuthorization: true,
      withCredentials: false,
      requestInterceptor: function(req) {{
        // Override server URL to gateway
        if (!req.url.startsWith("{gateway_url}")) {{
          try {{
            const u = new URL(req.url);
            req.url = "{gateway_url}" + u.pathname + u.search;
          }} catch(e) {{}}
        }}
        return req;
      }},
    }});
    function applyKey() {{
      const key = document.getElementById("apiKeyInput").value;
      if (key) {{
        ui.preauthorizeApiKey("apiKey", key);
        // Also set as header for key-auth plugin
        const oldInterceptor = ui.getConfigs().requestInterceptor;
        ui.getConfigs().requestInterceptor = function(req) {{
          req.headers["apikey"] = key;
          if (oldInterceptor) return oldInterceptor(req);
          return req;
        }};
      }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)
