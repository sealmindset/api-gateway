# Architecture

This document describes the system architecture of the API Gateway platform.
It is intended for platform engineers, solution architects, and cross-functional
IT teams who need to understand how the components fit together, how data flows
through the system, and how operational concerns (security, observability,
AI-assisted analysis) are addressed.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture Diagram](#2-high-level-architecture-diagram)
3. [Services](#3-services)
4. [Network Topology](#4-network-topology)
5. [Data Flow](#5-data-flow)
6. [Database Schema Overview](#6-database-schema-overview)
7. [Authentication Flow](#7-authentication-flow)
8. [RBAC Model](#8-rbac-model)
9. [Custom Plugin Architecture](#9-custom-plugin-architecture)
10. [AI Layer](#10-ai-layer)
11. [Observability Pipeline](#11-observability-pipeline)
12. [Deployment Topology](#12-deployment-topology)

---

## 1. System Overview

The API Gateway platform is a multi-service system built around **Kong Gateway**
(Community Edition 3.9.x) that provides:

- **API proxying and traffic management** -- Kong handles all inbound API
  traffic, applies authentication, rate limiting, subscription validation, and
  optional AI-powered analysis before forwarding requests to upstream services.

- **Self-service API registration** -- Teams register their APIs through the
  Admin Panel. Registrations go through a review/approval workflow before Kong
  routes and services are provisioned.

- **Subscriber and API key management** -- External consumers are modeled as
  subscribers with tiered plans, API keys, scoped rate limits, and subscription
  lifecycle management.

- **AI-assisted gateway intelligence** -- An AI layer (backed by Claude via
  Azure AI Foundry or direct Anthropic API) provides anomaly detection, smart
  routing, request/response transformation, rate-limit recommendations, and
  auto-generated documentation.

- **Security scanning** -- OWASP ZAP runs continuously in passive/active mode
  against gateway endpoints, with findings exported to Prometheus and Cribl.

- **Full observability stack** -- Prometheus collects metrics from Kong, the
  Admin Panel, ZAP, and infrastructure. Grafana provides dashboards. Cribl
  Stream routes and enriches logs from all components.

---

## 2. High-Level Architecture Diagram

```
                          Internet / Corporate Network
                                     |
                     +---------------+---------------+
                     |               |               |
                     v               v               v
              +-----------+   +-----------+   +-----------+
              |   Kong    |   |  Frontend |   |  Grafana  |
              |  Gateway  |   | (Next.js) |   |           |
              | :8000/8443|   |   :3000   |   |   :3000   |
              +-----+-----+   +-----+-----+   +-----+-----+
                    |               |               |
          +---------+---------+     |               |
          |         |         |     |               |
          v         v         v     v               v
     +--------+ +--------+ +----------+      +-----------+
     |Upstream| |Upstream| |  Admin   |      |Prometheus |
     |Svc  A  | |Svc  B  | |  Panel   |      |   :9090   |
     +--------+ +--------+ | (FastAPI)|      +-----+-----+
                            |  :8080   |           |
                            +----+-----+           |
                                 |                 |
              +--------+---------+--------+        |
              |        |         |        |        |
              v        v         v        v        v
         +--------+  +-----+  +-----+  +------+ +------+
         |PostgreSQL| |Redis| | Kong |  | ZAP  | |Cribl |
         |  :5432   | |:6379| |Admin | |Export | |Stream|
         |          | |     | | API  | |:9290  | |:9420 |
         | kong DB  | |     | |:8001 | +--+---+ +--+---+
         | admin DB | |     | +------+    |         |
         +----------+ +-----+      ^      v         v
                                   |   +-----+   (SIEM /
                                   |   | ZAP |    S3 /
                                   +---+:8090|    Splunk)
                                       +-----+
```

**Legend:**

- Ports shown are the internal container ports. External host mappings are
  configurable via environment variables.
- All services communicate over a single Docker bridge network
  (`api-gateway-net`) in development. In production, services are accessed
  through Kubernetes services and ingress controllers.

---

## 3. Services

### 3.1 Kong Gateway

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Image           | Custom build (`kong/Dockerfile`)               |
| Proxy ports     | `8000` (HTTP), `8443` (HTTPS/HTTP2)           |
| Admin API       | `8001` (HTTP), `8444` (HTTPS)                 |
| Status/metrics  | `8100` (Prometheus endpoint)                  |
| Database        | PostgreSQL (`kong` database)                  |
| Custom plugins  | `subscription-validator`, `ai-gateway`        |

Kong is the core traffic plane. Every API request enters through the proxy
listener and passes through the plugin execution chain:

1. **Authentication** (bundled: `key-auth`, `oauth2`, `jwt`, `basic-auth`)
2. **Subscription validation** (custom: `subscription-validator`, priority 850)
3. **AI gateway analysis** (custom: `ai-gateway`, priority 800)
4. **Rate limiting** (bundled: `rate-limiting`, priority 901)
5. **Proxy to upstream**

Kong connects to PostgreSQL for its configuration store and exposes a
Prometheus-compatible metrics endpoint on port 8100. The Admin API (port 8001)
is bound to `127.0.0.1` in production and should never be exposed to untrusted
networks.

Configuration highlights from `kong.conf`:

- TLS 1.2/1.3 only with AEAD cipher suites
- Upstream keepalive pool: 256 connections, 10,000 max requests, 60s idle
- Auto-scaled Nginx worker processes
- 16 MB client body size limit
- DNS resolution via container/cluster DNS with 30s TTL

### 3.2 Admin Panel (FastAPI)

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Framework       | FastAPI (Python, async)                       |
| Port            | `8080`                                        |
| Database        | PostgreSQL (`api_gateway_admin` database)     |
| Session store   | Redis (via Starlette `SessionMiddleware`)     |
| Auth            | Microsoft Entra ID OIDC (via `authlib`)       |

The Admin Panel is the control plane for the platform. It provides:

- **REST API routers**: `auth`, `subscribers`, `subscriptions`, `rbac`,
  `gateway`, `teams`, `api_registry`, `ai`
- **Kong Admin API proxy**: The `gateway` router forwards configuration
  requests to Kong's Admin API (`http://kong:8001`)
- **RBAC enforcement**: Every endpoint is gated by permission checks resolved
  from the `user_roles` -> `roles` -> `permissions` chain, cached in Redis
- **Audit logging**: All access-granted and access-denied events are written
  to the `audit_logs` table
- **Health probes**: `/health` (liveness) and `/ready` (database connectivity)
- **OpenAPI docs**: `/docs` (Swagger UI) and `/redoc`

At startup the Admin Panel:

1. Initializes the async SQLAlchemy engine and connection pool
2. Configures the Entra ID OIDC client
3. Seeds default RBAC roles (`super_admin`, `admin`, `operator`, `viewer`)

### 3.3 Frontend (Next.js)

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Framework       | Next.js (React, App Router)                   |
| Port            | `3000`                                        |
| Styling         | Tailwind CSS, PostCSS                         |
| Backend APIs    | Admin Panel (`http://admin-panel:8080`)       |

The Frontend is a server-rendered React application that provides the
administrative UI. Page routes include:

| Route               | Purpose                                     |
|---------------------|---------------------------------------------|
| `/dashboard`        | Overview metrics and status                 |
| `/subscribers`      | Manage API subscribers                      |
| `/api-keys`         | Issue and rotate API keys                   |
| `/plans`            | Define subscription plans                   |
| `/teams`            | Team management                             |
| `/api-registry`     | API registration and approval workflow      |
| `/gateway`          | Kong service/route/plugin configuration     |
| `/rbac`             | Role and permission management              |
| `/ai`               | AI prompt management and analysis           |
| `/settings`         | Platform settings                           |

The frontend communicates exclusively with the Admin Panel API. It does not
connect directly to Kong, PostgreSQL, or Redis.

### 3.4 PostgreSQL

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Version         | 16 (Alpine)                                   |
| Port            | `5432`                                        |
| Databases       | `kong`, `api_gateway_admin`                   |
| Users           | `kong`, `api_gateway_admin`, `api_gateway_readonly` |

A single PostgreSQL instance hosts two logically separated databases:

- **`kong`** -- Owned by the `kong` user. Managed entirely by Kong's migration
  system. Contains Kong's service, route, plugin, consumer, and credential
  configuration.

- **`api_gateway_admin`** -- Owned by the `api_gateway_admin` user. Schema
  managed by migration files in `database/migrations/`. Contains the
  application domain model (users, roles, subscribers, API keys, teams, API
  registrations, AI prompts, audit logs).

A read-only user (`api_gateway_readonly`) is provisioned with `SELECT`
privileges on the admin database for reporting and BI integrations.

The initialization script (`database/init.sh`) runs on first container start
via PostgreSQL's `docker-entrypoint-initdb.d` mechanism. It creates users,
databases, grants, and executes all migration SQL files in order:

1. `001_initial_schema.sql` -- Core tables (users, roles, subscribers, plans, etc.)
2. `002_kong_sync_functions.sql` -- Functions for Kong configuration sync
3. `003_ai_layer.sql` -- AI prompts and analysis tables
4. `004_teams_and_api_registry.sql` -- Teams, team members, API registrations

### 3.5 Redis

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Version         | 7 (Alpine)                                    |
| Port            | `6379` (internal), `6380` (host-mapped dev)   |
| Max memory      | 256 MB (dev), 1 GB (prod)                     |
| Eviction        | `allkeys-lru`                                 |
| Persistence     | AOF (`appendonly yes`)                        |

Redis serves three purposes:

1. **Session storage** -- Starlette `SessionMiddleware` stores OIDC tokens and
   user info in session cookies backed by the server-side session store.

2. **RBAC permission cache** -- Merged permission maps are cached per user
   under keys like `rbac:permissions:{user_id}` with a 5-minute TTL. Cache is
   invalidated on role assignment changes.

3. **Rate limiting backend** -- Kong's `rate-limiting` plugin uses Redis as a
   shared counter store for distributed rate limiting across gateway instances.

### 3.6 OWASP ZAP Scanner

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Port            | `8090` (API + proxy, mapped to host `8290`)   |
| Mode            | Passive by default, active via config         |
| Targets         | Kong proxy, Admin Panel health/docs endpoints |

ZAP runs as a long-lived daemon scanning gateway endpoints. It is built from a
custom Dockerfile in `security/zap/` with a baseline configuration
(`zap-baseline.conf`).

### 3.7 ZAP Exporter

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Port            | `9290` (Prometheus metrics)                   |
| Language        | Python (`exporter.py`)                        |
| Targets         | ZAP API, Kong proxy, Admin Panel              |

The ZAP Exporter bridges ZAP findings into the observability stack:

- Polls ZAP's API at a configurable interval (default 5 minutes)
- Dynamically discovers Kong routes to feed as scan targets
- Exposes findings as Prometheus metrics on `/metrics` (port 9290)
- Forwards structured findings to Cribl Stream via HTTP

### 3.8 Prometheus

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Version         | 2.51.0                                        |
| Port            | `9090`                                        |
| Retention       | 15 days (dev), 30 days / 10 GB (prod)        |
| Scrape interval | 15s (Kong, k8s pods), 30s (admin, ZAP, infra)|

Prometheus scrapes the following targets:

| Job name                      | Target                  | Metrics                        |
|-------------------------------|-------------------------|--------------------------------|
| `kong`                        | `kong:8100`             | Request rate, latency, status codes, upstream health |
| `admin-panel`                 | `admin-panel:3000`      | FastAPI request metrics        |
| `zap-exporter`                | `zap-exporter:9290`     | ZAP alert counts by severity   |
| `node-exporter`               | `node-exporter:9100`    | Host CPU, memory, disk, network |
| `cadvisor`                    | `cadvisor:8080`         | Container resource usage       |
| `kubernetes-pods`             | Auto-discovered         | Pods with `prometheus.io/scrape: "true"` |
| `kubernetes-service-endpoints`| Auto-discovered         | Service endpoints with scrape annotations |

Prometheus also forwards metrics to Cribl via `remote_write`, filtering for
`kong_*`, `node_*`, `container_*`, and `zap_*` metric families.

Alert rules are defined in `monitoring/prometheus/alerts.yml` and recording
rules in `monitoring/prometheus/recording_rules.yml`.

### 3.9 Grafana

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Version         | 10.4.0                                        |
| Port            | `3000`                                        |
| Data source     | Prometheus (auto-provisioned)                 |

Grafana is provisioned with dashboards and data sources at startup via
configuration files in `monitoring/grafana/provisioning/`. Pre-built dashboards:

| Dashboard               | Purpose                                    |
|--------------------------|--------------------------------------------|
| `gateway-overview.json`  | Kong traffic, latency p50/p95/p99, errors  |
| `rate-limiting.json`     | Rate limit hits by consumer/route/tier     |
| `authentication.json`    | OIDC login success/failure, session counts |
| `security-scanning.json` | ZAP findings by severity, trend over time  |
| `ai-layer.json`          | AI analysis counts, anomaly scores, costs  |
| `infrastructure.json`    | Container CPU/memory, PostgreSQL, Redis    |

### 3.10 Cribl Stream

| Property        | Value                                         |
|-----------------|-----------------------------------------------|
| Version         | 4.5.0 (Community Edition, single-instance)    |
| UI port         | `9420`                                        |
| Syslog input    | `5140`                                        |
| Mode            | Single-instance (`CRIBL_DIST_MODE=single`)    |

Cribl Stream is the log routing and enrichment layer. It receives data from:

- Prometheus `remote_write` endpoint
- ZAP Exporter HTTP POST
- Kong log plugins (TCP/HTTP log)
- Syslog (port 5140)

Processing pipelines defined in `monitoring/cribl/pipelines/`:

| Pipeline                  | Purpose                                    |
|---------------------------|--------------------------------------------|
| `kong-logs.yml`           | Parse and enrich Kong access/error logs    |
| `auth-events.yml`         | Extract authentication events              |
| `rate-limit-metrics.yml`  | Aggregate rate-limit counters              |
| `security-scanning.yml`   | Normalize ZAP findings                     |
| `ai-events.yml`           | Extract AI analysis metadata from logs     |

Cribl routes processed data to downstream destinations (SIEM, S3, Splunk, etc.)
based on routing rules in `monitoring/cribl/routes/routes.yml`.

---

## 4. Network Topology

### 4.1 Development (Docker Compose)

All services share a single bridge network (`api-gateway-net`). Host port
mappings are configurable via environment variables:

| Service          | Container Port | Default Host Port | Access Level     |
|------------------|---------------|-------------------|------------------|
| Kong proxy HTTP  | 8000          | 8000              | Client-facing    |
| Kong proxy HTTPS | 8443          | 8443              | Client-facing    |
| Kong admin API   | 8001          | 8001              | Internal only    |
| Kong status      | 8100          | 8100              | Internal only    |
| Admin Panel      | 8080          | 8080              | Internal only    |
| Frontend         | 3000          | 3000              | Client-facing    |
| PostgreSQL       | 5432          | 5432              | Internal only    |
| Redis            | 6379          | 6380              | Internal only    |
| ZAP              | 8090          | 8290              | Internal only    |
| ZAP Exporter     | 9290          | 9290              | Internal only    |
| Prometheus       | 9090          | 9090              | Internal only    |
| Grafana          | 3000          | 3000              | Operator-facing  |
| Cribl            | 9420          | 9420              | Operator-facing  |

### 4.2 Production (Kubernetes / Docker Compose Prod)

In production (`docker-compose.prod.yml` overrides):

- **No ports are exposed** on any service. All access is through Kubernetes
  ingress controllers or an external load balancer.
- Kong Admin API binds to `127.0.0.1:8001` only (loopback).
- Admin access logs are disabled (`KONG_ADMIN_ACCESS_LOG: "off"`).
- Resource limits and reservations are enforced on every container.
- Container images are pulled from a private ACR registry
  (`${ACR_REGISTRY}/api-gateway/*`).

### 4.3 Inter-Service Communication

```
Frontend  ----HTTP----> Admin Panel ----HTTP----> Kong Admin API (:8001)
                             |
                             +----asyncpg----> PostgreSQL (:5432)
                             +----aioredis---> Redis (:6379)
                             +----HTTP-------> AI Provider (external)

Kong      ----pg------> PostgreSQL (:5432)
Kong      ----redis----> Redis (:6379)        [rate-limiting]
Kong      ----HTTP----> Admin Panel (:8080)   [ai-gateway plugin]
Kong      ----HTTP----> Upstream services     [proxy]

ZAP Exporter --HTTP---> ZAP (:8090)
ZAP Exporter --HTTP---> Kong Admin API (:8001) [route discovery]
ZAP Exporter --HTTP---> Cribl (:9081)

Prometheus ---HTTP----> Kong (:8100)          [/metrics scrape]
Prometheus ---HTTP----> ZAP Exporter (:9290)  [/metrics scrape]
Prometheus ---HTTP----> Cribl (:9090)         [remote_write]
```

---

## 5. Data Flow

### 5.1 API Request Flow (Proxy Path)

```
Client
  |
  | HTTPS request to api.example.com
  v
Kong Proxy (:8000/:8443)
  |
  +--> [Authentication Plugin] (priority ~1000)
  |       Identifies consumer via API key, JWT, or OAuth2 token.
  |       Sets kong.client consumer context.
  |       Returns 401 on failure.
  |
  +--> [Subscription Validator Plugin] (priority 850)
  |       1. Read consumer ID from context
  |       2. Check LRU cache (keyed by consumer ID)
  |       3. On miss: HTTP GET to admin-panel validation endpoint
  |       4. Validate: subscription active, not expired, tier allowed
  |       5. Inject X-Subscription-* headers (ID, Tier, Expires-At, Features)
  |       6. Log validation event (structured fields for Cribl/Prometheus)
  |       7. Allow or deny (HTTP 403) the request
  |
  +--> [AI Gateway Plugin] (priority 800)
  |       1. Apply sampling rate (default 10% of requests)
  |       2. Build request data (method, path, headers, body, IP)
  |       3. Anomaly detection: POST to admin-panel /api/ai/analyze
  |       4. Smart routing: POST to admin-panel /api/ai/route
  |       5. Request transform: POST to admin-panel /api/ai/transform/request
  |       6. Set X-AI-Anomaly-Score, X-AI-Route-Decision, X-AI-Status headers
  |       7. On anomaly above threshold: block (403), warn (header), or log
  |       8. Cache AI decisions in kong.cache (configurable TTL)
  |
  +--> [Rate Limiting Plugin] (priority 901)
  |       Enforce per-consumer rate limits using Redis counters.
  |       Returns 429 if limit exceeded.
  |       Sets X-RateLimit-Limit, X-RateLimit-Remaining headers.
  |
  +--> [Proxy to Upstream]
  |       Forward request to the registered upstream service.
  |
  +--> [Response Transform] (body_filter phase, if enabled)
  |       Collect full response body, POST to AI transform endpoint,
  |       replace body with transformed version.
  |
  +--> [Log Phase]
          Emit structured log fields for AI decisions, subscription
          validation, and request metadata. Picked up by Cribl and
          Prometheus.
```

### 5.2 Admin Panel Management Flow

```
Admin User (browser)
  |
  | Authenticated via Entra ID OIDC
  v
Frontend (Next.js :3000)
  |
  | REST API calls
  v
Admin Panel (FastAPI :8080)
  |
  +--> RBAC check (Redis-cached permissions)
  |
  +--> Database operation (PostgreSQL api_gateway_admin)
  |      - CRUD on subscribers, API keys, plans, subscriptions
  |      - Team and API registration management
  |      - AI prompt template management
  |
  +--> Kong Admin API call (http://kong:8001)
  |      - Create/update/delete services, routes, plugins, consumers
  |      - Sync API registrations to Kong configuration
  |
  +--> Audit log entry (PostgreSQL audit_logs table)
```

### 5.3 API Registration Lifecycle

```
Team Member                    Admin Panel                Kong Gateway
    |                              |                           |
    |  POST /api/registrations     |                           |
    |  {name, upstream_url, ...}   |                           |
    |----------------------------->|                           |
    |  status: draft               |                           |
    |                              |                           |
    |  POST .../submit             |                           |
    |----------------------------->|                           |
    |  status: submitted           |                           |
    |                              |                           |
Platform Admin                     |                           |
    |  POST .../review             |                           |
    |  {action: "approve"}         |                           |
    |----------------------------->|                           |
    |  status: approved            |                           |
    |                              |                           |
    |  POST .../activate           |                           |
    |----------------------------->|                           |
    |                              |  POST /services           |
    |                              |-------------------------->|
    |                              |  POST /routes             |
    |                              |-------------------------->|
    |                              |  POST /plugins            |
    |                              |-------------------------->|
    |                              |                           |
    |  status: active              |  Kong provisioned         |
    |  kong_service_id set         |                           |
    |  kong_route_id set           |                           |
```

**Status lifecycle:**
`draft` -> `submitted` -> `approved` / `rejected` -> `active` -> `deprecated` -> `retired`

### 5.4 Metrics and Observability Flow

```
Kong (:8100/metrics) --------+
                              |
Admin Panel (/metrics) ------+----> Prometheus (:9090) ----> Grafana (:3000)
                              |            |
ZAP Exporter (:9290/metrics) +            |
                              |            +--> remote_write --> Cribl (:9090)
Node Exporter (:9100) -------+
cAdvisor (:8080) ------------+

Kong (log plugins) ----------------------------> Cribl (:5140 syslog / HTTP)
ZAP Exporter -----------------------------------> Cribl (:9081 HTTP)

Cribl -----> SIEM / S3 / Splunk / downstream destinations
```

---

## 6. Database Schema Overview

The `api_gateway_admin` database contains the following tables, managed by
SQL migrations in `database/migrations/`.

### 6.1 Entity-Relationship Summary

```
users -------< user_roles >------- roles
  |
  +----< team_members >---- teams ----< api_registrations
  |                                           |
  +----< audit_logs                    [kong_service_id]
                                       [kong_route_id]

subscribers ----< api_keys
     |
     +----------< subscriptions >------ plans

ai_prompts (standalone)
```

### 6.2 Table Details

#### Identity and Access

| Table          | Key Columns                                          | Notes                                      |
|----------------|------------------------------------------------------|--------------------------------------------|
| `users`        | `id` (UUID PK), `email`, `name`, `entra_oid`, `roles` (JSONB), `last_login` | Auto-provisioned on first OIDC login. `entra_oid` is the Entra object ID. Indexed on `email` and `entra_oid`. |
| `roles`        | `id` (UUID PK), `name`, `description`, `permissions` (JSONB) | Seeded defaults: `super_admin`, `admin`, `operator`, `viewer`. Permissions are a flat map of `"resource:action": true`. |
| `user_roles`   | `id` (UUID PK), `user_id` FK, `role_id` FK, `assigned_by` FK, `assigned_at` | Many-to-many with audit trail of who assigned the role. Unique on `(user_id, role_id)`. |

#### Teams and API Registration

| Table              | Key Columns                                          | Notes                                      |
|--------------------|------------------------------------------------------|--------------------------------------------|
| `teams`            | `id` (UUID PK), `name`, `slug` (unique), `contact_email`, `metadata` (JSONB), `is_active` | Organizational unit that owns APIs. |
| `team_members`     | `id` (UUID PK), `team_id` FK, `user_id` FK, `role` (`owner`/`admin`/`member`/`viewer`) | Unique on `(team_id, user_id)`. |
| `api_registrations`| `id` (UUID PK), `team_id` FK, `slug` (unique), `upstream_url`, `upstream_protocol`, `kong_service_id`, `kong_route_id`, `gateway_path`, `auth_type`, `status`, `reviewed_by` FK, plus 18 data contract columns (see below) | Supports REST, GraphQL, gRPC, WebSocket API types. Status workflow: draft -> submitted -> approved/rejected -> active -> deprecated -> retired. Rate limits per second/minute/hour. Data contract fields for contacts, SLAs, change management, and schema. |

**Data Contract Columns on `api_registrations`:**

| Category | Columns |
|----------|---------|
| Contacts | `contact_primary_email`, `contact_escalation_email`, `contact_slack_channel`, `contact_pagerduty_service`, `contact_support_url` |
| SLAs | `sla_uptime_target` (NUMERIC 5,2), `sla_latency_p50_ms`, `sla_latency_p95_ms`, `sla_latency_p99_ms`, `sla_error_budget_pct` (NUMERIC 5,2), `sla_support_hours` |
| Change Mgmt | `deprecation_notice_days` (default 90), `breaking_change_policy` (default `semver`), `versioning_scheme` (default `url-path`), `changelog_url` |
| Schema | `openapi_spec_url`, `max_request_size_kb` (default 128, enforced in Kong), `max_response_size_kb` |

#### Subscribers and Subscriptions

| Table           | Key Columns                                          | Notes                                      |
|-----------------|------------------------------------------------------|--------------------------------------------|
| `subscribers`   | `id` (UUID PK), `name`, `email`, `organization`, `tier`, `status` | External API consumers. |
| `api_keys`      | `id` (UUID PK), `subscriber_id` FK, `key_hash` (SHA-256, unique), `key_prefix` (8-12 chars), `name`, `scopes` (JSONB), `rate_limit`, `expires_at`, `is_active` | Keys stored as hashes. Raw key returned only once at creation. Prefix enables identification without exposing the full key. |
| `plans`         | `id` (UUID PK), `name` (unique), `rate_limit_second`/`minute`/`hour`, `max_api_keys`, `allowed_endpoints` (JSONB), `price_cents`, `is_active` | Defines rate limit tiers and endpoint access restrictions. |
| `subscriptions` | `id` (UUID PK), `subscriber_id` FK, `plan_id` FK, `status`, `starts_at`, `expires_at`, per-field rate limit overrides, `allowed_endpoints` (JSONB) | Links a subscriber to a plan. Supports per-subscription rate limit overrides that take precedence over plan defaults. |

#### AI and Audit

| Table          | Key Columns                                          | Notes                                      |
|----------------|------------------------------------------------------|--------------------------------------------|
| `ai_prompts`   | `id` (UUID PK), `slug` (unique), `name`, `category`, `system_prompt` (TEXT), `model`, `temperature`, `max_tokens`, `is_active`, `version` | Versioned prompt templates. Categories: `anomaly`, `rate_limit`, `routing`, `transform`, `documentation`. Indexed on `category`. |
| `audit_logs`   | `id` (UUID PK), `user_id` FK (nullable), `action`, `resource_type`, `resource_id`, `details` (JSONB), `ip_address`, `created_at` | Immutable append-only audit trail. Indexed on `created_at` and `(resource_type, resource_id)`. |

---

## 7. Authentication Flow

Authentication uses Microsoft Entra ID (Azure AD) via the OpenID Connect
authorization code flow.

```
Browser                 Admin Panel              Entra ID
   |                        |                        |
   |  GET /auth/login       |                        |
   |----------------------->|                        |
   |                        |  302 Redirect to       |
   |  <--------------------|  authorize endpoint     |
   |                        |                        |
   |  GET /authorize -------------------------------->|
   |  (user authenticates with SSO / MFA)            |
   |  <----------------------------------------------+
   |  302 callback?code=...                          |
   |                        |                        |
   |  GET /auth/callback    |                        |
   |  ?code=abc123          |                        |
   |----------------------->|                        |
   |                        |  POST /token           |
   |                        |----------------------->|
   |                        |  {access_token,        |
   |                        |   id_token, userinfo}  |
   |                        |<-----------------------|
   |                        |                        |
   |                        | Extract claims:        |
   |                        |   oid, email, name     |
   |                        |                        |
   |                        | Store in session:      |
   |                        |   token + userinfo     |
   |                        |                        |
   |                        | Provision/update user: |
   |                        |   INSERT or UPDATE     |
   |                        |   users table          |
   |                        |   (keyed on entra_oid) |
   |                        |                        |
   |  302 Redirect to /     |                        |
   |  Set-Cookie:           |                        |
   |    admin_session=...   |                        |
   |<-----------------------|                        |
```

Key properties:

- **Auto-provisioning**: On first login, a `users` record is created
  automatically from the Entra ID claims (`oid`, `email`, `name`). No manual
  account creation is required.
- **Session management**: OIDC tokens are stored server-side in the session.
  The session cookie (`admin_session`) is signed with `SECRET_KEY`, has a 1-hour
  max age, uses `SameSite=Lax`, and is `Secure`-only in non-debug mode.
- **No local passwords**: The platform has no password database. All
  authentication is delegated to Entra ID.
- **Role assignment**: New users have no roles. An administrator must assign
  roles via the RBAC management UI or API after the user's first login.
- **OIDC configuration**: The OIDC client is configured from environment
  variables: `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`. The
  OpenID discovery URL is derived as
  `https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration`.

---

## 8. RBAC Model

### 8.1 Platform Roles

The platform ships with four default roles, seeded at startup:

| Role           | Description                                      | Key Permissions                                |
|----------------|--------------------------------------------------|------------------------------------------------|
| `super_admin`  | Full system access including role management     | All permissions including `roles:write`, `roles:delete`, `users:write` |
| `admin`        | Full operational access                          | All except `roles:write/delete` and `users:write` |
| `operator`     | Day-to-day operations                            | Read/write on subscribers, keys, teams, APIs; read on gateway/audit; AI analyze and rate-limit |
| `viewer`       | Read-only access                                 | Read on all resources                          |

### 8.2 Team Roles

Within a team, members hold one of four scoped roles:

| Role     | Scope                                                    |
|----------|----------------------------------------------------------|
| `owner`  | Full team control, transfer ownership, delete team       |
| `admin`  | Manage members, manage API registrations                 |
| `member` | Create/edit API registrations, view team resources       |
| `viewer` | Read-only access to team resources                       |

### 8.3 Permission Format

Permissions use a `resource:action` format stored as JSONB in the `roles`
table. Resources include:

`subscribers`, `subscriptions`, `api_keys`, `roles`, `users`, `gateway`,
`audit`, `ai`, `teams`, `api_registry`

Actions include: `read`, `write`, `delete`, `approve` (for API registry),
`analyze`, `rate-limit`, `route`, `transform`, `documentation` (for AI).

### 8.4 Permission Evaluation

```
Incoming API Request
     |
     v
[1] Extract user from session cookie
     |
     v
[2] Check Redis cache: rbac:permissions:{user_id}
     |-- HIT --> evaluate permissions
     |-- MISS
     v
[3] Query DB: user_roles JOIN roles
     |
     v
[4] Merge all role permissions into flat map
     |
     v
[5] Cache merged permissions in Redis (5-min TTL)
     |
     v
[6] Check: does user have required permission?
     |-- YES --> log access_granted to audit_logs, allow request
     |-- NO  --> log access_denied to audit_logs, return 403
```

- **Platform admin bypass**: Users with `super_admin` or `admin` roles bypass
  team-scoped membership checks and can manage any resource.
- **Cache invalidation**: When role assignments change, the affected user's
  Redis cache key is explicitly deleted.

---

## 9. Custom Plugin Architecture

### 9.1 Subscription Validator (`subscription-validator.lua`)

**Purpose**: Ensures that an authenticated consumer holds a valid, unexpired
subscription with an authorized tier before the request reaches the upstream.

**Execution phase**: Access (priority 850 -- after auth plugins at 1000+, before
rate limiting at 901).

**Configuration**:

| Parameter              | Type     | Default              | Description                                   |
|------------------------|----------|----------------------|-----------------------------------------------|
| `validation_endpoint`  | string   | --                   | URL of the subscription validation service    |
| `timeout`              | integer  | --                   | HTTP timeout (ms)                             |
| `cache_ttl`            | integer  | --                   | Seconds to cache validation results           |
| `allowed_tiers`        | array    | --                   | Tiers permitted for this route/service        |
| `fail_open`            | boolean  | --                   | Allow requests when validation is unreachable |
| `header_prefix`        | string   | `X-Subscription-`   | Prefix for injected headers                   |

**Behavior**:

1. Retrieve the authenticated consumer from Kong context (set by upstream auth
   plugin). If no consumer is found, return 403 immediately.
2. Build cache key from consumer ID, check Kong's shared LRU cache.
3. On cache miss: HTTP GET to the external validation endpoint with
   `consumer_id` and `custom_id` query parameters.
4. Validate response: `valid == true`, not expired (compares `expires_at`
   against current time), tier is in `allowed_tiers` (case-insensitive).
5. On success: inject `X-Subscription-ID`, `X-Subscription-Tier`,
   `X-Subscription-Expires-At`, `X-Subscription-Valid`,
   `X-Subscription-Features`, `X-Subscription-Org-ID` headers.
6. On failure: return 403 with structured error body (includes `error` code,
   `current_tier`, `required_tiers`).
7. On service unavailability: return 503 (or allow if `fail_open=true`).
8. Log structured fields for observability: `subscription.consumer_id`,
   `subscription.tier`, `subscription.result`, `subscription.reason`.
9. Invalidate cache on expiration detection.

### 9.2 AI Gateway (`ai-gateway.lua` + `ai-gateway-schema.lua`)

**Purpose**: Integrates AI-powered analysis into the request pipeline for
anomaly detection, smart routing, and request/response transformation.

**Execution phases**: Access (priority 800), Body Filter, Log.

**Configuration**:

| Parameter                    | Type    | Default                          | Description                                  |
|------------------------------|---------|----------------------------------|----------------------------------------------|
| `ai_endpoint`                | string  | `http://admin-panel:8080/api/ai` | Base URL of the AI service                   |
| `enable_anomaly_detection`   | boolean | `true`                           | Enable anomaly detection                     |
| `enable_smart_routing`       | boolean | `false`                          | Enable AI-powered backend selection          |
| `enable_request_transform`   | boolean | `false`                          | Enable AI request body transformation        |
| `enable_response_transform`  | boolean | `false`                          | Enable AI response body transformation       |
| `anomaly_threshold`          | number  | `0.7`                            | Score threshold for anomaly action (0.0-1.0) |
| `anomaly_action`             | string  | `header`                         | Action on anomaly: `block`, `header`, `log`  |
| `sampling_rate`              | number  | `0.1`                            | Fraction of requests to analyze (0.0-1.0)    |
| `cache_ttl`                  | integer | `60`                             | Seconds to cache AI decisions                |
| `timeout`                    | integer | `5000`                           | HTTP timeout (ms) for AI calls               |
| `fail_open`                  | boolean | `true`                           | Allow requests when AI is unreachable        |
| `routing_backends`           | array   | `[]`                             | Backend names for smart routing              |
| `request_transform_rules`    | string  | --                               | Natural-language transformation rules        |
| `response_transform_rules`   | string  | --                               | Natural-language transformation rules        |

**Access phase**:

1. Roll a random number; skip if above `sampling_rate` (90% of requests are
   not analyzed by default).
2. Build request data: method, path, headers (with `authorization`, `cookie`,
   and `x-api-key` redacted), query params, body, source IP, consumer ID,
   timestamp.
3. **Anomaly detection** (if enabled): POST to `{ai_endpoint}/analyze`; cache
   result keyed by `consumer_id + path_hash`; set `X-AI-Anomaly-Score` and
   `X-AI-Analysis-Id` headers; if score >= threshold, take configured action
   (block with 403, add warning header, or log only).
4. **Smart routing** (if enabled): POST to `{ai_endpoint}/route` with request
   data and available backends; override upstream via
   `kong.service.set_target()`; inject any headers recommended by AI.
5. **Request transform** (if enabled): POST to `{ai_endpoint}/transform/request`
   with body, content type, and natural-language rules; replace request body
   with AI-transformed version.

**Body filter phase** (response transform):

- Accumulate response body chunks across multiple calls.
- On EOF (last chunk), POST full body to `{ai_endpoint}/transform/response`.
- Replace response body with transformed version (or pass through on failure).

**Log phase**: Emit structured log fields under:

- `ai.anomaly.score`, `ai.anomaly.is_anomalous`, `ai.anomaly.action`
- `ai.routing.selected_backend`, `ai.routing.confidence`
- `ai.transform.request.transform_id`, `ai.transform.request.tokens_used`
- `ai.transform.response.transform_id`, `ai.transform.response.tokens_used`
- `ai.active` (boolean: whether any AI feature was invoked)

---

## 10. AI Layer

### 10.1 Provider Architecture

The AI subsystem uses a provider abstraction pattern:

```
create_ai_agent()           [Factory - app/ai/agent.py]
       |
       +--> AnthropicFoundryProvider    [Azure AI Foundry endpoint]
       |         or
       +--> ClaudeProvider              [Direct Anthropic API]
       |
       +--> FailoverProvider            [Wraps primary + fallback]
                 |
                 +--> primary: AnthropicFoundryProvider
                 +--> fallback: ClaudeProvider
```

Provider selection is controlled by the `AI_PROVIDER` environment variable
(default: `anthropic_foundry`). The factory function in `app/ai/agent.py`
resolves credentials and endpoint URLs from environment variables and
instantiates the appropriate provider.

All providers implement the `AIProvider` abstract base class
(`app/ai/providers/base.py`) which defines seven core operations:

| Method                        | Purpose                                           |
|-------------------------------|---------------------------------------------------|
| `analyze_request()`           | Classify request intent and detect patterns       |
| `detect_anomaly()`            | Score request metrics against historical baseline |
| `suggest_rate_limit()`        | Recommend rate limits from usage history          |
| `generate_routing_decision()` | Select optimal backend from health data           |
| `transform_request()`         | AI-powered request body transformation            |
| `transform_response()`        | AI-powered response body transformation           |
| `generate_documentation()`    | Auto-generate API docs from OpenAPI/traffic       |

### 10.2 Failover Mechanism

The `FailoverProvider` wraps a primary and fallback provider. On any exception
from the primary:

1. The exception is logged.
2. A `primary_failed` flag is set to `True`.
3. The call is transparently retried on the fallback.
4. Subsequent calls skip the primary entirely (avoiding repeated timeouts).

If the fallback also fails, the exception propagates to the caller.

### 10.3 Safety Controls

The base provider class integrates optional AI safety utilities:

- **Input sanitization**: `sanitize_prompt_input()` strips injection attempts
- **Output validation**: `validate_agent_output()` checks AI responses
- **PII masking**: `mask_pii()` / `unmask_pii()` redact PII before sending to
  the AI provider and restore it in responses
- **Error sanitization**: `sanitize_ai_error()` prevents API keys and internal
  details from leaking in error messages

These are imported via graceful degradation -- if the safety module is not
available, the provider operates without safety controls and logs a debug
message at startup.

### 10.4 Cost and Token Tracking

Every provider tracks cumulative cost and token usage:

- `estimate_cost()` calculates USD cost per call from input/output token counts
- `_check_budget()` raises `ValueError` if a single call would exceed the
  `max_cost_per_analysis` ceiling (default $0.50)
- `_track_usage()` records per-call cost and accumulates totals
- The `FailoverProvider` aggregates cost/token metrics across both providers

### 10.5 Prompt Management

AI prompts are stored in the `ai_prompts` table and managed through the Admin
Panel UI (`/ai` route) and API (`/api/ai/prompts`). Prompts are:

- **Versioned**: Each update increments the `version` counter
- **Categorized**: `anomaly`, `rate_limit`, `routing`, `transform`, `documentation`
- **Activatable**: Can be enabled/disabled without deletion
- **Overridable**: Optional `model` and `temperature` fields allow per-prompt
  tuning without changing the global provider configuration

### 10.6 Integration Points

The AI layer connects to the rest of the system at two levels:

1. **Kong plugin level**: The `ai-gateway` Lua plugin calls the Admin Panel's
   AI endpoints during request processing. This is a synchronous HTTP call
   within the Kong access phase, so timeout and sampling rate configuration
   are critical for latency management. The plugin defaults to `fail_open=true`
   to prevent AI outages from blocking API traffic.

2. **Admin Panel level**: The FastAPI `ai` router exposes endpoints for
   on-demand analysis, prompt management, and configuration. These can be
   invoked from the UI or by the Kong plugin.

---

## 11. Observability Pipeline

### 11.1 Metrics Path

```
Kong                    Prometheus              Grafana
(status :8100)   --->   (scrape 15s)    --->    (dashboards)
  |                         |
  |                         +--> remote_write --> Cribl --> SIEM/S3
  |
ZAP Exporter (:9290) --+
Admin Panel (/metrics) -+
Node Exporter (:9100) -+
cAdvisor (:8080) ------+
```

### 11.2 Log Path

```
Kong access logs     --->  stdout  --->  Docker/K8s log driver
                                             |
Kong structured fields  ------------------>  Cribl Stream
  (subscription.*, ai.*)                     (pipelines)
                                                |
ZAP Exporter ----HTTP POST--->  Cribl          |
                                                v
                                          Downstream:
                                          - SIEM
                                          - S3 / Blob Storage
                                          - Splunk
                                          - Alerting
```

### 11.3 Key Metrics

| Metric Family              | Source        | Purpose                              |
|----------------------------|---------------|--------------------------------------|
| `kong_http_requests_total` | Kong          | Request counts by service/route/status |
| `kong_request_latency_ms`  | Kong          | End-to-end latency histogram         |
| `kong_upstream_latency_ms` | Kong          | Upstream-only latency histogram      |
| `kong_bandwidth_bytes`     | Kong          | Bandwidth by direction               |
| `zap_alerts_total`         | ZAP Exporter  | Security findings by severity        |

### 11.4 Grafana Dashboards

Six pre-provisioned dashboards cover the full operational surface:

| Dashboard            | Key Panels                                         |
|----------------------|----------------------------------------------------|
| Gateway Overview     | Request rate, latency percentiles, error rates     |
| Rate Limiting        | 429 responses by consumer/plan, limit utilization  |
| Authentication       | Login success/failure, session counts              |
| Security Scanning    | ZAP findings by severity, OWASP category trends   |
| AI Layer             | Anomaly scores, AI call latency, token costs       |
| Infrastructure       | Container CPU/memory, PostgreSQL connections, Redis |

### 11.5 Cribl Pipelines

| Pipeline                  | Input Source     | Key Transformations                |
|---------------------------|------------------|------------------------------------|
| `kong-logs.yml`           | Kong log plugins | Parse JSON, enrich with service metadata, extract latency fields |
| `auth-events.yml`         | Kong log plugins | Extract auth plugin, consumer, failure reason |
| `rate-limit-metrics.yml`  | Kong log plugins | Extract rate limit headers, compute utilization percentage |
| `security-scanning.yml`   | ZAP Exporter     | Map ZAP alert IDs to OWASP Top 10, assign severity scores |
| `ai-events.yml`           | Kong log plugins | Extract AI analysis metadata, anomaly scores, routing decisions |

---

## 12. Deployment Topology

### 12.1 Local Development

Managed by `docker-compose.yml`. All services run in containers on a single
bridge network. Source code is volume-mounted for hot reload (Admin Panel
`app/` and `tests/` directories, Frontend `src/` and `public/` directories).
Default credentials are set in environment variable defaults.

```bash
cp .env.example .env          # Configure environment
docker compose up -d          # Start all services
docker compose logs -f kong   # Follow Kong logs
```

### 12.2 Production (Docker Compose)

Managed by overlaying `docker-compose.prod.yml`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Key differences from development:

| Concern            | Development                    | Production                              |
|--------------------|--------------------------------|-----------------------------------------|
| Port exposure      | All ports host-mapped          | No ports exposed (ingress only)         |
| Kong Admin API     | `0.0.0.0:8001`                 | `127.0.0.1:8001` (loopback only)       |
| Container images   | Built locally                  | Pulled from ACR (`${ACR_REGISTRY}`)     |
| Source mounts      | Volumes for hot reload         | No volume mounts                        |
| Resource limits    | None                           | CPU/memory limits and reservations      |
| Redis memory       | 256 MB                         | 1 GB with `everysec` fsync             |
| Prometheus storage | 15-day retention               | 30-day retention, 10 GB size limit     |
| Logging            | Console output                 | JSON file driver with rotation          |
| Admin access log   | Enabled                        | Disabled (`"off"`)                      |

**Production resource allocations:**

| Service      | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|--------------|-----------|--------------|--------------|-----------------|
| PostgreSQL   | 2.0       | 4 GB         | 1.0          | 2 GB            |
| Kong         | 2.0       | 2 GB         | 1.0          | 1 GB            |
| Admin Panel  | 1.0       | 1 GB         | 0.5          | 512 MB          |
| Redis        | 1.0       | 1.5 GB       | 0.5          | 512 MB          |
| Prometheus   | 1.0       | 2 GB         | 0.5          | 1 GB            |
| Grafana      | 0.5       | 512 MB       | 0.25         | 256 MB          |
| Cribl        | 1.0       | 1 GB         | 0.5          | 512 MB          |

### 12.3 Kubernetes

The `k8s/` directory contains Kubernetes manifests organized as:

```
k8s/
  base/           # Base manifests (Deployments, Services, ConfigMaps)
  overlays/       # Environment-specific patches (dev, staging, prod)
  autoscaling/    # HPA and VPA configurations
```

Kubernetes service discovery is supported natively -- Prometheus is configured
with `kubernetes_sd_configs` for automatic pod and service endpoint scraping
based on annotations (`prometheus.io/scrape: "true"`).

### 12.4 Infrastructure as Code

The `terraform/` directory contains infrastructure provisioning for cloud
resources (database, Redis, networking, container registry, etc.).

---

## Appendix: Port Reference

| Port  | Protocol | Service                | Purpose                        |
|-------|----------|------------------------|--------------------------------|
| 3000  | HTTP     | Frontend (Next.js)     | Admin UI                       |
| 3000  | HTTP     | Grafana                | Dashboards (separate container)|
| 5140  | TCP      | Cribl Stream           | Syslog input                   |
| 5432  | TCP      | PostgreSQL             | Database                       |
| 6379  | TCP      | Redis                  | Cache / sessions / rate limits |
| 8000  | HTTP     | Kong Gateway           | Proxy (plaintext)              |
| 8001  | HTTP     | Kong Gateway           | Admin API                      |
| 8080  | HTTP     | Admin Panel (FastAPI)  | Control plane API              |
| 8090  | HTTP     | OWASP ZAP              | Scanner API + proxy            |
| 8100  | HTTP     | Kong Gateway           | Prometheus metrics             |
| 8443  | HTTPS    | Kong Gateway           | Proxy (TLS)                    |
| 8444  | HTTPS    | Kong Gateway           | Admin API (TLS)                |
| 9090  | HTTP     | Prometheus             | Metrics query + UI             |
| 9290  | HTTP     | ZAP Exporter           | Prometheus metrics             |
| 9420  | HTTP     | Cribl Stream           | Management UI                  |
