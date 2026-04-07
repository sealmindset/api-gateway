# API Reference

Complete reference for the API Gateway Admin Panel REST API, built with FastAPI.

**Base URL:** `https://<admin-panel-host>`
**Interactive docs:** `/docs` (Swagger UI) | `/redoc` (ReDoc)

## Authentication

All authenticated endpoints use Entra ID (Azure AD) OIDC. Users must first complete the OAuth login flow via `/auth/login`. Subsequent requests are authorized through server-side session cookies (`admin_session`).

Permission-protected endpoints are annotated with their required RBAC permission (e.g., `subscribers:read`). Platform admins (`super_admin`, `admin` roles) have access to all permissions.

## Common Response Models

### PaginatedResponse

Returned by all list endpoints that support pagination.

| Field | Type | Description |
|-------|------|-------------|
| `items` | `array` | Page of results |
| `total` | `integer` | Total matching records |
| `page` | `integer` | Current page number |
| `page_size` | `integer` | Items per page |

### Error Response

```json
{
  "detail": "Description of the error."
}
```

Standard HTTP status codes: `400` (bad request), `401` (unauthenticated), `403` (forbidden), `404` (not found), `409` (conflict), `422` (validation error), `502` (upstream gateway error), `503` (service unavailable).

---

## Health & Readiness

These endpoints are unauthenticated and intended for orchestration probes.

### GET /health

Liveness probe. Returns 200 if the process is running.

**Auth:** None

**Response:**

```json
{
  "status": "ok"
}
```

### GET /ready

Readiness probe. Verifies database connectivity.

**Auth:** None

**Response (200):**

```json
{
  "status": "ready"
}
```

**Response (503):**

```json
{
  "status": "not_ready",
  "detail": "DB engine not initialised"
}
```

---

## Auth Endpoints

Prefix: `/auth`

### GET /auth/login

Redirect the browser to the Entra ID authorization endpoint. Initiates the OIDC login flow.

**Auth:** None

**Response:** `302 Redirect` to Entra ID authorization URL.

### GET /auth/callback

Handle the OIDC callback from Entra ID. Exchanges the authorization code for tokens, stores them in the session, and provisions the local user record if needed.

**Auth:** None (callback from identity provider)

**Response:** `302 Redirect` to `/` on success.

**Error Response (400):**

```json
{
  "detail": "Authentication failed. Could not exchange code for token."
}
```

### POST /auth/logout

Clear the server-side session and log the user out.

**Auth:** Session cookie (any authenticated user)

**Response:**

```json
{
  "detail": "Logged out successfully."
}
```

### GET /auth/me

Return the current user's profile including assigned RBAC roles.

**Auth:** Authenticated user (session cookie)

**Response Model:** `CurrentUser`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | User ID |
| `email` | `string (email)` | User email |
| `name` | `string` | Display name |
| `entra_oid` | `string` | Entra ID object identifier |
| `roles` | `object \| null` | Legacy roles dict |
| `created_at` | `datetime` | Account creation timestamp |
| `last_login` | `datetime \| null` | Last login timestamp |
| `assigned_roles` | `array[RoleRead]` | RBAC roles assigned to the user |

**Example Response:**

```json
{
  "id": "a1b2c3d4-...",
  "email": "user@example.com",
  "name": "Jane Doe",
  "entra_oid": "00000000-0000-0000-0000-000000000000",
  "roles": null,
  "created_at": "2025-01-15T10:00:00Z",
  "last_login": "2025-06-01T14:30:00Z",
  "assigned_roles": [
    {
      "id": "...",
      "name": "admin",
      "description": "Platform administrator",
      "permissions": {"subscribers:read": true, "subscribers:write": true},
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

---

## Teams

Prefix: `/teams`

### GET /teams

List teams with optional filtering and pagination.

**Auth:** `teams:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number (>= 1) |
| `page_size` | `integer` | `20` | Items per page (1-100) |
| `search` | `string` | `null` | Search by team name or slug |
| `my_teams` | `boolean` | `false` | Only show teams the current user belongs to |

**Response Model:** `PaginatedResponse` with items of type `TeamDetail`.

### POST /teams

Create a new team. The creating user is automatically added as the team owner.

**Auth:** `teams:write`

**Request Body:** `TeamCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | Team name (max 256 chars) |
| `slug` | `string` | Yes | URL-safe identifier (max 128 chars, pattern: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`) |
| `description` | `string` | No | Team description |
| `contact_email` | `string (email)` | Yes | Team contact email |
| `metadata` | `object` | No | Arbitrary metadata |

**Response (201):** `TeamDetail`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Team ID |
| `name` | `string` | Team name |
| `slug` | `string` | URL slug |
| `description` | `string \| null` | Description |
| `contact_email` | `string` | Contact email |
| `metadata` | `object \| null` | Metadata |
| `is_active` | `boolean` | Active status |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |
| `member_count` | `integer` | Number of members |
| `api_count` | `integer` | Number of registered APIs |

**Error (409):** Slug already exists.

### GET /teams/{team_id}

Get a team by ID.

**Auth:** `teams:read`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | `uuid` | Team identifier |

**Response:** `TeamDetail`

### PATCH /teams/{team_id}

Update team details. Requires `admin` or `owner` role within the team (or platform admin).

**Auth:** `teams:write` + team role `admin`+

**Request Body:** `TeamUpdate` (all fields optional)

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Team name |
| `description` | `string` | Description |
| `contact_email` | `string (email)` | Contact email |
| `metadata` | `object` | Metadata |
| `is_active` | `boolean` | Active status |

**Response:** `TeamRead`

### DELETE /teams/{team_id}

Deactivate a team (soft delete). Requires `owner` role within the team.

**Auth:** `teams:delete` + team role `owner`

**Response:** `204 No Content`

### GET /teams/{team_id}/members

List members of a team.

**Auth:** `teams:read`

**Response:** `array[TeamMemberRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Membership ID |
| `team_id` | `uuid` | Team ID |
| `user_id` | `uuid` | User ID |
| `role` | `string` | Role: `owner`, `admin`, `member`, or `viewer` |
| `joined_at` | `datetime` | Join timestamp |
| `user_name` | `string \| null` | User's display name |
| `user_email` | `string \| null` | User's email |

### POST /teams/{team_id}/members

Add a user to a team. Requires `admin`+ role within the team.

**Auth:** `teams:write` + team role `admin`+

**Request Body:** `TeamMemberAdd`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `user_id` | `uuid` | Yes | -- | ID of the user to add |
| `role` | `string` | No | `"member"` | One of: `owner`, `admin`, `member`, `viewer` |

**Response (201):** `TeamMemberRead`

**Errors:** `404` (user not found), `409` (already a member).

### PATCH /teams/{team_id}/members/{member_id}

Change a member's role. Requires `admin`+ role within the team.

**Auth:** `teams:write` + team role `admin`+

**Request Body:** `TeamMemberUpdate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | `string` | Yes | One of: `owner`, `admin`, `member`, `viewer` |

**Response:** `TeamMemberRead`

### DELETE /teams/{team_id}/members/{member_id}

Remove a member from a team. Requires `admin`+ role. Cannot remove the last owner.

**Auth:** `teams:write` + team role `admin`+

**Response:** `204 No Content`

**Error (400):** Cannot remove the last owner.

---

## API Registry

Prefix: `/api-registry`

Manages the lifecycle of API registrations through a workflow: `draft` -> `pending_review` -> `approved` -> `active` -> `deprecated` -> `retired`.

### Status Transitions

| Current Status | Allowed Next Statuses |
|----------------|----------------------|
| `draft` | `pending_review` |
| `pending_review` | `approved`, `rejected` |
| `approved` | `active` |
| `rejected` | `draft` |
| `active` | `deprecated` |
| `deprecated` | `active`, `retired` |
| `retired` | (none) |

### GET /api-registry

List API registrations with filters and pagination.

**Auth:** `api_registry:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number |
| `page_size` | `integer` | `20` | Items per page (1-100) |
| `team_id` | `uuid` | `null` | Filter by team |
| `status` | `string` | `null` | Filter by status |
| `search` | `string` | `null` | Search by name or slug |

**Response:** `PaginatedResponse` with `ApiRegistrationRead` items.

### POST /api-registry

Register a new API. User must be a member of the specified team.

**Auth:** `api_registry:write` + team membership (`member`+)

**Request Body:** `ApiRegistrationCreate`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `string` | Yes | -- | API name (max 256) |
| `slug` | `string` | Yes | -- | URL-safe identifier (max 128) |
| `description` | `string` | No | `null` | Description |
| `version` | `string` | No | `"v1"` | API version |
| `api_type` | `string` | No | `"rest"` | One of: `rest`, `graphql`, `grpc`, `websocket` |
| `documentation_url` | `string` | No | `null` | Link to external docs |
| `tags` | `array[string]` | No | `null` | Tags for categorization |
| `upstream_url` | `string` | Yes | -- | Backend service URL |
| `upstream_protocol` | `string` | No | `"https"` | One of: `http`, `https`, `grpc`, `grpcs` |
| `health_check_path` | `string` | No | `"/health"` | Health check endpoint path |
| `gateway_path` | `string` | No | `null` | Custom gateway path (defaults to `/api/{slug}`) |
| `rate_limit_second` | `integer` | No | `5` | Rate limit per second |
| `rate_limit_minute` | `integer` | No | `100` | Rate limit per minute |
| `rate_limit_hour` | `integer` | No | `3000` | Rate limit per hour |
| `auth_type` | `string` | No | `"key-auth"` | One of: `key-auth`, `oauth2`, `jwt`, `none` |
| `requires_approval` | `boolean` | No | `true` | Whether the API requires review before activation |
| `team_id` | `uuid` | Yes | -- | Owning team ID |
| `contact_primary_email` | `string` | No | `null` | Primary on-call contact email (max 320) |
| `contact_escalation_email` | `string` | No | `null` | Escalation contact email (max 320) |
| `contact_slack_channel` | `string` | No | `null` | Slack channel for alerts (max 128) |
| `contact_pagerduty_service` | `string` | No | `null` | PagerDuty service key (max 256) |
| `contact_support_url` | `string` | No | `null` | Support page or runbook URL |
| `sla_uptime_target` | `float` | No | `null` | Uptime SLA target, e.g. `99.95` (0-100) |
| `sla_latency_p50_ms` | `integer` | No | `null` | P50 latency target in ms |
| `sla_latency_p95_ms` | `integer` | No | `null` | P95 latency target in ms |
| `sla_latency_p99_ms` | `integer` | No | `null` | P99 latency target in ms |
| `sla_error_budget_pct` | `float` | No | `null` | Error budget percentage (0-100) |
| `sla_support_hours` | `string` | No | `null` | Support hours, e.g. `"24/7"`, `"business-hours-cst"` |
| `deprecation_notice_days` | `integer` | No | `90` | Minimum days notice before deprecation |
| `breaking_change_policy` | `string` | No | `"semver"` | One of: `semver`, `date-based`, `never-break`, `custom` |
| `versioning_scheme` | `string` | No | `"url-path"` | One of: `url-path`, `header`, `query-param`, `content-type` |
| `changelog_url` | `string` | No | `null` | Link to API changelog |
| `openapi_spec_url` | `string` | No | `null` | Link to OpenAPI spec |
| `max_request_size_kb` | `integer` | No | `128` | Max request body size in KB (1-102400). Enforced in Kong via `request-size-limiting` plugin |
| `max_response_size_kb` | `integer` | No | `null` | Max response body size in KB |
| `cache_enabled` | `boolean` | No | `false` | Enable response caching via Kong `proxy-cache` plugin |
| `cache_ttl_seconds` | `integer` | No | `300` | Cache TTL in seconds (1-86400) |
| `cache_methods` | `array[string]` | No | `["GET","HEAD"]` | HTTP methods to cache |
| `cache_content_types` | `array[string]` | No | `["application/json"]` | Content types to cache |
| `cache_vary_headers` | `array[string]` | No | `["Accept"]` | Headers that vary cache keys |
| `cache_bypass_on_auth` | `boolean` | No | `true` | Advisory: don't cache personalized responses |

**Response (201):** `ApiRegistrationRead`

**Error (409):** Slug already exists.

### GET /api-registry/{reg_id}

Get a single API registration by ID.

**Auth:** `api_registry:read`

**Response:** `ApiRegistrationRead`

The full response model includes all fields from the create schema plus:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Registration ID |
| `team_id` | `uuid` | Owning team |
| `kong_service_id` | `string \| null` | Kong service ID (set on activation) |
| `kong_route_id` | `string \| null` | Kong route ID (set on activation) |
| `status` | `string` | Current lifecycle status |
| `submitted_at` | `datetime \| null` | When submitted for review |
| `reviewed_by` | `uuid \| null` | Reviewer user ID |
| `reviewed_at` | `datetime \| null` | When reviewed |
| `review_notes` | `string \| null` | Reviewer notes |
| `activated_at` | `datetime \| null` | When activated in Kong |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

### PATCH /api-registry/{reg_id}

Update an API registration. Only allowed when status is `draft` or `rejected`. Editing a rejected API resets it to `draft`.

**Auth:** `api_registry:write` + team membership (`member`+)

**Request Body:** `ApiRegistrationUpdate` (all fields optional, same as create minus `team_id`)

**Response:** `ApiRegistrationRead`

**Error (400):** Cannot edit an API that is not in `draft` or `rejected` status.

### DELETE /api-registry/{reg_id}

Delete an API registration. Only allowed in `draft` or `rejected` status.

**Auth:** `api_registry:delete` + team role `admin`+

**Response:** `204 No Content`

### POST /api-registry/{reg_id}/submit

Submit a draft API for review.

**Auth:** `api_registry:write` + team membership (`member`+)

**Request Body:** None

**Response:** `ApiRegistrationRead` (status becomes `pending_review`)

**Error (400):** Only draft APIs can be submitted.

### POST /api-registry/{reg_id}/review

Approve or reject a pending API registration.

**Auth:** `api_registry:approve`

**Request Body:** `ApiRegistrationReview`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | `string` | Yes | `"approve"` or `"reject"` |
| `notes` | `string` | No | Review notes |

**Response:** `ApiRegistrationRead`

**Error (400):** Only pending APIs can be reviewed.

### POST /api-registry/{reg_id}/activate

Activate an approved API. Provisions a Kong service, route, rate-limiting plugin, auth plugin, and prometheus plugin.

**Auth:** `api_registry:approve`

**Request Body:** None

**Response:** `ApiRegistrationRead` (status becomes `active`, `kong_service_id` and `kong_route_id` populated)

**Error (400):** Only approved APIs can be activated.

### POST /api-registry/{reg_id}/status

Change the status of an active or deprecated API (deprecate, reactivate, or retire). Retiring an API deprovisions it from Kong.

**Auth:** `api_registry:approve`

**Request Body:** `ApiRegistrationStatusChange`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `string` | Yes | One of: `active`, `deprecated`, `retired` |

**Response:** `ApiRegistrationRead`

**Error (400):** Invalid status transition.

### GET /api-registry/{reg_id}/usage

Get usage metrics for a registered API from Kong.

**Auth:** `api_registry:read`

**Response:**

```json
{
  "api_id": "uuid",
  "api_name": "My API",
  "api_slug": "my-api",
  "status": "active",
  "gateway_path": "/api/my-api",
  "kong_service_id": "...",
  "kong_route_id": "...",
  "service": {
    "protocol": "https",
    "host": "backend.example.com",
    "port": 443,
    "enabled": true
  },
  "route": {
    "paths": ["/api/my-api"],
    "methods": null,
    "protocols": ["http", "https"]
  },
  "plugins": [
    {"name": "rate-limiting", "enabled": true, "config": {}}
  ],
  "rate_limits": {
    "second": 5,
    "minute": 100,
    "hour": 3000
  }
}
```

### PATCH /api-registry/{reg_id}/contract

Update data contract fields on an API registration. Allowed in **any status** (draft, active, deprecated) without re-approval. Only contract-related fields (contacts, SLAs, change management, schema) can be updated through this endpoint.

If the API is active and `max_request_size_kb` is changed, the Kong `request-size-limiting` plugin is updated automatically.

**Auth:** `api_registry:write` + team membership (`member`+)

**Request Body:** `DataContractUpdate` (all fields optional)

| Field | Type | Description |
|-------|------|-------------|
| `contact_primary_email` | `string` | Primary on-call contact email |
| `contact_escalation_email` | `string` | Escalation contact email |
| `contact_slack_channel` | `string` | Slack channel for alerts |
| `contact_pagerduty_service` | `string` | PagerDuty service key |
| `contact_support_url` | `string` | Support page or runbook URL |
| `sla_uptime_target` | `float` | Uptime SLA target (0-100) |
| `sla_latency_p50_ms` | `integer` | P50 latency target in ms |
| `sla_latency_p95_ms` | `integer` | P95 latency target in ms |
| `sla_latency_p99_ms` | `integer` | P99 latency target in ms |
| `sla_error_budget_pct` | `float` | Error budget percentage (0-100) |
| `sla_support_hours` | `string` | Support hours (e.g. `"24/7"`) |
| `deprecation_notice_days` | `integer` | Minimum days notice before deprecation |
| `breaking_change_policy` | `string` | One of: `semver`, `date-based`, `never-break`, `custom` |
| `versioning_scheme` | `string` | One of: `url-path`, `header`, `query-param`, `content-type` |
| `changelog_url` | `string` | Link to API changelog |
| `openapi_spec_url` | `string` | Link to OpenAPI spec |
| `max_request_size_kb` | `integer` | Max request body size in KB (1-102400) |
| `max_response_size_kb` | `integer` | Max response body size in KB |
| `cache_enabled` | `boolean` | Enable/disable response caching |
| `cache_ttl_seconds` | `integer` | Cache TTL in seconds (1-86400) |
| `cache_methods` | `array[string]` | HTTP methods to cache |
| `cache_content_types` | `array[string]` | Content types to cache |
| `cache_vary_headers` | `array[string]` | Headers that vary cache keys |
| `cache_bypass_on_auth` | `boolean` | Advisory: don't cache personalized responses |

**Response:** `ApiRegistrationRead`

**Error (404):** Registration not found.
**Error (422):** Validation error (e.g., `sla_uptime_target > 100`, negative latency, invalid policy).

**Kong sync behavior:** If the API is active:
- Changing `max_request_size_kb` updates the `request-size-limiting` plugin
- Changing any `cache_*` field syncs the `proxy-cache` plugin (creates, updates, or removes it based on `cache_enabled`)

---

## Public API Catalog

Prefix: `/public/api-catalog`

These endpoints are **unauthenticated** and intended for API consumers and subscribers to discover available APIs and their data contracts.

### GET /public/api-catalog

List all active APIs with their data contracts. Only APIs in `active` status are included.

**Auth:** None

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number |
| `page_size` | `integer` | `20` | Items per page (max 100) |
| `search` | `string` | `null` | Filter by name or slug (case-insensitive) |

**Response:** `PaginatedResponse` containing `PublicApiCatalogEntry` items.

### GET /public/api-catalog/{slug}

Get a single active API's data contract by slug.

**Auth:** None

**Response:** `PublicApiCatalogEntry`

```json
{
  "name": "Weather Forecast API",
  "slug": "weather-forecast-api",
  "description": "Returns 7-day forecasts by ZIP code.",
  "version": "v1",
  "api_type": "rest",
  "documentation_url": "https://docs.example.com/weather-api",
  "gateway_path": "/api/weather",
  "auth_type": "key-auth",
  "tags": ["weather", "forecast"],
  "status": "active",
  "rate_limit_second": 10,
  "rate_limit_minute": 200,
  "rate_limit_hour": 5000,
  "contact_primary_email": "oncall@example.com",
  "contact_escalation_email": "escalation@example.com",
  "contact_slack_channel": "#weather-api-alerts",
  "sla_uptime_target": 99.95,
  "sla_latency_p50_ms": 50,
  "sla_latency_p95_ms": 200,
  "sla_latency_p99_ms": 500,
  "sla_support_hours": "24/7",
  "deprecation_notice_days": 60,
  "breaking_change_policy": "semver",
  "versioning_scheme": "url-path",
  "max_request_size_kb": 512,
  "openapi_spec_url": "https://docs.example.com/openapi.json"
}
```

**Note:** Internal fields (`upstream_url`, `kong_service_id`, `kong_route_id`, `reviewed_by`, `team_id`) are excluded from the public catalog response.

**Error (404):** API not found or not in `active` status.

### GET /public/api-catalog/{slug}/try-it

Interactive Swagger UI page for testing an active API. Loads the API's OpenAPI specification and pre-configures the gateway URL as the server. Subscribers enter their API key in the authorize dialog to make authenticated requests.

**Auth:** None (API key entered in Swagger UI, enforced by Kong)

**Response (200):** HTML page with embedded Swagger UI.

**Error (404):** API not found, not active, or no `openapi_spec_url` configured.

---

## Subscribers

Prefix: `/subscribers`

### GET /subscribers

List subscribers with pagination and optional filters.

**Auth:** `subscribers:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number |
| `page_size` | `integer` | `20` | Items per page (1-100) |
| `status` | `string` | `null` | Filter by status |
| `tier` | `string` | `null` | Filter by tier |
| `search` | `string` | `null` | Search by name, email, or organization |

**Response:** `PaginatedResponse` with `SubscriberRead` items.

### POST /subscribers

Create a new subscriber.

**Auth:** `subscribers:write`

**Request Body:** `SubscriberCreate`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `string` | Yes | -- | Subscriber name (max 256) |
| `email` | `string (email)` | Yes | -- | Contact email |
| `organization` | `string` | No | `null` | Organization name (max 256) |
| `tier` | `string` | No | `"free"` | Subscription tier (max 32) |

**Response (201):** `SubscriberRead`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Subscriber ID |
| `name` | `string` | Name |
| `email` | `string` | Email |
| `organization` | `string \| null` | Organization |
| `tier` | `string` | Tier |
| `status` | `string` | Status (e.g., `active`, `deleted`) |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

### GET /subscribers/{subscriber_id}

Retrieve a single subscriber by ID.

**Auth:** `subscribers:read`

**Response:** `SubscriberRead`

### PATCH /subscribers/{subscriber_id}

Update subscriber fields.

**Auth:** `subscribers:write`

**Request Body:** `SubscriberUpdate` (all fields optional)

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Name (max 256) |
| `email` | `string (email)` | Email |
| `organization` | `string` | Organization (max 256) |
| `tier` | `string` | Tier (max 32) |
| `status` | `string` | Status (max 32) |

**Response:** `SubscriberRead`

### DELETE /subscribers/{subscriber_id}

Soft-delete a subscriber by setting status to `deleted`.

**Auth:** `subscribers:delete`

**Response:** `204 No Content`

### PUT /subscribers/{subscriber_id}/rate-limit

Set rate-limit overrides on the subscriber's active subscription.

**Auth:** `subscribers:write`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rate_limit_per_second` | `integer` | `null` | Requests per second |
| `rate_limit_per_minute` | `integer` | `null` | Requests per minute |
| `rate_limit_per_hour` | `integer` | `null` | Requests per hour |

**Response:**

```json
{
  "detail": "Rate limits updated.",
  "subscription_id": "uuid"
}
```

**Error (404):** No active subscription found.

---

## Subscriber API Keys

Nested under `/subscribers/{subscriber_id}/keys`.

### GET /subscribers/{subscriber_id}/keys

List all API keys for a subscriber.

**Auth:** `api_keys:read`

**Response:** `array[ApiKeyRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Key ID |
| `subscriber_id` | `uuid` | Owning subscriber |
| `key_prefix` | `string` | First 8 characters of the key |
| `name` | `string` | Key name |
| `scopes` | `array \| null` | Allowed scopes |
| `rate_limit` | `integer \| null` | Per-key rate limit |
| `expires_at` | `datetime \| null` | Expiration timestamp |
| `is_active` | `boolean` | Whether the key is active |
| `created_at` | `datetime` | Creation timestamp |
| `last_used_at` | `datetime \| null` | Last usage timestamp |

### POST /subscribers/{subscriber_id}/keys

Generate a new API key for a subscriber and sync to Kong.

**Auth:** `api_keys:write`

**Request Body:** `ApiKeyCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | Key name (max 128) |
| `scopes` | `array[string]` | No | Allowed scopes |
| `rate_limit` | `integer` | No | Per-key rate limit |
| `expires_at` | `datetime` | No | Expiration timestamp |

**Response (201):** `ApiKeyCreated`

Includes all `ApiKeyRead` fields plus:

| Field | Type | Description |
|-------|------|-------------|
| `raw_key` | `string` | The full API key (shown only once, starts with `gw_`) |

**Example Response:**

```json
{
  "id": "...",
  "subscriber_id": "...",
  "key_prefix": "gw_abc12",
  "name": "Production Key",
  "scopes": ["read", "write"],
  "rate_limit": 100,
  "expires_at": null,
  "is_active": true,
  "created_at": "2025-06-01T00:00:00Z",
  "last_used_at": null,
  "raw_key": "gw_a1b2c3d4e5f6..."
}
```

### POST /subscribers/{subscriber_id}/keys/{key_id}/rotate

Rotate an API key: revokes the old one and issues a new one with the same configuration.

**Auth:** `api_keys:write`

**Request Body:** None

**Response:** `ApiKeyRotateResponse`

| Field | Type | Description |
|-------|------|-------------|
| `old_key_id` | `uuid` | The revoked key's ID |
| `new_key` | `ApiKeyCreated` | The newly created key (includes `raw_key`) |

### DELETE /subscribers/{subscriber_id}/keys/{key_id}

Revoke (deactivate) an API key.

**Auth:** `api_keys:delete`

**Response:** `204 No Content`

---

## Plans

Prefix: `/plans`

### GET /plans

List all subscription plans.

**Auth:** `subscriptions:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `active_only` | `boolean` | `true` | Only return active plans |

**Response:** `array[PlanRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Plan ID |
| `name` | `string` | Plan name |
| `description` | `string \| null` | Description |
| `rate_limit_second` | `integer` | Requests per second |
| `rate_limit_minute` | `integer` | Requests per minute |
| `rate_limit_hour` | `integer` | Requests per hour |
| `max_api_keys` | `integer` | Maximum API keys allowed |
| `allowed_endpoints` | `array[string] \| null` | Allowed endpoint patterns |
| `price_cents` | `integer` | Price in cents |
| `is_active` | `boolean` | Whether the plan is active |
| `created_at` | `datetime` | Creation timestamp |

### POST /plans

Create a new subscription plan.

**Auth:** `subscriptions:write`

**Request Body:** `PlanCreate`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `string` | Yes | -- | Plan name (max 64) |
| `description` | `string` | No | `null` | Description |
| `rate_limit_second` | `integer` | No | `1` | Rate limit per second |
| `rate_limit_minute` | `integer` | No | `30` | Rate limit per minute |
| `rate_limit_hour` | `integer` | No | `500` | Rate limit per hour |
| `max_api_keys` | `integer` | No | `2` | Max API keys |
| `allowed_endpoints` | `array[string]` | No | `null` | Allowed endpoints |
| `price_cents` | `integer` | No | `0` | Price in cents |
| `is_active` | `boolean` | No | `true` | Active status |

**Response (201):** `PlanRead`

### GET /plans/{plan_id}

Get a single plan by ID.

**Auth:** `subscriptions:read`

**Response:** `PlanRead`

### PATCH /plans/{plan_id}

Update plan fields.

**Auth:** `subscriptions:write`

**Request Body:** `PlanUpdate` (all fields optional, same as `PlanCreate`)

**Response:** `PlanRead`

### DELETE /plans/{plan_id}

Deactivate a plan (soft delete). Sets `is_active` to `false`.

**Auth:** `subscriptions:delete`

**Response:** `204 No Content`

---

## Subscriptions

Prefix: `/subscriptions`

### GET /subscriptions

List subscriptions with optional filters and pagination.

**Auth:** `subscriptions:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number |
| `page_size` | `integer` | `20` | Items per page (1-100) |
| `subscriber_id` | `uuid` | `null` | Filter by subscriber |
| `status` | `string` | `null` | Filter by status |

**Response:** `PaginatedResponse` with `SubscriptionRead` items.

### POST /subscriptions

Create a subscription for a subscriber.

**Auth:** `subscriptions:write`

**Request Body:** `SubscriptionCreate`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `subscriber_id` | `uuid` | Yes | -- | Subscriber ID |
| `plan_id` | `uuid` | Yes | -- | Plan ID |
| `starts_at` | `datetime` | Yes | -- | Start timestamp |
| `expires_at` | `datetime` | No | `null` | Expiration timestamp |
| `rate_limit_per_second` | `integer` | No | `null` | Override: requests per second |
| `rate_limit_per_minute` | `integer` | No | `null` | Override: requests per minute |
| `rate_limit_per_hour` | `integer` | No | `null` | Override: requests per hour |
| `allowed_endpoints` | `array[string]` | No | `null` | Override: allowed endpoints |

**Response (201):** `SubscriptionRead`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Subscription ID |
| `subscriber_id` | `uuid` | Subscriber ID |
| `plan_id` | `uuid` | Plan ID |
| `starts_at` | `datetime` | Start timestamp |
| `expires_at` | `datetime \| null` | Expiration |
| `rate_limit_per_second` | `integer \| null` | Rate limit override |
| `rate_limit_per_minute` | `integer \| null` | Rate limit override |
| `rate_limit_per_hour` | `integer \| null` | Rate limit override |
| `allowed_endpoints` | `array[string] \| null` | Endpoint override |
| `status` | `string` | Subscription status |
| `created_at` | `datetime` | Creation timestamp |

**Errors:** `404` (subscriber or plan not found).

### GET /subscriptions/{subscription_id}

Retrieve a subscription by ID.

**Auth:** `subscriptions:read`

**Response:** `SubscriptionRead`

### PATCH /subscriptions/{subscription_id}

Modify a subscription.

**Auth:** `subscriptions:write`

**Request Body:** `SubscriptionUpdate` (all fields optional)

| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | `uuid` | Change plan |
| `status` | `string` | Change status |
| `expires_at` | `datetime` | Change expiration |
| `rate_limit_per_second` | `integer` | Rate limit override |
| `rate_limit_per_minute` | `integer` | Rate limit override |
| `rate_limit_per_hour` | `integer` | Rate limit override |
| `allowed_endpoints` | `array[string]` | Endpoint override |

**Response:** `SubscriptionRead`

### DELETE /subscriptions/{subscription_id}

Cancel a subscription. Sets status to `cancelled`.

**Auth:** `subscriptions:delete`

**Response:** `204 No Content`

### POST /subscriptions/bulk

Perform a bulk action on multiple subscriptions.

**Auth:** `subscriptions:write`

**Request Body:** `BulkSubscriptionAction`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `subscription_ids` | `array[uuid]` | Yes | List of subscription IDs |
| `action` | `string` | Yes | One of: `activate`, `suspend`, `cancel` |

**Response:**

```json
{
  "detail": "Bulk activate completed.",
  "updated": 5
}
```

**Error (400):** Invalid action.

### GET /subscriptions/{subscription_id}/usage

Return usage statistics for a subscription. Currently returns rate-limit configuration; full metrics integration is pending.

**Auth:** `subscriptions:read`

**Response:**

```json
{
  "subscription_id": "uuid",
  "status": "active",
  "rate_limits": {
    "per_second": 5,
    "per_minute": 100,
    "per_hour": 3000
  },
  "note": "Usage metrics integration pending."
}
```

---

## RBAC

Prefix: `/rbac`

### Roles

#### GET /rbac/roles

List all defined roles.

**Auth:** `roles:read`

**Response:** `array[RoleRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Role ID |
| `name` | `string` | Role name (max 64) |
| `description` | `string \| null` | Description |
| `permissions` | `object` | Permission map (e.g., `{"subscribers:read": true}`) |
| `created_at` | `datetime` | Creation timestamp |

#### POST /rbac/roles

Create a new role.

**Auth:** `roles:write`

**Request Body:** `RoleCreate`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `string` | Yes | -- | Role name (max 64, must be unique) |
| `description` | `string` | No | `null` | Description |
| `permissions` | `object` | No | `{}` | Permission map |

**Response (201):** `RoleRead`

**Error (409):** Role name already exists.

#### GET /rbac/roles/{role_id}

Get a role by ID.

**Auth:** `roles:read`

**Response:** `RoleRead`

#### PATCH /rbac/roles/{role_id}

Update a role's metadata or permissions.

**Auth:** `roles:write`

**Request Body:** `RoleUpdate` (all fields optional)

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Role name |
| `description` | `string` | Description |
| `permissions` | `object` | Permission map |

**Response:** `RoleRead`

#### DELETE /rbac/roles/{role_id}

Delete a role and cascade-remove all assignments.

**Auth:** `roles:delete`

**Response:** `204 No Content`

### User-Role Assignments

#### POST /rbac/assignments

Assign a role to a user. Invalidates the user's cached permissions.

**Auth:** `roles:write`

**Request Body:** `UserRoleAssign`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | `uuid` | Yes | Target user ID |
| `role_id` | `uuid` | Yes | Role ID to assign |

**Response (201):** `UserRoleRead`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Assignment ID |
| `user_id` | `uuid` | User ID |
| `role_id` | `uuid` | Role ID |
| `assigned_by` | `uuid \| null` | Who made the assignment |
| `assigned_at` | `datetime` | Assignment timestamp |

**Errors:** `404` (user or role not found), `409` (already assigned).

#### DELETE /rbac/assignments/{user_id}/{role_id}

Revoke a role from a user. Invalidates the user's cached permissions.

**Auth:** `roles:write`

**Response:** `204 No Content`

### User Queries

#### GET /rbac/users/{user_id}/roles

List roles assigned to a specific user.

**Auth:** `roles:read`

**Response:** `array[RoleRead]`

#### GET /rbac/users

List all users with their assigned role names. Intended for the admin assignment UI.

**Auth:** `users:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number |
| `page_size` | `integer` | `50` | Items per page (1-200) |
| `search` | `string` | `null` | Search by name or email |

**Response:** `PaginatedResponse` with items containing:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | User ID |
| `email` | `string` | Email |
| `name` | `string` | Display name |
| `entra_oid` | `string` | Entra ID object ID |
| `created_at` | `string \| null` | ISO creation timestamp |
| `last_login` | `string \| null` | ISO last login timestamp |
| `role_names` | `array[string]` | List of assigned role names |

### Permissions

#### GET /rbac/permissions

Return the complete permission catalogue derived from the default role definitions.

**Auth:** `roles:read`

**Response:**

```json
{
  "permissions": [
    "ai:analyze",
    "ai:documentation",
    "api_keys:read",
    "api_keys:write",
    "audit:read",
    "gateway:read",
    "roles:read",
    "subscribers:read",
    "..."
  ]
}
```

### Audit Log

#### GET /rbac/audit

Query the audit log with optional filters and pagination.

**Auth:** `audit:read`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number |
| `page_size` | `integer` | `50` | Items per page (1-200) |
| `user_id` | `uuid` | `null` | Filter by acting user |
| `action` | `string` | `null` | Filter by action (e.g., `create`, `update`, `delete`) |
| `resource_type` | `string` | `null` | Filter by resource type (e.g., `subscriber`, `api_key`, `role`) |

**Response:** `PaginatedResponse` with `AuditLogRead` items.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Log entry ID |
| `user_id` | `uuid \| null` | Acting user ID |
| `action` | `string` | Action performed |
| `resource_type` | `string` | Type of resource affected |
| `resource_id` | `string \| null` | Affected resource ID |
| `details` | `object \| null` | Additional details |
| `ip_address` | `string \| null` | Client IP address |
| `created_at` | `datetime` | Timestamp |

---

## Gateway (Kong)

Prefix: `/gateway`

Proxy endpoints to the Kong Admin API for managing services, routes, plugins, and consumers.

### Services

#### GET /gateway/services

List all services registered in Kong.

**Auth:** `gateway:read`

**Response:** `array[KongServiceRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Kong service ID |
| `name` | `string \| null` | Service name |
| `host` | `string` | Upstream host |
| `port` | `integer` | Upstream port |
| `protocol` | `string` | Protocol (http, https, grpc, etc.) |
| `path` | `string \| null` | Upstream path |
| `enabled` | `boolean` | Whether the service is enabled |

#### GET /gateway/services/{service_id}

Get a specific Kong service.

**Auth:** `gateway:read`

**Response:** `KongServiceRead`

### Routes

#### GET /gateway/routes

List all routes registered in Kong.

**Auth:** `gateway:read`

**Response:** `array[KongRouteRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Kong route ID |
| `name` | `string \| null` | Route name |
| `protocols` | `array[string]` | Protocols (http, https, etc.) |
| `hosts` | `array[string] \| null` | Matched hostnames |
| `paths` | `array[string] \| null` | Matched paths |
| `methods` | `array[string] \| null` | Matched HTTP methods |

#### GET /gateway/routes/{route_id}

Get a specific Kong route.

**Auth:** `gateway:read`

**Response:** `KongRouteRead`

### Plugins

#### GET /gateway/plugins

List all plugins registered in Kong.

**Auth:** `gateway:read`

**Response:** `array[KongPluginRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Plugin ID |
| `name` | `string` | Plugin name (e.g., `rate-limiting`, `key-auth`) |
| `service` | `object \| null` | Associated service reference |
| `route` | `object \| null` | Associated route reference |
| `consumer` | `object \| null` | Associated consumer reference |
| `config` | `object` | Plugin configuration |
| `enabled` | `boolean` | Whether the plugin is enabled |

#### POST /gateway/plugins

Add a new plugin to Kong.

**Auth:** `gateway:write`

**Request Body:** Free-form JSON dict matching the Kong plugin schema. At minimum:

```json
{
  "name": "rate-limiting",
  "service": {"id": "..."},
  "config": {
    "minute": 100
  }
}
```

**Response (201):** `KongPluginRead`

#### PATCH /gateway/plugins/{plugin_id}

Update plugin configuration.

**Auth:** `gateway:write`

**Request Body:** Free-form JSON dict with fields to update.

**Response:** `KongPluginRead`

#### DELETE /gateway/plugins/{plugin_id}

Remove a plugin from Kong.

**Auth:** `gateway:write`

**Response:** `204 No Content`

### Consumers

#### GET /gateway/consumers

List all consumers in Kong.

**Auth:** `gateway:read`

**Response:** `array[KongConsumerRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Consumer ID |
| `username` | `string \| null` | Username |
| `custom_id` | `string \| null` | Custom identifier |

#### GET /gateway/consumers/{consumer_id}

Get a specific Kong consumer.

**Auth:** `gateway:read`

**Response:** `KongConsumerRead`

#### POST /gateway/consumers

Create a new consumer in Kong.

**Auth:** `gateway:write`

**Request Body:** Free-form JSON dict:

```json
{
  "username": "my-consumer",
  "custom_id": "user@example.com"
}
```

**Response (201):** `KongConsumerRead`

#### DELETE /gateway/consumers/{consumer_id}

Remove a consumer from Kong.

**Auth:** `gateway:write`

**Response:** `204 No Content`

### Gateway Health

#### GET /gateway/health

Return Kong node status and database connectivity info.

**Auth:** `gateway:read`

**Response:** `KongHealthResponse`

| Field | Type | Description |
|-------|------|-------------|
| `database` | `object` | Database connectivity status from Kong |
| `server` | `object` | Server status from Kong |

---

## AI

Prefix: `/ai`

AI-powered gateway features including anomaly detection, smart routing, request/response transformation, and documentation generation. These endpoints require the AI provider (e.g., Claude) to be configured and available. Returns `503` if the AI provider is not configured or reachable.

### POST /ai/analyze

Analyze a single request for anomalous behavior.

**Auth:** `ai:analyze`

**Request Body:** `AnalyzeRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_data` | `RequestData` | Yes | HTTP request data to analyze |
| `metrics` | `RequestMetrics` | No | Accompanying traffic metrics |
| `baseline` | `BaselineProfile` | No | Baseline behavioral profile for comparison |

`RequestData` fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `method` | `string` | Yes | HTTP method |
| `path` | `string` | Yes | Request path |
| `headers` | `object` | No | Request headers |
| `query_params` | `object` | No | Query parameters |
| `body` | `any` | No | Request body |
| `source_ip` | `string` | No | Client IP |
| `timestamp` | `datetime` | No | Request timestamp |
| `consumer_id` | `string` | No | Consumer identifier |

`RequestMetrics` fields:

| Field | Type | Description |
|-------|------|-------------|
| `request_rate` | `float` | Current request rate |
| `avg_latency_ms` | `float` | Average latency in ms |
| `error_rate` | `float` | Error rate |
| `payload_size_bytes` | `integer` | Payload size |
| `unique_endpoints_hit` | `integer` | Unique endpoints hit |
| `requests_last_minute` | `integer` | Requests in the last minute |
| `requests_last_hour` | `integer` | Requests in the last hour |

`BaselineProfile` fields:

| Field | Type | Description |
|-------|------|-------------|
| `avg_request_rate` | `float` | Baseline request rate |
| `avg_latency_ms` | `float` | Baseline average latency |
| `typical_error_rate` | `float` | Baseline error rate |
| `common_paths` | `array[string]` | Commonly accessed paths |
| `common_methods` | `array[string]` | Commonly used HTTP methods |
| `typical_payload_size` | `integer` | Typical payload size in bytes |

**Response:** `AnomalyDetectionResult`

| Field | Type | Description |
|-------|------|-------------|
| `analysis_id` | `string (uuid)` | Unique analysis ID |
| `anomaly_score` | `float` | Score from 0.0 to 1.0 |
| `is_anomalous` | `boolean` | Whether the request is anomalous |
| `reasons` | `array[string]` | Reasons for the classification |
| `recommended_action` | `string` | `allow`, `warn`, or `block` |
| `details` | `object` | Additional details |
| `analyzed_at` | `datetime` | Analysis timestamp |

### POST /ai/anomaly/batch

Batch-analyze multiple requests for anomalies using parallel processing.

**Auth:** `ai:analyze`

**Request Body:** `BatchAnalyzeRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `requests` | `array[AnalyzeRequest]` | Yes | List of requests to analyze |

**Response:** `array[AnomalyDetectionResult]` -- results in the same order as input. Individual failures return a safe default result (score 0.0, not anomalous) rather than failing the entire batch.

### POST /ai/rate-limit/suggest

Get AI-suggested rate limits for a consumer based on usage history.

**Auth:** `ai:rate-limit`

**Request Body:** `RateLimitSuggestRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `consumer_id` | `string` | Yes | Consumer identifier |
| `usage_history` | `array[object]` | Yes | Usage records with timestamp, count, endpoint, etc. |
| `current_limits` | `object` | No | Current rate limits, e.g., `{"second": 5, "minute": 100}` |

**Response:** `RateLimitSuggestion`

| Field | Type | Description |
|-------|------|-------------|
| `consumer_id` | `string` | Consumer ID |
| `suggested_limits` | `object` | e.g., `{"second": 10, "minute": 200, "hour": 5000}` |
| `reasoning` | `string` | Explanation of the suggestion |
| `confidence` | `float` | Confidence score (0.0 to 1.0) |
| `based_on_samples` | `integer` | Number of samples analyzed |

### POST /ai/route

Get a smart routing decision. Given a request, available backends, and health data, the AI selects the optimal backend.

**Auth:** `ai:route`

**Request Body:** `RouteRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_data` | `RequestData` | Yes | The incoming request |
| `available_backends` | `array[BackendInfo]` | Yes | Available backend services |
| `backend_health` | `array[BackendHealth]` | No | Health data for each backend |

`BackendInfo` fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Backend name |
| `url` | `string` | Backend URL |
| `weight` | `float` | Routing weight (default 1.0) |
| `region` | `string` | Deployment region |
| `capabilities` | `array[string]` | Backend capabilities |

`BackendHealth` fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Backend name |
| `healthy` | `boolean` | Whether the backend is healthy |
| `latency_ms` | `float` | Current latency |
| `error_rate` | `float` | Current error rate |
| `active_connections` | `integer` | Active connection count |
| `cpu_usage` | `float` | CPU usage percentage |

**Response:** `RoutingDecision`

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | `string (uuid)` | Decision ID |
| `selected_backend` | `string` | Chosen backend name |
| `reasoning` | `string` | Explanation |
| `confidence` | `float` | Confidence score (0.0 to 1.0) |
| `fallback_backend` | `string \| null` | Fallback if primary fails |
| `headers_to_add` | `object` | Headers to inject into the proxied request |

### POST /ai/transform/request

Transform a request body using AI-powered natural-language rules.

**Auth:** `ai:transform`

**Request Body:** `TransformRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | `any` | Yes | The request body to transform |
| `content_type` | `string` | No | MIME type (default `application/json`) |
| `transformation_rules` | `string` | Yes | Natural-language description of the transformation |
| `context` | `object` | No | Extra context (consumer info, route metadata) |

**Response:** `TransformResult`

| Field | Type | Description |
|-------|------|-------------|
| `transform_id` | `string (uuid)` | Transform ID |
| `transformed_body` | `any` | The transformed body |
| `content_type` | `string` | Output MIME type |
| `changes_summary` | `string` | Summary of changes made |
| `tokens_used` | `integer` | AI tokens consumed |

### POST /ai/transform/response

Transform a response body using AI-powered natural-language rules. Same request/response schema as `/ai/transform/request`.

**Auth:** `ai:transform`

### POST /ai/documentation/generate

Auto-generate API documentation from an OpenAPI spec and/or traffic samples.

**Auth:** `ai:documentation`

**Request Body:** `DocumentationRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `openapi_spec` | `object` | No* | Existing OpenAPI spec to enhance |
| `traffic_samples` | `array[TrafficSample]` | No* | Observed request/response pairs |
| `title` | `string` | No | Documentation title |
| `description` | `string` | No | Documentation description |

*At least one of `openapi_spec` or `traffic_samples` must be provided (422 otherwise).

`TrafficSample` fields:

| Field | Type | Description |
|-------|------|-------------|
| `request` | `RequestData` | The request data |
| `response_status` | `integer` | HTTP response status code |
| `response_headers` | `object` | Response headers |
| `response_body` | `any` | Response body |

**Response:** `DocumentationResult`

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | `string (uuid)` | Document ID |
| `markdown` | `string` | Generated markdown documentation |
| `openapi_spec` | `object \| null` | Generated/enhanced OpenAPI spec |
| `endpoints_documented` | `integer` | Number of endpoints documented |
| `tokens_used` | `integer` | AI tokens consumed |

### GET /ai/health

Check AI provider health and status.

**Auth:** None

**Response:** `AIHealthResponse`

| Field | Type | Description |
|-------|------|-------------|
| `provider` | `string` | AI provider name |
| `model` | `string` | Model identifier |
| `available` | `boolean` | Whether the AI provider is available |
| `latency_ms` | `float \| null` | Provider latency |
| `total_requests` | `integer` | Total requests made |
| `total_tokens` | `integer` | Total tokens consumed |
| `estimated_cost_usd` | `float` | Estimated cost in USD |
| `capabilities` | `array[string]` | Available capabilities |

### GET /ai/config

Return the current AI configuration.

**Auth:** `ai:read`

**Response:** `AIConfigResponse`

| Field | Type | Description |
|-------|------|-------------|
| `provider` | `string` | Provider name |
| `model` | `string` | Model identifier |
| `capabilities` | `array[string]` | Available capabilities |
| `max_tokens` | `integer` | Max tokens per request |
| `temperature` | `float` | Model temperature |
| `rate_limit_rpm` | `integer \| null` | Requests per minute limit |

### AI Prompt Management

CRUD endpoints for managing AI prompt templates used by the various AI features.

#### GET /ai/prompts

List all AI prompt templates, optionally filtered by category.

**Auth:** None (unauthenticated)

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category` | `string` | `null` | Filter by category (e.g., `anomaly`, `rate_limit`, `routing`, `transform`, `documentation`) |

**Response:** `array[AIPromptRead]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `uuid` | Prompt ID |
| `slug` | `string` | URL-safe unique identifier (max 100) |
| `name` | `string` | Display name (max 255) |
| `category` | `string` | Category |
| `system_prompt` | `string` | System prompt template text |
| `model` | `string \| null` | Optional model override |
| `temperature` | `float` | Temperature (0.0 to 2.0) |
| `max_tokens` | `integer` | Max tokens (1 to 128000) |
| `is_active` | `boolean` | Whether the prompt is active |
| `version` | `integer` | Version number (auto-incremented on update) |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

#### GET /ai/prompts/{prompt_id}

Get a single prompt by ID.

**Auth:** None (unauthenticated)

**Response:** `AIPromptRead`

#### POST /ai/prompts

Create a new prompt template.

**Auth:** `ai:analyze`

**Request Body:** `AIPromptCreate`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `slug` | `string` | Yes | -- | URL-safe identifier (max 100, must be unique) |
| `name` | `string` | Yes | -- | Display name (max 255) |
| `category` | `string` | Yes | -- | Category |
| `system_prompt` | `string` | Yes | -- | Prompt template text |
| `model` | `string` | No | `null` | Model override (max 100) |
| `temperature` | `float` | No | `0.3` | Temperature (0.0 to 2.0) |
| `max_tokens` | `integer` | No | `4096` | Max tokens (1 to 128000) |
| `is_active` | `boolean` | No | `true` | Active status |

**Response (201):** `AIPromptRead`

**Error (409):** Prompt with the given slug already exists.

#### PUT /ai/prompts/{prompt_id}

Update an existing prompt template. Automatically increments the version number.

**Auth:** `ai:analyze`

**Request Body:** `AIPromptUpdate` (all fields optional)

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Display name (max 255) |
| `system_prompt` | `string` | Prompt template text |
| `model` | `string` | Model override (max 100) |
| `temperature` | `float` | Temperature (0.0 to 2.0) |
| `max_tokens` | `integer` | Max tokens (1 to 128000) |
| `is_active` | `boolean` | Active status |

**Response:** `AIPromptRead`

#### DELETE /ai/prompts/{prompt_id}

Delete a prompt template.

**Auth:** `ai:analyze`

**Response:** `204 No Content`

---

## Permission Reference

The following permissions are used across the API. Roles are configured via the RBAC system and map to these permissions.

| Permission | Used By |
|------------|---------|
| `subscribers:read` | List/get subscribers |
| `subscribers:write` | Create/update subscribers, set rate limits |
| `subscribers:delete` | Delete subscribers |
| `api_keys:read` | List API keys |
| `api_keys:write` | Create/rotate API keys |
| `api_keys:delete` | Revoke API keys |
| `subscriptions:read` | List/get plans and subscriptions, view usage |
| `subscriptions:write` | Create/update plans and subscriptions, bulk actions |
| `subscriptions:delete` | Delete plans, cancel subscriptions |
| `teams:read` | List/get teams and members |
| `teams:write` | Create/update teams, manage members |
| `teams:delete` | Delete teams |
| `api_registry:read` | List/get API registrations, view usage |
| `api_registry:write` | Create/update/submit API registrations |
| `api_registry:delete` | Delete API registrations |
| `api_registry:approve` | Review, activate, change status of API registrations |
| `roles:read` | List roles, view permissions |
| `roles:write` | Create/update roles, assign/revoke user roles |
| `roles:delete` | Delete roles |
| `users:read` | List users (admin UI) |
| `audit:read` | View audit logs |
| `gateway:read` | List Kong services, routes, plugins, consumers, health |
| `gateway:write` | Create/update/delete Kong plugins, consumers |
| `ai:analyze` | Anomaly detection, batch analysis, manage AI prompts |
| `ai:rate-limit` | AI rate-limit suggestions |
| `ai:route` | AI smart routing |
| `ai:transform` | AI request/response transformation |
| `ai:documentation` | AI documentation generation |
| `ai:read` | View AI configuration |

---

## Audit Logging

All write operations (create, update, delete, status changes, role assignments) are automatically recorded in the audit log with:

- Acting user ID
- Action type (e.g., `create`, `update`, `delete`, `rotate`, `assign_role`, `bulk_activate`)
- Resource type and ID
- Request details (JSON payload)
- Client IP address
- Timestamp

Query the audit log via `GET /rbac/audit`.
