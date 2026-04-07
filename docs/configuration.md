# Configuration Reference

Complete reference for every environment variable and configuration parameter across all services in the API Gateway platform. Variables are organized by service, with tables showing name, description, whether the variable is required, its default value, and an example.

> **Convention**: Variables marked **Required (prod)** are optional during local development (sensible defaults are provided) but must be explicitly set in production deployments.

---

## Table of Contents

- [Environment File (.env)](#environment-file-env)
- [Admin Panel (FastAPI)](#admin-panel-fastapi)
  - [Application](#application)
  - [Database](#database)
  - [Redis](#redis)
  - [Kong Admin API](#kong-admin-api)
  - [Microsoft Entra ID (OIDC)](#microsoft-entra-id-oidc)
  - [AI / Claude](#ai--claude)
  - [Rate Limit Tier Defaults](#rate-limit-tier-defaults)
  - [Cribl Integration](#cribl-integration)
  - [CORS](#cors)
- [Kong Gateway](#kong-gateway)
  - [Database Connection](#kong-database-connection)
  - [Listeners](#kong-listeners)
  - [Logging](#kong-logging)
  - [Plugins](#kong-plugins)
  - [DNS](#kong-dns)
  - [Nginx Tuning](#kong-nginx-tuning)
  - [SSL / TLS](#kong-ssl--tls)
  - [Performance](#kong-performance)
  - [Observability](#kong-observability)
- [Frontend (Next.js)](#frontend-nextjs)
- [PostgreSQL](#postgresql)
- [Redis](#redis-1)
- [Prometheus](#prometheus)
- [Grafana](#grafana)
- [Cribl Stream](#cribl-stream)
  - [Core Settings](#cribl-core-settings)
  - [Distributed / Leader](#cribl-distributed--leader)
  - [Worker Settings](#cribl-worker-settings)
  - [Global Variables](#cribl-global-variables)
  - [Output Destinations](#cribl-output-destinations)
  - [Notifications](#cribl-notifications)
  - [Inputs](#cribl-inputs)
- [OWASP ZAP Scanner](#owasp-zap-scanner)
- [ZAP Exporter](#zap-exporter)
- [CI/CD and Container Registry](#cicd-and-container-registry)
- [Host Port Mapping](#host-port-mapping)
- [Production Checklist](#production-checklist)

---

## Environment File (.env)

All services read configuration from environment variables. A `.env.example` template is provided at the repository root.

```bash
cp .env.example .env
# Edit .env with your values -- never commit this file
```

The setup script `scripts/setup-local.sh` auto-generates secrets for local development.

---

## Admin Panel (FastAPI)

Source: `admin-panel/app/config.py` (Pydantic `BaseSettings`, reads from environment or `.env` file).

### Application

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ENVIRONMENT` | Runtime environment identifier | Optional | `development` | `production` |
| `SECRET_KEY` | Secret key for JWT signing, session encryption, and CSRF protection. **Generate with `openssl rand -hex 32`** | **Required (prod)** | `change-me-in-production` | `a3f8c9e1d7b2...` |
| `DEBUG` | Enable debug mode (verbose errors, auto-reload) | Optional | `false` | `true` |
| `APP_NAME` | Display name for the admin panel | Optional | `API Gateway Admin Panel` | `SN API Gateway` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT access token lifetime in minutes | Optional | `60` | `30` |

### Database

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `DATABASE_URL` | Full PostgreSQL connection DSN | **Required** | `postgresql://api_gateway_admin:admin_local_dev@localhost:5432/api_gateway_admin` | `postgresql://user:pass@db-host:5432/api_gateway_admin` |
| `DB_POOL_MIN_SIZE` | Minimum connections in the async connection pool | Optional | `5` | `10` |
| `DB_POOL_MAX_SIZE` | Maximum connections in the async connection pool | Optional | `20` | `50` |
| `DB_ECHO` | Log all SQL statements (debug only) | Optional | `false` | `true` |

### Redis

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `REDIS_URL` | Redis connection URL for session storage and caching | **Required** | `redis://localhost:6379/0` | `redis://:secretpass@redis-host:6379/0` |

### Kong Admin API

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_ADMIN_URL` | Base URL for the Kong Admin API | **Required** | `http://localhost:8001` | `http://kong:8001` |
| `KONG_ADMIN_TOKEN` | Optional bearer token for authenticating to the Kong Admin API | Optional | `null` | `my-admin-token` |

### Microsoft Entra ID (OIDC)

These variables configure OAuth2 / OpenID Connect authentication via Microsoft Entra ID (Azure AD).

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ENTRA_TENANT_ID` | Azure AD tenant ID (GUID) | **Required (prod)** | `not-configured` | `72f988bf-86f1-41af-91ab-2d7cd011db47` |
| `ENTRA_CLIENT_ID` | Application (client) ID registered in Entra ID | **Required (prod)** | `not-configured` | `abcd1234-ef56-7890-abcd-ef1234567890` |
| `ENTRA_CLIENT_SECRET` | Client secret value from Entra ID app registration | **Required (prod)** | `not-configured` | `~A8Q...secret...` |
| `ENTRA_REDIRECT_URI` | OAuth2 redirect URI registered in the Entra ID app | **Required (prod)** | `http://localhost:8000/auth/callback` | `https://admin.api-gateway.example.com/auth/callback` |

Derived properties (computed at runtime, not directly settable):
- **Authority URL**: `https://login.microsoftonline.com/{ENTRA_TENANT_ID}`
- **OpenID Config URL**: `{authority}/v2.0/.well-known/openid-configuration`
- **JWKS URI**: `https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys`

### AI / Claude

Configure the AI provider used for traffic analysis, anomaly detection, and prompt management.

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `AI_PROVIDER` | AI backend: `anthropic_foundry` (Azure AI Foundry) or `claude` (direct Anthropic API) | Optional | `anthropic_foundry` | `claude` |
| `ANTHROPIC_API_KEY` | Anthropic API key. Used by both `claude` and `anthropic_foundry` providers unless `AZURE_AI_FOUNDRY_API_KEY` overrides | **Required (prod)** | *(empty)* | `sk-ant-api03-...` |
| `ANTHROPIC_MODEL` | Model or deployment name to use | Optional | `cogdep-aifoundry-dev-eus2-claude-sonnet-4-5` | `claude-sonnet-4-20250514` |
| `AZURE_AI_FOUNDRY_ENDPOINT` | Azure AI Foundry endpoint URL (required when `AI_PROVIDER=anthropic_foundry`) | Conditional | *(empty)* | `https://my-foundry.cognitiveservices.azure.com` |
| `AZURE_AI_FOUNDRY_API_KEY` | Separate API key for Azure AI Foundry. Falls back to `ANTHROPIC_API_KEY` if not set | Optional | *(empty)* | `abc123def456...` |
| `AI_MAX_COST_PER_ANALYSIS` | Maximum cost budget per AI analysis in USD | Optional | `0.50` | `1.00` |
| `AI_SAMPLING_RATE` | Fraction of requests to analyze (0.0 to 1.0) | Optional | `0.1` | `0.25` |

### Rate Limit Tier Defaults

These define the default rate limits per subscription tier. Each tier has `_SECOND`, `_MINUTE`, and `_HOUR` variants. All values are integers representing requests per time window.

| Variable | Description | Default |
|---|---|---|
| `RATE_LIMIT_FREE_SECOND` | Free tier: requests per second | `1` |
| `RATE_LIMIT_FREE_MINUTE` | Free tier: requests per minute | `30` |
| `RATE_LIMIT_FREE_HOUR` | Free tier: requests per hour | `500` |
| `RATE_LIMIT_BASIC_SECOND` | Basic tier: requests per second | `5` |
| `RATE_LIMIT_BASIC_MINUTE` | Basic tier: requests per minute | `100` |
| `RATE_LIMIT_BASIC_HOUR` | Basic tier: requests per hour | `3000` |
| `RATE_LIMIT_PRO_SECOND` | Pro tier: requests per second | `20` |
| `RATE_LIMIT_PRO_MINUTE` | Pro tier: requests per minute | `500` |
| `RATE_LIMIT_PRO_HOUR` | Pro tier: requests per hour | `15000` |
| `RATE_LIMIT_ENTERPRISE_SECOND` | Enterprise tier: requests per second | `100` |
| `RATE_LIMIT_ENTERPRISE_MINUTE` | Enterprise tier: requests per minute | `3000` |
| `RATE_LIMIT_ENTERPRISE_HOUR` | Enterprise tier: requests per hour | `100000` |

### Cribl Integration

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `CRIBL_ENDPOINT` | Cribl Stream / Edge endpoint for log forwarding | Optional | `http://localhost:9514` | `http://cribl:9514` |
| `CRIBL_TOKEN` | Authentication token for Cribl endpoint | Optional | `null` | `cribl-auth-token-123` |

### CORS

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | Optional | `http://localhost:3000,http://localhost:8000` | `https://admin.example.com,https://portal.example.com` |

---

## Kong Gateway

Kong is configured via `kong/kong.conf` (file-based defaults) and environment variables in `docker-compose.yml`. Environment variables use the `KONG_` prefix and override any file-based settings. Full reference: [Kong Configuration Docs](https://docs.konghq.com/gateway/latest/reference/configuration/).

### Kong Database Connection

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_DATABASE` | Database backend: `postgres` or `off` (DB-less mode) | **Required** | `postgres` | `postgres` |
| `KONG_PG_HOST` | PostgreSQL hostname | **Required** | `kong-database` | `postgres` |
| `KONG_PG_PORT` | PostgreSQL port | Optional | `5432` | `5432` |
| `KONG_PG_USER` | PostgreSQL username for Kong | **Required** | `kong` | `kong` |
| `KONG_PG_PASSWORD` | PostgreSQL password for Kong | **Required (prod)** | `kong` | `kong_secure_password` |
| `KONG_PG_DATABASE` | PostgreSQL database name for Kong | Optional | `kong` | `kong` |
| `KONG_PG_TIMEOUT` | PostgreSQL connection timeout in milliseconds | Optional | `5000` | `10000` |
| `KONG_PG_MAX_CONCURRENT_QUERIES` | Maximum concurrent queries (0 = unlimited) | Optional | `0` | `100` |
| `KONG_PG_SEMAPHORE_TIMEOUT` | Semaphore wait timeout in milliseconds | Optional | `60000` | `30000` |
| `KONG_PG_SSL` | Enable SSL for PostgreSQL connections | Optional | `off` | `on` |
| `KONG_PG_SSL_VERIFY` | Verify PostgreSQL server certificate | Optional | `off` | `on` |

### Kong Listeners

| Variable | Description | Required | Default (dev) | Default (prod) |
|---|---|---|---|---|
| `KONG_PROXY_LISTEN` | Proxy listener addresses (client-facing traffic) | Optional | `0.0.0.0:8000, 0.0.0.0:8443 ssl` | `0.0.0.0:8000, 0.0.0.0:8443 ssl http2` |
| `KONG_ADMIN_LISTEN` | Admin API listener addresses | Optional | `0.0.0.0:8001, 0.0.0.0:8444 ssl` | `127.0.0.1:8001` |
| `KONG_STATUS_LISTEN` | Status/metrics endpoint listener | Optional | `0.0.0.0:8100` | `0.0.0.0:8100` |

> **Security**: The Admin API must never be exposed to untrusted networks. In production it is bound to `127.0.0.1` only.

### Kong Logging

| Variable | Description | Required | Default (dev) | Default (prod) |
|---|---|---|---|---|
| `KONG_LOG_LEVEL` | Log verbosity: `debug`, `info`, `notice`, `warn`, `error`, `crit` | Optional | `info` | `warn` |
| `KONG_PROXY_ACCESS_LOG` | Proxy access log destination | Optional | `/dev/stdout` | `/dev/stdout` |
| `KONG_PROXY_ERROR_LOG` | Proxy error log destination | Optional | `/dev/stderr` | `/dev/stderr` |
| `KONG_ADMIN_ACCESS_LOG` | Admin API access log destination | Optional | `/dev/stdout` | `off` |
| `KONG_ADMIN_ERROR_LOG` | Admin API error log destination | Optional | `/dev/stderr` | `/dev/stderr` |

### Kong Plugins

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_PLUGINS` | Comma-separated list of plugins to load. `bundled` loads all built-in plugins | **Required** | `bundled,subscription-validator,ai-gateway` | `bundled,my-custom-plugin` |

The declarative configuration (`kong/kong.yml`) enables these plugins:

| Plugin | Scope | Purpose |
|---|---|---|
| `correlation-id` | Global | Injects `X-Request-ID` header for distributed tracing |
| `prometheus` | Global | Exposes metrics on status port 8100 |
| `tcp-log` | Global | Ships structured JSON logs to Cribl Stream over TCP (port 5514) |
| `http-log` | Global | Fallback HTTP log shipping to Cribl (port 9080) |
| `cors` | Global | Cross-origin resource sharing headers |
| `ip-restriction` | Global (disabled by default) / Internal service (enabled) | IP allowlist enforcement |
| `bot-detection` | Global | Blocks known bot user-agents |
| `request-transformer` | Global | Adds gateway metadata headers (`X-Gateway`, `X-Gateway-Version`) |
| `oauth2` | Service: api-v1-oauth2 | OAuth2 bearer token authentication |
| `key-auth` | Service: api-v1-keyauth | API key authentication (header or query param) |
| `basic-auth` | Service: internal-api | Basic authentication for internal endpoints |
| `rate-limiting` | Per-service | Request rate limiting per minute/hour |
| `subscription-validator` | Custom | Validates subscription tier status |
| `ai-gateway` | Custom | AI traffic routing and analysis |

### Kong DNS

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_DNS_RESOLVER` | Custom DNS resolver address. Leave empty for system/container DNS | Optional | *(empty)* | `127.0.0.11:53` |
| `KONG_DNS_ORDER` | DNS resolution order | Optional | `LAST,A,SRV,CNAME` | `LAST,A,SRV` |
| `KONG_DNS_VALID_TTL` | TTL override for valid DNS responses (seconds) | Optional | `30` | `60` |
| `KONG_DNS_STALE_TTL` | Time to serve stale DNS records (seconds) | Optional | `4` | `10` |
| `KONG_DNS_NOT_FOUND_TTL` | Cache duration for NXDOMAIN responses (seconds) | Optional | `1` | `5` |
| `KONG_DNS_ERROR_TTL` | Cache duration for DNS errors (seconds) | Optional | `1` | `5` |
| `KONG_DNS_NO_SYNC` | Disable synchronous DNS resolution | Optional | `off` | `on` |

### Kong Nginx Tuning

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_NGINX_WORKER_PROCESSES` | Number of Nginx worker processes | Optional | `auto` | `4` |
| `KONG_CLIENT_MAX_BODY_SIZE` | Maximum client request body size | Optional | `16m` | `64m` |
| `KONG_CLIENT_BODY_BUFFER_SIZE` | Client body buffer size | Optional | `8k` | `16k` |
| `KONG_NGINX_HTTP_LUA_SHARED_DICT` | Lua shared memory dictionaries (production tuning) | Optional | *(not set)* | `prometheus_metrics 32m` |

### Kong SSL / TLS

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_SSL_CERT` | Path to SSL certificate for the proxy listener | Optional | `/etc/kong/ssl/server.crt` | `/certs/proxy.crt` |
| `KONG_SSL_CERT_KEY` | Path to SSL private key for the proxy listener | Optional | `/etc/kong/ssl/server.key` | `/certs/proxy.key` |
| `KONG_SSL_PROTOCOLS` | Allowed SSL/TLS protocol versions | Optional | `TLSv1.2 TLSv1.3` | `TLSv1.3` |
| `KONG_SSL_PREFER_SERVER_CIPHERS` | Prefer server cipher order | Optional | `on` | `on` |
| `KONG_SSL_CIPHERS` | Allowed cipher suites | Optional | `ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384` | *(see kong.conf)* |
| `KONG_ADMIN_SSL_CERT` | Path to SSL certificate for Admin API | Optional | `/etc/kong/ssl/server.crt` | `/certs/admin.crt` |
| `KONG_ADMIN_SSL_CERT_KEY` | Path to SSL private key for Admin API | Optional | `/etc/kong/ssl/server.key` | `/certs/admin.key` |

### Kong Performance

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_UPSTREAM_KEEPALIVE_POOL_SIZE` | Connection pool size to upstream services | Optional | `256` | `128` |
| `KONG_UPSTREAM_KEEPALIVE_MAX_REQUESTS` | Max requests per keepalive connection | Optional | `10000` | `5000` |
| `KONG_UPSTREAM_KEEPALIVE_IDLE_TIMEOUT` | Idle timeout for keepalive connections (seconds) | Optional | `60` | `120` |
| `KONG_ANONYMOUS_REPORTS` | Send anonymous usage reports to Kong Inc. | Optional | `off` | `off` |

### Kong Observability

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_TRUSTED_IPS` | Trusted proxy IP ranges for `X-Forwarded-For` header extraction | Optional | `0.0.0.0/0,::/0` | `10.0.0.0/8` |
| `KONG_REAL_IP_HEADER` | Header to extract real client IP from | Optional | `X-Forwarded-For` | `X-Real-IP` |
| `KONG_REAL_IP_RECURSIVE` | Recursively search trusted IPs in the header | Optional | `on` | `off` |

---

## Frontend (Next.js)

Source: `frontend/next.config.js`. The frontend uses server-side API rewrites (not `NEXT_PUBLIC_*` browser-exposed variables) to proxy requests to backend services.

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_ADMIN_URL` | Kong Admin API URL. Server-side only, used for `/api/kong/*` proxy rewrites | **Required** | `http://kong:8001` | `http://kong:8001` |
| `ADMIN_API_URL` | Admin Panel API URL. Server-side only, used for `/api/*` proxy rewrites | **Required** | `http://admin-panel:8080` | `http://admin-panel:8080` |
| `FRONTEND_PORT` | Host port mapped to the Next.js dev server | Optional | `3000` | `3001` |

> **Note**: These are server-side runtime variables, never exposed to the browser. The Next.js frontend proxies all API calls through its own server using `rewrites()` in `next.config.js`, eliminating the need for `NEXT_PUBLIC_*` variables.

---

## PostgreSQL

PostgreSQL 16 (Alpine) serves as the primary database for both Kong and the Admin Panel. Two separate databases and users are created on initialization via `database/init.sh`.

### Superuser (Initialization Only)

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `POSTGRES_USER` | PostgreSQL superuser name | Optional | `postgres` | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password | **Required (prod)** | `postgres_local_dev` | `strong_random_password` |
| `POSTGRES_DB` | Default database created on init | Optional | `postgres` | `postgres` |
| `POSTGRES_PORT` | Host port mapped to PostgreSQL | Optional | `5432` | `5433` |

### Kong Database User

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `KONG_PG_USER` | Username for Kong's database | Optional | `kong` | `kong` |
| `KONG_PG_PASSWORD` | Password for Kong's database user | **Required (prod)** | `kong_local_dev` | `kong_secure_password` |
| `KONG_PG_DATABASE` | Database name for Kong | Optional | `kong` | `kong` |

### Admin Panel Database User

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ADMIN_DB_USER` | Username for the admin panel database | Optional | `api_gateway_admin` | `api_gateway_admin` |
| `ADMIN_DB_PASSWORD` | Password for the admin panel database user | **Required (prod)** | `admin_local_dev` | `admin_secure_password` |
| `ADMIN_DB_NAME` | Database name for the admin panel | Optional | `api_gateway_admin` | `api_gateway_admin` |
| `ADMIN_DB_HOST` | Database hostname (production only; in dev, uses Docker service name `postgres`) | Prod only | `postgres` | `managed-db.azure.com` |

---

## Redis

Redis 7 (Alpine) provides rate limiting storage and session caching.

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `REDIS_PASSWORD` | Redis authentication password (`requirepass`) | **Required (prod)** | `redis_local_dev` | `redis_secure_password` |
| `REDIS_PORT` | Host port mapped to Redis (container always listens on 6379 internally) | Optional | `6380` | `6379` |
| `REDIS_HOST` | Redis hostname (production only; in dev, uses Docker service name `redis`) | Prod only | `redis` | `managed-redis.azure.com` |

### Redis Server Settings

These are hardcoded in `docker-compose.yml` command arguments, not environment variables:

| Setting | Dev Value | Prod Value | Description |
|---|---|---|---|
| `maxmemory` | `256mb` | `1gb` | Maximum memory limit |
| `maxmemory-policy` | `allkeys-lru` | `allkeys-lru` | Eviction policy when memory limit is reached |
| `appendonly` | `yes` | `yes` | Append-only file persistence |
| `appendfsync` | *(default: everysec)* | `everysec` | AOF fsync frequency |
| `tcp-backlog` | *(default: 128)* | `511` | TCP listen backlog queue size |
| `timeout` | *(default: 0)* | `300` | Client idle timeout in seconds (0 = disabled) |

---

## Prometheus

Prometheus v2.51.0 collects metrics from all services. Configuration is file-based via `monitoring/prometheus/prometheus.yml`, `alerts.yml`, and `recording_rules.yml`.

### Command-Line Flags

| Flag | Description | Dev Value | Prod Value |
|---|---|---|---|
| `--config.file` | Path to Prometheus config file | `/etc/prometheus/prometheus.yml` | `/etc/prometheus/prometheus.yml` |
| `--storage.tsdb.path` | TSDB storage directory | `/prometheus` | `/prometheus` |
| `--storage.tsdb.retention.time` | Data retention period | `15d` | `30d` |
| `--storage.tsdb.retention.size` | Maximum TSDB size on disk | *(not set)* | `10GB` |
| `--web.enable-lifecycle` | Enable HTTP reload (`/-/reload`) and shutdown APIs | `true` | `true` |

### Global Scrape Settings

Defined in `monitoring/prometheus/prometheus.yml`:

| Setting | Value | Description |
|---|---|---|
| `scrape_interval` | `15s` | Default interval between scrapes |
| `evaluation_interval` | `15s` | Interval between rule evaluations |
| `scrape_timeout` | `10s` | Timeout per scrape request |
| External label: `cluster` | `api-gateway` | Label applied to all metrics |
| External label: `environment` | `production` | Label applied to all metrics |

### Scrape Targets

| Job Name | Target | Interval | Metrics Path | Description |
|---|---|---|---|---|
| `kong` | `kong:8100` | 15s | `/metrics` | Kong Gateway Prometheus plugin |
| `admin-panel` | `admin-panel:3000` | 30s | `/metrics` | Admin Panel application metrics |
| `node-exporter` | `node-exporter:9100` | 30s | `/metrics` | Host-level system metrics |
| `cadvisor` | `cadvisor:8080` | 30s | `/metrics` | Container-level metrics |
| `zap-exporter` | `zap-exporter:9290` | 30s | `/metrics` | OWASP ZAP security scan metrics |
| `kubernetes-pods` | *(auto-discovered)* | 15s | *(annotation-driven)* | Pods with `prometheus.io/scrape: "true"` |
| `kubernetes-service-endpoints` | *(auto-discovered)* | 15s | *(annotation-driven)* | Services with `prometheus.io/scrape: "true"` |

### Remote Write

Prometheus forwards selected metrics to Cribl Stream:

| Setting | Value | Description |
|---|---|---|
| URL | `http://cribl:9090/api/v1/write` | Cribl Prometheus remote write endpoint |
| Metric filter | `kong_.*`, `node_.*`, `container_.*`, `zap_.*` | Only these metric prefixes are forwarded |
| `max_samples_per_send` | `5000` | Batch size limit |
| `batch_send_deadline` | `5s` | Maximum time before flushing a batch |

### Alertmanager

| Setting | Value | Description |
|---|---|---|
| Target | `alertmanager:9093` | Alertmanager endpoint for firing alerts |

### Host Port

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `PROMETHEUS_PORT` | Host port mapped to Prometheus UI and API | Optional | `9090` | `9090` |

---

## Grafana

Grafana v10.4.0 provides dashboards and visualization. Data sources and dashboards are auto-provisioned from `monitoring/grafana/provisioning/`.

### Environment Variables

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `GF_SECURITY_ADMIN_USER` | Grafana admin username | **Required (prod)** | `admin` | `grafana_admin` |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin password | **Required (prod)** | `admin` | `strong_password` |
| `GF_USERS_ALLOW_SIGN_UP` | Allow public user registration | Optional | `false` | `false` |
| `GF_SERVER_ROOT_URL` | Public-facing root URL for Grafana | Optional | `http://localhost:3000` | `https://grafana.api-gateway.example.com` |
| `GF_AUTH_ANONYMOUS_ENABLED` | Allow anonymous access (production override) | Optional | *(not set)* | `false` |
| `GF_LOG_MODE` | Log output mode (production override) | Optional | *(not set)* | `console` |
| `GF_LOG_LEVEL` | Log verbosity (production override) | Optional | *(not set)* | `warn` |
| `GRAFANA_PORT` | Host port mapped to Grafana UI | Optional | `3000` | `3001` |
| `GRAFANA_ROOT_URL` | Public URL used in `docker-compose.prod.yml` override | Prod only | *(not set)* | `https://grafana.api-gateway.example.com` |

### Provisioned Data Sources

Auto-configured via `monitoring/grafana/provisioning/datasources/datasources.yml`:

| Name | Type | URL | Default | Notes |
|---|---|---|---|---|
| Prometheus | `prometheus` | `http://prometheus:9090` | Yes | Supports alerting, incremental querying |
| PostgreSQL | `postgres` | `postgres-kong:5432` | No | Uses `$__env{POSTGRES_USER}` and `$__env{POSTGRES_PASSWORD}` for credentials; SSL mode: `require` |

---

## Cribl Stream

Cribl Stream v4.5.0 (Community Edition) handles log routing, transformation, and forwarding to downstream SIEM/observability platforms.

### Cribl Core Settings

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `CRIBL_DIST_MODE` | Deployment mode: `single` (Docker Compose) or `managed-edge` (distributed) | Optional | `single` | `managed-edge` |
| `CRIBL_PORT` | Host port mapped to Cribl UI (port 9420) | Optional | `9420` | `9420` |
| `CRIBL_SYSLOG_PORT` | Host port mapped to syslog input (port 5140) | Optional | `5140` | `5140` |

### Cribl Distributed / Leader

These apply when `CRIBL_DIST_MODE=managed-edge` (defined in `monitoring/cribl/cribl.yml`):

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `CRIBL_LEADER_HOST` | Hostname of the Cribl leader node | Conditional | `cribl-leader` | `cribl-leader.internal` |
| `CRIBL_LEADER_AUTH_TOKEN` | Authentication token for leader communication | Conditional | *(none)* | `leader-secret-token` |

### Cribl Worker Settings

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `CRIBL_WORKER_PROCESSES` | Number of worker processes (`auto` = detect CPU cores) | Optional | `auto` | `4` |
| `CRIBL_WORKER_MEM_LIMIT` | Worker memory limit in MB | Optional | `2048` | `4096` |
| `CRIBL_HTTP_AUTH_TOKEN` | Auth token for HTTP inputs (Kong log, ZAP findings) | Optional | *(none)* | `http-input-secret` |

### Cribl Global Variables

Available in all pipelines as `C.vars.*` (defined in `monitoring/cribl/cribl.yml`):

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Environment label added to all processed events | `production` |
| `CLUSTER_NAME` | Cluster name label | `api-gateway` |

### Cribl Output Destinations

Configured in `monitoring/cribl/cribl.yml`:

#### Splunk HEC (Real-Time Indexing)

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `SPLUNK_HEC_URL` | Splunk HTTP Event Collector URL | Conditional | `https://splunk-hec.internal:8088` | `https://splunk.corp.com:8088` |
| `SPLUNK_HEC_TOKEN` | Splunk HEC authentication token | Conditional | *(none)* | `12345678-abcd-ef01-...` |

#### Amazon S3 (Long-Term Archive)

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `S3_ARCHIVE_BUCKET` | S3 bucket name for log archives | Conditional | `api-gateway-logs-archive` | `my-log-bucket` |
| `AWS_REGION` | AWS region for S3 | Conditional | `us-east-1` | `us-west-2` |
| `S3_ROLE_ARN` | IAM role ARN to assume for S3 access | Optional | *(empty)* | `arn:aws:iam::123456:role/cribl-s3` |

#### Prometheus Remote Write (Metrics)

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `PROMETHEUS_REMOTE_WRITE_URL` | Prometheus remote write endpoint | Optional | `http://prometheus:9090/api/v1/write` | `http://thanos:9090/api/v1/write` |

#### Alerting Webhook

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ALERTING_WEBHOOK_URL` | URL for anomaly alert delivery (Alertmanager, PagerDuty, etc.) | Optional | `https://alertmanager:9093/api/v2/alerts` | `https://pagerduty.example.com/webhook` |

### Cribl Notifications

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL for Cribl internal pipeline alerts (errors, backpressure) | Optional | *(none)* | `https://hooks.slack.com/services/T.../B.../...` |

### Cribl Inputs

Defined in `monitoring/cribl/routes/routes.yml`:

| Input ID | Type | Port | Auth | Source | Description |
|---|---|---|---|---|---|
| `http_zap` | HTTP | `9081` | Token | ZAP Exporter | Receives security scan findings as JSON |
| `syslog_kong` | Syslog (TCP) | `5514` | None | Kong `tcp-log` plugin | Receives Kong access logs |
| `http_kong` | HTTP | `9080` | Token | Kong `http-log` plugin | Receives Kong logs as JSON over HTTP |
| `prometheus_rw` | Prometheus | `9090` | None | Prometheus remote write | Receives forwarded Prometheus metrics |

### Cribl Routing Pipelines

Events are routed to specialized pipelines based on content filters:

| Route | Pipeline | Filter Summary | Outputs |
|---|---|---|---|
| Kong Access Logs | `kong-logs` | Syslog/HTTP from Kong, excluding auth and rate-limit events | Splunk, S3, Prometheus |
| Authentication Events | `auth-events` | Events with `auth_event: true`, 401/403 status, or auth plugin names | Splunk, S3, Alerting (if anomalous) |
| Rate Limit Events | `rate-limit-metrics` | Events with `rate_limit_event: true`, 429 status, or rate-limit headers | Prometheus, S3 |
| Security Scan Findings | `security-scanning` | Events from ZAP exporter or with `sourcetype: zap:*` | Splunk (severity >= 3), S3, Alerting (severity >= 3) |
| Prometheus Metrics | *(passthrough)* | Events from `prometheus_rw` input | Prometheus remote write |
| Default | *(none)* | Unmatched events | S3 (for investigation) |

---

## OWASP ZAP Scanner

ZAP runs as a persistent daemon container. It has no user-configurable environment variables in this deployment -- it is configured through its Dockerfile and the baseline scan config file. All dynamic behavior is driven by the **ZAP Exporter** service via ZAP's REST API.

### Scan Rule Configuration

The file `security/zap/zap-baseline.conf` defines the action for each passive scan rule by OWASP ZAP rule ID:

| Action | Meaning | Example Rules |
|---|---|---|
| `FAIL` | Report as critical finding; blocks pipeline if used in CI | XSS Persistent (40014), XSS Reflected (40012), SQL Injection (40018), SSRF (40046), PII Disclosure (10062), Proxy Disclosure (40025), Open Redirect (40028) |
| `WARN` | Report as warning finding | Missing HSTS (10035), Missing CSP (10038), Cookie flags (10010, 10011, 10054), X-Frame-Options (10020), X-Content-Type-Options (10021), Information Disclosure (10023, 10027), Server Version Leak (10036, 10037) |
| `IGNORE` | Suppress the rule entirely | *(none configured by default)* |
| `INFO` | Informational only | *(none configured by default)* |

---

## ZAP Exporter

The ZAP Exporter bridges OWASP ZAP with Prometheus metrics and Cribl Stream. It periodically triggers ZAP scans, collects findings, updates Prometheus gauges/counters, and forwards new alerts to Cribl.

Source: `security/zap-exporter/exporter.py`.

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ZAP_API_URL` | ZAP daemon REST API URL | Optional | `http://zap:8090` | `http://zap:8090` |
| `ZAP_SCAN_MODE` | Scan mode: `passive` (safe for production) or `active` (includes attack-pattern testing -- non-production only) | Optional | `passive` | `active` |
| `ZAP_SCAN_INTERVAL_MINUTES` | Minutes between automated scan cycles | Optional | `5` | `15` |
| `ZAP_TARGET_URLS` | Comma-separated list of initial scan target URLs. Additional targets are auto-discovered from Kong Admin API routes | Optional | `http://kong:8000/health,http://admin-panel:8080/health,http://admin-panel:8080/docs` | `http://kong:8000/api/v1` |
| `CRIBL_STREAM_URL` | Cribl Stream HTTP endpoint for forwarding ZAP findings | Optional | *(empty -- forwarding disabled)* | `http://cribl:9081/api/v1/zap` |
| `CRIBL_STREAM_TOKEN` | Bearer token for authenticating to Cribl Stream HTTP input | Optional | *(empty)* | `cribl-zap-token` |
| `KONG_ADMIN_URL` | Kong Admin API URL (used for automatic route discovery to expand scan targets) | Optional | `http://kong:8001` | `http://kong:8001` |
| `LOG_LEVEL` | Python logging level for the exporter service | Optional | `INFO` | `DEBUG` |

### ZAP Host Ports

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ZAP_API_PORT` | Host port for ZAP API (defined in `.env.example` but not currently mapped in compose) | Optional | `8280` | `8280` |
| `ZAP_PROXY_PORT` | Host port for ZAP proxy + API (maps to container port 8090) | Optional | `8290` | `8290` |
| `ZAP_EXPORTER_PORT` | Host port for ZAP Exporter Prometheus metrics (maps to container port 9290) | Optional | `9290` | `9290` |
| `ZAP_LOG_LEVEL` | Log level passed to ZAP Exporter as its `LOG_LEVEL` environment variable | Optional | `INFO` | `DEBUG` |

### ZAP Exporter Prometheus Metrics

The exporter exposes the following metrics at `/metrics` on port 9290:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `zap_alerts_total` | Counter | `severity`, `alert_name`, `owasp_category` | Total ZAP alerts detected (increments for new alerts) |
| `zap_alerts_active` | Gauge | `severity` | Currently active alerts by severity (High/Medium/Low/Informational) |
| `zap_alerts_by_confidence` | Gauge | `confidence` | Active alerts by confidence level |
| `zap_scan_duration_seconds` | Histogram | `scan_type` | Duration of scan cycles |
| `zap_scan_status` | Gauge | `scan_type` | Current scan status (0=idle, 1=running, 2=completed, 3=error) |
| `zap_last_scan_timestamp` | Gauge | `scan_type` | Unix timestamp of last completed scan |
| `zap_scan_urls_total` | Gauge | *(none)* | Number of URLs discovered and scanned |
| `zap_up` | Gauge | *(none)* | Whether ZAP daemon is reachable (1=up, 0=down) |

---

## CI/CD and Container Registry

These variables are used in `docker-compose.prod.yml` for production container image references.

| Variable | Description | Required | Default | Example |
|---|---|---|---|---|
| `ACR_REGISTRY` | Azure Container Registry hostname | **Required (prod)** | *(none)* | `myacr.azurecr.io` |
| `IMAGE_TAG` | Docker image tag for production deployments | **Required (prod)** | *(none)* | `v1.2.3` or `latest` |

---

## Host Port Mapping

Summary of all host ports configurable via environment variables. These control which ports are exposed on the Docker host during development.

| Variable | Service | Container Port | Default Host Port |
|---|---|---|---|
| `POSTGRES_PORT` | PostgreSQL | `5432` | `5432` |
| `REDIS_PORT` | Redis | `6379` | `6380` |
| `KONG_PROXY_PORT` | Kong Proxy (HTTP) | `8000` | `8000` |
| `KONG_PROXY_SSL_PORT` | Kong Proxy (HTTPS) | `8443` | `8443` |
| `KONG_ADMIN_PORT` | Kong Admin API | `8001` | `8001` |
| `KONG_STATUS_PORT` | Kong Status/Metrics | `8100` | `8100` |
| `ADMIN_PANEL_PORT` | Admin Panel (FastAPI) | `8080` | `8080` |
| `FRONTEND_PORT` | Frontend (Next.js) | `3000` | `3000` |
| `ZAP_PROXY_PORT` | OWASP ZAP Proxy + API | `8090` | `8290` |
| `ZAP_EXPORTER_PORT` | ZAP Exporter Metrics | `9290` | `9290` |
| `PROMETHEUS_PORT` | Prometheus | `9090` | `9090` |
| `GRAFANA_PORT` | Grafana | `3000` | `3000` |
| `CRIBL_PORT` | Cribl Stream UI | `9420` | `9420` |
| `CRIBL_SYSLOG_PORT` | Cribl Syslog Input | `5140` | `5140` |

> **Note**: Grafana and the Next.js frontend both default to host port 3000. In a typical development setup, change one of them (e.g., `FRONTEND_PORT=3001`) to avoid conflicts. In production (`docker-compose.prod.yml`), all host port mappings are removed -- services are accessed through Kubernetes ingress or internal service networking only.

---

## Production Checklist

Before deploying to production, verify the following:

1. All passwords and secrets are changed from defaults. Use `openssl rand -hex 32` or equivalent.
2. `DEBUG` is set to `false`.
3. `ENVIRONMENT` is set to `production`.
4. `SECRET_KEY` is a cryptographically random value, unique per environment.
5. `CORS_ORIGINS` contains only your actual frontend domain(s).
6. `ENTRA_REDIRECT_URI` points to the production callback URL.
7. `KONG_ADMIN_LISTEN` is bound to `127.0.0.1` (no external access to Admin API).
8. `ZAP_SCAN_MODE` is set to `passive` (never run `active` scans against production).
9. `GRAFANA_ADMIN_PASSWORD` is changed from the default `admin`.
10. AI API keys (`ANTHROPIC_API_KEY`, `AZURE_AI_FOUNDRY_API_KEY`) are stored in a secrets manager (e.g., Azure Key Vault, Kubernetes Sealed Secrets), not in plain text `.env` files.
11. `ACR_REGISTRY` and `IMAGE_TAG` are set for production container images.
12. PostgreSQL SSL is enabled (`KONG_PG_SSL=on`) if connecting to a managed database.
