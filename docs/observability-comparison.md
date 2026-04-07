# Observability: Azure Monitor vs. API Gateway Stack

This document maps Azure Monitor capabilities to the equivalent (or better) tooling in the API Gateway platform. The purpose is to demonstrate that teams migrating from APIM do not lose observability — they gain self-service access to richer, more granular telemetry.

**Target audience:** Architecture reviewers, Security Engineering, DevOps, and teams currently using Azure Monitor Workbooks with APIM.

---

## Summary

| Azure Monitor Feature | API Gateway Equivalent | Assessment |
|---|---|---|
| Application Insights | Cribl pipelines + Prometheus metrics | **Better** — geo-IP enrichment, PII masking, anomaly detection built into the pipeline |
| Log Analytics queries | Grafana + PromQL + Cribl search | **Better** — self-service dashboards, no tickets required |
| Azure Alerts | 36 Prometheus alert rules across 7 groups | **Better** — more granular, pre-built for API gateway use cases |
| Azure Workbooks | 6 Grafana dashboards | **Better** — domain-specific, auto-provisioned, no manual setup |
| Azure Monitor Metrics | Prometheus with 14 recording rules | **Equivalent** |
| Azure Sentinel (SIEM) | Cribl → Splunk HEC (real-time) | **Equivalent** — already integrated |
| Azure Blob Archive | Cribl → S3 (gzip, lifecycle managed) | **Equivalent** |

---

## Detailed Comparisons

### 1. Application Insights → Cribl Pipelines + Prometheus

**What Application Insights does:** Collects request traces, dependency calls, exceptions, and performance counters. Provides a transaction search, application map, and failure analysis.

**What our stack does:**

Cribl Stream processes all telemetry through **5 specialized pipelines**:

| Pipeline | What it processes | Enrichment |
|----------|------------------|------------|
| `kong-logs` | All API request/response logs | Geo-IP (country, city, ASN), field normalization, size categorization |
| `auth-events` | Authentication successes/failures | Subscriber metadata lookup, brute-force detection, credential stuffing detection |
| `rate-limit-metrics` | Rate limit events (429s) | Utilization %, aggregation by consumer/service/window |
| `security-scanning` | OWASP ZAP findings | Severity normalization, OWASP category mapping, PII masking in evidence |
| `ai-events` | AI analysis logs | PII masking (SSN, email, phone, credit card, API keys), hourly cost aggregation |

**What we do that Application Insights does not:**
- **PII masking at the pipeline level** — sensitive data is stripped before it reaches any storage destination
- **Geo-IP enrichment** — every request is tagged with country, city, and ASN from MaxMind GeoLite2
- **Anomaly detection in the pipeline** — brute-force and credential-stuffing patterns are detected in real-time, not after the fact in a query
- **Cost tracking for AI analysis** — per-model, per-provider cost aggregation

### 2. Log Analytics → Grafana + PromQL

**What Log Analytics does:** KQL-based query workspace for searching and analyzing logs. Teams write custom queries to investigate incidents, build reports, and create alerts.

**What our stack does:**

Grafana provides a visual query interface backed by Prometheus (for metrics) and PostgreSQL (for admin panel operational data). PromQL replaces KQL for metric queries.

**Key advantage: self-service.** Teams currently using APIM with Log Analytics typically need to:
1. Request access to the Log Analytics workspace
2. Learn KQL syntax
3. Write and save custom queries
4. Share queries via Workbooks (which require additional setup)

With Grafana, teams get **pre-built dashboards** that answer the most common questions out of the box. For custom queries, PromQL is available in the Explore view — no access requests needed.

### 3. Azure Alerts → Prometheus Alert Rules

**What Azure Alerts does:** Threshold-based alerting on metrics and log queries. Supports action groups (email, SMS, webhook, Logic App).

**What our stack does:**

**36 pre-built alert rules** organized into 7 groups:

| Group | Alert Count | Examples |
|-------|-------------|---------|
| Kong Error Rates | 3 | >5% 5xx (critical), >1% 5xx (warning), >25% 4xx (warning) |
| Kong Latency | 3 | P99 >1000ms (critical), P95 >500ms (warning), P95 doubles vs 1hr avg (warning) |
| Authentication | 3 | >20% auth failures / brute force (critical), >10% failures (warning), 0% success rate (critical) |
| Rate Limiting | 2 | >10 violations/sec (warning), >15% of traffic rate-limited (critical) |
| Infrastructure | 7 | Pod down (critical), >85% memory (warning), >85% CPU (warning), DB connection errors (critical), HPA maxed out (warning) |
| AI Layer | 5 | Provider down (critical), P99 >3s (warning), >10 anomalies/min (warning), cost >$5/hr (warning), cost >$20/hr (critical) |
| OWASP ZAP Security | 5 | Critical vulnerability (critical), >5 medium findings (warning), >10 new findings in 10min (warning), scanner down (warning), scan stale >30min (warning) |

Every alert includes: severity label, component tag, team label, summary, description, impact assessment, runbook URL, and dashboard link.

**What we do that Azure Alerts does not (out of the box):**
- **AI cost budget alerts** — automatic warnings when AI analysis spending exceeds thresholds
- **Security scanner alerts** — ZAP findings trigger alerts in real-time, not as a separate workflow
- **Authentication anomaly alerts** — brute-force and credential-stuffing patterns detected and alerted automatically

### 4. Azure Workbooks → Grafana Dashboards

**What Workbooks does:** Interactive visual reports combining metrics, logs, and text. Teams create custom workbooks for their specific monitoring needs.

**What our stack does:**

**6 auto-provisioned dashboards**, each focused on a specific domain:

| Dashboard | Key Panels |
|-----------|-----------|
| **Gateway Overview** | Total req/sec with thresholds, error rates (5xx/4xx), P95/P99 latencies, breakdown by service and route |
| **Authentication** | Auth success/failure rates, method breakdown, failed login patterns |
| **Rate Limiting** | Violations by consumer, utilization percentages, violation rates per service |
| **Infrastructure** | CPU/memory by container, pod health, node capacity |
| **Security Scanning** | ZAP findings by severity, scan results timeline, OWASP Top 10 categories |
| **AI Layer** | Analysis latency, cost tracking, anomaly detection metrics, provider/model breakdown |

**Key advantage:** These dashboards are **provisioned automatically** when the stack starts. Teams using Azure Workbooks must create their own — which means most teams have incomplete monitoring until someone invests the time to build it.

### 5. Azure Monitor Metrics → Prometheus + Recording Rules

**What Azure Monitor Metrics does:** Platform metrics (CPU, memory, requests) with 1-minute granularity and 93-day retention.

**What our stack does:**

Prometheus scrapes **9 targets** at 15-30 second intervals with 15-day local retention (extensible via remote write to long-term storage).

**14 recording rules** pre-compute frequently accessed aggregates:

| Rule | What it computes |
|------|-----------------|
| `kong_request_rate:5m` | Request rate by service, route, status code |
| `kong_request_rate_by_service:5m` | Aggregated by service |
| `kong_latency_p50:5m` | Median latency |
| `kong_latency_p95:5m` | 95th percentile latency |
| `kong_latency_p99:5m` | 99th percentile latency |
| `kong_auth_success_rate:5m` | Auth success rate by service |
| `kong_rate_limit_violations:5m` | Rate limit violations by service/consumer |
| `ai_analysis_rate:5m` | AI analysis rate by type/provider/model |
| `ai_anomaly_detection_rate:5m` | Anomaly detection rate by action |
| `ai_average_latency:5m` | Average AI analysis latency |
| `ai_cost_rate:1h` | Hourly AI cost by provider/model |
| `ai_anomaly_block_rate:5m` | Anomaly block rate |

### 6. Azure Sentinel → Cribl → Splunk HEC

**What Sentinel does:** Cloud-native SIEM for security event correlation, threat hunting, and incident response.

**What our stack does:**

Cribl routes security-relevant events to **Splunk HEC** in real-time:
- High-severity ZAP findings → `security_alerts` index
- Auth anomalies (brute force, credential stuffing) → Splunk + AlertManager webhook
- AI high-severity anomalies → Splunk + AlertManager webhook
- All events → S3 archive for long-term retention

**Cribl adds value before the SIEM sees the data:**
- PII is masked (emails, SSNs, phone numbers, credit cards, API keys)
- Severity is normalized across sources
- Events are enriched with subscriber metadata and geo-IP
- Health check noise is filtered out

### 7. Azure Blob Archive → Cribl → S3

**What Azure Blob does:** Tiered storage (hot/cool/archive) for long-term log retention.

**What our stack does:**

Cribl writes to S3 with:
- Path pattern: `kong/{environment}/{date}/{sourcetype}/{hour}/`
- Compression: gzip
- Max file size: 32MB
- Persistent queue: 5GB (survives Cribl restarts)
- Lifecycle: 300s max open time before rotation

---

## What Azure Monitor Has That We Don't (Yet)

| Azure Feature | Status | Path Forward |
|---|---|---|
| Application Map (dependency visualization) | Not implemented | Can be built as a Grafana panel using service mesh telemetry |
| Live Metrics Stream (real-time view) | Partially covered by Grafana auto-refresh (30s) | Grafana Live supports WebSocket streaming for true real-time |
| Profiler / Snapshot Debugger | Not applicable | Not a gateway concern — this is application-level |
| Smart Detection (ML-based anomalies) | Covered differently — Cribl pipeline rules + AI layer | Our anomaly detection is API-gateway-specific, not generic |

---

## Cost Comparison

| Component | Azure APIM + Monitor | API Gateway Stack |
|---|---|---|
| API Gateway | Azure APIM per-unit pricing ($0.07-$3.40/1M calls depending on tier) | Kong CE — **free** (open source) |
| Metrics | Azure Monitor Metrics — included but limited retention | Prometheus — **free** (open source), 15-day retention |
| Dashboards | Azure Workbooks — free but manual | Grafana — **free** (open source), 6 pre-built dashboards |
| Log Processing | Log Analytics — per-GB ingestion ($2.76/GB) | Cribl — **already deployed**, no additional cost |
| Alerting | Azure Alerts — per-rule pricing ($0.10-$1.50/rule/month) | Prometheus AlertManager — **free**, 36 rules included |
| SIEM | Azure Sentinel — per-GB pricing ($2.46/GB) | Splunk — **already deployed** via Cribl integration |
| Archive | Azure Blob — per-GB storage | S3 — **already available** via Cribl integration |

The infrastructure cost for the API Gateway observability stack is **$0 in additional licensing**. It runs on Docker containers (or Kubernetes pods) using infrastructure Sleep Number already operates.
