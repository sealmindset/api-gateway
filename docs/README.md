# API Gateway Platform Documentation

The API Gateway platform provides a centralized, self-service portal for teams to register, secure, and monitor their APIs through a Kong-based gateway. It combines enterprise-grade traffic management with AI-powered analysis, OWASP security scanning, and full observability through Prometheus, Grafana, and Cribl Stream.

## Documentation Index

| Document | Description | Audience |
|----------|-------------|----------|
| [Getting Started](getting-started.md) | Prerequisites, local setup, first login | All engineers |
| [Architecture](architecture.md) | System design, components, data flows, network topology | Platform engineers, architects |
| [Self-Service Guide](self-service-guide.md) | Register a team, submit an API, manage keys, view metrics | API teams (day-to-day users) |
| [Administration Guide](admin-guide.md) | RBAC, user management, approval workflows, platform operations | Platform admins |
| [Kong Gateway](kong-gateway.md) | Gateway internals, custom plugins, rate limiting, routing | Platform engineers |
| [Monitoring & Observability](monitoring.md) | Prometheus, Grafana dashboards, alerting, Cribl Stream pipelines | SRE, platform engineers |
| [Security](security.md) | OWASP ZAP scanning, auth architecture, vulnerability management | Security, platform engineers |
| [AI Features](ai-features.md) | Anomaly detection, smart routing, request transforms, documentation generation | Platform engineers, AI/ML |
| [Deployment](deployment.md) | Azure Container Apps, production configuration, CI/CD, scaling | DevOps, platform engineers |
| [API Reference](api-reference.md) | Complete endpoint reference for the admin panel API | All engineers |
| [Configuration Reference](configuration.md) | All environment variables across every service | DevOps, platform engineers |
| [Troubleshooting](troubleshooting.md) | Common issues, debugging, health checks, log locations | All engineers |

## Quick Links

- **Admin Portal**: `https://<portal-host>:3000`
- **Kong Proxy**: `https://<gateway-host>:8000`
- **Kong Admin API**: `http://<gateway-host>:8001` (internal only)
- **Grafana Dashboards**: `http://<monitoring-host>:3200`
- **Prometheus**: `http://<monitoring-host>:9090`
- **API Docs (Swagger)**: `http://<admin-host>:8080/docs`

## Platform at a Glance

```
                        Internet / Internal Consumers
                                    |
                          +-------------------+
                          |   Kong Gateway    |  Rate limiting, auth, routing
                          |  (port 8000/8443) |  Custom plugins: subscription-validator, ai-gateway
                          +-------------------+
                           /        |        \
                  +----------+ +----------+ +----------+
                  | Team A   | | Team B   | | Team C   |
                  | APIs     | | APIs     | | APIs     |
                  +----------+ +----------+ +----------+
                                    |
                    +-------------------------------+
                    |       Admin Panel (FastAPI)    |  Self-service portal
                    |       + Next.js Frontend      |  Teams, API Registry, RBAC
                    +-------------------------------+
                     /              |              \
          +----------+    +-------------+    +-----------+
          | PostgreSQL|    |   Redis     |    |  Entra ID |
          |  (data)  |    | (cache/     |    |  (SSO)    |
          +----------+    |  sessions)  |    +-----------+
                          +-------------+
                                    |
                    +-------------------------------+
                    |        Observability           |
                    | Prometheus | Grafana | Cribl   |
                    | ZAP Scanner | AI Analysis     |
                    +-------------------------------+
```
