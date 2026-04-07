# Security

## Overview

The API Gateway platform implements defense-in-depth through multiple security layers:

- **Network isolation** -- all backend services run on a private Docker bridge network with only the Kong proxy exposed externally.
- **Authentication** -- Microsoft Entra ID OIDC for admin panel users; API keys, OAuth 2.0, JWT, and Basic Auth for API consumers.
- **Two-layer RBAC** -- platform-level permission-based access control plus team-level membership-based access control.
- **OWASP ZAP continuous scanning** -- automated vulnerability scanning against the OWASP Top 10, with results streamed to Prometheus and Grafana.
- **AI-powered anomaly detection** -- request-level threat scoring with configurable enforcement actions.

---

## Authentication Architecture

### Admin Panel Users (Microsoft Entra ID OIDC)

Admin panel users authenticate via Microsoft Entra ID using the OpenID Connect (OIDC) protocol. The flow works as follows:

1. User navigates to the admin panel and is redirected to the Entra ID login page (SSO).
2. After successful authentication, Entra ID issues an ID token and access token.
3. Tokens are stored server-side in the user's session.
4. Users are auto-provisioned on first login -- no manual account creation is required. The user record is created from the OIDC claims (email, display name, tenant ID).

Session cookies have a 1-hour TTL, the `Secure` flag is set in production, and `SameSite=Lax` is enforced.

### API Consumers

API consumers authenticate to Kong-proxied endpoints using one of the following mechanisms, configured per route or service:

| Method | Header / Flow | Notes |
|--------|--------------|-------|
| Key Auth | `X-API-Key` header | Simplest option; suitable for server-to-server calls |
| OAuth 2.0 | `authorization_code` or `client_credentials` grant | Full OAuth 2.0 flow via Kong's OAuth2 plugin |
| JWT | `Authorization: Bearer <token>` | Token validated against a stored public key or HMAC secret |
| Basic Auth | `Authorization: Basic <base64>` | Username/password pair |

Consumer credentials are managed through the admin panel and synced to Kong.

### API Key Format and Storage

API keys follow a deterministic format:

```
gw_<urlsafe_base64_32_characters>
```

- **Generation**: `gw_` prefix + 32 URL-safe random characters.
- **Storage**: the raw key is SHA256-hashed before being written to the database. The raw key is displayed to the user exactly once at creation time and cannot be retrieved afterward.
- **Identification**: the first 8 characters of the key (the prefix) are stored in plaintext and used for display and lookup in the admin UI.
- **Kong sync**: the hashed credential is synced to Kong as a consumer key-auth credential.

---

## OWASP ZAP Security Scanning

### Architecture

ZAP runs as a daemon inside a Docker container (`ghcr.io/zaproxy/zaproxy:stable`) on the internal network. It scans both the Kong proxy endpoints and the admin panel on a 5-minute interval.

### Scan Modes

| Mode | Behavior | Environment |
|------|----------|-------------|
| **Passive** (default) | Spider + passive scan rules only. Observes responses without injecting payloads. | All environments |
| **Active** | Includes attack-pattern probes (SQL injection, XSS, etc.) in addition to passive rules. | Non-production only |

> **Warning**: Active scanning sends attack payloads to the target application. Only enable active mode in non-production environments.

### Dynamic Target Discovery

ZAP auto-discovers scan targets by querying the Kong Admin API for registered routes. This ensures new routes are covered without manual configuration changes.

### OWASP Top 10 2021 Rule Mapping

The scanner enforces 30+ rules mapped to the OWASP Top 10 2021 categories. Findings are classified as either **FAIL** (blocks release / fires alert) or **WARN** (advisory, review recommended).

#### A01: Broken Access Control

| Rule | Severity | Action |
|------|----------|--------|
| Missing or misconfigured HSTS header | Medium | WARN |
| `X-Powered-By` header disclosed | Low | WARN |

#### A02: Cryptographic Failures

| Rule | Severity | Action |
|------|----------|--------|
| Timestamp disclosure in response headers or body | Low | WARN |
| SSL/TLS certificate or configuration issues | High | FAIL |

#### A03: Injection

| Rule | Severity | Action |
|------|----------|--------|
| SQL injection | High | FAIL |
| XSS (persistent / stored) | High | FAIL |
| XSS (reflected) | High | FAIL |

#### A05: Security Misconfiguration

| Rule | Severity | Action |
|------|----------|--------|
| Missing or weak Content-Security-Policy | Medium | WARN |
| Missing `X-Frame-Options` header | Medium | WARN |
| Insecure cookie settings (missing Secure, HttpOnly, SameSite) | Medium | WARN |

#### A07: Authentication Failures

| Rule | Severity | Action |
|------|----------|--------|
| PII disclosure in response | High | FAIL |
| Application debug error messages exposed | Medium | WARN |

#### A10: Server-Side Request Forgery (SSRF)

| Rule | Severity | Action |
|------|----------|--------|
| Proxy disclosure | High | FAIL |

### Results Pipeline

```
ZAP Daemon
  --> ZAP API
    --> ZAP Exporter
      --> Prometheus (metrics)
      --> Cribl Stream (log aggregation)
        --> Grafana Dashboard
```

- **Prometheus metrics**: vulnerability counts by severity, OWASP category, and scan target.
- **Cribl Stream**: structured log events for correlation and long-term retention.
- **Grafana dashboard**: real-time vulnerability counts, OWASP Top 10 breakdown, trend charts, and scan status indicators.

### Alerting

| Alert | Condition | Delay |
|-------|-----------|-------|
| `ZAPCriticalVulnerability` | Any finding with High severity | Fires immediately (0m) |

---

## Network Security

### Docker Network Isolation

All services run on an isolated Docker bridge network (`api-gateway-net`). Only the Kong proxy container exposes ports to the host network.

```
Internet
  |
  v
Kong Proxy (ports 8000/8443)
  |
  +--> api-gateway-net (bridge) --> Backend Services
       |-- Admin API (Next.js)
       |-- PostgreSQL
       |-- Redis
       |-- ZAP Daemon
       |-- Prometheus / Grafana
       |-- Kong Admin API (8001, internal only)
```

**Kong Admin API (port 8001) is never exposed to the internet.** It binds exclusively to the internal Docker network.

### TLS Configuration

- HTTPS listeners enforce TLS 1.2 or higher.
- Modern cipher suites only (no RC4, no 3DES, no CBC-mode ciphers where avoidable).
- TLS termination occurs at the Kong proxy layer.

### CORS

CORS is configured per origin:

- **Production**: `*.sleepnumber.com`
- **Development**: `localhost` origins are additionally permitted.

### IP Restriction

The Kong IP restriction plugin is available for internal-only APIs. Default allowlist:

```
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
```

### Bot Detection

Bot detection is enabled with an allowlist for known monitoring agents (health checks, uptime probes). Unrecognized bot user agents receive a 403 response.

---

## Access Control

### Platform RBAC (Permission-Based)

Platform-level access control uses a permission model with the format `resource:action`. Permissions are evaluated on every request and cached in Redis for performance.

Four default roles are provided:

| Role | Description |
|------|-------------|
| **Super Admin** | Full access to all resources and actions |
| **Admin** | Manage services, routes, consumers, and team settings |
| **Developer** | Read/write access to services and routes within assigned teams |
| **Viewer** | Read-only access |

Custom roles can be created by combining granular permissions.

### Team RBAC (Membership-Based)

Team-level access control is membership-based with a strict role hierarchy:

```
owner > admin > member > viewer
```

- **Owner**: full control of team settings, membership, and resources.
- **Admin**: manage team resources and members (cannot delete team or transfer ownership).
- **Member**: create and manage own resources within the team.
- **Viewer**: read-only access to team resources.

### Platform Admin Override

Users with platform admin privileges bypass team-level checks entirely. This provides global oversight without requiring membership in every team.

### Access Decision Logging

All access control decisions -- both granted and denied -- are written to the audit trail. These records are viewable in the admin panel under the `/rbac` audit tab.

---

## AI-Powered Threat Detection

The AI Gateway plugin provides real-time anomaly detection on API traffic.

### How It Works

1. The plugin samples a configurable fraction of incoming requests.
2. Each sampled request is scored on a 0.0 to 1.0 anomaly scale by the AI analysis service.
3. Requests exceeding the configured threshold trigger the configured enforcement action.

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sampling_rate` | Configurable | Fraction of requests to analyze (0.0 - 1.0) |
| `anomaly_threshold` | 0.7 | Score at or above which the action is triggered |
| `action` | `log` | One of: `block`, `header`, `log` |

### Enforcement Actions

| Action | Behavior |
|--------|----------|
| `block` | Returns HTTP 403 to the client |
| `header` | Adds `X-AI-Anomaly-Score` header to the upstream request as a warning; request proceeds |
| `log` | Logs the anomaly score; request proceeds unmodified |

### Fail-Open Design

If the AI analysis service is unavailable (timeout, error, unreachable), the plugin allows the request through. This prevents the AI layer from becoming a single point of failure for API traffic.

### Cost Controls

- Per-analysis budget limits prevent runaway costs.
- Sampling rate caps ensure only a fraction of traffic is analyzed.

---

## Secret Management

### Principles

- **No hardcoded secrets.** All secrets are injected via environment variables.
- **`.env` excluded from version control.** The `.gitignore` file prevents accidental commits of the `.env` file.
- **One-time display.** API keys are shown to the user exactly once at creation time and stored only as SHA256 hashes.

### Local Development

The `setup-local.sh` script generates random secrets automatically:

```bash
openssl rand -hex 16
```

This produces cryptographically random 32-character hex strings for session secrets, database passwords, and other sensitive values.

### Production

In production environments, secrets are sourced from:

- **Azure Key Vault** -- for centrally managed secrets with access policies and rotation support.
- **Container app secrets** -- for secrets injected directly into the container runtime environment.

Never copy `.env` files to production hosts. Always use the platform's native secret management.

### API Key Hashing

API keys are hashed with SHA256 before storage. The raw key cannot be recovered from the hash. If a key is lost, it must be rotated (a new key is generated and the old one is invalidated).

---

## Audit Trail

### What Is Logged

Every state-changing operation produces an audit record containing:

| Field | Description |
|-------|-------------|
| `user` | The authenticated user who performed the action |
| `action` | The operation performed (e.g., `create`, `update`, `delete`, `rotate`) |
| `resource` | The target resource type and identifier |
| `details` | Additional context stored as JSONB (e.g., changed fields, before/after values) |
| `ip_address` | The client IP address of the request |
| `timestamp` | When the action occurred (UTC) |

### Storage

Audit records are written to the `audit_logs` table, which is **append-only and immutable**. Records cannot be updated or deleted through the application.

### Querying

Audit logs are queryable via the `/rbac/audit` endpoint. Supported filters include user, action, resource type, date range, and IP address.

---

## Security Best Practices

1. **Never expose Kong Admin API (port 8001) to the internet.** It should only be accessible on the internal Docker network.

2. **Rotate API keys periodically.** Use the key rotation endpoint in the admin panel. The old key is invalidated immediately when a new one is issued.

3. **Use active ZAP scanning only in non-production environments.** Active scans send attack payloads and can disrupt production traffic or trigger security controls.

4. **Review ZAP findings on the Grafana security dashboard regularly.** Pay particular attention to High-severity findings that trigger the `ZAPCriticalVulnerability` alert.

5. **Set `fail_open=false` on the subscription-validator plugin in production.** This ensures requests are rejected if the validation service is unreachable, rather than allowed through.

6. **Enable IP restriction for internal-only APIs.** Use the Kong IP restriction plugin with the default private network ranges to prevent external access.

7. **Never commit `.env` files or secrets to version control.** Verify `.gitignore` includes `.env` before every new repository setup.

8. **Use TLS 1.2+ for all external-facing listeners.** Disable older protocol versions and weak cipher suites.

9. **Monitor the audit trail for denied access attempts.** Repeated denials from the same user or IP may indicate an attack or misconfiguration.

10. **Keep the ZAP container image up to date.** New scan rules and vulnerability signatures are added regularly to `ghcr.io/zaproxy/zaproxy:stable`.
