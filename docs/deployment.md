# Deployment Guide

## Overview

The API Gateway platform is designed to run on **Azure Container Apps** with managed PostgreSQL, managed Redis, and Azure Container Registry for container images. This guide covers production deployment, configuration, and operational considerations.

All services run as individual Container Apps within a shared Container App Environment. Managed Azure services handle database, caching, and image storage, minimizing operational overhead while maintaining production-grade reliability.

---

## Azure Container Apps Architecture

### Container App Environment

A single Container App Environment hosts all services. The environment is integrated with an Azure Virtual Network (VNet) for network isolation.

```
┌─────────────────────────────────────────────────────────────────┐
│  Container App Environment (VNet-integrated)                    │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  kong         │  │  frontend    │  │  admin-panel │          │
│  │  External     │  │  External    │  │  Internal    │          │
│  │  Ingress      │  │  Ingress     │  │  Ingress     │          │
│  │  Min 2 replicas│ │  2 replicas  │  │  2-4 replicas│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  zap          │  │  zap-exporter│                             │
│  │  Internal     │  │  Internal    │                             │
│  │  1 replica    │  │  1 replica   │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Azure DB for │  │ Azure Cache  │  │ Azure        │
│ PostgreSQL   │  │ for Redis    │  │ Container    │
│ (kong,       │  │ (TLS)        │  │ Registry     │
│  admin DB)   │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Services

| Service | Ingress | Replicas | Notes |
|---------|---------|----------|-------|
| **kong** | External (internet-facing) | Min 2, scales on HTTP requests | Custom domain + managed TLS certificate |
| **admin-panel** | Internal only | 2-4 | Gunicorn with 4 uvicorn workers per replica |
| **frontend** | External (admin portal) | 2 | Next.js standalone server |
| **zap** | Internal only | 1 | Long startup (~90s+), resource-intensive Java app |
| **zap-exporter** | Internal only | 1 | Prometheus metrics exporter for ZAP |

### Managed Services

- **Azure Database for PostgreSQL Flexible Server** -- hosts two databases: `kong` and `api_gateway_admin`
- **Azure Cache for Redis** -- session storage and RBAC caching, TLS-enabled
- **Azure Container Registry** -- stores all Docker images

---

## Prerequisites

Before deploying, ensure you have:

- Azure subscription with **Contributor** access (or equivalent RBAC)
- **Azure CLI** (`az`) installed and authenticated (`az login`)
- **Docker** installed for building images
- An **Azure Container Registry** created
- An **Azure AD App Registration** configured for Entra ID authentication (with redirect URIs set for production)
- A **Resource Group** created for all resources

```bash
# Verify prerequisites
az account show
az acr list --output table
docker --version
```

---

## Building and Pushing Images

Build each service image and push to your Azure Container Registry.

```bash
# Set variables
ACR_REGISTRY=youracr.azurecr.io
IMAGE_TAG=v1.0.0

# Authenticate to ACR
az acr login --name youracr

# Build images
docker build -t $ACR_REGISTRY/api-gw-kong:$IMAGE_TAG ./kong
docker build -t $ACR_REGISTRY/api-gw-admin-panel:$IMAGE_TAG --target production ./admin-panel
docker build -t $ACR_REGISTRY/api-gw-frontend:$IMAGE_TAG --target production ./frontend
docker build -t $ACR_REGISTRY/api-gw-zap:$IMAGE_TAG ./security/zap
docker build -t $ACR_REGISTRY/api-gw-zap-exporter:$IMAGE_TAG ./security/zap-exporter

# Push images
docker push $ACR_REGISTRY/api-gw-kong:$IMAGE_TAG
docker push $ACR_REGISTRY/api-gw-admin-panel:$IMAGE_TAG
docker push $ACR_REGISTRY/api-gw-frontend:$IMAGE_TAG
docker push $ACR_REGISTRY/api-gw-zap:$IMAGE_TAG
docker push $ACR_REGISTRY/api-gw-zap-exporter:$IMAGE_TAG
```

To build and push all images in one step using ACR Tasks (no local Docker needed):

```bash
az acr build --registry youracr --image api-gw-kong:$IMAGE_TAG ./kong
az acr build --registry youracr --image api-gw-admin-panel:$IMAGE_TAG --target production ./admin-panel
az acr build --registry youracr --image api-gw-frontend:$IMAGE_TAG --target production ./frontend
az acr build --registry youracr --image api-gw-zap:$IMAGE_TAG ./security/zap
az acr build --registry youracr --image api-gw-zap-exporter:$IMAGE_TAG ./security/zap-exporter
```

---

## Environment Configuration for Production

The following environment variables must be configured for each Container App. Store secrets in **Azure Key Vault** and reference them as Container App secrets.

### Common Settings

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | `production` | Enables production behaviors across all services |

### Database

| Variable | Value | Notes |
|----------|-------|-------|
| `DATABASE_URL` | `postgresql://adminuser@your-pg-server:password@your-pg-server.postgres.database.azure.com:5432/api_gateway_admin?sslmode=require` | Admin panel database |
| `KONG_PG_HOST` | `your-pg-server.postgres.database.azure.com` | Kong PostgreSQL host |
| `KONG_PG_USER` | `konguser` | Kong database user |
| `KONG_PG_PASSWORD` | (from Key Vault) | Kong database password |
| `KONG_PG_DATABASE` | `kong` | Kong database name |
| `KONG_PG_SSL` | `on` | Require SSL for Kong DB connections |

### Redis

| Variable | Value | Notes |
|----------|-------|-------|
| `REDIS_URL` | `rediss://default:accesskey@your-redis.redis.cache.windows.net:6380/0` | Note `rediss://` (TLS) and port 6380 |

### Authentication (Entra ID)

| Variable | Value | Notes |
|----------|-------|-------|
| `ENTRA_TENANT_ID` | Your Azure AD tenant ID | From App Registration |
| `ENTRA_CLIENT_ID` | Your application (client) ID | From App Registration |
| `ENTRA_CLIENT_SECRET` | (from Key Vault) | Client secret value |
| `ENTRA_REDIRECT_URI` | `https://your-frontend-domain.com/auth/callback` | Must match App Registration |

### Security

| Variable | Value | Notes |
|----------|-------|-------|
| `SECRET_KEY` | (from Key Vault) | Generate with `openssl rand -hex 32` |
| `KONG_ADMIN_LISTEN` | `127.0.0.1:8001` | Never expose Kong Admin API publicly |
| `CORS_ORIGINS` | `https://your-frontend-domain.com` | Production frontend domain |

### AI Provider

| Variable | Value | Notes |
|----------|-------|-------|
| `AZURE_AI_FOUNDRY_ENDPOINT` | `https://your-ai-endpoint.cognitiveservices.azure.com` | Azure AI Foundry endpoint |
| `AZURE_AI_FOUNDRY_API_KEY` | (from Key Vault) | API key for AI services |

---

## Azure Container Apps Deployment

Follow these steps in order. Each step includes the relevant `az` CLI commands.

### Step 1: Create Container App Environment

```bash
RESOURCE_GROUP=rg-api-gateway-prod
LOCATION=eastus2
ENVIRONMENT_NAME=cae-api-gateway-prod
VNET_NAME=vnet-api-gateway-prod
SUBNET_NAME=snet-container-apps

# Create VNet and subnet for Container Apps
az network vnet create \
  --resource-group $RESOURCE_GROUP \
  --name $VNET_NAME \
  --location $LOCATION \
  --address-prefix 10.0.0.0/16

az network vnet subnet create \
  --resource-group $RESOURCE_GROUP \
  --vnet-name $VNET_NAME \
  --name $SUBNET_NAME \
  --address-prefix 10.0.0.0/23

SUBNET_ID=$(az network vnet subnet show \
  --resource-group $RESOURCE_GROUP \
  --vnet-name $VNET_NAME \
  --name $SUBNET_NAME \
  --query id --output tsv)

# Create Container App Environment
az containerapp env create \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --infrastructure-subnet-resource-id $SUBNET_ID
```

### Step 2: Deploy PostgreSQL Flexible Server

```bash
PG_SERVER=pg-api-gateway-prod
PG_ADMIN_USER=pgadmin
PG_ADMIN_PASSWORD="<strong-password-from-key-vault>"

az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $PG_SERVER \
  --location $LOCATION \
  --admin-user $PG_ADMIN_USER \
  --admin-password $PG_ADMIN_PASSWORD \
  --sku-name Standard_B2s \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --yes

# Allow connections from Container App Environment subnet
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $PG_SERVER \
  --rule-name allow-container-apps \
  --start-ip-address 10.0.0.0 \
  --end-ip-address 10.0.1.255

# Create databases
az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $PG_SERVER \
  --database-name kong

az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $PG_SERVER \
  --database-name api_gateway_admin
```

**Run database migrations** against the `api_gateway_admin` database before deploying the admin panel:

```bash
PG_HOST=$PG_SERVER.postgres.database.azure.com

# Run migrations in order
psql "postgresql://$PG_ADMIN_USER:$PG_ADMIN_PASSWORD@$PG_HOST:5432/api_gateway_admin?sslmode=require" \
  -f database/migrations/001_initial_schema.sql

psql "postgresql://$PG_ADMIN_USER:$PG_ADMIN_PASSWORD@$PG_HOST:5432/api_gateway_admin?sslmode=require" \
  -f database/migrations/002_kong_sync_functions.sql

psql "postgresql://$PG_ADMIN_USER:$PG_ADMIN_PASSWORD@$PG_HOST:5432/api_gateway_admin?sslmode=require" \
  -f database/migrations/003_ai_layer.sql

psql "postgresql://$PG_ADMIN_USER:$PG_ADMIN_PASSWORD@$PG_HOST:5432/api_gateway_admin?sslmode=require" \
  -f database/migrations/004_teams_and_api_registry.sql
```

### Step 3: Deploy Azure Cache for Redis

```bash
REDIS_NAME=redis-api-gateway-prod

az redis create \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --location $LOCATION \
  --sku Standard \
  --vm-size C1 \
  --enable-non-ssl-port false

# Retrieve the access key
REDIS_KEY=$(az redis list-keys \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --query primaryKey --output tsv)
```

### Step 4: Run Kong Migrations (Container App Job)

Bootstrap the Kong database schema before deploying Kong itself:

```bash
ACR_REGISTRY=youracr.azurecr.io
IMAGE_TAG=v1.0.0

az containerapp job create \
  --name job-kong-migrations \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_REGISTRY/api-gw-kong:$IMAGE_TAG \
  --registry-server $ACR_REGISTRY \
  --trigger-type Manual \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars \
    KONG_DATABASE=postgres \
    KONG_PG_HOST=$PG_SERVER.postgres.database.azure.com \
    KONG_PG_USER=$PG_ADMIN_USER \
    KONG_PG_PASSWORD=$PG_ADMIN_PASSWORD \
    KONG_PG_DATABASE=kong \
    KONG_PG_SSL=on \
  --command "kong" --args "migrations" "bootstrap"

# Execute the job
az containerapp job start \
  --name job-kong-migrations \
  --resource-group $RESOURCE_GROUP
```

For subsequent upgrades, create a similar job with `kong migrations up` instead of `bootstrap`.

### Step 5: Deploy Kong

```bash
az containerapp create \
  --name ca-kong \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_REGISTRY/api-gw-kong:$IMAGE_TAG \
  --registry-server $ACR_REGISTRY \
  --ingress external \
  --target-port 8000 \
  --min-replicas 2 \
  --max-replicas 10 \
  --cpu 1.0 \
  --memory 2Gi \
  --scale-rule-name http-scaling \
  --scale-rule-type http \
  --scale-rule-http-concurrency 100 \
  --env-vars \
    KONG_DATABASE=postgres \
    KONG_PG_HOST=$PG_SERVER.postgres.database.azure.com \
    KONG_PG_USER=$PG_ADMIN_USER \
    KONG_PG_PASSWORD=secretref:kong-pg-password \
    KONG_PG_DATABASE=kong \
    KONG_PG_SSL=on \
    KONG_PROXY_LISTEN="0.0.0.0:8000, 0.0.0.0:8443 ssl" \
    KONG_ADMIN_LISTEN="127.0.0.1:8001" \
    KONG_STATUS_LISTEN="0.0.0.0:8100" \
  --secrets kong-pg-password=$PG_ADMIN_PASSWORD
```

Add a custom domain and managed certificate:

```bash
# Add custom domain
az containerapp hostname add \
  --name ca-kong \
  --resource-group $RESOURCE_GROUP \
  --hostname api.yourdomain.com

# Bind managed certificate
az containerapp hostname bind \
  --name ca-kong \
  --resource-group $RESOURCE_GROUP \
  --hostname api.yourdomain.com \
  --environment $ENVIRONMENT_NAME \
  --validation-method CNAME
```

### Step 6: Deploy Admin Panel

```bash
az containerapp create \
  --name ca-admin-panel \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_REGISTRY/api-gw-admin-panel:$IMAGE_TAG \
  --registry-server $ACR_REGISTRY \
  --ingress internal \
  --target-port 8080 \
  --min-replicas 2 \
  --max-replicas 4 \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars \
    ENVIRONMENT=production \
    DATABASE_URL=secretref:database-url \
    REDIS_URL=secretref:redis-url \
    SECRET_KEY=secretref:secret-key \
    ENTRA_TENANT_ID=$ENTRA_TENANT_ID \
    ENTRA_CLIENT_ID=$ENTRA_CLIENT_ID \
    ENTRA_CLIENT_SECRET=secretref:entra-client-secret \
    KONG_ADMIN_URL=http://ca-kong.internal.$ENVIRONMENT_NAME.azurecontainerapps.io:8001 \
    AZURE_AI_FOUNDRY_ENDPOINT=$AI_FOUNDRY_ENDPOINT \
    AZURE_AI_FOUNDRY_API_KEY=secretref:ai-foundry-key \
  --secrets \
    database-url="postgresql://$PG_ADMIN_USER:$PG_ADMIN_PASSWORD@$PG_SERVER.postgres.database.azure.com:5432/api_gateway_admin?sslmode=require" \
    redis-url="rediss://default:$REDIS_KEY@$REDIS_NAME.redis.cache.windows.net:6380/0" \
    secret-key="$(openssl rand -hex 32)" \
    entra-client-secret="$ENTRA_CLIENT_SECRET" \
    ai-foundry-key="$AI_FOUNDRY_API_KEY"
```

### Step 7: Deploy Frontend

```bash
az containerapp create \
  --name ca-frontend \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_REGISTRY/api-gw-frontend:$IMAGE_TAG \
  --registry-server $ACR_REGISTRY \
  --ingress external \
  --target-port 3000 \
  --min-replicas 2 \
  --max-replicas 4 \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars \
    NEXT_PUBLIC_API_URL=https://api.yourdomain.com \
    NEXT_PUBLIC_ADMIN_API_URL=http://ca-admin-panel.internal.$ENVIRONMENT_NAME.azurecontainerapps.io:8080

# Add custom domain for the admin portal
az containerapp hostname add \
  --name ca-frontend \
  --resource-group $RESOURCE_GROUP \
  --hostname admin.yourdomain.com

az containerapp hostname bind \
  --name ca-frontend \
  --resource-group $RESOURCE_GROUP \
  --hostname admin.yourdomain.com \
  --environment $ENVIRONMENT_NAME \
  --validation-method CNAME
```

### Step 8: Deploy ZAP and ZAP Exporter

```bash
# Deploy ZAP
az containerapp create \
  --name ca-zap \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_REGISTRY/api-gw-zap:$IMAGE_TAG \
  --registry-server $ACR_REGISTRY \
  --ingress internal \
  --target-port 8090 \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2Gi

# Deploy ZAP Exporter
az containerapp create \
  --name ca-zap-exporter \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_REGISTRY/api-gw-zap-exporter:$IMAGE_TAG \
  --registry-server $ACR_REGISTRY \
  --ingress internal \
  --target-port 9290 \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --env-vars \
    ZAP_API_URL=http://ca-zap.internal.$ENVIRONMENT_NAME.azurecontainerapps.io:8090
```

### Step 9: Deploy Monitoring

**Option A: Self-hosted Prometheus + Grafana**

Deploy Prometheus and Grafana as Container Apps within the same environment:

```bash
# Deploy Prometheus
az containerapp create \
  --name ca-prometheus \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image prom/prometheus:latest \
  --ingress internal \
  --target-port 9090 \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.5 \
  --memory 1Gi

# Deploy Grafana
az containerapp create \
  --name ca-grafana \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image grafana/grafana:latest \
  --ingress internal \
  --target-port 3000 \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.5 \
  --memory 1Gi
```

**Option B: Azure-native monitoring**

Use Azure Monitor for Container Apps metrics and Azure Managed Grafana for dashboards. This eliminates the need to run Prometheus and Grafana as separate Container Apps.

```bash
# Create Azure Managed Grafana instance
az grafana create \
  --name grafana-api-gateway-prod \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### Step 10: Configure Log Aggregation

**Option A: Cribl Stream as a Container App**

Deploy Cribl Stream within the environment to aggregate and route logs.

**Option B: Azure-native log aggregation**

Use Azure Event Hubs and Log Analytics workspace for centralized logging:

```bash
az monitor log-analytics workspace create \
  --resource-group $RESOURCE_GROUP \
  --workspace-name law-api-gateway-prod \
  --location $LOCATION

# Link Container App Environment to Log Analytics
az containerapp env update \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --logs-workspace-id <LOG_ANALYTICS_WORKSPACE_ID>
```

---

## Scaling Considerations

### Kong

- **Scale horizontally.** Kong is stateless -- all configuration is stored in PostgreSQL.
- Minimum 2 replicas for high availability. Scale based on concurrent HTTP request count.
- Allocate 1 CPU / 2 GB memory per replica as a baseline.

### Admin Panel

- 2-4 replicas. Each replica runs Gunicorn with 4 uvicorn workers.
- Scale based on CPU utilization (target ~70%).
- 0.5 CPU / 1 GB memory per replica is typically sufficient.

### Frontend

- 2 replicas for availability. Stateless Next.js standalone server.
- Lightweight resource requirements: 0.5 CPU / 1 GB memory.

### PostgreSQL

- Use **Burstable** tier (Standard_B2s) for development/staging, **General Purpose** tier for production.
- Enable **High Availability** (zone-redundant) for production workloads.
- Monitor connection count -- Kong can consume many connections under load.

### Redis

- **Standard C1** or higher. Used for session storage and RBAC caching.
- Enable data persistence if session loss during Redis restarts is unacceptable.
- Monitor memory usage and eviction rates.

### ZAP

- **Single replica only.** ZAP is a resource-intensive Java application.
- Allocate a minimum of 1 CPU / 2 GB memory (more if scanning large targets).
- Do not scale horizontally -- ZAP maintains in-memory scan state.

---

## Health Checks

Configure Container App probes for each service. These ensure Azure routes traffic only to healthy instances and restarts unhealthy ones.

### Kong

```yaml
# Liveness and readiness probe
probes:
  - type: liveness
    httpGet:
      path: /status
      port: 8100
    initialDelaySeconds: 15
    periodSeconds: 10
  - type: readiness
    httpGet:
      path: /status
      port: 8100
    initialDelaySeconds: 15
    periodSeconds: 5
```

Alternatively, use the `kong health` CLI command as an exec probe.

### Admin Panel

```yaml
probes:
  - type: liveness
    httpGet:
      path: /health
      port: 8080
    initialDelaySeconds: 10
    periodSeconds: 10
  - type: readiness
    httpGet:
      path: /ready
      port: 8080
    initialDelaySeconds: 10
    periodSeconds: 5
    # /ready checks database connectivity
```

### Frontend

```yaml
probes:
  - type: liveness
    httpGet:
      path: /
      port: 3000
    initialDelaySeconds: 10
    periodSeconds: 10
  - type: readiness
    httpGet:
      path: /
      port: 3000
    initialDelaySeconds: 10
    periodSeconds: 5
```

### ZAP

```yaml
probes:
  - type: liveness
    httpGet:
      path: /JSON/core/view/version/
      port: 8090
    initialDelaySeconds: 90  # ZAP has a long startup time
    periodSeconds: 30
  - type: readiness
    httpGet:
      path: /JSON/core/view/version/
      port: 8090
    initialDelaySeconds: 90
    periodSeconds: 10
```

### ZAP Exporter

```yaml
probes:
  - type: liveness
    httpGet:
      path: /health
      port: 9290
    initialDelaySeconds: 5
    periodSeconds: 10
  - type: readiness
    httpGet:
      path: /health
      port: 9290
    initialDelaySeconds: 5
    periodSeconds: 5
```

---

## Database Migrations

### Admin Panel Database (`api_gateway_admin`)

Run migrations **before** deploying or upgrading the admin-panel Container App. Migration files are in `database/migrations/` and must be applied in order:

1. `001_initial_schema.sql` -- base tables and schema
2. `002_kong_sync_functions.sql` -- functions for syncing with Kong
3. `003_ai_layer.sql` -- AI prompt management tables
4. `004_teams_and_api_registry.sql` -- teams and API registry tables

```bash
# Run all migrations in sequence
for migration in database/migrations/*.sql; do
  echo "Running $migration..."
  psql "postgresql://$PG_ADMIN_USER:$PG_ADMIN_PASSWORD@$PG_HOST:5432/api_gateway_admin?sslmode=require" \
    -f "$migration"
done
```

### Kong Database (`kong`)

Kong manages its own schema. Use the Kong CLI:

```bash
# First-time setup (bootstrap)
kong migrations bootstrap

# Upgrades (when updating Kong version)
kong migrations up
kong migrations finish
```

In Azure Container Apps, run these as **Container App Jobs** (see Step 4 above).

---

## SSL/TLS

### Container App Ingress

Azure Container Apps provides **managed TLS certificates** for custom domains. No manual certificate management is required.

```bash
# Verify custom domain and TLS binding
az containerapp hostname list \
  --name ca-kong \
  --resource-group $RESOURCE_GROUP \
  --output table
```

### Kong HTTPS Listener

Kong is configured to listen on both HTTP (8000) and HTTPS (8443). For production:

- **Option A:** Terminate TLS at Azure Container Apps ingress (recommended). Kong receives plain HTTP from the ingress controller.
- **Option B:** Use Azure Front Door for global TLS termination and WAF capabilities.
- **Option C:** Configure Kong with your own certificate for end-to-end encryption.

### Database Connections

All database connections must use SSL:

```
# PostgreSQL -- include sslmode=require
postgresql://user:password@host:5432/dbname?sslmode=require

# Kong PostgreSQL SSL
KONG_PG_SSL=on
```

### Redis

Use the TLS-enabled Azure Redis endpoint:

```
# Port 6380 (TLS), not 6379 (non-TLS)
rediss://default:accesskey@your-redis.redis.cache.windows.net:6380/0
```

Note the `rediss://` scheme (double s) which indicates TLS.

---

## Monitoring in Production

### Option A: Self-hosted Prometheus + Grafana

Deploy Prometheus and Grafana as Container Apps (see Step 9). This mirrors the local development setup and uses the same dashboards and alert rules.

Configure Prometheus to scrape:

| Target | Endpoint | Port |
|--------|----------|------|
| Kong | `/metrics` (via Prometheus plugin) | 8001 |
| Admin panel | `/metrics` | 8080 |
| ZAP exporter | `/metrics` | 9290 |

### Option B: Azure Monitor + Managed Grafana

Use Azure-native monitoring for a fully managed experience:

- **Azure Monitor** collects Container App metrics (CPU, memory, request count, latency) automatically.
- **Azure Managed Grafana** provides dashboards backed by Azure Monitor data.
- Use **Azure Monitor alerts** for threshold-based alerting.

### Alerting

For production alerts, configure your alerting pipeline:

- **AlertManager** (if using self-hosted Prometheus): route to PagerDuty, Slack, or Microsoft Teams.
- **Azure Monitor Action Groups**: send alerts to email, SMS, webhooks, or Azure Logic Apps for integration with PagerDuty/Slack/Teams.

---

## Backup and Recovery

### Azure PostgreSQL

Azure Database for PostgreSQL Flexible Server includes **automated backups** by default:

- Default retention: 7 days (configurable up to 35 days)
- Point-in-time restore supported within the retention window
- Geo-redundant backup available for disaster recovery

```bash
# Check backup configuration
az postgres flexible-server show \
  --resource-group $RESOURCE_GROUP \
  --name $PG_SERVER \
  --query "backup" --output table

# Update backup retention to 35 days
az postgres flexible-server update \
  --resource-group $RESOURCE_GROUP \
  --name $PG_SERVER \
  --backup-retention 35

# Restore to a point in time
az postgres flexible-server restore \
  --resource-group $RESOURCE_GROUP \
  --name pg-api-gateway-prod-restored \
  --source-server $PG_SERVER \
  --restore-time "2026-04-05T12:00:00Z"
```

### Redis

Enable data persistence on Azure Cache for Redis:

- **AOF persistence**: logs every write operation (higher durability, more I/O)
- **RDB snapshots**: periodic point-in-time snapshots (lower overhead)

```bash
# Enable RDB persistence (Standard tier or higher)
az redis update \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --set "redisConfiguration.rdb-backup-enabled=true" \
  --set "redisConfiguration.rdb-backup-frequency=60"
```

### Kong Configuration

Kong configuration is stored entirely in PostgreSQL. Backing up the `kong` database backs up all Kong configuration (routes, services, plugins, consumers).

### Application State

All services (Kong, admin-panel, frontend, ZAP, ZAP exporter) are **stateless**. Only the databases (PostgreSQL and Redis) contain state that requires backup. Container images are stored in Azure Container Registry, which has its own replication and redundancy.
