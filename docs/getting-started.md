# Getting Started

This guide walks you through setting up the API Gateway platform locally and verifying that all services are running correctly.

## Prerequisites

**Required:**

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Engine)
- Docker Compose v2 (bundled with Docker Desktop)
- git
- A modern web browser

**Optional:**

- Azure CLI -- needed for deploying to Azure environments
- Terraform -- needed for infrastructure provisioning

## Local Development Setup

### Quick Start (Recommended)

Clone the repository and run the automated setup script:

```bash
git clone <repo-url> api-gateway
cd api-gateway
./scripts/setup-local.sh
```

The setup script handles everything automatically:

- Generates secrets and writes a `.env` file
- Builds and starts all containers
- Imports the Kong declarative configuration
- Seeds a default `super_admin` user for local development

To tear down and recreate the environment from scratch, use the `--reset` flag:

```bash
./scripts/setup-local.sh --reset
```

### Manual Setup

If you prefer to set things up step by step:

1. Copy the example environment file and edit as needed:

   ```bash
   cp .env.example .env
   ```

2. Start all services:

   ```bash
   docker compose up -d
   ```

3. Wait for health checks to pass, then import the Kong configuration:

   ```bash
   docker exec api-gw-kong kong config db_import /etc/kong/kong.yml
   ```

## Services and Ports

The following ports are used by default. Your `.env` file may override these values.

| Service | Port | Protocol / Notes |
| --- | --- | --- |
| Kong Proxy | 8000 | HTTP |
| Kong Proxy | 8443 | HTTPS |
| Kong Admin API | 8001 | HTTP |
| Admin Panel (FastAPI) | 8080 | HTTP |
| Frontend (Next.js) | 3000 | HTTP |
| PostgreSQL | 5432 | TCP |
| Redis | 6380 | TCP |
| Prometheus | 9090 | HTTP |
| Grafana | 3200 | HTTP (default is 3000, remapped to avoid conflict with frontend) |
| Cribl Stream | 9420 | HTTP |
| ZAP Scanner | 8290 | HTTP |
| ZAP Exporter | 9290 | HTTP |

## First Login

### Authentication with Microsoft Entra ID

The platform uses Microsoft Entra ID (Azure AD) for single sign-on. When you visit the frontend for the first time, you will be redirected to the Entra ID login page.

**Important:** On first login, your user account is auto-provisioned with **no roles**. A platform admin must assign you a role before you can access any features.

For local development, the setup script seeds a default `super_admin` user so you can get started immediately.

### Entra ID App Registration (for new environments)

If you are setting up Entra ID from scratch:

1. Create an App Registration in Azure AD.
2. Set the redirect URI to:

   ```
   http://localhost:8080/auth/callback
   ```

3. Add the following values to your `.env` file:

   ```bash
   ENTRA_TENANT_ID=<your-tenant-id>
   ENTRA_CLIENT_ID=<your-client-id>
   ENTRA_CLIENT_SECRET=<your-client-secret>
   ```

## Verifying the Stack

Once everything is running, confirm that services are healthy:

```bash
docker compose ps
```

All services should show a status of `healthy` or `running`.

Then verify individual endpoints:

| Check | Command / URL |
| --- | --- |
| Frontend | Open [http://localhost:3000](http://localhost:3000) in your browser |
| API Docs (Swagger) | Open [http://localhost:8080/docs](http://localhost:8080/docs) in your browser |
| Grafana | Open [http://localhost:3200](http://localhost:3200) (default credentials: `admin` / `admin`) |
| Kong Proxy health | `curl http://localhost:8000/health` |

## What's Next

- **API teams** -- See the [Self-Service Guide](self-service-guide.md) for onboarding your APIs.
- **Administrators** -- See the [Admin Guide](admin-guide.md) for user management, RBAC, and platform configuration.
- **Architecture** -- See the [Architecture Overview](architecture.md) to understand how the system fits together.
