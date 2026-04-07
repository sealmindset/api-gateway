# RFC-001: Self-Service API Gateway Platform

**Sleep Number — Platform Engineering**

---

| | |
|---|---|
| **Status** | Draft — Awaiting Review |
| **Author** | Platform Engineering |
| **Date** | April 6, 2026 |
| **Review Deadline** | _TBD_ |
| **Decision Authority** | Architecture Review Committee |
| **Reviewers** | DevOps / Platform Engineering, Security Engineering, Network Engineering |
| **Repository** | `api-gateway` (working implementation available for review) |

---

## Executive Summary

This RFC proposes a self-service API Gateway platform that allows teams to register, secure, monitor, and manage their APIs through a web portal backed by a Kong gateway. The platform addresses gaps in our current integration pattern (SNIP) around self-service onboarding, automated security scanning, team-scoped access control, and per-API observability.

**This is additive to SNIP, not a replacement.** Existing integrations on APIM, Function Apps, and Cosmos continue to operate unchanged.

We are requesting targeted feedback from DevOps, Security Engineering, and Network Engineering on specific infrastructure, security, and network questions. The Architecture Review Committee will make the go/no-go decision based on reviewer input.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Proposed Capability](#2-proposed-capability)
3. [Access Control Model](#3-access-control-model)
4. [API Lifecycle](#4-api-lifecycle)
5. [Questions for DevOps / Platform Engineering](#51-devops--platform-engineering)
6. [Questions for Security Engineering](#52-security-engineering)
7. [Questions for Network Engineering](#53-network-engineering)
8. [Open Questions](#6-open-questions)
9. [Relationship to SNIP](#7-relationship-to-snip)
10. [Supporting Documentation](#8-proof-of-capability)
11. [Response Instructions](#9-response-instructions)
12. [Decision Criteria](#10-decision-criteria)

---

## 1. Problem Statement

Sleep Number's current integration pattern (SNIP) uses Azure API Management, Function Apps, Cosmos DB, and Storage Accounts — originally stood up to replace MuleSoft. While SNIP serves its purpose for existing integrations, the following operational gaps have emerged:

| Gap | Impact |
|-----|--------|
| **No self-service API onboarding** | Every new API exposure requires a ticket to the platform team. Teams wait days to weeks for manual APIM configuration, Function App setup, and Cosmos provisioning. |
| **No unified approval workflow** | API exposure decisions happen in Slack threads and email chains. There is no auditable record of who approved what, when, or why. |
| **Limited observability per API** | APIM provides aggregate metrics, but per-team, per-API, per-consumer observability requires custom Log Analytics queries. Teams cannot self-serve their own traffic data. |
| **No automated security scanning** | New API surfaces are not automatically scanned for OWASP vulnerabilities before going live. Security reviews are manual and inconsistent. |
| **Rate limiting is coarse-grained** | APIM policies apply at the product/subscription level. Per-consumer, per-API tiered rate limiting requires custom policy XML and is difficult to manage at scale. |
| **Team-scoped access control is manual** | There is no built-in concept of "Team A owns these APIs and can only manage their own." Access boundaries are enforced by convention, not by the platform. |

> **Important:** This RFC does NOT propose replacing SNIP. It proposes a complementary capability for teams that need self-service API onboarding with automated governance.

---

## 2. Proposed Capability

A self-service API Gateway platform that allows teams to:

1. **Register their team** and manage membership (owner, admin, member, viewer roles)
2. **Submit APIs** for gateway exposure through a web portal — specifying upstream URL, auth type, rate limits, and gateway path
3. **Go through an approval workflow** — draft → submitted → approved/rejected → activated — with full audit trail
4. **Have the gateway automatically provision** the service, route, auth plugin, rate-limiting plugin, and Prometheus metrics on activation
5. **Monitor their own API traffic** through Grafana dashboards scoped to their services
6. **Receive automated OWASP security scans** (ZAP) against their API surfaces
7. **Manage subscribers and API keys** with per-consumer rate limit overrides

### Architecture at a Glance

```
                    Internet / Internal Consumers
                                |
                      +-------------------+
                      |   Kong Gateway    |  Rate limiting, auth, routing
                      |  (port 8000/8443) |  Custom plugins
                      +-------------------+
                       /        |        \
              +----------+ +----------+ +----------+
              | Team A   | | Team B   | | Team C   |
              | APIs     | | APIs     | | APIs     |
              +----------+ +----------+ +----------+
                                |
                +-------------------------------+
                |     Self-Service Portal       |  FastAPI + Next.js
                |     Teams, API Registry, RBAC |  Entra ID SSO
                +-------------------------------+
                 /              |              \
      +----------+    +-------------+    +-----------+
      | PostgreSQL|    |   Redis     |    |  Entra ID |
      +----------+    +-------------+    +-----------+
                                |
                +-------------------------------+
                |        Observability           |
                | Prometheus | Grafana | Cribl   |
                | ZAP Scanner | AI Analysis     |
                +-------------------------------+
```

### Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| API Gateway | Kong CE 3.9 | Open-source, plugin-extensible, proven at scale, no per-call licensing |
| Admin Backend | FastAPI (Python) | Async, auto-generated OpenAPI docs, strong typing |
| Frontend | Next.js 14 | Server-side rendering, React ecosystem |
| Database | PostgreSQL 16 | Kong's native DB; single engine for gateway config + admin data |
| Cache | Redis 7 | Sessions, RBAC cache, rate-limit counters |
| Auth | Microsoft Entra ID | Existing IdP; OIDC SSO with auto-provisioning |
| Security Scanning | OWASP ZAP | Industry-standard, Prometheus-exportable results |
| Observability | Prometheus + Grafana + Cribl Stream | Metrics, dashboards, log routing |
| AI Analysis | Azure AI Foundry (Claude) | Anomaly detection, recommendations (optional layer) |
| Deployment | Azure Container Apps | Serverless containers on existing Azure subscription |

---

## 3. Access Control Model

Two-layer RBAC ensures both feature access and resource ownership:

**Layer 1 — Platform RBAC** (who can use which features):

| Role | Can Manage Teams/APIs | Can Approve APIs | Can Manage Roles | Read-Only |
|------|----------------------|-----------------|-----------------|-----------|
| super_admin | Yes | Yes | Yes | — |
| admin | Yes | Yes | No | — |
| operator | Yes (submit only) | No | No | — |
| viewer | — | — | — | Yes |

**Layer 2 — Team RBAC** (who can touch which resources):
- Teams own their APIs, subscribers, and keys
- Team roles: owner > admin > member > viewer
- Platform admins bypass team checks for cross-cutting operations

Both layers must pass for any operation.

---

## 4. API Lifecycle

```
  Team creates     Team submits     Admin reviews     Admin activates     Kong serves
  draft API    →   for review   →   approve/reject →  provisions Kong  →  live traffic
                                        ↓
                                    rejected with
                                    notes → team
                                    revises → resubmit
```

**On activation**, Kong automatically receives: service, route, rate-limiting plugin, auth plugin, and Prometheus plugin.

**On retirement**, Kong resources are automatically deprovisioned.

---

## 5. Questions for Reviewing Teams

> **Ground rules:** Answer the specific question asked. Provide constraints, requirements, or risks — not alternative technology proposals. If you don't have a strong opinion, write "no concern" so we know you reviewed it.

---

### 5.1 DevOps / Platform Engineering

**DQ-1. Container App resource limits.** The platform deploys 10 containers. Given our Container Apps environment quotas and cost targets, what memory/CPU limits do you require per service class?

| Service Class | Examples | Your Limit |
|---------------|----------|------------|
| Internet-facing, scaled | Kong (min 2 replicas) | _fill in_ |
| Internet-facing, static | Frontend (2 replicas) | _fill in_ |
| Internal, scaled | Admin panel (2–4 replicas) | _fill in_ |
| Internal, singleton | ZAP, exporters | _fill in_ |
| Monitoring | Prometheus, Grafana, Cribl | _fill in_ |

**DQ-2. Image registry and pipeline.** We push 5 images to ACR with semver tags. Which ACR instance, naming convention, and build pipeline template should we use? Provide the template name or link.

**DQ-3. Database provisioning.** We need two PostgreSQL databases on Flexible Server (one for Kong, one for admin data). Existing instance or new? If new, what tier and HA config?

**DQ-4. Redis provisioning.** Azure Cache for Redis for sessions, RBAC cache, and rate counters. What tier/SKU? Existing instance with capacity?

**DQ-5. Terraform state and modules.** Where should state be stored? Required module versions or naming conventions?

**DQ-6. Secret management.** Eight secrets required (DB passwords, Entra client secret, AI API key, etc.). Azure Key Vault references in Container App config, or different pattern? Provide the Key Vault name.

---

### 5.2 Security Engineering

**SQ-1. Entra ID app registration.** We need an app registration (redirect URI, client secret, scopes: openid/email/profile). What is the approval process? Required token lifetimes, conditional access policies, or app role definitions?

**SQ-2. Network exposure surface.**

| Service | Proposed Exposure | Your Requirement |
|---------|------------------|------------------|
| Kong proxy (8000/8443) | External (internet-facing) | _fill in_ |
| Admin portal (3000) | External (internet-facing) | _fill in_ |
| Kong Admin API (8001) | Internal only | _fill in_ |
| All other services | Internal only | _fill in_ |

**SQ-3. OWASP ZAP scanning scope.** Active scans generate test traffic. Restrict to non-prod only, or acceptable in prod with rate controls? What severity threshold blocks API activation (Critical only? High+)?

**SQ-4. API key management.** Keys are SHA-256 hashed before storage, shown once at creation, rotation is atomic (revoke old + create new). Does this meet requirements, or must keys be stored in Key Vault?

**SQ-5. Audit log retention.** All actions logged with user ID, action, resource, IP, timestamp. Required retention period? SIEM export needed (Splunk, Sentinel)? If so, provide ingestion endpoint.

**SQ-6. TLS requirements.** Kong supports TLS 1.2+. DB connections use sslmode=require. Redis uses TLS. Minimum TLS version, cipher suite, or CA requirements?

---

### 5.3 Network Engineering

**NQ-1. DNS and custom domains.** Kong needs a public DNS record (e.g., `api.<domain>.com`); admin portal needs one (e.g., `api-admin.<domain>.com`). What domains? Who creates records, and what's the lead time?

**NQ-2. VNet integration.** Container Apps can integrate with existing VNet. Required? If so, which VNet/subnet? NSG rules? Provide the VNet resource ID.

**NQ-3. Firewall and egress rules.** Kong calls upstream APIs, ZAP scans targets. Firewall rule changes needed? Private endpoint paths to request?

**NQ-4. WAF / DDoS.** Azure Front Door or App Gateway with WAF required in front of Kong, or is Kong's built-in rate limiting sufficient initially? If WAF required, provide the profile name.

**NQ-5. Health probe requirements.** Kong: `/status` on 8100. Admin panel: `/health` and `/ready` on 8080. Specific interval, timeout, or threshold requirements for your LB probes?

---

## 6. Open Questions

| # | Question | Raised By | Status |
|---|----------|-----------|--------|
| OQ-1 | Should the admin portal be VPN-only, or is Entra ID auth sufficient for internet exposure? | Author | Open |
| OQ-2 | Target timeline for the first team to onboard an API? | Author | Open |
| OQ-3 | Should this platform federate with SNIP's APIM (Kong routes to APIM backends), or operate in parallel? | Author | Open |
| OQ-4 | Compliance requirements (SOC 2, PCI, HIPAA) for APIs exposed through this gateway? | Author | Open |
| OQ-5 | Include AI analysis layer in initial deployment, or defer to later phase? | Author | Open |

---

## 7. Relationship to SNIP

| Concern | Answer |
|---------|--------|
| Does this replace APIM? | No. Existing APIM-managed APIs continue as-is. |
| Does this replace Function Apps? | No. Function Apps remain SNIP's compute layer. |
| Can a team use both? | Yes. Some APIs on APIM/SNIP, others on this gateway. |
| What about teams already on APIM? | They stay unless they choose to migrate. Migration is not proposed here. |
| When would a team use this instead of SNIP? | When they need self-service onboarding, per-API observability, automated security scanning, or team-scoped access control. |
| Could these capabilities be added to SNIP? | Possibly — that would be a separate RFC with its own scope and tradeoffs. |

---

## 8. Supporting Documentation

A working implementation exists in the `api-gateway` repository with 270K of documentation:

| Document | Coverage |
|----------|----------|
| Architecture | System design, data flows, DB schema, network topology |
| Self-Service Guide | Team onboarding and API registration walkthrough |
| Admin Guide | RBAC, approval workflows, Entra ID setup |
| Security | OWASP scanning, auth architecture, threat detection |
| Deployment | Azure Container Apps, scaling, health probes |
| API Reference | 70+ endpoints with request/response schemas |
| Configuration | 100+ environment variables across all services |

---

## 9. Response Instructions

1. **Respond by:** _[Review Deadline — TBD]_
2. **Respond to:** Only the questions in your team's section (5.1, 5.2, or 5.3). Add cross-cutting concerns to Section 6.
3. **Format:** Fill in tables where provided. Open-ended answers under 200 words per question.
4. **If no concern:** Write "No concern" so we know you reviewed it.
5. **Alternative approaches:** Welcome as separate RFCs, not as responses to this one.

---

## 10. Decision Criteria

| Criterion | Threshold |
|-----------|-----------|
| Security Engineering — no unresolved blocking concerns | Required |
| Network Engineering — confirms network path is feasible | Required |
| DevOps — confirms resource/deployment model fits practices | Required |
| Estimated Azure monthly cost within budget | Required |
| At least one team committed to pilot | Recommended |
| AI layer scope agreed (include or defer) | Recommended |

---

## Glossary

| Term | Definition |
|------|-----------|
| **SNIP** | Sleep Number Integration Platform — current pattern using Azure APIM, Function Apps, Cosmos, Storage |
| **Kong** | Open-source API gateway for proxying, auth, rate limiting, plugin execution |
| **APIM** | Azure API Management — Microsoft's managed API gateway |
| **RBAC** | Role-Based Access Control |
| **ZAP** | OWASP Zed Attack Proxy — open-source web security scanner |
| **Entra ID** | Microsoft Entra ID (formerly Azure AD) |
| **ADR** | Architecture Decision Record — documents finalized decisions (distinct from an RFC) |
| **RFC** | Request for Comments — proposes and gathers feedback; does not declare a final decision |
