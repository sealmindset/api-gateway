# RFC-001: Self-Service API Gateway Platform

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Author** | Platform Engineering |
| **Date** | 2026-04-06 |
| **Review Deadline** | _TBD_ |
| **Decision Authority** | Architecture Review Committee |
| **Reviewers** | DevOps / Platform Engineering, Security Engineering, Network Engineering |

---

## 1. Problem Statement

Sleep Number's current integration pattern (SNIP) uses Azure API Management (APIM), Function Apps, Cosmos DB, and Storage Accounts -- a stack originally stood up to replace MuleSoft. While SNIP serves its purpose for existing integrations, the following operational gaps have emerged:

| Gap | Impact |
|-----|--------|
| **No self-service API onboarding** | Every new API exposure requires a ticket to the platform team. Teams wait days to weeks for manual APIM configuration, Function App setup, and Cosmos provisioning. |
| **No unified approval workflow** | API exposure decisions happen in Slack threads and email chains. There is no auditable record of who approved what, when, or why. |
| **Limited observability per API** | APIM provides aggregate metrics, but per-team, per-API, per-consumer observability requires custom Log Analytics queries. Teams cannot self-serve their own traffic data. |
| **No automated security scanning** | New API surfaces are not automatically scanned for OWASP vulnerabilities before going live. Security reviews are manual and inconsistent. |
| **Rate limiting is coarse-grained** | APIM policies apply at the product/subscription level. Per-consumer, per-API tiered rate limiting requires custom policy XML and is difficult to manage at scale. |
| **Team-scoped access control is manual** | There is no built-in concept of "Team A owns these APIs and can only manage their own." Access boundaries are enforced by convention, not by the platform. |

**This RFC does NOT propose replacing SNIP.** Existing integrations running on APIM/Function Apps/Cosmos continue to operate. This RFC proposes a complementary capability for teams that need to expose APIs through a managed gateway with self-service onboarding, automated security scanning, and team-scoped governance.

### What This RFC Is

- A proposal for a **new capability** that addresses the gaps listed above
- A request for **specific, targeted feedback** from each reviewing team
- Input for the Architecture Review Committee to make a go/no-go decision

### What This RFC Is NOT

- A declaration that this is the final architecture (that will be an ADR after approval)
- A proposal to replace SNIP, APIM, or any existing integration
- A comparison of Kong vs. APIM (the technology choice is a means to the capability, not the point)

---

## 2. Proposed Capability

A self-service API Gateway platform that allows teams to:

1. **Register their team** and manage membership (owner, admin, member, viewer)
2. **Submit APIs** for gateway exposure through a web portal -- specifying upstream URL, auth type, rate limits, and gateway path
3. **Go through an approval workflow** -- draft → submitted → approved/rejected → activated -- with full audit trail
4. **Have Kong automatically provision** the service, route, auth plugin, rate-limiting plugin, and Prometheus metrics on activation
5. **Monitor their own API traffic** through Grafana dashboards scoped to their services
6. **Receive automated OWASP security scans** (ZAP) against their API surfaces before and after activation
7. **Manage subscribers and API keys** with per-consumer rate limit overrides
8. **Define data contracts** on APIs -- contacts (who to call on failures), SLA targets (latency, uptime), change management policies (deprecation notice, versioning), and schema constraints (max request size, OpenAPI spec)
9. **Browse a public API catalog** -- subscribers discover available APIs and their contracts without authentication

### Architecture Summary

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

### Technology Choices and Rationale

| Component | Choice | Why This, Not Something Else |
|-----------|--------|------------------------------|
| API Gateway | Kong CE 3.9 | Open-source, plugin-extensible, Lua/Go plugin SDK, declarative config, proven at scale. Does not require per-call licensing. |
| Admin Backend | FastAPI (Python) | Async, auto-generates OpenAPI docs, strong typing with Pydantic, fast development velocity. |
| Frontend | Next.js 14 | Server-side rendering, React ecosystem, file-based routing. |
| Database | PostgreSQL 16 | Kong's native database. Single engine for both gateway config and admin data (separate databases). |
| Cache | Redis 7 | Session storage, RBAC permission cache (5-min TTL), rate-limit counters for Kong. |
| Auth | Microsoft Entra ID (OIDC) | Already our IdP. Users authenticate with existing credentials. Auto-provisioned on first login. |
| Security Scanning | OWASP ZAP | Industry-standard open-source scanner. Passive + active scanning. Prometheus-exportable results. |
| Observability | Prometheus + Grafana + Cribl Stream | Prometheus for metrics, Grafana for dashboards, Cribl for log routing/enrichment. |
| AI Analysis | Azure AI Foundry (Claude) | Anomaly detection, rate-limit recommendations, smart routing suggestions. Optional layer -- platform works without it. |
| Deployment | Azure Container Apps | Serverless containers on our existing Azure subscription. No K8s cluster management overhead. |

---

## 3. Access Control Model

The platform enforces a two-layer RBAC model:

**Layer 1 -- Platform RBAC** (who can use which features):
- `super_admin`: Full access including role management
- `admin`: Full access except role management
- `operator`: Day-to-day ops, can submit APIs but cannot approve (separation of duties)
- `viewer`: Read-only

**Layer 2 -- Team RBAC** (who can touch which resources):
- Teams own their APIs, subscribers, and keys
- Team roles: owner > admin > member > viewer
- Platform admins bypass team checks for cross-cutting operations

Both layers must pass. A user needs the right platform permission AND the right team membership.

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

On activation, Kong automatically receives:
- A **service** pointing to the upstream URL
- A **route** mapped to the gateway path
- A **rate-limiting plugin** (per-second/minute/hour)
- An **auth plugin** (key-auth, OAuth 2.0, JWT, or none)
- A **Prometheus plugin** for per-service metrics

On retirement, Kong resources are automatically deprovisioned.

---

## 5. What We Need From Each Team

This section contains specific questions for each reviewing team. Please respond only to your team's section. Each question is scoped to your domain of expertise and asks for concrete input that will directly shape the implementation.

**Ground rules for responses:**
- Answer the specific question asked. If you have concerns outside these questions, add them in Section 6 (Open Questions).
- Provide constraints, requirements, or risks -- not alternative technology proposals. Technology alternatives belong in a separate RFC if warranted.
- If you don't have a strong opinion on a question, say "no concern" so we know you reviewed it.

---

### 5.1 DevOps / Platform Engineering

You own the CI/CD pipelines, container infrastructure, and deployment processes. Your input determines whether this platform can be built, deployed, and operated within our existing practices.

**DQ-1. Container App resource allocation.** The platform deploys 10 containers (Kong, admin-panel, frontend, PostgreSQL, Redis, Prometheus, Grafana, Cribl, ZAP, ZAP-exporter). Given our current Azure Container Apps environment quotas and cost targets, are there specific memory/CPU limits or replica caps you need us to adhere to? If so, provide them per service class (internet-facing, internal, monitoring).

| Service Class | Examples | Your Limit |
|---------------|----------|------------|
| Internet-facing, scaled | Kong (min 2 replicas) | _fill in_ |
| Internet-facing, static | Frontend (2 replicas) | _fill in_ |
| Internal, scaled | Admin panel (2-4 replicas) | _fill in_ |
| Internal, singleton | ZAP, exporters | _fill in_ |
| Monitoring | Prometheus, Grafana, Cribl | _fill in_ |

**DQ-2. Image registry and build pipeline.** We plan to push 5 container images to ACR and tag with semver. Do you require a specific ACR instance, image naming convention, or build pipeline template (e.g., must use GitHub Actions reusable workflow X, or ADO pipeline template Y)? Provide the template name or link.

**DQ-3. Database provisioning.** The platform needs two PostgreSQL databases (one for Kong, one for admin data) on Azure Database for PostgreSQL Flexible Server. Do you have an existing Flexible Server we should use, or should we provision a new one? If new, what tier (Burstable B1ms, General Purpose D2s, etc.) and HA configuration do you require?

**DQ-4. Redis provisioning.** We need Azure Cache for Redis for session storage, RBAC caching, and Kong rate-limit counters. What tier and SKU do you require? Do you have an existing Redis instance with available capacity?

**DQ-5. Terraform state and modules.** We have Terraform configs for all Azure resources. Where should state be stored (which Storage Account / container)? Are there required Terraform module versions or naming conventions we must follow?

**DQ-6. Secret management.** The platform requires 8 secrets (DB passwords, Entra client secret, AI API key, etc.). What is the approved pattern -- Azure Key Vault references in Container App config, or a different mechanism? Provide the Key Vault name or policy.

---

### 5.2 Security Engineering

You own application security, vulnerability management, identity, and compliance. Your input determines whether this platform meets security standards before it goes live.

**SQ-1. Entra ID app registration.** The platform needs an app registration with redirect URI, client secret, and scopes (openid, email, profile). What is the approval process for creating this? Do you require specific token lifetime settings, conditional access policies, or app role definitions beyond what Entra provides by default?

**SQ-2. Network exposure surface.** Only two services are internet-facing: Kong (API proxy on 8000/8443) and the Next.js frontend (admin portal on 3000). The Kong Admin API (8001) is internal-only and never exposed. Is this exposure model acceptable, or do you require the admin portal to also be internal-only (accessible via VPN/private endpoint)?

| Service | Proposed Exposure | Your Requirement |
|---------|------------------|------------------|
| Kong proxy (8000/8443) | External (internet-facing) | _fill in_ |
| Admin portal (3000) | External (internet-facing) | _fill in_ |
| Kong Admin API (8001) | Internal only | _fill in_ |
| All other services | Internal only | _fill in_ |

**SQ-3. OWASP ZAP scanning scope.** ZAP runs passive scans continuously and active scans on-demand against APIs registered in the gateway. Active scans generate test traffic against upstream services. Do you require active scanning to be restricted to non-production environments only, or is active scanning in production acceptable with rate controls? What is your finding severity threshold for blocking an API activation (Critical only? High and above?)?

**SQ-4. API key storage and rotation.** API keys are generated server-side, hashed with SHA-256 before database storage, and synced to Kong consumers. The plaintext key is shown once at creation time. Key rotation revokes the old key and creates a new one atomically. Does this meet your key management requirements, or do you require integration with a specific secrets vault (e.g., keys stored in Key Vault, not PostgreSQL)?

**SQ-5. Audit log retention and export.** All RBAC actions, API lifecycle changes, and access decisions are logged to an append-only audit_logs table with user ID, action, resource, IP address, and timestamp. What is the required retention period? Do you need audit logs exported to a SIEM (Splunk, Sentinel)? If so, provide the ingestion endpoint or Cribl destination name.

**SQ-6. TLS requirements.** Kong supports TLS 1.2+ with configurable cipher suites. Database connections use `sslmode=require`. Redis uses TLS. Do you have a specific minimum TLS version, cipher suite list, or certificate authority requirement (e.g., must use internal CA, not Let's Encrypt)?

---

### 5.3 Network Engineering

You own DNS, load balancing, firewall rules, and VNet architecture. Your input determines how traffic reaches the gateway and how services communicate.

**NQ-1. DNS and custom domains.** Kong needs a public DNS record (e.g., `api.<domain>.com`) and the admin portal needs one (e.g., `api-admin.<domain>.com`). Azure Container Apps supports custom domains with managed TLS certificates. What domain(s) should we use? Who creates the CNAME/A records, and what is the lead time?

**NQ-2. VNet integration.** Azure Container Apps can integrate with an existing VNet for internal service-to-service traffic and private endpoint access to Azure Database/Redis. Do you require VNet integration? If so, which VNet and subnet should we use, and are there existing NSG rules we need to conform to? Provide the VNet resource ID.

**NQ-3. Firewall and egress rules.** Kong makes outbound calls to upstream APIs (team backends). The admin panel calls the Kong Admin API (internal). ZAP makes outbound calls to scan targets. Do any of these outbound paths require firewall rule changes? If upstream APIs are behind private endpoints or in peered VNets, list the network paths we need to request.

**NQ-4. WAF / DDoS placement.** Do you require Azure Front Door or Application Gateway with WAF in front of Kong, or is Kong's built-in rate limiting and auth sufficient for the initial deployment? If WAF is required, provide the Front Door profile or App Gateway name.

**NQ-5. Load balancer health probes.** Kong exposes a status endpoint on port 8100 (`/status`). The admin panel exposes `/health` (liveness) and `/ready` (readiness, checks DB + Redis). Do your load balancer health probe configurations have specific interval, timeout, or threshold requirements?

---

## 5b. Observability: Azure Monitor Equivalence

Teams currently using Azure Monitor (Application Insights, Log Analytics, Azure Alerts, Workbooks) with APIM will find equivalent or better capabilities in this platform's observability stack.

| Azure Monitor Feature | This Stack | Assessment |
|---|---|---|
| Application Insights | Cribl (5 pipelines) + Prometheus | **Better** — geo-IP enrichment, PII masking, anomaly detection in pipeline |
| Log Analytics / KQL | Grafana + PromQL | **Better** — self-service dashboards, no tickets needed |
| Azure Alerts | 36 Prometheus alert rules (7 groups) | **Better** — more granular, pre-built for API gateway |
| Azure Workbooks | 6 Grafana dashboards (auto-provisioned) | **Better** — domain-specific, zero setup |
| Azure Monitor Metrics | Prometheus + 14 recording rules | **Equivalent** |
| Azure Sentinel (SIEM) | Cribl → Splunk HEC (real-time) | **Equivalent** — already integrated |

Cribl Stream is **already deployed** in the Sleep Number environment. Grafana and Prometheus run as containers alongside the gateway. No additional licensing is required.

For the full comparison, including what Azure Monitor provides that this stack does not yet cover, see [Observability Comparison](observability-comparison.md).

---

## 6. Open Questions

This section captures questions that don't fit neatly into one team's domain, or that emerged during the RFC drafting process. Any reviewer may add questions here.

| # | Question | Raised By | Status |
|---|----------|-----------|--------|
| OQ-1 | Should the admin portal be accessible only via VPN, or is Entra ID authentication sufficient for internet exposure? | Author | Open |
| OQ-2 | What is the target timeline for the first team to onboard an API through this platform? | Author | Open |
| OQ-3 | Should this platform federate with SNIP's existing APIM instance (e.g., Kong routes to APIM-managed backends), or operate as a parallel path? | Author | Open |
| OQ-4 | Are there compliance requirements (SOC 2, PCI, HIPAA) that apply to APIs exposed through this gateway? If so, which controls apply? | Author | Open |
| OQ-5 | Should the AI analysis layer (anomaly detection, smart routing) be included in the initial deployment, or deferred to a later phase? | Author | Open |

---

## 7. Relationship to SNIP

This capability is **additive to SNIP**, not a replacement.

| Concern | Answer |
|---------|--------|
| Does this replace APIM? | No. Existing APIM-managed APIs continue as-is. |
| Does this replace Function Apps? | No. Function Apps remain the compute layer for SNIP integrations. |
| Can a team use both? | Yes. A team could have some APIs on APIM/SNIP and others on this gateway. |
| What about teams already on APIM? | They stay on APIM unless they choose to migrate. Migration is not proposed here. |
| When would a team use this instead of SNIP? | When they need self-service onboarding, per-API observability, automated security scanning, or team-scoped access control -- capabilities SNIP does not currently provide. |
| Could these capabilities be added to SNIP instead? | Possibly. That would be a separate RFC with its own scope, timeline, and tradeoffs. This RFC proposes one path; alternatives are welcome as separate proposals. |

---

## 8. Proof of Capability

A working implementation exists in the `api-gateway` repository. The following documentation is available for reviewers who want to go deeper:

| Document | What It Covers |
|----------|---------------|
| [Architecture](architecture.md) | System design, data flows, database schema, network topology |
| [Self-Service Guide](self-service-guide.md) | End-to-end team onboarding and API registration walkthrough |
| [Admin Guide](admin-guide.md) | RBAC, approval workflows, Entra ID setup |
| [Kong Gateway](kong-gateway.md) | Custom plugins, rate limiting, auth methods |
| [Security](security.md) | OWASP scanning, auth architecture, threat detection |
| [Deployment](deployment.md) | Azure Container Apps deployment, scaling, health probes |
| [API Reference](api-reference.md) | All 70+ API endpoints with schemas |
| [Configuration](configuration.md) | 100+ environment variables across all services |
| [Troubleshooting](troubleshooting.md) | Common issues, debugging, recovery procedures |

---

## 9. Response Instructions

1. **Respond by:** _[Review Deadline TBD]_
2. **Respond in:** Comments on this document (PR, Confluence, or email thread -- per committee process)
3. **Respond to:** Only the questions in your team's section (5.1, 5.2, or 5.3). Add cross-cutting concerns to Section 6.
4. **Format:** Fill in the tables where provided. For open-ended questions, keep responses under 200 words per question.
5. **If you have no concern** on a question, write "No concern" so we know you reviewed it rather than skipped it.
6. **If you believe this capability should not proceed**, state the specific risk or requirement that blocks it, not an alternative technology preference. Alternative approaches are welcome as separate RFCs.

---

## 10. Decision Criteria

The Architecture Review Committee will evaluate this RFC based on:

| Criterion | Threshold |
|-----------|-----------|
| Security Engineering has no unresolved **blocking** concerns | Required |
| Network Engineering confirms network path is feasible | Required |
| DevOps confirms resource/deployment model fits existing practices | Required |
| Estimated Azure monthly cost is within budget envelope | Required |
| At least one team has committed to pilot onboarding | Recommended |
| AI analysis layer scope is agreed (include or defer) | Recommended |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **SNIP** | Sleep Number Integration Platform -- the current integration pattern using Azure APIM, Function Apps, Cosmos DB, and Storage Accounts |
| **Kong** | Open-source API gateway that handles proxying, auth, rate limiting, and plugin execution |
| **APIM** | Azure API Management -- Microsoft's managed API gateway service |
| **RBAC** | Role-Based Access Control -- permissions assigned through roles rather than directly to users |
| **ZAP** | OWASP Zed Attack Proxy -- open-source security scanner for web applications |
| **Entra ID** | Microsoft Entra ID (formerly Azure AD) -- Microsoft's identity and access management service |
| **ADR** | Architecture Decision Record -- a document recording a finalized architectural decision (distinct from an RFC) |
| **Cribl Stream** | Observability pipeline for routing, enriching, and filtering log/metric data |
