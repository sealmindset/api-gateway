-- =============================================================================
-- Migration 003: AI Layer Tables
-- =============================================================================
-- Description: Adds tables to support the AI-powered analysis layer for the
--              API gateway. This includes caching/auditing of AI analyses,
--              anomaly event tracking, intelligent rate limit suggestions,
--              auto-generated documentation storage, and prompt template
--              management with 3-tier resolution (Redis -> DB -> seed).
--
-- Dependencies: 001_initial_schema.sql (users table, update_updated_at_column)
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. AI Analysis Results Cache & Audit Log
-- =============================================================================
-- Stores every AI analysis invocation for auditing, cost tracking, and
-- deduplication via input_hash. Each row represents one LLM call.
CREATE TABLE ai_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_type   VARCHAR(50) NOT NULL,       -- anomaly, rate_limit, routing, transform, documentation
    request_id      VARCHAR(255),               -- correlation ID from Kong request header
    consumer_id     VARCHAR(255),               -- Kong consumer identifier
    input_hash      VARCHAR(64),                -- SHA-256 of input payload for deduplication
    result          JSONB NOT NULL,             -- structured analysis result from the model
    model           VARCHAR(100) NOT NULL,      -- model identifier (e.g., claude-sonnet-4-20250514)
    provider        VARCHAR(50) NOT NULL,       -- provider name (e.g., anthropic, openai)
    input_tokens    INTEGER,                    -- token count for input/prompt
    output_tokens   INTEGER,                    -- token count for completion/response
    cost_usd        DECIMAL(10,6),              -- estimated cost in USD for this invocation
    latency_ms      INTEGER,                    -- wall-clock latency of the AI call in milliseconds
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ai_analyses IS 'Audit log and cache of all AI analysis invocations across the gateway.';
COMMENT ON COLUMN ai_analyses.input_hash IS 'SHA-256 hash of the analysis input, used for deduplication and cache lookups.';
COMMENT ON COLUMN ai_analyses.analysis_type IS 'Category of analysis: anomaly, rate_limit, routing, transform, documentation.';

-- =============================================================================
-- 2. AI Anomaly Events
-- =============================================================================
-- Tracks individual anomaly detection events for pattern analysis, alerting,
-- and retrospective investigation. Each row is one flagged request.
CREATE TABLE ai_anomaly_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id      VARCHAR(255),               -- Kong request correlation ID
    consumer_id     VARCHAR(255),               -- Kong consumer identifier
    source_ip       INET,                       -- client IP address
    anomaly_score   DECIMAL(3,2),               -- 0.00 to 1.00 confidence score
    anomaly_type    VARCHAR(100),               -- classification (e.g., credential_stuffing, data_exfil, unusual_pattern)
    action_taken    VARCHAR(50),                -- enforcement action: allow, throttle, block, alert
    details         JSONB,                      -- additional context (features, explanation, raw signals)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ai_anomaly_events IS 'Individual anomaly detection events flagged by the AI layer.';
COMMENT ON COLUMN ai_anomaly_events.anomaly_score IS 'Confidence score from 0.00 (benign) to 1.00 (certain anomaly).';
COMMENT ON COLUMN ai_anomaly_events.action_taken IS 'Enforcement action applied: allow, throttle, block, or alert.';

-- =============================================================================
-- 3. AI Rate Limit Suggestions
-- =============================================================================
-- Records AI-generated rate limit recommendations with current vs suggested
-- values, confidence scores, and approval tracking. Supports a human-in-the-loop
-- workflow where suggestions must be explicitly applied.
CREATE TABLE ai_rate_limit_suggestions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id                 VARCHAR(255) NOT NULL,      -- target consumer
    current_limit_per_second    INTEGER,                    -- current configured limit
    current_limit_per_minute    INTEGER,
    current_limit_per_hour      INTEGER,
    suggested_per_second        INTEGER,                    -- AI-recommended limit
    suggested_per_minute        INTEGER,
    suggested_per_hour          INTEGER,
    confidence                  DECIMAL(3,2),               -- 0.00 to 1.00
    reasoning                   TEXT,                       -- human-readable explanation from the model
    applied                     BOOLEAN DEFAULT false,      -- whether suggestion was accepted
    applied_at                  TIMESTAMPTZ,                -- when it was applied
    applied_by                  UUID REFERENCES users(id),  -- who approved it
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ai_rate_limit_suggestions IS 'AI-generated rate limit recommendations with approval workflow tracking.';
COMMENT ON COLUMN ai_rate_limit_suggestions.confidence IS 'Model confidence in the suggestion, from 0.00 to 1.00.';
COMMENT ON COLUMN ai_rate_limit_suggestions.applied IS 'Whether the suggestion has been reviewed and applied by a human operator.';

-- =============================================================================
-- 4. AI-Generated Documentation
-- =============================================================================
-- Stores versioned auto-generated API documentation. Each service can have
-- multiple versions, supporting both Markdown and OpenAPI JSON formats.
CREATE TABLE ai_documentation (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    VARCHAR(255) NOT NULL,      -- Kong service name
    version         INTEGER NOT NULL DEFAULT 1, -- incremented per service
    title           VARCHAR(500),               -- documentation title
    description     TEXT,                       -- brief summary
    markdown        TEXT NOT NULL,              -- full Markdown documentation
    openapi_json    JSONB,                      -- OpenAPI 3.x specification (if generated)
    generated_from  VARCHAR(50),                -- source: openapi_spec, traffic_sample
    model           VARCHAR(100),               -- model used for generation
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ai_documentation IS 'Versioned auto-generated API documentation per service.';
COMMENT ON COLUMN ai_documentation.generated_from IS 'Source data used: openapi_spec (existing spec enrichment) or traffic_sample (inferred from live traffic).';

-- =============================================================================
-- 5. Prompt Templates
-- =============================================================================
-- Manages prompt templates with 3-tier resolution: Redis (hot cache) -> DB
-- (source of truth) -> seed defaults (fallback). Supports versioning and
-- per-prompt model/temperature overrides.
CREATE TABLE ai_prompts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(100) UNIQUE NOT NULL,   -- unique identifier for lookup
    name            VARCHAR(255) NOT NULL,          -- human-friendly display name
    category        VARCHAR(50) NOT NULL,           -- anomaly, rate_limit, routing, transform, documentation
    system_prompt   TEXT NOT NULL,                  -- the system prompt template
    model           VARCHAR(100),                   -- model override (NULL = use default)
    temperature     DECIMAL(2,1) DEFAULT 0.3,       -- sampling temperature
    max_tokens      INTEGER DEFAULT 4096,           -- max output tokens
    is_active       BOOLEAN DEFAULT true,           -- soft disable without deletion
    version         INTEGER DEFAULT 1,              -- incremented on each update
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ai_prompts IS 'Prompt templates for AI analysis. Resolved via 3-tier lookup: Redis -> DB -> seed defaults.';
COMMENT ON COLUMN ai_prompts.slug IS 'URL-safe unique identifier used for programmatic lookup.';
COMMENT ON COLUMN ai_prompts.is_active IS 'When false, the prompt is skipped during resolution and the seed default is used instead.';

-- =============================================================================
-- 6. Indexes
-- =============================================================================

-- ai_analyses: query by type + time, consumer + time, and dedup by hash
CREATE INDEX idx_ai_analyses_type_created
    ON ai_analyses(analysis_type, created_at DESC);

CREATE INDEX idx_ai_analyses_consumer
    ON ai_analyses(consumer_id, created_at DESC);

CREATE INDEX idx_ai_analyses_input_hash
    ON ai_analyses(input_hash);

-- ai_anomaly_events: query by consumer, score ranking, and time range
CREATE INDEX idx_ai_anomaly_events_consumer
    ON ai_anomaly_events(consumer_id, created_at DESC);

CREATE INDEX idx_ai_anomaly_events_score
    ON ai_anomaly_events(anomaly_score DESC);

CREATE INDEX idx_ai_anomaly_events_created
    ON ai_anomaly_events(created_at DESC);

-- ai_rate_limit_suggestions: query by consumer + time
CREATE INDEX idx_ai_rate_suggestions_consumer
    ON ai_rate_limit_suggestions(consumer_id, created_at DESC);

-- ai_documentation: query by service + latest version
CREATE INDEX idx_ai_documentation_service
    ON ai_documentation(service_name, version DESC);

-- ai_prompts: lookup by slug and filter by category
CREATE INDEX idx_ai_prompts_slug
    ON ai_prompts(slug);

CREATE INDEX idx_ai_prompts_category
    ON ai_prompts(category);

-- =============================================================================
-- 7. Seed Default Prompts
-- =============================================================================
-- These serve as the fallback tier in the 3-tier resolution chain.
-- Production prompts should be managed via the admin API and cached in Redis.

INSERT INTO ai_prompts (slug, name, category, system_prompt, temperature, max_tokens) VALUES
(
    'anomaly-detection',
    'Anomaly Detection',
    'anomaly',
    'You are an API security expert analyzing request patterns for anomalies. '
    'Given a batch of recent API requests with metadata (IP, consumer, path, method, '
    'headers, timing, payload size), identify requests that deviate from normal patterns. '
    'Score each request from 0.0 (normal) to 1.0 (highly anomalous). '
    'Classify anomaly types: credential_stuffing, data_exfiltration, enumeration_attack, '
    'unusual_geographic_origin, payload_injection, rate_abuse, session_hijacking. '
    'Respond with structured JSON only.',
    0.0,
    2048
),
(
    'rate-limit-advisor',
    'Rate Limit Advisor',
    'rate_limit',
    'You are an API rate limiting expert. Analyze the provided traffic patterns for a '
    'consumer and recommend optimal rate limits. Consider: historical request volume, '
    'time-of-day patterns, burst behavior, error rates, and endpoint sensitivity. '
    'Provide recommended limits for per-second, per-minute, and per-hour windows. '
    'Include a confidence score (0.0-1.0) and human-readable reasoning. '
    'Respond with structured JSON only.',
    0.0,
    2048
),
(
    'smart-routing',
    'Smart Routing',
    'routing',
    'You are an API traffic routing expert. Given the current state of backend services '
    '(health, latency, capacity, error rates) and the incoming request characteristics '
    '(consumer tier, endpoint, payload size, priority), recommend the optimal backend target. '
    'Factor in: latency SLAs, geographic affinity, canary deployments, and circuit breaker state. '
    'Respond with structured JSON only.',
    0.3,
    1024
),
(
    'request-transform',
    'Request Transform',
    'transform',
    'You are an API request transformation expert. Given a source request format and a '
    'target API specification, generate the transformation mapping. Handle: header mapping, '
    'body restructuring, field renaming, type coercion, default values, and conditional logic. '
    'Produce a deterministic transformation that can be cached and replayed. '
    'Respond with structured JSON only.',
    0.2,
    4096
),
(
    'response-transform',
    'Response Transform',
    'transform',
    'You are an API response transformation expert. Given a backend response and the '
    'consumer''s expected format, generate the transformation mapping. Handle: field filtering, '
    'restructuring, pagination wrapping, error normalization, and schema versioning. '
    'Produce a deterministic transformation that can be cached and replayed. '
    'Respond with structured JSON only.',
    0.2,
    4096
),
(
    'api-documentation',
    'API Documentation Generator',
    'documentation',
    'You are an API documentation expert. Given either an OpenAPI specification or a sample '
    'of live API traffic (requests and responses), generate comprehensive developer-facing '
    'documentation in Markdown format. Include: overview, authentication, endpoints with '
    'request/response examples, error codes, rate limits, and best practices. '
    'If an OpenAPI spec is provided, also produce an enriched OpenAPI 3.x JSON output. '
    'Write clearly for a developer audience.',
    0.5,
    8192
);

-- =============================================================================
-- 8. Triggers
-- =============================================================================
-- Automatically update the updated_at timestamp on prompt modifications.
-- Depends on update_updated_at_column() from migration 001.

CREATE TRIGGER set_ai_prompts_updated_at
    BEFORE UPDATE ON ai_prompts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;
