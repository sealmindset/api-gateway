# API Gateway

A centralized API Gateway built on Kong, with a FastAPI admin panel for managing subscribers, API keys, subscriptions, and rate limiting. Deployed on Azure Kubernetes Service (AKS) with Terraform-managed infrastructure.

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
| **Kong Gateway** | API proxy with rate limiting, authentication, request transformation |
| **Admin Panel** | FastAPI app for managing subscribers, API keys, plans, and subscriptions |
| **PostgreSQL 16** | Primary datastore for Kong and the admin panel (separate databases) |
| **Redis 7** | Rate limiting backend, session cache, and distributed locking |
| **Prometheus** | Metrics collection from Kong and admin panel |
| **Grafana** | Dashboards for API traffic, rate limiting, and system health |
| **Cribl Stream** | Log routing, transformation, and forwarding |

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

- **API Gateway Overview** - Traffic, latency, error rates
- **Rate Limiting** - Rate limit hits by consumer and plan
- **Upstream Health** - Backend service health and response times
- **Admin Panel** - Application metrics and database performance

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
│   ├── app/                          # Application source code
│   ├── tests/                        # Unit and integration tests
│   ├── Dockerfile                    # Multi-stage container build
│   ├── requirements.txt              # Production dependencies
│   └── requirements-dev.txt          # Development/test dependencies
├── database/
│   ├── init.sql                      # Database initialization
│   └── migrations/
│       ├── 001_initial_schema.sql    # Tables, indexes, default data
│       └── 002_kong_sync_functions.sql # Sync functions and triggers
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
│   └── plugins/                      # Custom Lua plugins
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
├── .env.example                      # Environment variable template
├── .gitignore                        # Git ignore rules
└── README.md                         # This file
```
