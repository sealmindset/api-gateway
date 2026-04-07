# Kong Gateway

## Overview

Kong 3.9 Community Edition serves as the API gateway for the platform. It handles all inbound API traffic, authenticating requests, enforcing rate limits, routing to upstream services, and collecting metrics. Two custom Lua plugins extend Kong with subscription validation and AI-powered analysis.

---

## Architecture

Kong runs in **PostgreSQL-backed** mode (not DB-less), allowing dynamic configuration changes without restarts.

### Listeners and Ports

| Port | Purpose | Notes |
|------|---------|-------|
| 8000 | HTTP proxy | Primary inbound traffic |
| 8443 | HTTPS proxy | TLS 1.2+ enforced |
| 8001 | Admin API | Internal only, never exposed to the internet |
| 8100 | Status endpoint | Prometheus metrics |

### Connection Tuning

- **Upstream keepalive pool size**: 256
- **Max requests per connection**: 10,000
- **Idle timeout**: 60 seconds
- **Max request body size**: 16 MB

### DNS Resolution

DNS resolution order: `LAST, A, SRV, CNAME`. Kong checks the last successful type first, then falls back through A, SRV, and CNAME records in order.

---

## Request Processing Pipeline

Plugins execute in **priority order** from highest to lowest. The full pipeline for a typical request:

```
Client Request
  |
  v
1. Correlation ID          (highest priority)  -- adds X-Request-ID header
2. Auth plugins            (key-auth, oauth2, jwt, basic-auth) -- identity verification
3. Subscription Validator  (priority 850)      -- validates active subscription, checks tier
4. AI Gateway              (priority 800)      -- anomaly detection, smart routing, transforms
5. Rate Limiting                               -- enforces per-consumer/per-service limits
6. Request Transformer                         -- adds X-Gateway, X-Gateway-Version headers
7. CORS / Bot Detection / IP Restriction       -- security and access control
  |
  v
Proxy to Upstream Service
  |
  v
Response passes back through response-phase plugins
  |
  v
8. Logging                 (lowest priority)   -- TCP log to Cribl, HTTP log fallback
  |
  v
Client Response
```

---

## Custom Plugin: subscription-validator

**Priority**: 850

### Purpose

Validates that the consumer has an active subscription before allowing the request through the gateway. Blocks unauthorized consumers with a `403 Forbidden` response.

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `validation_endpoint` | (required) | URL of the subscription validation service |
| `timeout` | 5000 ms | HTTP timeout for validation calls |
| `cache_ttl` | 300 s | How long to cache validation results (LRU cache) |
| `allowed_tiers` | (optional) | List of subscription tiers permitted for this service/route |
| `fail_open` | false | If true, allows requests when the validation service is unreachable |
| `header_prefix` | `X-Subscription` | Prefix for injected headers |

### Request Flow

1. **Extract consumer** from the authenticated request context.
2. **Check LRU cache** for a cached validation result.
3. On cache miss, **call the validation service** with the consumer identity.
4. **Validate** that the subscription is active and the tier is in the allowed list.
5. If invalid or inactive, return **403 Forbidden**.
6. If valid, inject subscription headers and forward the request upstream.

### Injected Headers

| Header | Description |
|--------|-------------|
| `X-Subscription-ID` | Unique subscription identifier |
| `X-Subscription-Tier` | Current tier (free, standard, premium, enterprise) |
| `X-Subscription-Expires-At` | Subscription expiration timestamp |
| `X-Subscription-Valid` | Boolean indicating validation result |
| `X-Subscription-Features` | Comma-separated list of enabled features |
| `X-Subscription-Org-ID` | Organization identifier for the subscriber |

### Fail-Open Behavior

When `fail_open` is set to **false** (the default), any failure to reach the validation service results in a `403`. When set to **true**, requests are allowed through if the validation service is unreachable, and the subscription headers are omitted.

---

## Custom Plugin: ai-gateway

**Priority**: 800

### Purpose

AI-powered request analysis including anomaly detection, smart routing, and request/response transformation. Uses an external AI service to score and optionally modify traffic.

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ai_endpoint` | (required) | URL of the admin panel AI analysis endpoint |
| `enable_anomaly_detection` | true | Enable anomaly scoring on requests |
| `enable_smart_routing` | false | Enable AI-based backend selection |
| `enable_request_transform` | false | Enable AI-driven request transformations |
| `enable_response_transform` | false | Enable AI-driven response transformations |
| `anomaly_threshold` | 0.7 | Score above which a request is flagged (0.0 to 1.0) |
| `sampling_rate` | 0.1 | Fraction of requests sent for AI analysis (0.0 to 1.0) |
| `cache_ttl` | 60 s | Cache duration for AI analysis results |
| `timeout` | 5000 ms | HTTP timeout for AI service calls |
| `fail_open` | true | Allow requests through if the AI service is unreachable |
| `anomaly_action` | `log` | Action on anomalous requests: `block`, `header`, or `log` |

### Anomaly Detection

Each sampled request receives a score from 0.0 (normal) to 1.0 (highly anomalous). When the score exceeds the configured `anomaly_threshold`, the plugin takes the action specified by `anomaly_action`:

- **block**: Reject the request with a `403` response.
- **header**: Allow the request but add the `X-AI-Anomaly-Score` header for upstream services to inspect.
- **log**: Allow the request and log the anomaly score (no visible effect to the client).

### Smart Routing

When enabled, the plugin sends request metadata and backend health data to the AI service, which selects the optimal upstream target. The selected route is communicated via the `X-AI-Route-Decision` header.

### Request and Response Transforms

When enabled, the plugin applies natural-language transformation rules defined in the admin panel. These can modify headers, body content, or query parameters on requests and responses.

### Response Headers

| Header | Description |
|--------|-------------|
| `X-AI-Anomaly-Score` | Anomaly score assigned to the request (0.0 to 1.0) |
| `X-AI-Route-Decision` | Backend selected by smart routing |
| `X-AI-Status` | Status of the AI analysis (e.g., `analyzed`, `skipped`, `error`) |
| `X-AI-Analysis-Id` | Unique identifier for the analysis record |

### Sampling

Only a fraction of requests are sent for AI analysis, controlled by `sampling_rate`. At the default of `0.1`, roughly 10% of requests are analyzed. Requests that are not sampled pass through without any AI processing overhead.

---

## Rate Limiting Tiers

Rate limits are enforced per consumer and backed by **Redis** with a fault-tolerant policy.

| Tier | Per Second | Per Minute | Per Hour |
|------|-----------|-----------|---------|
| Free | 1 | 30 | 500 |
| Standard | 5 | 100 | 3,000 |
| Premium | 20 | 500 | 15,000 |
| Enterprise | 100 | 3,000 | 100,000 |

When a consumer exceeds a limit, Kong returns `429 Too Many Requests` with `Retry-After` and `X-RateLimit-*` headers indicating the current state and when the limit resets.

---

## Authentication Methods

Kong supports multiple authentication plugins, configured per service or per route.

### key-auth

API key authentication. The key can be supplied via:

- **Header**: `X-API-Key`
- **Query parameter**: `apikey`

### oauth2

OAuth 2.0 with support for:

- **Authorization Code** grant (for user-facing applications)
- **Client Credentials** grant (for service-to-service communication)
- Access token expiry: **2 hours**
- Refresh token expiry: **14 days**

### jwt

JSON Web Token authentication. Consumers present a signed JWT, and Kong validates the signature and claims before forwarding the request.

### basic-auth

Username and password authentication, intended for **internal services** where token-based auth is not required.

---

## Declarative Configuration (kong.yml)

The initial gateway configuration is loaded from `kong.yml` via `kong config db_import` during setup. After import, all configuration lives in PostgreSQL and can be modified through the Admin API.

### Global Plugins

The following plugins are enabled globally across all services:

- **correlation-id** -- generates `X-Request-ID` on every request
- **prometheus** -- exposes metrics at `:8100/metrics`
- **tcp-log** -- ships logs to Cribl
- **http-log** -- fallback log destination
- **cors** -- cross-origin resource sharing headers
- **ip-restriction** -- block or allow by IP/CIDR
- **bot-detection** -- blocks known bot user agents
- **request-transformer** -- adds `X-Gateway` and `X-Gateway-Version` headers

### Pre-Configured Services

| Service Name | Auth Method | Description |
|-------------|-------------|-------------|
| `api-v1-oauth2` | OAuth 2.0 | Public API with OAuth authentication |
| `api-v1-keyauth` | API Key | Public API with key-based authentication |
| `internal-api-basicauth` | Basic Auth | Internal service endpoints |
| `health-check` | None | Gateway health endpoint |

### Consumer Groups

Consumer groups map to rate limiting tiers. Each group has rate-limiting plugin configuration matching the tier table above. When a consumer is assigned to a group, they inherit that group's limits.

---

## API Registration Integration

When an API registration is activated through the admin panel, Kong is configured automatically via the Admin API.

### On Activation

1. A **service** is created: `api-reg-{slug}` pointing to the registered upstream URL.
2. A **route** is created: `api-reg-{slug}-route` with the configured paths and methods.
3. **Plugins are auto-attached**:
   - `rate-limiting` with limits from the registration configuration
   - The appropriate auth plugin (key-auth, oauth2, etc.)
   - `prometheus` with per-consumer tracking enabled
   - `request-size-limiting` with `allowed_payload_size` set to the registration's `max_request_size_kb` (default 128 KB)

### On Retirement

When an API registration is retired, the corresponding Kong service and route are **deleted** from the gateway. Consumers that only accessed the retired API will receive `404` responses.

### On Contract Update

When a data contract is updated on an active API (`PATCH /api-registry/{id}/contract`) and the `max_request_size_kb` field is changed, the Kong `request-size-limiting` plugin is automatically updated. The admin panel checks for an existing plugin on the service and either creates or patches it:

- If the plugin exists: `PATCH /services/{svc}/plugins/{plugin_id}` with the new size
- If no plugin exists: `POST /services/{svc}/plugins` to create it

This keeps Kong enforcement in sync with the data contract without requiring re-activation.

### Proxy Cache Plugin

APIs with `cache_enabled=true` in their data contract get a `proxy-cache` plugin attached to their Kong service. This caches responses in memory to reduce upstream load and improve latency for repeat requests.

**Configuration (from data contract):**

| Data Contract Field | Kong Plugin Config | Default |
|---|---|---|
| `cache_ttl_seconds` | `cache_ttl` | 300 |
| `cache_methods` | `request_method` | `["GET", "HEAD"]` |
| `cache_content_types` | `content_type` | `["application/json"]` |
| `cache_vary_headers` | `vary_headers` | `["Accept"]` |

**Fixed settings:**
- `strategy`: `memory` (Kong CE 3.9 limitation — Redis strategy requires Kong Enterprise)
- `response_code`: `[200, 301, 302]`
- `cache_control`: `true` (respects upstream `Cache-Control` headers)
- `storage_ttl`: `cache_ttl * 2` (internal storage buffer)

**Lifecycle:**
- On activation: plugin created if `cache_enabled=true`
- On contract update: plugin created/updated/removed based on `cache_enabled`
- Disabling cache removes the plugin entirely (no stale cache)

**Safe defaults:** Caching is **disabled by default**. The `cache_bypass_on_auth` advisory flag (default `true`) reminds teams that caching personalized or PII-containing responses requires careful evaluation.

---

## Operational Notes

### Health Checks

Run `kong health` to verify the gateway process and database connectivity. The status endpoint at `:8100` also serves as a liveness probe.

### Configuration Reload

Kong watches PostgreSQL for configuration changes. When a service, route, or plugin is created or updated via the Admin API, the change takes effect without restarting the gateway process.

### Logging

Logs are emitted in **JSON format** to stdout and stderr, picked up by the Docker logging driver. Primary log destination is **Cribl** via the TCP log plugin, with an HTTP log endpoint as a fallback.

### Metrics

The Prometheus plugin exposes detailed metrics at `:8100/metrics`, including:

- **Per-consumer** request counts and latencies
- **Per-route** traffic breakdowns
- **Per-status-code** response distributions
- Upstream health and connection pool statistics
