# Troubleshooting Guide

This guide covers common issues, debugging techniques, and recovery procedures for the API Gateway platform. It is intended for platform engineers and SRE teams responsible for operating the stack.

---

## Table of Contents

- [Health Check Endpoints](#health-check-endpoints)
- [Common Issues](#common-issues)
  - [Kong Won't Start](#kong-wont-start)
  - [Admin Panel Can't Connect to Database](#admin-panel-cant-connect-to-database)
  - [Frontend Shows Blank Page or API Errors](#frontend-shows-blank-page-or-api-errors)
  - [Authentication Failures (Entra ID)](#authentication-failures-entra-id)
  - [Permission Denied Errors (RBAC)](#permission-denied-errors-rbac)
  - [API Registration Stuck in Status](#api-registration-stuck-in-status)
  - [Kong Returns 502/503](#kong-returns-502503)
  - [Rate Limiting Not Working](#rate-limiting-not-working)
  - [ZAP Scanner Not Starting](#zap-scanner-not-starting)
  - [Metrics Not Appearing in Grafana](#metrics-not-appearing-in-grafana)
- [Debugging Commands](#debugging-commands)
- [Log Locations](#log-locations)
- [Performance Issues](#performance-issues)
- [Recovery Procedures](#recovery-procedures)
- [Alert Reference](#alert-reference)

---

## Health Check Endpoints

Use these endpoints to verify each service is running and healthy.

| Service | Endpoint | Port (dev) | Method | Notes |
|---|---|---|---|---|
| **Kong Gateway** | `/status` | 8100 | GET | Prometheus status endpoint; returns connection/request stats |
| **Kong Gateway** | (container) `kong health` | -- | CLI | Docker healthcheck command; checks nginx master process |
| **Kong Admin API** | `/status` | 8001 | GET | Admin API status; also confirms DB connectivity |
| **Admin Panel** | `/health` | 8080 | GET | Liveness probe -- returns 200 if the process is running |
| **Admin Panel** | `/ready` | 8080 | GET | Readiness probe -- verifies DB engine is initialized and can execute `SELECT 1` |
| **Frontend** | `/` | 3000 | GET | Next.js dev server; healthcheck uses `wget --spider` |
| **ZAP Scanner** | `/JSON/core/view/version/` | 8290 (maps to 8090 inside container) | GET | Returns ZAP version JSON; slow startup -- allow 90s+ |
| **ZAP Exporter** | `/health` | 9290 | GET | Metrics bridge health; also exposes `/metrics` for Prometheus |
| **Prometheus** | `/-/healthy` | 9090 | GET | Built-in health endpoint |
| **Grafana** | `/api/health` | 3000 (Grafana port, configurable via `GRAFANA_PORT`) | GET | Returns Grafana health status |
| **Cribl Stream** | `/api/v1/health` | 9420 | GET | Cribl management API health |
| **PostgreSQL** | -- | 5432 | CLI | `pg_isready -U postgres` inside the container |
| **Redis** | -- | 6380 (maps to 6379 inside container) | CLI | `redis-cli -a <password> ping` inside the container |

Quick health sweep from the Docker host:

```bash
# Kong status
curl -sf http://localhost:8100/status | jq .

# Kong Admin API
curl -sf http://localhost:8001/status | jq .

# Admin Panel liveness + readiness
curl -sf http://localhost:8080/health
curl -sf http://localhost:8080/ready

# ZAP version (may take 90s+ after startup)
curl -sf http://localhost:8290/JSON/core/view/version/

# ZAP exporter
curl -sf http://localhost:9290/health

# Prometheus
curl -sf http://localhost:9090/-/healthy

# Grafana
curl -sf http://localhost:3000/api/health

# Cribl
curl -sf http://localhost:9420/api/v1/health
```

---

## Common Issues

### Kong Won't Start

**Symptoms**: `api-gw-kong` container exits or restarts in a loop.

**1. Database migrations not run**

Kong requires `kong migrations bootstrap` to complete before it starts. The `kong-migrations` service handles this. If it failed, Kong will not start.

```bash
# Check migration service status
docker compose ps kong-migrations

# View migration logs
docker compose logs kong-migrations --tail 50

# Re-run migrations manually
docker compose run --rm kong-migrations kong migrations bootstrap

# If upgrading Kong versions, run upgrade migrations
docker compose run --rm kong-migrations kong migrations up
docker compose run --rm kong-migrations kong migrations finish
```

**2. Custom plugin errors**

Kong is configured with custom plugins: `subscription-validator` and `ai-gateway` (set via `KONG_PLUGINS`). If a plugin's Lua files are missing or contain errors, Kong will refuse to start.

```bash
# Check Kong error logs for plugin issues
docker compose logs kong --tail 100 | grep -i "plugin\|error\|lua"

# Validate Kong configuration
docker compose exec kong kong config -c /etc/kong/kong.conf --vv

# Test with only bundled plugins (to isolate the issue)
# Temporarily set KONG_PLUGINS=bundled in your .env
```

**3. Port conflicts**

Kong binds to ports 8000 (proxy HTTP), 8443 (proxy HTTPS), 8001 (Admin API), and 8100 (status/metrics). If another process occupies these ports, Kong will fail.

```bash
# Check for port conflicts
lsof -i :8000 -i :8001 -i :8100 -i :8443

# Or on Linux
ss -tlnp | grep -E '8000|8001|8100|8443'
```

**4. PostgreSQL not reachable**

Kong depends on `postgres` with `condition: service_healthy`. If Postgres is unhealthy, Kong never starts.

```bash
# Check Postgres health
docker compose ps postgres
docker compose exec postgres pg_isready -U postgres

# Check if the Kong database and user exist
docker compose exec postgres psql -U postgres -c "\l" | grep kong
docker compose exec postgres psql -U postgres -c "\du" | grep kong
```

---

### Admin Panel Can't Connect to Database

**Symptoms**: Admin panel `/ready` returns 503 with `"status": "not_ready"`. Logs show connection errors.

**1. Verify the connection string**

The admin panel expects `DATABASE_URL` in the format `postgresql://user:pass@host:5432/dbname`. It automatically converts this to `postgresql+asyncpg://` at startup.

```bash
# Check the configured DATABASE_URL (from docker-compose env)
docker compose exec admin-panel env | grep DATABASE_URL

# Test connectivity from inside the container
docker compose exec admin-panel python -c "
import asyncio, asyncpg
async def test():
    conn = await asyncpg.connect('postgresql://api_gateway_admin:admin_local_dev@postgres:5432/api_gateway_admin')
    result = await conn.fetchval('SELECT 1')
    print(f'Connected OK, result={result}')
    await conn.close()
asyncio.run(test())
"
```

**2. Database not created**

The `database/init.sh` script runs on first Postgres startup to create the `api_gateway_admin` database and user. If the Postgres volume already existed from a previous setup, the init script is skipped.

```bash
# Check if the admin database exists
docker compose exec postgres psql -U postgres -c "\l" | grep api_gateway_admin

# Create it manually if missing
docker compose exec postgres psql -U postgres -c "
  CREATE USER api_gateway_admin WITH PASSWORD 'admin_local_dev';
  CREATE DATABASE api_gateway_admin OWNER api_gateway_admin;
"
```

**3. SSL mode mismatch**

In production, `DATABASE_URL` may require `?sslmode=require`. asyncpg does not accept the `sslmode` query parameter the same way psycopg2 does. Check the connection string format for your environment.

**4. Migrations not applied**

The admin panel uses SQLAlchemy models but the initial schema is created by `database/migrations/` scripts that run via `docker-entrypoint-initdb.d`. If tables are missing:

```bash
# Check which tables exist
docker compose exec postgres psql -U api_gateway_admin -d api_gateway_admin -c "\dt"

# Re-apply migrations by recreating the database (DESTRUCTIVE -- dev only)
docker compose down -v  # removes volumes
docker compose up -d
```

**5. Connection pool exhaustion**

The admin panel pool defaults to `db_pool_max_size=20`. Under heavy load, all connections may be in use. Check for leaked sessions or increase the pool.

```bash
# Check active connections to the admin DB
docker compose exec postgres psql -U postgres -c "
  SELECT count(*), state FROM pg_stat_activity
  WHERE datname = 'api_gateway_admin'
  GROUP BY state;
"
```

---

### Frontend Shows Blank Page or API Errors

**Symptoms**: Next.js frontend at `http://localhost:3000` shows a white page or network errors in browser console.

**1. Admin panel not reachable**

The frontend depends on `admin-panel` being healthy. It uses `ADMIN_API_URL=http://admin-panel:8080` for server-side requests.

```bash
# Confirm admin panel is up
docker compose ps admin-panel
curl -sf http://localhost:8080/health

# Check frontend logs
docker compose logs frontend --tail 50
```

**2. Proxy / CORS misconfiguration**

The admin panel sets `CORS_ORIGINS` to `http://localhost:3000,http://localhost:8080` in development. If the frontend is served from a different origin, CORS will block API calls.

```bash
# Verify CORS origins
docker compose exec admin-panel env | grep CORS_ORIGINS

# Test with a preflight request
curl -v -X OPTIONS http://localhost:8080/api/v1/subscribers \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET"
```

**3. Next.js build errors**

If using hot-reload mounts, a syntax error in `frontend/src/` can crash the dev server.

```bash
docker compose logs frontend --tail 100 | grep -i "error\|failed"
```

---

### Authentication Failures (Entra ID)

**Symptoms**: Users cannot log in. Redirects fail or return "invalid_client" / "unauthorized_client" errors.

**1. Entra ID not configured**

The admin panel defaults to `entra_tenant_id=not-configured` and `entra_client_id=not-configured`. These must be set to valid values.

```bash
# Check current Entra config
docker compose exec admin-panel env | grep ENTRA
```

Required environment variables:
- `ENTRA_TENANT_ID` -- Azure AD tenant GUID
- `ENTRA_CLIENT_ID` -- Application (client) ID from the app registration
- `ENTRA_CLIENT_SECRET` -- A valid, non-expired client secret
- `ENTRA_REDIRECT_URI` -- Must exactly match what is registered in Azure AD (default: `http://localhost:8000/auth/callback`)

**2. Redirect URI mismatch**

The `ENTRA_REDIRECT_URI` must exactly match one of the redirect URIs configured in the Azure AD app registration. A trailing slash mismatch or http vs https difference will cause failures.

```bash
# Compare configured redirect URI
docker compose exec admin-panel env | grep ENTRA_REDIRECT_URI

# This must match the app registration in Azure Portal:
# Azure Portal -> App registrations -> <your app> -> Authentication -> Redirect URIs
```

**3. Expired client secret**

Entra ID client secrets have expiration dates. If the secret has expired, authentication will fail with a generic `invalid_client` error from Microsoft.

Check in Azure Portal: App registrations -> your app -> Certificates & secrets -> verify the expiration date.

**4. Token validation issues**

The admin panel validates tokens against `https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration`. If the tenant ID is wrong or the JWKS endpoint is unreachable, token validation fails silently.

```bash
# Verify the OpenID config is reachable
curl -sf "https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration" | jq .issuer
```

---

### Permission Denied Errors (RBAC)

**Symptoms**: Authenticated users get HTTP 403 with `"Permission '<name>' required."` even though they should have access.

**1. User has no roles assigned**

New users synced from Entra ID start with no roles. An admin must assign roles via the RBAC API.

```bash
# List a user's roles via the Admin Panel API
curl -sf http://localhost:8080/api/v1/rbac/users/<user-id>/roles \
  -H "Authorization: Bearer <token>" | jq .
```

Available default roles: `super_admin`, `admin`, `operator`, `viewer`. See the RBAC module for the full permission matrix.

**2. Wrong role for the operation**

Each endpoint requires a specific permission. For example, `api_registry:approve` is only granted to `super_admin` and `admin` roles. The `operator` role can read and write API registrations but cannot approve them.

**3. RBAC cache stale**

Permissions are cached in Redis with a 300-second (5-minute) TTL under the key pattern `rbac:permissions:<user-id>`. After changing a user's roles, the cache may serve stale data.

```bash
# Invalidate a specific user's permission cache
docker compose exec redis redis-cli -a redis_local_dev DEL "rbac:permissions:<user-uuid>"

# Or flush all RBAC caches
docker compose exec redis redis-cli -a redis_local_dev KEYS "rbac:permissions:*"
docker compose exec redis redis-cli -a redis_local_dev --scan --pattern "rbac:permissions:*" | \
  xargs -r docker compose exec -T redis redis-cli -a redis_local_dev DEL
```

**4. Redis not reachable**

If Redis is down, the RBAC middleware falls through to database queries but logs warnings. Check Redis health:

```bash
docker compose exec redis redis-cli -a redis_local_dev ping
# Expected: PONG
```

---

### API Registration Stuck in Status

**Symptoms**: An API registration remains in `draft`, `submitted`, or `approved` status and never progresses.

The API registration workflow follows a state machine: `draft` -> `submitted` -> `approved` -> `active` (or `rejected` at the review step).

**1. Never submitted**

The team owner must explicitly submit the registration. Check the `submitted_at` timestamp.

```bash
# Check registration status
curl -sf http://localhost:8080/api/v1/api-registry/<slug> \
  -H "Authorization: Bearer <token>" | jq '{status, submitted_at, reviewed_at, activated_at}'
```

**2. Missing approval permission**

Only users with `api_registry:approve` permission (roles: `super_admin`, `admin`) can approve or reject a registration. Operators can submit but not approve.

**3. Kong service/route creation failed**

When a registration is approved and activated, the admin panel creates a Kong service and route via the Admin API (`http://kong:8001`). If Kong's Admin API is unreachable or returns an error, the activation step fails.

```bash
# Verify Kong Admin API is accessible from admin-panel
docker compose exec admin-panel curl -sf http://kong:8001/status | jq .

# Check if the Kong service was created
curl -sf http://localhost:8001/services/<slug> | jq .
```

---

### Kong Returns 502/503

**Symptoms**: Requests through Kong return `502 Bad Gateway` or `503 Service Unavailable`.

**1. Upstream service unreachable**

Kong proxies requests to upstream URLs defined in service configurations (e.g., `http://api-v1:8080`). If the upstream is down or the hostname cannot be resolved, Kong returns 502.

```bash
# Check Kong's view of the service
curl -sf http://localhost:8001/services | jq '.data[] | {name, host, port, protocol}'

# Test upstream connectivity from inside Kong
docker compose exec kong curl -sf http://api-v1:8080/health

# Check Kong's DNS resolution
docker compose exec kong nslookup api-v1
```

**2. DNS resolution failure**

Kong is configured with `KONG_DNS_ORDER=LAST,A,SRV`. If the Docker internal DNS is not resolving service names, Kong cannot reach upstreams.

```bash
# Verify DNS from inside the Kong container
docker compose exec kong getent hosts postgres
docker compose exec kong getent hosts admin-panel
```

**3. Wrong protocol (HTTP vs HTTPS)**

If a service is configured with `protocol: https` but the upstream only serves HTTP (or vice versa), Kong will get connection errors. Check the service configuration:

```bash
curl -sf http://localhost:8001/services/<service-name> | jq '{protocol, host, port, path}'
```

**4. Upstream timeout**

Default timeouts are `connect_timeout: 30s`, `read_timeout: 60s`, `write_timeout: 60s`. If the upstream is slow, increase these values or investigate the upstream.

---

### Rate Limiting Not Working

**Symptoms**: Consumers are not being rate-limited, or rate limits are applied inconsistently.

**1. Rate limiting policy is `local`**

In the default configuration, `rate-limiting` uses `policy: local`, which counts requests per Kong worker process. In a multi-node or multi-worker setup, the actual limit is multiplied by the number of workers. Switch to `policy: redis` for accurate distributed rate limiting.

```bash
# Check rate-limiting plugin config on a service
curl -sf http://localhost:8001/services/api-v1-keyauth/plugins | \
  jq '.data[] | select(.name=="rate-limiting") | .config'
```

**2. Redis connection issues**

If using `policy: redis`, Kong must be able to reach Redis. Check the Redis configuration in Kong's environment.

```bash
# Test Redis from Kong container
docker compose exec kong redis-cli -h redis -p 6379 -a redis_local_dev ping
```

**3. Plugin not applied to the right scope**

Rate limiting can be global, per-service, or per-route. Verify the plugin is attached where expected:

```bash
# List all rate-limiting plugins
curl -sf http://localhost:8001/plugins?name=rate-limiting | jq '.data[] | {id, service: .service.id, route: .route.id, config: {minute: .config.minute, hour: .config.hour}}'
```

---

### ZAP Scanner Not Starting

**Symptoms**: `api-gw-zap` container stays in `starting` or `unhealthy` state for a long time.

**1. Normal slow startup**

ZAP is a Java application with a heavy startup sequence. The Docker healthcheck has `start_period: 90s` for this reason. Wait at least 2 minutes before investigating.

```bash
# Watch ZAP container status
docker compose ps zap
docker compose logs zap --tail 30 -f
```

**2. Java memory issues**

ZAP can be memory-hungry. If the container is OOM-killed, increase its memory limit.

```bash
# Check if OOM killed
docker inspect api-gw-zap --format='{{.State.OOMKilled}}'

# Check current memory usage
docker stats api-gw-zap --no-stream
```

**3. ZAP exporter can't reach ZAP**

The `zap-exporter` service depends on ZAP being healthy. If ZAP never becomes healthy, the exporter will not start.

```bash
# Test ZAP API from inside the network
docker compose exec zap-exporter curl -sf http://zap:8090/JSON/core/view/version/
```

---

### Metrics Not Appearing in Grafana

**Symptoms**: Grafana dashboards show "No data" or panels are empty.

**1. Prometheus scrape targets down**

```bash
# Check Prometheus target health
curl -sf http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health, lastError}'
```

**2. Wrong scrape port or path**

Prometheus scrape targets are defined in `monitoring/prometheus/prometheus.yml`. Verify the ports match what the services actually expose:

- Kong metrics: `kong:8100` at `/metrics`
- Admin panel metrics: `admin-panel:3000` at `/metrics` (verify this is correct for your setup)
- ZAP exporter: `zap-exporter:9290` at `/metrics`

**3. Prometheus not connected to Grafana**

```bash
# Check Grafana datasource
curl -sf http://localhost:3000/api/datasources -u admin:admin | jq '.[].name'

# Verify Prometheus is reachable from Grafana
docker compose exec grafana wget -qO- http://prometheus:9090/-/healthy
```

**4. Dashboard provisioning failed**

Dashboards are provisioned from `monitoring/grafana/dashboards/*.json`. If a JSON file is malformed, Grafana silently skips it.

```bash
docker compose logs grafana --tail 100 | grep -i "provision\|error\|dashboard"
```

---

## Debugging Commands

### Docker and Container Management

```bash
# View all service statuses
docker compose ps

# Follow logs for a specific service
docker compose logs <service> --tail 100 -f

# Follow logs for multiple services
docker compose logs kong admin-panel --tail 50 -f

# Restart a single service
docker compose restart <service>

# Rebuild and restart a service (after code changes)
docker compose up -d --build <service>

# Get a shell inside a container
docker compose exec <service> sh
```

### Kong Debugging

```bash
# Validate Kong configuration
docker compose exec kong kong config -c /etc/kong/kong.conf

# Check Kong configuration (verbose)
docker compose exec kong kong config -c /etc/kong/kong.conf --vv

# List all configured services
curl -sf http://localhost:8001/services | jq '.data[] | {name, host, port, protocol}'

# List all routes
curl -sf http://localhost:8001/routes | jq '.data[] | {name, paths, service: .service.id}'

# List all plugins (globally applied)
curl -sf http://localhost:8001/plugins | jq '.data[] | {name, enabled, service: .service.id, route: .route.id}'

# List all consumers
curl -sf http://localhost:8001/consumers | jq '.data[] | {username, custom_id}'

# Check Kong node status
curl -sf http://localhost:8001/status | jq .

# Check Kong's database reachability
curl -sf http://localhost:8001/ | jq '{database: .configuration.database, pg_host: .configuration.pg_host}'

# Trace a request through Kong (add debug headers)
curl -v http://localhost:8000/health -H "X-Request-ID: debug-$(date +%s)"
```

### Database Debugging

```bash
# Connect to the admin panel database
docker compose exec postgres psql -U api_gateway_admin -d api_gateway_admin

# Check table row counts
docker compose exec postgres psql -U api_gateway_admin -d api_gateway_admin -c "
  SELECT schemaname, relname, n_live_tup
  FROM pg_stat_user_tables
  ORDER BY n_live_tup DESC;
"

# Check active database connections
docker compose exec postgres psql -U postgres -c "
  SELECT datname, usename, state, count(*)
  FROM pg_stat_activity
  GROUP BY datname, usename, state
  ORDER BY count DESC;
"

# Check for long-running queries
docker compose exec postgres psql -U postgres -c "
  SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
  FROM pg_stat_activity
  WHERE state != 'idle'
  ORDER BY duration DESC
  LIMIT 10;
"

# Connect to the Kong database
docker compose exec postgres psql -U kong -d kong
```

### Redis Debugging

```bash
# Test connectivity
docker compose exec redis redis-cli -a redis_local_dev ping

# Check memory usage
docker compose exec redis redis-cli -a redis_local_dev INFO memory | grep used_memory_human

# List RBAC cache keys
docker compose exec redis redis-cli -a redis_local_dev KEYS "rbac:permissions:*"

# Check a specific RBAC cache entry
docker compose exec redis redis-cli -a redis_local_dev GET "rbac:permissions:<user-uuid>"

# Monitor Redis commands in real-time (use briefly, high overhead)
docker compose exec redis redis-cli -a redis_local_dev MONITOR

# Check connected clients
docker compose exec redis redis-cli -a redis_local_dev CLIENT LIST
```

### Prometheus and Monitoring

```bash
# Query a metric directly
curl -sf 'http://localhost:9090/api/v1/query?query=up' | jq '.data.result[] | {instance: .metric.instance, job: .metric.job, value: .value[1]}'

# Check firing alerts
curl -sf 'http://localhost:9090/api/v1/alerts' | jq '.data.alerts[] | {alertname: .labels.alertname, state, severity: .labels.severity}'

# Reload Prometheus config (hot reload, requires --web.enable-lifecycle)
curl -sf -X POST http://localhost:9090/-/reload
```

---

## Log Locations

### Container Logs (Docker)

All services log to stdout/stderr and are captured by Docker's logging driver.

| Service | Container Name | Log Command |
|---|---|---|
| Kong Gateway | `api-gw-kong` | `docker compose logs kong` |
| Kong Migrations | `api-gw-kong-migrations` | `docker compose logs kong-migrations` |
| Admin Panel | `api-gw-admin-panel` | `docker compose logs admin-panel` |
| Frontend | `api-gw-frontend` | `docker compose logs frontend` |
| PostgreSQL | `api-gw-postgres` | `docker compose logs postgres` |
| Redis | `api-gw-redis` | `docker compose logs redis` |
| ZAP Scanner | `api-gw-zap` | `docker compose logs zap` |
| ZAP Exporter | `api-gw-zap-exporter` | `docker compose logs zap-exporter` |
| Prometheus | `api-gw-prometheus` | `docker compose logs prometheus` |
| Grafana | `api-gw-grafana` | `docker compose logs grafana` |
| Cribl Stream | `api-gw-cribl` | `docker compose logs cribl` |

### Kong Internal Logs

- **Access log** (proxy): stdout (`KONG_PROXY_ACCESS_LOG=/dev/stdout`)
- **Error log** (proxy): stderr (`KONG_PROXY_ERROR_LOG=/dev/stderr`)
- **Admin access log**: stdout in dev, `off` in production
- **Admin error log**: stderr
- **Internal log directory**: `/usr/local/kong/logs/` inside the container (contains `error.log` and `access.log` if file logging is enabled)

In production, Kong's log level is set to `warn` (`KONG_LOG_LEVEL=warn`). For debugging, temporarily increase to `debug` or `info`:

```bash
# Change log level without restart (Kong 3.x+)
curl -sf -X PUT http://localhost:8001/debug/node/log-level/debug
# Revert after debugging
curl -sf -X PUT http://localhost:8001/debug/node/log-level/warn
```

### Admin Panel Logs

- **Format**: Structured `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- **Output**: stdout (captured by Docker)
- **Key loggers**:
  - `app.middleware.rbac` -- permission checks, cache hits/misses
  - `app.middleware.auth` -- authentication events
  - `app.routers.api_registry` -- API registration workflow events
  - `app.ai.agent` -- AI analysis requests and responses

### Production Log Shipping

In production, Docker uses the `json-file` log driver with rotation:
- Kong: 100MB x 10 files
- Admin Panel: 50MB x 5 files
- PostgreSQL: 50MB x 5 files
- Other services: 25MB x 3 files

Logs are also shipped to Cribl Stream via:
- **TCP log plugin** (Kong -> Cribl on port 5514): primary path for Kong access/error logs
- **HTTP log plugin** (Kong -> Cribl on port 9080): fallback path
- **Prometheus remote_write** (Prometheus -> Cribl on port 9090): metrics forwarding

---

## Performance Issues

### Slow API Responses

**Diagnose with Grafana**: Open the Gateway Overview dashboard and check upstream latency vs. Kong proxy latency.

```bash
# Check P95 latency from Prometheus
curl -sf 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(kong_latency_bucket{type="upstream"}[5m]))by(le,service))' | jq '.data.result[] | {service: .metric.service, p95_ms: .value[1]}'

# Check if the issue is Kong or the upstream
curl -v http://localhost:8000/api/v1/some-endpoint -o /dev/null -w \
  "DNS: %{time_namelookup}s\nConnect: %{time_connect}s\nTTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n"
```

**Key alerts**: `KongHighLatencyP99` (>1s, critical), `KongHighLatencyP95` (>500ms, warning), `KongUpstreamLatencySpike` (2x baseline).

### High Memory Usage

**Kong**: Each nginx worker consumes memory. In production, `KONG_NGINX_WORKER_PROCESSES=auto` scales to CPU count. The Prometheus metrics shared dict uses 32MB (`lua_shared_dict prometheus_metrics 32m`). Production memory limit is 2GB.

```bash
docker stats api-gw-kong --no-stream --format "{{.MemUsage}}"
```

**ZAP Scanner**: ZAP is a Java process that can easily consume 1GB+. If running active scans, memory usage spikes further.

```bash
docker stats api-gw-zap --no-stream --format "{{.MemUsage}}"
```

**PostgreSQL**: Default pool sizes are `db_pool_max_size=20` for the admin panel. Monitor active connections:

```bash
docker compose exec postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
```

### Database Connection Exhaustion

The admin panel uses asyncpg with a pool of 5-20 connections (`db_pool_min_size=5`, `db_pool_max_size=20`). Kong maintains its own connection pool to its separate database.

```bash
# Check total connections per database
docker compose exec postgres psql -U postgres -c "
  SELECT datname, count(*) as connections
  FROM pg_stat_activity
  GROUP BY datname;
"

# Check PostgreSQL max_connections setting
docker compose exec postgres psql -U postgres -c "SHOW max_connections;"
```

If connections are exhausted, either:
- Increase `max_connections` in PostgreSQL
- Reduce pool sizes in application config
- Look for connection leaks (sessions not being returned to the pool)

---

## Recovery Procedures

### Reset Redis Cache

Flush all cached data (RBAC permissions, sessions). Users will need to re-authenticate, and permissions will be re-fetched from the database.

```bash
# Flush the default database (DB 0)
docker compose exec redis redis-cli -a redis_local_dev FLUSHDB

# Or selectively clear only RBAC caches
docker compose exec redis redis-cli -a redis_local_dev --scan --pattern "rbac:permissions:*" | \
  xargs -r docker compose exec -T redis redis-cli -a redis_local_dev DEL
```

### Force RBAC Permission Refresh

To refresh permissions for a single user without flushing all caches:

```bash
# Delete the specific user's cached permissions
docker compose exec redis redis-cli -a redis_local_dev DEL "rbac:permissions:<user-uuid>"
```

The next API request from that user will trigger a fresh database lookup and re-cache the result for 300 seconds.

### Rebuild Kong Configuration from Database

If Kong's in-memory config is out of sync with the database:

```bash
# Option 1: Restart Kong to force a full config reload
docker compose restart kong

# Option 2: Import the declarative config into the database
docker compose exec kong kong config db_import /etc/kong/kong.yml

# Option 3: In an emergency, reset Kong's database and re-bootstrap
docker compose run --rm kong-migrations kong migrations reset --yes
docker compose run --rm kong-migrations kong migrations bootstrap
docker compose exec kong kong config db_import /etc/kong/kong.yml
docker compose restart kong
```

### Re-run Admin Panel Database Migrations

If the admin panel's database schema is out of date or tables are missing:

```bash
# Check current table state
docker compose exec postgres psql -U api_gateway_admin -d api_gateway_admin -c "\dt"

# To recreate from scratch (DESTRUCTIVE -- dev environments only):
docker compose exec postgres psql -U postgres -c "DROP DATABASE api_gateway_admin;"
docker compose exec postgres psql -U postgres -c "CREATE DATABASE api_gateway_admin OWNER api_gateway_admin;"
docker compose restart admin-panel
# The admin panel will re-seed default roles on startup
```

### Full Stack Reset (Development Only)

When all else fails in a development environment:

```bash
# Stop all containers and remove volumes
docker compose down -v

# Remove any orphan containers
docker compose down --remove-orphans

# Rebuild all images from scratch
docker compose build --no-cache

# Start everything
docker compose up -d

# Watch the startup sequence
docker compose logs -f
```

---

## Alert Reference

The platform defines alerts in `monitoring/prometheus/alerts.yml`. Key alerts to know:

| Alert | Severity | What It Means |
|---|---|---|
| `KongHighErrorRate` | critical | 5xx rate > 5% for 2 minutes |
| `KongHighLatencyP99` | critical | P99 latency > 1 second for 3 minutes |
| `KongAuthFailureSpike` | critical | Auth failure rate > 20% for 2 minutes |
| `KongPodDown` | critical | Kong scrape target unreachable for 1 minute |
| `KongDatabaseConnectionErrors` | critical | Kong cannot reach PostgreSQL for 1 minute |
| `KongRateLimitViolationSpike` | warning | Rate-limited requests > 10/sec for 2 minutes |
| `AIProviderDown` | critical | AI provider error rate > 95% or no responses for 5 minutes |
| `AICostBudgetCritical` | critical | AI spending > $20/hour for 5 minutes |
| `ZAPCriticalVulnerability` | critical | High-severity ZAP findings detected |
| `ZAPScannerDown` | warning | ZAP scanner unreachable for 5 minutes |

For the full list, see `monitoring/prometheus/alerts.yml`.
