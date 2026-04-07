# AI-Powered Features

## Overview

The API Gateway platform integrates Claude (via Azure AI Foundry or direct Anthropic API) for intelligent API traffic analysis. The AI layer provides:

- **Anomaly Detection** -- identify suspicious or unusual request patterns in real time
- **Rate Limit Recommendations** -- suggest optimal rate limits based on actual consumer usage
- **Smart Routing** -- select the best backend for each request based on health and context
- **Request/Response Transformation** -- apply natural-language transformation rules to payloads
- **Documentation Generation** -- produce API documentation from OpenAPI specs or live traffic

AI analysis is cost-controlled. Each individual analysis call is budgeted (default $0.50), and only a configurable fraction of traffic is sampled (default 10%). Prometheus metrics, alerting rules, and a Grafana dashboard provide real-time cost visibility.

---

## AI Provider Configuration

The platform supports two providers. Set the active provider with the `AI_PROVIDER` environment variable.

| Provider | `AI_PROVIDER` value | Required env vars |
|---|---|---|
| Azure AI Foundry (default) | `anthropic_foundry` | `AZURE_AI_FOUNDRY_ENDPOINT`, `AZURE_AI_FOUNDRY_API_KEY` |
| Direct Anthropic API | `claude` | `ANTHROPIC_API_KEY` |

### Model Selection

Set `ANTHROPIC_MODEL` to override the default model. The default is:

```
cogdep-aifoundry-dev-eus2-claude-sonnet-4-5
```

### Cost Controls

| Variable | Description | Default |
|---|---|---|
| `AI_MAX_COST_PER_ANALYSIS` | Maximum spend per single AI analysis call | `0.50` ($0.50) |
| `AI_SAMPLING_RATE` | Fraction of requests analyzed (0.0--1.0) | `0.1` (10%) |

---

## Endpoints

### Anomaly Detection

**POST /api/ai/analyze**

Analyzes a single request for anomalies.

Request body:

| Field | Type | Description |
|---|---|---|
| `request` | object | The request data to analyze (method, path, headers, body) |
| `metrics` | object | Current traffic metrics (request rate, error rate, latency) |
| `baseline` | object | *(optional)* Baseline traffic profile for comparison |

Response:

| Field | Type | Description |
|---|---|---|
| `anomaly_score` | float | Score from 0.0 (normal) to 1.0 (highly anomalous) |
| `is_anomalous` | boolean | Whether the score exceeds the configured threshold |
| `reasons` | string[] | Human-readable explanations for the score |
| `recommended_action` | string | Suggested action (`block`, `header`, `log`) |

The Kong ai-gateway plugin calls this endpoint on sampled requests in real time. The anomaly threshold (default 0.7) and action are configurable per plugin instance.

**POST /api/ai/anomaly/batch**

Accepts an array of request objects for bulk anomaly analysis. Returns an array of results in the same format as the single-request endpoint. Use this for offline or batch-processing workflows.

---

### Rate Limit Recommendations

**POST /api/ai/rate-limit/suggest**

Suggests optimal rate limits for a consumer based on historical usage.

Request body:

| Field | Type | Description |
|---|---|---|
| `consumer_id` | string | The Kong consumer identifier |
| `usage_history` | object[] | Historical usage data points |
| `current_limits` | object | Currently configured rate limits |

Response:

| Field | Type | Description |
|---|---|---|
| `suggested_limits` | object | Recommended rate limit values |
| `reasoning` | string | Explanation of why these limits were chosen |
| `confidence` | float | Confidence score for the recommendation |
| `sample_count` | integer | Number of data points used in the analysis |

---

### Smart Routing

**POST /api/ai/route**

Selects the best backend for a request.

Request body:

| Field | Type | Description |
|---|---|---|
| `request` | object | The incoming request data |
| `backends` | object[] | Available backend targets |
| `health` | object | Current health status for each backend |

Response:

| Field | Type | Description |
|---|---|---|
| `selected_backend` | string | The chosen backend identifier |
| `reasoning` | string | Explanation of the routing decision |
| `confidence` | float | Confidence score for the decision |
| `fallback` | string | Recommended fallback backend |
| `recommended_headers` | object | Headers to add to the proxied request |

When the Kong plugin receives a routing decision, it can override the upstream target via `kong.service.set_target()`.

---

### Request/Response Transformation

**POST /api/ai/transform/request**
**POST /api/ai/transform/response**

Transforms request or response bodies using natural-language rules.

Request body:

| Field | Type | Description |
|---|---|---|
| `body` | string | The original body content |
| `content_type` | string | MIME type of the body (e.g. `application/json`) |
| `rules` | string[] | Natural-language transformation instructions |
| `context` | object | *(optional)* Additional context for the transformation |

Response:

| Field | Type | Description |
|---|---|---|
| `transformed_body` | string | The body after applying transformations |
| `content_type` | string | MIME type of the transformed body |
| `changes` | string[] | Summary of changes applied |
| `tokens_used` | integer | Number of tokens consumed |

The Kong plugin applies request transformation rules during the **access phase** and response transformation rules during the **body_filter phase**.

---

### Documentation Generation

**POST /api/ai/documentation/generate**

Generates API documentation from specs or live traffic.

Request body:

| Field | Type | Description |
|---|---|---|
| `openapi_spec` | object | *(optional)* An OpenAPI specification |
| `traffic_samples` | object[] | *(optional)* Request/response pairs captured from live traffic |

At least one of `openapi_spec` or `traffic_samples` must be provided.

Response:

| Field | Type | Description |
|---|---|---|
| `documentation` | string | Generated Markdown documentation |
| `openapi_spec` | object | Generated or enriched OpenAPI specification |
| `endpoints_documented` | integer | Number of endpoints covered |
| `tokens_used` | integer | Number of tokens consumed |

---

### AI Health and Configuration

**GET /api/ai/health**

Returns the current health of the AI subsystem.

Response fields: `provider`, `status`, `model`, `available` (boolean), `latency` (ms), `request_count`, `token_count`, `estimated_cost`, `capabilities` (list of supported features).

**GET /api/ai/config**

Returns the active AI configuration.

Response fields: `provider`, `model`, `capabilities`, `rate_limits`.

---

## Prompt Management

**Endpoints:** GET, POST, PUT, DELETE on `/api/ai/prompts`

AI prompts are stored in the database as managed templates. Each prompt belongs to a category and can be edited through the API or the frontend.

### Prompt Fields

| Field | Type | Description |
|---|---|---|
| `slug` | string | Unique identifier for the prompt |
| `name` | string | Display name |
| `category` | string | One of: `anomaly`, `rate_limit`, `routing`, `transform`, `documentation` |
| `system_prompt` | text | The prompt text sent to the AI model |
| `model` | string | *(optional)* Model override for this prompt |
| `temperature` | float | Sampling temperature |
| `max_tokens` | integer | Maximum tokens for the response |
| `version` | integer | Auto-incremented on each update |

### Frontend

Prompts can be managed through the **AI Prompts** page at `/ai/prompts` in the admin UI. The page provides a form-based editor for creating and updating prompt templates.

---

## Kong AI Gateway Plugin

The `ai-gateway` Kong plugin connects the data plane to the AI analysis service. It runs at **priority 800**, which places it after authentication and subscription validation in the plugin execution order.

### Behavior

1. On each request, the plugin rolls a random sample against the configured sampling rate (default 10%).
2. If the request is sampled, the plugin sends it to the AI service for anomaly detection and (if configured) smart routing.
3. If the AI service is unavailable, the plugin **fails open** -- the request passes through unmodified.
4. Results are cached. Route decisions and anomaly scores are cached independently.

### Response Headers

The plugin adds the following headers to proxied responses when analysis is performed:

| Header | Description |
|---|---|
| `X-AI-Anomaly-Score` | The anomaly score (0.0--1.0) |
| `X-AI-Route-Decision` | The backend selected by smart routing |
| `X-AI-Status` | Status of the AI analysis (`ok`, `skipped`, `error`) |
| `X-AI-Analysis-Id` | Unique identifier for the analysis request |

### Logging

The plugin emits structured log entries for every analysis. These logs are designed for ingestion by **Cribl** for downstream processing and dashboarding.

---

## Monitoring AI Costs

### Prometheus Metrics

The AI service exposes metrics tracking analysis rate, latency, and estimated cost per call.

A **recording rule** aggregates cost into an hourly rate:

```
ai_cost_rate:1h
```

This metric is broken down by `provider`, `model`, and `type` (anomaly, routing, transform, etc.).

### Alert Rules

| Alert | Threshold | Severity |
|---|---|---|
| `AICostBudgetWarning` | $5 per hour | warning |
| `AICostBudgetCritical` | $20 per hour | critical |

### Grafana Dashboard

The **AI Layer** Grafana dashboard provides real-time cost tracking, analysis latency percentiles, sampling hit rates, and per-feature breakdowns. Use it to verify that sampling rates and per-analysis budgets are keeping costs within acceptable bounds.
