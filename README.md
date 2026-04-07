# API Gateway

A centralized API Gateway built on Kong CE with an AI-powered intelligence layer using Claude (Anthropic). Features multi-authentication (OAuth2, API Key, Basic Auth), subscription management, and a FastAPI admin panel with OIDC via Entra ID and database-driven RBAC. The AI layer provides real-time anomaly detection, intelligent rate limiting, smart routing, request/response transformation, and auto-documentation generation. Deployed on Azure Kubernetes Service (AKS) with Terraform-managed infrastructure, horizontal autoscaling via HPA/KEDA, and full observability through Prometheus, Grafana, and Cribl Stream.

## Architecture Overview

```
                         Internet
                            |
                      [Azure LB / Ingress]
                            |
                   +--------+--------+
                   |                 |
              [Kong Gateway]   [Admin Panel]
                   |                 |
            [AI Gateway Plugin] [AI Provider Layer]
                   |                 |
                   +---[ Claude ]----+
                   |    (Anthropic / Azure AI Foundry)
                   |
              +--------+--------+
              |        |        |
         [PostgreSQL] [Redis]  [Monitoring]
                                    |
                          +---------+---------+
                          |         |         |
                    [Prometheus] [Grafana] [Cribl]
```

**Components:**

| Component | Purpose |
|---|---|
| **Kong Gateway** | API proxy with multi-auth (OAuth2, API Key, Basic Auth), rate limiting, request transformation |
| **AI Gateway Plugin** | Kong Lua plugin that invokes Claude for real-time anomaly detection, smart routing, and request/response transformation |
| **AI Provider Layer** | Async Python layer using Anthropic SDK (`AsyncAnthropic`) with DOE self-annealing, failover, and cost tracking |
| **Admin Panel** | FastAPI app with OIDC (Entra ID), database-driven RBAC, subscriber management, and AI management endpoints |
| **PostgreSQL 16** | Primary datastore for Kong, admin panel, and AI analysis results (separate databases) |
| **Redis 7** | Rate limiting backend, session cache, RBAC permission cache, and AI result caching |
| **Prometheus** | Metrics collection from Kong, admin panel, and AI layer |
| **Grafana** | 5 dashboards: gateway overview, authentication, rate limiting, infrastructure, and AI layer |
| **Cribl Stream** | Log routing with 4 pipelines: Kong logs, auth events, rate limit metrics, and AI events |

## Prerequisites

- **Docker** >= 24.0 with Docker Compose v2
- **Terraform** >= 1.7 (for infrastructure management)
- **kubectl** (for Kubernetes deployments)
- **Azure CLI** (for AKS access)
- **Python 3.12** (for admin panel development)

## Local Development Setup

### Quick Start

```bash
# Clone the repository
git clone <repo-url> && cd api-gateway

# Run the setup script (handles everything)
./scripts/setup-local.sh
```

The setup script will:
1. Check prerequisites
2. Create `.env` from `.env.example` with generated secrets
3. Build and start all Docker Compose services
4. Wait for health checks to pass
5. Seed default admin user
6. Print access URLs

### Manual Setup

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your preferred values

# Start services
docker compose up -d

# Check service health
docker compose ps

# View logs
docker compose logs -f kong
docker compose logs -f admin-panel
```

### Service URLs (Local)

| Service | URL |
|---|---|
| Kong Proxy | http://localhost:8000 |
| Kong Admin API | http://localhost:8001 |
| Admin Panel | http://localhost:8080 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| Cribl Stream | http://localhost:9420 |

### Default Credentials

| Service | Username | Password |
|---|---|---|
| Admin Panel | admin@localhost | admin |
| Grafana | admin | admin |

Change these immediately after first login.

### Reset Environment

```bash
# Destroy all data and start fresh
./scripts/setup-local.sh --reset
```

## Authentication Methods

The API Gateway supports multiple authentication methods, configured per-route in Kong.

### API Key Authentication

Subscribers receive API keys through the admin panel. Keys are passed via header:

```bash
curl -H "X-API-Key: your-api-key-here" https://api-gateway.example.com/api/v1/resource
```

### JWT Authentication

For service-to-service communication:

```bash
curl -H "Authorization: Bearer <jwt-token>" https://api-gateway.example.com/api/v1/resource
```

### OAuth 2.0

For third-party integrations (configured per-route):

```bash
curl -H "Authorization: Bearer <oauth-access-token>" https://api-gateway.example.com/api/v1/resource
```

## AI-Powered Intelligence Layer

The gateway includes a Claude-powered AI layer that provides real-time intelligence capabilities inline with the request pipeline. The AI layer supports both **Azure AI Foundry** (default) and **direct Anthropic API** as providers.

### AI Capabilities

| Capability | Description | Kong Plugin Phase |
|---|---|---|
| **Anomaly Detection** | Analyzes request patterns and metrics against historical baselines. Returns anomaly score (0-1) with recommended action (allow/throttle/block/alert). | `access` |
| **Intelligent Rate Limiting** | Suggests optimal per-consumer rate limits based on usage history, traffic patterns, and subscription tier. | API endpoint |
| **Smart Routing** | Selects the optimal backend based on request content, backend health, latency, and capacity. | `access` |
| **Request Transformation** | Transforms request bodies using natural language rules (e.g., "convert XML to JSON", "add correlation headers"). | `access` |
| **Response Transformation** | Transforms response bodies before returning to the client. | `body_filter` |
| **Auto-Documentation** | Generates API documentation from OpenAPI specs or captured traffic samples. | API endpoint |

### Architecture

```
Client Request
      |
  [Kong Gateway]
      |
  [ai-gateway plugin]  ──sampling rate (default 10%)──>  [Admin Panel AI API]
      |                                                          |
      |                                                   [AI Provider Layer]
      |                                                          |
      |                                              ┌───────────┴───────────┐
      |                                              |                       |
      |                                    [Anthropic Foundry]     [Direct Anthropic]
      |                                    (Azure AI endpoint)     (api.anthropic.com)
      |                                              |                       |
      |                                              └───────────┬───────────┘
      |                                                          |
      |  <──── anomaly score, routing decision, transforms ──────┘
      |
  [Upstream Service]
```

### AI Provider Configuration

The AI layer defaults to **Azure AI Foundry** (`anthropic_foundry`). A single `ANTHROPIC_API_KEY` works for both providers.

| Variable | Description | Default |
|---|---|---|
| `AI_PROVIDER` | Provider selection | `anthropic_foundry` |
| `ANTHROPIC_API_KEY` | API key (used by both providers) | — |
| `AZURE_AI_FOUNDRY_ENDPOINT` | Azure AI Foundry endpoint URL | — |
| `AZURE_AI_FOUNDRY_API_KEY` | Optional separate foundry key (falls back to `ANTHROPIC_API_KEY`) | — |
| `ANTHROPIC_MODEL` | Model/deployment name | `cogdep-aifoundry-dev-eus2-claude-sonnet-4-5` |
| `AI_MAX_COST_PER_ANALYSIS` | Budget ceiling per analysis (USD) | `0.50` |
| `AI_SAMPLING_RATE` | Fraction of requests analyzed (0.0-1.0) | `0.1` |

**Azure AI Foundry (default):**

```bash
AI_PROVIDER=anthropic_foundry
ANTHROPIC_API_KEY=your-api-key
AZURE_AI_FOUNDRY_ENDPOINT=https://your-endpoint.services.ai.azure.com
ANTHROPIC_MODEL=cogdep-aifoundry-dev-eus2-claude-sonnet-4-5
```

**Direct Anthropic API:**

```bash
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-your-key
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

### AI API Endpoints

All AI endpoints require authentication and RBAC permissions (`ai:*`).

```bash
# Detect anomalies in a request
curl -X POST http://localhost:8080/ai/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_data": {"method": "POST", "path": "/api/v1/users", "headers": {}, "body": {}},
    "metrics": {"request_rate": 150, "error_rate": 0.05, "avg_latency_ms": 200},
    "baseline": {"avg_request_rate": 50, "avg_error_rate": 0.01}
  }'

# Get AI-suggested rate limits for a consumer
curl -X POST http://localhost:8080/ai/rate-limit/suggest \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "consumer_id": "acme-corp",
    "usage_history": [{"hour": "2024-01-01T00:00:00Z", "requests": 1200}],
    "current_limits": {"per_second": 10, "per_minute": 200, "per_hour": 5000}
  }'

# Get smart routing decision
curl -X POST http://localhost:8080/ai/route \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "request": {"method": "GET", "path": "/api/v1/search", "query": "complex query"},
    "available_backends": [{"name": "primary", "url": "http://api-1:8080"}, {"name": "secondary", "url": "http://api-2:8080"}],
    "backend_health": {"primary": {"healthy": true, "latency_ms": 50}, "secondary": {"healthy": true, "latency_ms": 200}}
  }'

# Transform a request body using natural language rules
curl -X POST http://localhost:8080/ai/transform/request \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {"user_name": "John", "user_email": "john@example.com"},
    "transformation_rules": [{"rule": "Convert snake_case keys to camelCase"}, {"rule": "Add a timestamp field"}]
  }'

# Auto-generate API documentation from traffic samples
curl -X POST http://localhost:8080/ai/documentation/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "traffic_samples": [
      {"request": {"method": "GET", "path": "/api/v1/users"}, "response": {"status": 200, "body": [{"id": 1, "name": "Alice"}]}},
      {"request": {"method": "POST", "path": "/api/v1/users", "body": {"name": "Bob"}}, "response": {"status": 201}}
    ]
  }'

# Batch analyze multiple requests
curl -X POST http://localhost:8080/ai/anomaly/batch \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"requests": [...]}'

# Check AI layer health
curl http://localhost:8080/ai/health

# View AI configuration
curl -H "Authorization: Bearer <token>" http://localhost:8080/ai/config
```

### Kong AI Gateway Plugin

The `ai-gateway` Kong plugin runs inline with the request pipeline. Configuration per-service or per-route:

```bash
# Enable AI gateway plugin on a service
curl -X POST http://localhost:8001/services/my-service/plugins \
  -d "name=ai-gateway" \
  -d "config.enable_anomaly_detection=true" \
  -d "config.enable_smart_routing=false" \
  -d "config.anomaly_threshold=0.7" \
  -d "config.sampling_rate=0.1" \
  -d "config.fail_open=true" \
  -d "config.timeout=5000"
```

| Config | Type | Default | Description |
|---|---|---|---|
| `enable_anomaly_detection` | boolean | `true` | Analyze requests for anomalies |
| `enable_smart_routing` | boolean | `false` | AI-driven backend selection |
| `enable_request_transform` | boolean | `false` | AI-powered request transformation |
| `enable_response_transform` | boolean | `false` | AI-powered response transformation |
| `anomaly_threshold` | number | `0.7` | Score above which to take action (0-1) |
| `sampling_rate` | number | `0.1` | Fraction of requests to analyze |
| `fail_open` | boolean | `true` | Allow requests through if AI is unavailable |
| `timeout` | integer | `5000` | AI endpoint timeout in ms |
| `cache_ttl` | integer | `60` | Cache AI results for this many seconds |

**Response headers added by the plugin:**

- `X-AI-Anomaly-Score` -- Anomaly score (0-1) when anomaly detection is active
- `X-AI-Route-Decision` -- Selected backend when smart routing is active
- `X-AI-Analysis-Id` -- Unique ID for the AI analysis (for debugging)
- `X-AI-Status` -- `available` or `unavailable` (when AI endpoint is down and fail_open=true)

### AI Resilience Features

- **DOE Self-Annealing** -- Automatically detects and corrects invalid model configurations at runtime
- **Exponential Backoff** -- Retries rate-limited requests with 5s/10s/20s delays
- **Failover Provider** -- Optional wrapping with automatic failover to a secondary provider
- **Fail-Open** -- When AI is unavailable, requests pass through with `X-AI-Status: unavailable`
- **Sampling** -- Only analyzes a configurable fraction of requests (default 10%) to control costs
- **Cost Budget** -- Per-analysis cost ceiling ($0.50 default) prevents runaway spending
- **PII Masking** -- Sensitive data is masked before sending to AI and unmasked in responses

### AI RBAC Permissions

| Permission | Roles | Description |
|---|---|---|
| `ai:read` | all roles | View AI config and health |
| `ai:analyze` | super_admin, admin, operator | Run anomaly detection |
| `ai:rate-limit` | super_admin, admin, operator | Get rate limit suggestions |
| `ai:route` | super_admin, admin | Get routing decisions |
| `ai:transform` | super_admin, admin | Run request/response transforms |
| `ai:documentation` | super_admin, admin | Generate API documentation |

### AI Monitoring

The AI layer has its own Grafana dashboard (**AI Layer**) and Prometheus metrics:

| Metric | Description |
|---|---|
| `ai_gateway_analyses_total` | Total AI analyses by type, provider, model |
| `ai_gateway_anomaly_score` | Anomaly score distribution |
| `ai_gateway_latency_ms` | AI analysis latency |
| `ai_gateway_cost_usd_total` | Cumulative AI cost in USD |
| `ai_gateway_tokens_total` | Token usage (input/output) |

**AI-specific alerts:**
- `AIProviderDown` -- AI endpoint returning errors for > 5 min
- `AIHighLatency` -- AI analysis p99 > 3s
- `AIAnomalySpike` -- Anomaly detection rate > 10/min
- `AICostBudgetWarning` -- Hourly AI cost > $5
- `AICostBudgetCritical` -- Hourly AI cost > $20

### AI Database Tables

| Table | Purpose |
|---|---|
| `ai_analyses` | Cached analysis results with cost/token tracking |
| `ai_anomaly_events` | Anomaly event log with scores and actions |
| `ai_rate_limit_suggestions` | AI rate limit suggestion history (applied/ignored) |
| `ai_documentation` | Auto-generated documentation versions |
| `ai_prompts` | Managed prompt templates (3-tier resolution: Redis -> DB -> seed) |

## Subscription Management

### Plans

Four default plans with configurable rate limits:

| Plan | Req/sec | Req/min | Req/day | Monthly Quota |
|---|---|---|---|---|
| Free | 5 | 100 | 10,000 | 100,000 |
| Standard | 25 | 500 | 100,000 | 2,000,000 |
| Premium | 100 | 2,000 | 500,000 | 10,000,000 |
| Enterprise | 500 | 10,000 | 2,000,000 | 50,000,000 |

### Managing Subscribers

Use the Admin Panel API:

```bash
# Create a subscriber
curl -X POST http://localhost:8080/api/v1/subscribers \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "email": "api@acme.com", "organization": "Acme"}'

# Create a subscription (assign a plan)
curl -X POST http://localhost:8080/api/v1/subscriptions \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"subscriber_id": "<id>", "plan_id": "<plan-id>"}'

# Generate an API key
curl -X POST http://localhost:8080/api/v1/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"subscriber_id": "<id>", "name": "Production Key"}'
```

### Data Contracts

Registered APIs support formal data contracts that define operational commitments:

- **Contacts** -- Primary and escalation emails, Slack channels, PagerDuty service keys
- **SLA targets** -- Uptime (e.g. 99.95%), latency percentiles (P50/P95/P99), error budgets, support hours
- **Change management** -- Deprecation notice days, breaking change policy (semver, date-based, never-break), versioning scheme
- **Schema** -- OpenAPI spec URL, max request/response size

Contracts can be updated on active APIs without re-approval via `PATCH /api-registry/{id}/contract`. The `max_request_size_kb` field is enforced in Kong via the `request-size-limiting` plugin.

### Public API Catalog

Subscribers can discover available APIs and their contracts via the unauthenticated public catalog:

```bash
# List all active APIs
curl http://localhost:8880/public/api-catalog

# Search by name
curl http://localhost:8880/public/api-catalog?search=weather

# View a specific API's contract
curl http://localhost:8880/public/api-catalog/weather-forecast-api
```

### Kong Sync

Changes in the admin panel are automatically synced to Kong via database notification triggers. For manual sync:

```bash
# Sync all subscribers
./scripts/kong-sync.sh

# Sync a specific subscriber
./scripts/kong-sync.sh --subscriber <uuid>

# Check sync status
./scripts/kong-sync.sh --status

# Dry run (show what would change)
./scripts/kong-sync.sh --dry-run
```

## Deployment

### Pipeline Overview

```
Push to branch  -->  CI Pipeline (lint, test, security scan, build)
                          |
PR to main      -->  PR Gate (all checks must pass, CODEOWNERS approval)
                          |
Merge to main   -->  Deploy Pipeline:
                          |
                     dev (auto) --> staging (auto) --> prod (manual approval)
```

### Environments

| Environment | Trigger | Approval |
|---|---|---|
| Dev | Auto on merge to main | None |
| Staging | Auto after dev succeeds | None |
| Production | After staging succeeds | Manual (infra-team) |

Each deployment runs smoke tests and automatically rolls back on failure.

### Manual Deployment

```bash
# Plan infrastructure changes
cd terraform/environments/dev
terraform init
terraform plan

# Apply infrastructure
terraform apply

# Deploy to Kubernetes
kubectl apply -f k8s/overlays/dev/
```

### Rollback

```bash
# Rollback Kubernetes deployment
kubectl rollout undo deployment/kong-gateway -n api-gateway
kubectl rollout undo deployment/admin-panel -n api-gateway

# Verify rollback
kubectl rollout status deployment/kong-gateway -n api-gateway
```

## Monitoring

### Prometheus Metrics

Kong exposes metrics at `:8100/metrics`. Key metrics:

- `kong_http_requests_total` - Total HTTP requests by service, route, status
- `kong_request_latency_ms` - Request latency histogram
- `kong_bandwidth_bytes` - Bandwidth by direction (ingress/egress)
- `kong_upstream_target_health` - Upstream target health status

### Grafana Dashboards

Pre-provisioned dashboards are available at http://localhost:3000:

- **Gateway Overview** -- Traffic, latency, error rates, active consumers
- **Authentication** -- Auth success/failure by method, suspicious activity
- **Rate Limiting** -- Rate limit violations by consumer/tier, rejection rates
- **Infrastructure** -- Pod CPU/memory, HPA status, database/Redis health
- **AI Layer** -- AI analysis rates, anomaly detection, cost tracking, latency

### Alerting

Prometheus alerting rules are defined in `monitoring/prometheus/alerts.yml`. Alerts are routed through Grafana notification channels.

Key alerts:
- High error rate (>5% 5xx responses)
- High latency (p99 > 5s)
- Rate limiting threshold reached
- Upstream service down
- Database connection pool exhaustion

### Log Management

Cribl Stream collects logs from all services and routes them to configured destinations. Access the Cribl UI at http://localhost:9420 to configure log pipelines, filtering, and forwarding.

### Azure Monitor Equivalence

For teams currently using Azure Monitor (Application Insights, Log Analytics, Azure Alerts, Workbooks) with APIM, the observability stack in this platform provides equivalent or better capabilities at no additional licensing cost. See [Observability Comparison](docs/observability-comparison.md) for a detailed feature-by-feature mapping.

## Troubleshooting

### Kong not starting

```bash
# Check Kong logs
docker compose logs kong

# Verify database migrations ran
docker compose logs kong-migrations

# Re-run migrations
docker compose run --rm kong-migrations kong migrations bootstrap
docker compose run --rm kong-migrations kong migrations up
```

### Admin panel cannot connect to database

```bash
# Verify PostgreSQL is running
docker compose ps postgres

# Test database connection
docker compose exec postgres psql -U postgres -d api_gateway_admin -c "SELECT 1"

# Check admin panel logs
docker compose logs admin-panel
```

### Kong sync failures

```bash
# Check sync status
./scripts/kong-sync.sh --status

# Run sync with verbose output
./scripts/kong-sync.sh --dry-run

# Verify Kong Admin API is accessible
curl http://localhost:8001/status
```

### Rate limiting not working

```bash
# Check consumer plugins in Kong
curl http://localhost:8001/consumers/<consumer-id>/plugins

# Verify Redis connectivity
docker compose exec redis redis-cli -a "${REDIS_PASSWORD}" ping

# Check rate-limiting plugin is enabled globally
curl http://localhost:8001/plugins | python3 -m json.tool
```

### Resetting everything

```bash
# Nuclear option: destroy everything and start fresh
./scripts/setup-local.sh --reset
```

## Project Structure

```
api-gateway/
├── .github/
│   ├── CODEOWNERS                    # Required reviewers by path
│   └── workflows/
│       ├── ci.yml                    # CI pipeline (lint, test, scan, build)
│       ├── deploy.yml                # Deploy pipeline (dev -> staging -> prod)
│       └── pr-gate.yml               # PR merge requirements
├── admin-panel/                      # FastAPI admin application
│   ├── app/
│   │   ├── ai/                       # AI-powered intelligence layer
│   │   │   ├── agent.py              # AI agent factory
│   │   │   ├── prompts.py            # System prompts for each capability
│   │   │   ├── schemas.py            # Pydantic models for AI I/O
│   │   │   └── providers/
│   │   │       ├── base.py           # Abstract AI provider with cost tracking
│   │   │       ├── claude.py         # Claude provider (AsyncAnthropic + DOE)
│   │   │       ├── anthropic_foundry.py  # Azure AI Foundry variant
│   │   │       └── failover.py       # Failover wrapping provider
│   │   ├── middleware/               # OIDC auth + RBAC middleware
│   │   ├── models/                   # SQLAlchemy models + Pydantic schemas
│   │   └── routers/                  # API routes (auth, subscribers, ai, public_catalog, etc.)
│   ├── Dockerfile                    # Multi-stage container build (dev + prod)
│   └── requirements.txt              # Production dependencies
├── database/
│   ├── init.sql                      # Database initialization
│   └── migrations/
│       ├── 001_initial_schema.sql    # Tables, indexes, default data
│       ├── 002_kong_sync_functions.sql # Sync functions and triggers
│       ├── 003_ai_layer.sql          # AI tables, prompts, indexes
│       ├── 004_rbac_teams.sql        # RBAC and team tables
│       └── 005_data_contracts.sql    # Data contract columns on api_registrations
├── docker-compose.yml                # Local development stack
├── docker-compose.prod.yml           # Production overrides
├── k8s/                              # Kubernetes manifests
│   ├── base/                         # Base manifests
│   └── overlays/                     # Environment-specific overlays
│       ├── dev/
│       ├── staging/
│       └── prod/
├── kong/                             # Kong configuration and plugins
│   ├── Dockerfile                    # Custom Kong image
│   └── plugins/
│       ├── subscription-validator.lua  # Subscription validation plugin
│       ├── ai-gateway.lua              # AI-powered gateway plugin
│       └── ai-gateway-schema.lua       # AI gateway plugin schema
├── monitoring/
│   ├── cribl/                        # Cribl Stream configuration
│   ├── grafana/                      # Grafana dashboards and provisioning
│   └── prometheus/                   # Prometheus config and alert rules
├── scripts/
│   ├── kong-sync.sh                  # Sync admin panel data to Kong
│   └── setup-local.sh               # Local development setup
├── terraform/                        # Infrastructure as Code
│   ├── modules/                      # Reusable Terraform modules
│   └── environments/                 # Per-environment configurations
│       ├── dev/
│       ├── staging/
│       └── prod/
├── tests/                            # Integration test suite
│   └── integration/
│       ├── conftest.py               # Shared fixtures (admin/viewer sessions, Kong client)
│       ├── test_01_health.py         # Health and readiness probes
│       ├── test_02_auth.py           # OIDC auth and session management
│       ├── test_03_rbac.py           # Role and permission management
│       ├── test_04_teams_registry.py # Teams and API registration lifecycle
│       ├── test_05_security.py       # Security headers, injection, auth enforcement
│       ├── test_06_subscribers.py    # Subscriber and API key CRUD
│       ├── test_07_gateway.py        # Kong gateway proxy operations
│       ├── test_08_e2e_lifecycle.py  # End-to-end workflows (register→activate→verify)
│       ├── test_09_rate_limits.py    # Plan tiers, subscription rate limits
│       ├── test_10_advanced_security.py # IDOR, privilege escalation, header injection
│       └── test_11_data_contracts.py # Data contracts, public catalog, Kong enforcement
├── .env.example                      # Environment variable template
├── .gitignore                        # Git ignore rules
└── README.md                         # This file
```

## Testing

### Integration Test Suite

The project includes 174 integration tests that run against the live Docker Compose stack.

```bash
# Run all tests
cd tests
python3 -m pytest integration/ -v --tb=short

# Run specific test file
python3 -m pytest integration/test_11_data_contracts.py -v

# Run with summary
python3 -m pytest integration/ -v --tb=short -q
```

**Test coverage areas:**
- Health checks and readiness probes
- OIDC authentication and session management
- RBAC (role CRUD, permission enforcement, audit logging)
- Team management and API registration lifecycle
- Security (headers, injection prevention, CORS, null bytes)
- Subscriber onboarding and API key management
- Kong gateway proxy operations
- End-to-end workflows (team → register → submit → approve → activate → verify Kong)
- Plan tier rate limits and subscription overrides
- Advanced security (IDOR, privilege escalation, header injection, mass assignment, resource enumeration)
- Data contracts (CRUD, validation, public catalog, Kong enforcement, RBAC, audit)
