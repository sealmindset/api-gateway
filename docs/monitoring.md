# Monitoring and Observability

## Overview

The API Gateway observability stack provides full visibility into API traffic, security posture, and infrastructure health. Four core components work together:

| Component | Role | Default Port |
|---|---|---|
| **Prometheus** | Metrics collection, recording rules, alerting rules | 9090 |
| **Grafana** | Visualization and dashboarding | 3200 |
| **Cribl Stream** | Log routing, enrichment, and fan-out to multiple destinations | 9420 |
| **AlertManager** | Alert grouping, deduplication, and notification delivery | 9093 |

All components are deployed via Docker Compose and are pre-configured with dashboards, pipelines, and alert rules out of the box.

---

## Prometheus

### Scrape Configuration

Prometheus collects metrics from every layer of the platform at two intervals depending on the volatility of the target.

| Target | Endpoint | Scrape Interval | Notes |
|---|---|---|---|
| Kong Gateway | `:8100/metrics` | 15s | Prometheus plugin exposes request, latency, and bandwidth counters |
| Node Exporter | `:9100/metrics` | 15s | Host-level CPU, memory, disk, and network |
| cAdvisor | `:8080/metrics` | 15s | Per-container resource usage |
| Admin Panel | `/api/metrics` | 30s | Application-level metrics for the management UI |
| ZAP Exporter | `:9290/metrics` | 30s | OWASP ZAP scanner status and vulnerability counts |

### Remote Write

Prometheus is configured to remote-write a filtered subset of metrics to Cribl Stream for downstream fan-out. Only metrics matching the following prefixes are forwarded:

- `kong_*`
- `node_*`
- `container_*`
- `zap_*`

### Recording Rules

Recording rules pre-aggregate expensive queries so dashboards and alerts can evaluate quickly.

| Rule | Description |
|---|---|
| `gateway:request_rate:by_service_code` | Request rate broken down by service, route, and HTTP status code |
| `gateway:latency_p50:by_service` | 50th percentile request latency per service |
| `gateway:latency_p95:by_service` | 95th percentile request latency per service |
| `gateway:latency_p99:by_service` | 99th percentile request latency per service |
| `gateway:auth_success_rate` | Ratio of successful authentications to total auth attempts |
| `gateway:rate_limit_violations` | Rate of 429 responses across all services |
| `ai:analysis_rate` | Volume of AI-layer analysis requests per second |
| `ai:analysis_cost` | Estimated cost of AI analysis over a rolling window |

---

## Alert Rules

The platform ships with 30+ alert rules organized into six groups. Every rule includes a severity label (`CRITICAL` or `WARNING`) and a human-readable summary annotation.

### Kong Error Rates

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `KongHighErrorRate` | 5xx responses > 5% of total requests | 2m | CRITICAL | A significant share of requests are failing server-side. Investigate upstream health immediately. |
| `KongElevatedErrorRate` | 5xx responses > 1% of total requests | 5m | WARNING | Server errors are above baseline. Review error logs for a pattern. |
| `KongHigh4xxRate` | 4xx responses > 25% of total requests | 5m | WARNING | High client-error rate may indicate a misconfigured consumer, bad deployment, or scanning activity. |

### Kong Latency

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `KongHighLatencyP99` | P99 request latency > 1s | 3m | CRITICAL | Tail latency has breached the 1-second SLO. Check upstream services and database connections. |
| `KongHighLatencyP95` | P95 request latency > 500ms | 5m | WARNING | Latency is elevated for most users. Look for slow upstreams or resource contention. |
| `KongUpstreamLatencySpike` | Upstream latency > 2x the hourly rolling average | 5m | WARNING | A sudden increase relative to recent history suggests a regression or resource issue in the upstream. |

### Authentication

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `KongAuthFailureSpike` | 401/403 responses > 20% of total requests | 2m | CRITICAL | A sharp increase in auth failures may indicate a brute-force attack or credential compromise. |
| `KongNoAuthSuccesses` | Auth success rate = 0% (all attempts failing) | 5m | CRITICAL | No consumers are authenticating successfully. Likely a misconfigured auth plugin or identity provider outage. |

### Rate Limiting

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `KongRateLimitViolationSpike` | Rate-limit 429 responses > 10/s | 2m | WARNING | A consumer or set of consumers is hitting limits at an unusual pace. |
| `KongRateLimitViolationCritical` | 429 responses > 15% of total requests | 5m | CRITICAL | A large fraction of traffic is being rejected. Verify rate-limit configuration and check for abuse. |

### Infrastructure

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `KongPodDown` | Kong pod target is unreachable | 1m | CRITICAL | The gateway process is not responding to health checks. |
| `KongPodHighMemory` | Container memory utilization > 85% | 5m | WARNING | Pod is approaching its memory limit and may be OOM-killed. |
| `KongPodHighCPU` | Container CPU utilization > 85% | 5m | WARNING | Pod is CPU-bound and may begin dropping requests. |
| `KongPodRestarting` | > 3 restarts in the last hour | — | WARNING | Frequent restarts suggest a crash loop or resource pressure. |
| `KongDatabaseConnectionErrors` | Database connection errors > 0 | 2m | CRITICAL | Kong cannot reach its datastore. Declarative or DB-less modes are unaffected. |
| `KongDatabaseLatencyHigh` | Database query latency elevated | 5m | WARNING | Slow datastore queries will degrade configuration propagation. |
| `KongHPAMaxedOut` | HPA is at maximum replica count | 10m | WARNING | Autoscaler has no headroom to add replicas. Consider raising the max or optimizing resource usage. |

### AI Layer

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `AIProviderDown` | AI provider error rate > 95% | 2m | CRITICAL | The AI analysis backend is effectively unreachable. Failover or circuit-break. |
| `AIAnomalySpike` | > 10 anomalies detected per minute | 5m | WARNING | The anomaly detector is firing at an elevated rate. May be a real attack or a noisy model. |
| `AICostBudgetWarning` | Estimated AI spend > $5/hr | 5m | WARNING | AI analysis costs are above the soft budget threshold. |
| `AICostBudgetCritical` | Estimated AI spend > $20/hr | 2m | CRITICAL | AI analysis costs have exceeded the hard budget threshold. Automatic throttling may engage. |

### OWASP ZAP Security

| Alert | Condition | For | Severity | Description |
|---|---|---|---|---|
| `ZAPCriticalVulnerability` | High-severity finding count > 0 | — | CRITICAL | ZAP has detected a high-severity vulnerability. Triage and remediate immediately. |
| `ZAPScannerDown` | ZAP exporter unreachable | 5m | WARNING | The security scanner is not responding. Scans are not running. |
| `ZAPScanStale` | Time since last completed scan > 30m | — | WARNING | Scans should complete on a regular cadence. Investigate whether ZAP is stuck or misconfigured. |

---

## Grafana Dashboards

Six dashboards are pre-provisioned and available at `http://<host>:3200`. Default credentials are `admin` / `admin`.

### 1. Gateway Overview

High-level health of the API Gateway.

- Request rate (total and per-service)
- Error rate (4xx and 5xx)
- Latency percentiles (P50, P95, P99)
- Top services by request volume
- Bandwidth in/out

### 2. Authentication

Visibility into authentication activity and failures.

- Auth success vs. failure rate over time
- Failure breakdown by type (401 Unauthorized vs. 403 Forbidden)
- Top failing consumers
- Auth failure heatmap by time of day

### 3. Rate Limiting

Rate-limit policy effectiveness and consumer behavior.

- 429 violation rate over time
- Top rate-limited consumers
- Limit utilization percentage by tier (e.g., free, standard, premium)
- Violation trend by service

### 4. Infrastructure

Container and host-level resource monitoring.

- Pod CPU and memory utilization
- Restart counts over time
- Database connection pool usage
- HPA current vs. desired replica count
- Node-level disk and network I/O

### 5. AI Layer

Monitoring for the AI analysis and anomaly-detection subsystem.

- Analysis request volume over time
- Anomaly detection count and rate
- Estimated cost tracking (hourly and daily)
- AI provider latency distribution
- Model performance (accuracy, false-positive rate)

### 6. Security Scanning

OWASP ZAP scanner status and findings.

- Scanner status indicator (idle, running, completed, error)
- Vulnerability counts by severity (High, Medium, Low, Informational)
- OWASP Top 10 category breakdown
- Scan duration over time
- Alert trend over time (new vs. resolved)
- Top vulnerability types

---

## Cribl Stream Pipeline

Cribl Stream acts as the central log and event router, accepting data from multiple sources, enriching it, and fanning it out to the appropriate destinations.

Access the Cribl UI at `http://<host>:9420`.

### Inputs

| Input | Protocol | Port | Source |
|---|---|---|---|
| ZAP Events | HTTP | 9081 | ZAP exporter pushes scan results and findings |
| Kong Syslog | Syslog (TCP) | 5514 | Kong access logs and error logs via syslog plugin |
| Kong HTTP Log | HTTP | 9080 | Kong HTTP log plugin sends per-request JSON payloads |
| Prometheus Remote Write | HTTP | 9090 | Prometheus forwards filtered metric samples |

### Routes

Cribl evaluates events against six routes in order. The first matching route wins.

| # | Route | Filter | Pipeline | Destinations |
|---|---|---|---|---|
| 1 | Kong Access Logs | Syslog source, access log format | `kong-logs` | Splunk, S3, Prometheus |
| 2 | Auth Events | HTTP status 401 or 403 | `auth-events` | Splunk, S3, AlertManager (if anomalous) |
| 3 | Rate Limit Events | HTTP status 429 | `rate-limit-metrics` | Prometheus, S3 |
| 4 | Security Scan Findings | Source = ZAP exporter | `security-scanning` | Splunk (severity >= 3), S3, AlertManager |
| 5 | Prometheus Metrics | Prometheus remote write format | passthrough | Prometheus remote write |
| 6 | Default | Catch-all | none | S3 archive |

### Pipeline Features

All pipelines share a common set of enrichment and safety functions:

- **JSON parsing** -- Structured fields are extracted from raw log lines.
- **Field extraction** -- Service name, route, consumer, and status code are promoted to top-level fields.
- **PII masking** -- Bearer tokens, API keys, and email addresses are redacted before data leaves the pipeline.
- **Severity-based routing** -- Security findings are forwarded to Splunk only when severity >= 3 (Medium and above).
- **OWASP category labeling** -- ZAP findings are tagged with their OWASP Top 10 category for downstream aggregation.
- **Metadata enrichment** -- Environment, cluster, and deployment version are appended to every event.

### Outputs

| Destination | Transport | Configuration |
|---|---|---|
| **Splunk** | HEC (HTTPS) | Real-time hot tier. 1 GB persistent queue, gzip compression, 5 sender workers. |
| **S3** | S3 API | Archive tier. Date-partitioned prefixes (`year/month/day/hour`). Files are flushed at 32 MB or on a time interval. |
| **Prometheus** | Remote write | Forwards converted metrics back to Prometheus for alerting and dashboarding. |
| **AlertManager** | Webhook | Fires alerts for anomalous auth events and high-severity security findings. |

---

## Key Metrics to Watch

The following metrics are the most important for day-to-day operations and incident response.

| Metric | Type | Labels | Description |
|---|---|---|---|
| `kong_http_requests_total` | Counter | `service`, `route`, `code` | Total HTTP requests processed by the gateway. Primary indicator of traffic volume and error rates. |
| `kong_request_latency_ms` | Histogram | `service`, `route` | End-to-end request latency as seen by Kong (includes upstream time). Use for P50/P95/P99 calculations. |
| `kong_upstream_latency_ms` | Histogram | `service`, `route` | Time spent waiting for the upstream service to respond. Isolates backend performance from gateway overhead. |
| `zap_alerts_active` | Gauge | `severity` | Number of currently active security findings by severity level. Should be zero for `high`. |
| `zap_scan_status` | Gauge | — | Scanner state: `0` = idle, `1` = running, `2` = completed, `3` = error. Alert if stuck in error state. |

### Useful PromQL Examples

**Request error rate (5xx) over the last 5 minutes:**

```promql
sum(rate(kong_http_requests_total{code=~"5.."}[5m]))
  /
sum(rate(kong_http_requests_total[5m]))
```

**P99 latency by service:**

```promql
histogram_quantile(0.99, sum by (service, le) (rate(kong_request_latency_ms_bucket[5m])))
```

**Auth failure rate:**

```promql
sum(rate(kong_http_requests_total{code=~"401|403"}[5m]))
  /
sum(rate(kong_http_requests_total[5m]))
```

**Active high-severity vulnerabilities:**

```promql
zap_alerts_active{severity="high"}
```
