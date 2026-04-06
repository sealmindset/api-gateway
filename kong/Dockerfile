# =============================================================================
# Kong API Gateway - Multi-Stage Dockerfile
# =============================================================================
# Builds a production-ready Kong 3.9 image with:
#   - Custom kong.conf configuration
#   - Declarative kong.yml (for DB-less or db_import)
#   - Custom Lua plugins (subscription-validator)
#   - Self-signed SSL certificates for development
#   - Non-root execution for security
#
# Build:
#   docker build -t api-gateway-kong:latest .
#
# Run (DB mode):
#   docker run -d --name kong \
#     -e KONG_PG_HOST=kong-database \
#     -e KONG_PG_PASSWORD=secure_password \
#     -p 8000:8000 -p 8443:8443 -p 8001:8001 -p 8100:8100 \
#     api-gateway-kong:latest
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Plugin Builder
# ---------------------------------------------------------------------------
# Install build dependencies and prepare custom plugin files. This stage
# ensures that only runtime artifacts are copied into the final image.
FROM kong:3.9 AS builder

USER root

# Install build tools needed for any native Lua module compilation.
# If your custom plugins are pure Lua (no C extensions), this stage
# can be simplified or removed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create directory structure for custom plugins
RUN mkdir -p /tmp/plugins/subscription-validator /tmp/plugins/ai-gateway

# Copy custom plugin sources
COPY plugins/subscription-validator.lua /tmp/plugins/subscription-validator/handler.lua
COPY plugins/ai-gateway.lua /tmp/plugins/ai-gateway/handler.lua
COPY plugins/ai-gateway-schema.lua /tmp/plugins/ai-gateway/schema.lua

# Create the plugin schema file required by Kong's plugin loader.
# The schema defines configuration fields that operators can set per-service,
# per-route, or globally.
RUN cat > /tmp/plugins/subscription-validator/schema.lua << 'SCHEMA_EOF'
-- ==========================================================================
-- subscription-validator plugin schema
-- ==========================================================================
-- Defines the configuration interface for the subscription-validator plugin.
-- These fields are validated by Kong when the plugin is applied.

local typedefs = require "kong.db.schema.typedefs"

return {
  name = "subscription-validator",
  fields = {
    { protocols = typedefs.protocols_http },
    { consumer = typedefs.no_consumer },
    { config = {
        type = "record",
        fields = {
          -- URL of the subscription validation service
          {
            validation_endpoint = {
              type = "string",
              required = true,
              default = "http://subscription-service:8080/validate",
            },
          },
          -- HTTP timeout for validation requests (milliseconds)
          {
            timeout = {
              type = "integer",
              required = true,
              default = 5000,
            },
          },
          -- Cache TTL for successful validation responses (seconds)
          {
            cache_ttl = {
              type = "integer",
              required = true,
              default = 300,
            },
          },
          -- Tiers that are allowed to access the endpoint
          {
            allowed_tiers = {
              type = "array",
              elements = { type = "string" },
              default = { "free", "standard", "premium", "enterprise" },
            },
          },
          -- Whether to allow requests when the validation service is unreachable
          {
            fail_open = {
              type = "boolean",
              default = false,
            },
          },
          -- Header prefix for subscription metadata added to proxied requests
          {
            header_prefix = {
              type = "string",
              default = "X-Subscription-",
            },
          },
        },
      },
    },
  },
}
SCHEMA_EOF

# ---------------------------------------------------------------------------
# Stage 2: SSL Certificate Generator
# ---------------------------------------------------------------------------
# Generate self-signed certificates for development and testing. In
# production, replace these with certificates from your PKI or a CA
# like Let's Encrypt.
FROM kong:3.9 AS ssl-generator

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/ssl && \
    openssl req -new -newkey rsa:2048 -days 365 -nodes -x509 \
      -subj "/C=US/ST=Minnesota/L=Minneapolis/O=SleepNumber/CN=api-gateway.local" \
      -keyout /tmp/ssl/server.key \
      -out /tmp/ssl/server.crt && \
    chmod 644 /tmp/ssl/server.crt && \
    chmod 640 /tmp/ssl/server.key

# ---------------------------------------------------------------------------
# Stage 3: Final Runtime Image
# ---------------------------------------------------------------------------
# Assemble the production image with only the artifacts needed at runtime.
FROM kong:3.9

LABEL maintainer="platform-engineering@sleepnumber.com"
LABEL description="Kong API Gateway with multi-auth, rate limiting, and Cribl integration"
LABEL version="1.0.0"

USER root

# Create directories for configuration, plugins, and SSL
RUN mkdir -p /etc/kong/ssl \
             /usr/local/share/lua/5.1/kong/plugins/subscription-validator \
             /usr/local/share/lua/5.1/kong/plugins/ai-gateway \
    && chown -R kong:kong /etc/kong \
    && chown -R kong:kong /usr/local/share/lua/5.1/kong/plugins/subscription-validator \
    && chown -R kong:kong /usr/local/share/lua/5.1/kong/plugins/ai-gateway

# Copy SSL certificates from generator stage
COPY --from=ssl-generator --chown=kong:kong /tmp/ssl/server.crt /etc/kong/ssl/server.crt
COPY --from=ssl-generator --chown=kong:kong /tmp/ssl/server.key /etc/kong/ssl/server.key

# Copy custom plugin files from builder stage
COPY --from=builder --chown=kong:kong /tmp/plugins/subscription-validator/handler.lua \
     /usr/local/share/lua/5.1/kong/plugins/subscription-validator/handler.lua
COPY --from=builder --chown=kong:kong /tmp/plugins/subscription-validator/schema.lua \
     /usr/local/share/lua/5.1/kong/plugins/subscription-validator/schema.lua

# Copy ai-gateway plugin files from builder stage
COPY --from=builder --chown=kong:kong /tmp/plugins/ai-gateway/handler.lua \
     /usr/local/share/lua/5.1/kong/plugins/ai-gateway/handler.lua
COPY --from=builder --chown=kong:kong /tmp/plugins/ai-gateway/schema.lua \
     /usr/local/share/lua/5.1/kong/plugins/ai-gateway/schema.lua

# Copy Kong configuration files
COPY --chown=kong:kong kong.conf /etc/kong/kong.conf
COPY --chown=kong:kong kong.yml /etc/kong/kong.yml

# ---------------------------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------------------------
# These provide sensible defaults that can be overridden at runtime.
# Sensitive values (passwords, keys) MUST be overridden via environment
# variables or a secrets manager -- never bake them into the image.

ENV KONG_CONF=/etc/kong/kong.conf
ENV KONG_PREFIX=/usr/local/kong

# Database defaults (override in production)
ENV KONG_DATABASE=postgres
ENV KONG_PG_HOST=kong-database
ENV KONG_PG_PORT=5432
ENV KONG_PG_USER=kong
ENV KONG_PG_PASSWORD=kong
ENV KONG_PG_DATABASE=kong

# Listener configuration
ENV KONG_PROXY_LISTEN="0.0.0.0:8000 reuseport backlog=16384, 0.0.0.0:8443 http2 ssl reuseport backlog=16384"
ENV KONG_ADMIN_LISTEN="127.0.0.1:8001 reuseport backlog=16384, 127.0.0.1:8444 http2 ssl reuseport backlog=16384"
ENV KONG_STATUS_LISTEN="0.0.0.0:8100"

# Plugin configuration
ENV KONG_PLUGINS="bundled,subscription-validator,ai-gateway"

# Logging
ENV KONG_LOG_LEVEL=info

# SSL
ENV KONG_SSL_CERT=/etc/kong/ssl/server.crt
ENV KONG_SSL_CERT_KEY=/etc/kong/ssl/server.key

# DNS resolver: leave unset so Docker/Kubernetes DNS is used automatically.
# Override via KONG_DNS_RESOLVER env var if a custom resolver is needed.

# Disable anonymous telemetry
ENV KONG_ANONYMOUS_REPORTS=off

# Custom: identify the runtime environment for log tagging
ENV KONG_ENVIRONMENT=production

# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------
# 8000  - Proxy HTTP
# 8443  - Proxy HTTPS
# 8001  - Admin API HTTP (localhost only by default)
# 8444  - Admin API HTTPS (localhost only by default)
# 8100  - Status / Prometheus metrics
EXPOSE 8000 8443 8001 8444 8100

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD kong health || exit 1

# ---------------------------------------------------------------------------
# Run as non-root
# ---------------------------------------------------------------------------
USER kong

# Default entrypoint from the base Kong image starts Kong with the
# provided configuration. Override CMD for migrations or custom startup.
CMD ["kong", "docker-start"]
