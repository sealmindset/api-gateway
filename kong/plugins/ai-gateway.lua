-- =============================================================================
-- Kong Plugin: ai-gateway
-- =============================================================================
-- Integrates AI-powered analysis into the Kong request pipeline. Calls the
-- admin-panel AI endpoints for anomaly detection, smart routing, and
-- request/response transformation.
--
-- Priority 800: runs after authentication (1000+) and subscription validation
-- (850), but before rate limiting and proxying.
--
-- Key behaviours:
--   - Sampling: only a configurable fraction of requests are sent to the AI.
--   - Fail-open: when the AI service is unreachable and fail_open=true the
--     request passes through with an X-AI-Status: unavailable header.
--   - Caching: AI decisions are cached in kong.cache to reduce latency.
--   - Observability: headers and structured log fields expose AI decisions
--     to Cribl, Prometheus, and other log consumers.
-- =============================================================================

local http  = require "resty.http"
local cjson = require "cjson.safe"
local kong  = kong
local ngx   = ngx
local fmt   = string.format
local math_random = math.random

-- ---------------------------------------------------------------------------
-- Plugin metadata
-- ---------------------------------------------------------------------------
local AIGateway = {
  PRIORITY = 800,
  VERSION  = "1.0.0",
}

-- ---------------------------------------------------------------------------
-- Constants
-- ---------------------------------------------------------------------------
local LOG_PREFIX       = "[ai-gateway] "
local CACHE_KEY_PREFIX = "ai_gateway:"
local HEADER_SCORE     = "X-AI-Anomaly-Score"
local HEADER_ROUTE     = "X-AI-Route-Decision"
local HEADER_ID        = "X-AI-Analysis-Id"
local HEADER_STATUS    = "X-AI-Status"

-- ---------------------------------------------------------------------------
-- Helper: HTTP POST to the AI admin-panel
-- ---------------------------------------------------------------------------
-- Makes a JSON POST request to the specified AI endpoint path.
--
-- @param conf      table   Plugin configuration
-- @param path      string  API path (appended to conf.ai_endpoint)
-- @param payload   table   Request body (will be JSON-encoded)
-- @return table|nil        Parsed response body, or nil on error
-- @return string|nil       Error message, or nil on success
local function ai_request(conf, path, payload)
  local httpc = http.new()
  httpc:set_timeout(conf.timeout)

  local url = conf.ai_endpoint .. path
  local json_body = cjson.encode(payload)
  if not json_body then
    return nil, "failed to encode request payload"
  end

  local res, err = httpc:request_uri(url, {
    method  = "POST",
    body    = json_body,
    headers = {
      ["Content-Type"] = "application/json",
      ["Accept"]       = "application/json",
      ["X-Request-ID"] = kong.request.get_header("X-Request-ID") or "",
      ["X-Gateway"]    = "kong",
    },
    ssl_verify = false,
  })

  if not res then
    return nil, fmt("AI endpoint unreachable: %s", err or "unknown error")
  end

  if res.status >= 500 then
    return nil, fmt("AI endpoint returned HTTP %d", res.status)
  end

  if res.status >= 400 then
    return nil, fmt("AI endpoint rejected request: HTTP %d - %s", res.status, (res.body or ""):sub(1, 200))
  end

  local body, decode_err = cjson.decode(res.body)
  if not body then
    return nil, fmt("failed to decode AI response: %s", decode_err or "unknown")
  end

  return body, nil
end

-- ---------------------------------------------------------------------------
-- Helper: Build request data table from the current Kong request
-- ---------------------------------------------------------------------------
-- Extracts method, path, headers, query params, body, and source IP from the
-- current request context for transmission to the AI analysis endpoint.
--
-- @return table  Request data suitable for the AI /analyze endpoint
local function build_request_data()
  local headers = kong.request.get_headers(50)  -- cap at 50 to avoid oversized payloads

  -- Redact sensitive headers
  headers["authorization"] = nil
  headers["cookie"]        = nil
  headers["x-api-key"]     = nil

  local body, _ = kong.request.get_body()

  local consumer = kong.client.get_consumer()

  return {
    method       = kong.request.get_method(),
    path         = kong.request.get_path(),
    headers      = headers,
    query_params = kong.request.get_query(50),
    body         = body,
    source_ip    = kong.client.get_ip(),
    timestamp    = ngx.http_time(ngx.time()),
    consumer_id  = consumer and consumer.id or nil,
  }
end

-- ---------------------------------------------------------------------------
-- Helper: Handle AI service failure according to fail_open policy
-- ---------------------------------------------------------------------------
-- @param conf    table   Plugin configuration
-- @param err     string  Error message
-- @param phase   string  Phase name for logging
-- @return boolean        True if request should continue (fail-open)
local function handle_ai_failure(conf, err, phase)
  if conf.fail_open then
    kong.log.warn(LOG_PREFIX, fmt(
      "AI service unavailable in %s phase: %s; fail_open=true, allowing request", phase, err
    ))
    kong.service.request.set_header(HEADER_STATUS, "unavailable")
    return true
  else
    kong.log.err(LOG_PREFIX, fmt(
      "AI service unavailable in %s phase: %s; fail_open=false, blocking request", phase, err
    ))
    return false
  end
end

-- ---------------------------------------------------------------------------
-- Anomaly detection
-- ---------------------------------------------------------------------------
-- @param conf          table  Plugin configuration
-- @param request_data  table  Current request data
-- @return table|nil           Analysis result, or nil on failure
local function run_anomaly_detection(conf, request_data)
  -- Check cache first
  local consumer_id = request_data.consumer_id or "anonymous"
  local path_hash = ngx.crc32_short(request_data.path or "/")
  local cache_key = fmt("%sanomaly:%s:%s", CACHE_KEY_PREFIX, consumer_id, path_hash)

  local result, err = kong.cache:get(cache_key, { ttl = conf.cache_ttl }, function()
    local payload = {
      request_data = request_data,
      metrics      = {
        source_ip = request_data.source_ip,
      },
    }

    local res, req_err = ai_request(conf, "/analyze", payload)
    if not res then
      return nil, req_err
    end
    return res
  end)

  if err then
    kong.log.warn(LOG_PREFIX, fmt("anomaly detection failed: %s", err))
    return nil
  end

  return result
end

-- ---------------------------------------------------------------------------
-- Smart routing
-- ---------------------------------------------------------------------------
-- @param conf          table  Plugin configuration
-- @param request_data  table  Current request data
-- @return table|nil           Routing decision, or nil on failure
local function run_smart_routing(conf, request_data)
  local backends = {}
  for _, name in ipairs(conf.routing_backends or {}) do
    backends[#backends + 1] = { name = name, url = name, weight = 1.0 }
  end

  if #backends == 0 then
    kong.log.debug(LOG_PREFIX, "smart routing skipped: no backends configured")
    return nil
  end

  local payload = {
    request_data       = request_data,
    available_backends = backends,
    backend_health     = {},
  }

  local result, err = ai_request(conf, "/route", payload)
  if not result then
    kong.log.warn(LOG_PREFIX, fmt("smart routing failed: %s", err))
    return nil
  end

  return result
end

-- ---------------------------------------------------------------------------
-- Request transformation
-- ---------------------------------------------------------------------------
-- @param conf          table  Plugin configuration
-- @param request_data  table  Current request data
-- @return table|nil           Transform result, or nil on failure
local function run_request_transform(conf, request_data)
  local rules = conf.request_transform_rules
  if not rules or rules == "" then
    kong.log.debug(LOG_PREFIX, "request transform skipped: no rules configured")
    return nil
  end

  local content_type = kong.request.get_header("Content-Type") or "application/json"

  local payload = {
    body                 = request_data.body,
    content_type         = content_type,
    transformation_rules = rules,
    context = {
      method      = request_data.method,
      path        = request_data.path,
      consumer_id = request_data.consumer_id,
    },
  }

  local result, err = ai_request(conf, "/transform/request", payload)
  if not result then
    kong.log.warn(LOG_PREFIX, fmt("request transform failed: %s", err))
    return nil
  end

  return result
end

-- ---------------------------------------------------------------------------
-- Access phase handler
-- ---------------------------------------------------------------------------
function AIGateway:access(conf)
  -- Apply sampling rate: skip AI analysis for most requests
  if math_random() >= conf.sampling_rate then
    kong.log.debug(LOG_PREFIX, "request not sampled for AI analysis")
    return
  end

  -- Build request data once, reuse across all AI calls
  local request_data = build_request_data()

  -- -------------------------------------------------------------------
  -- 1. Anomaly detection
  -- -------------------------------------------------------------------
  if conf.enable_anomaly_detection then
    local result = run_anomaly_detection(conf, request_data)

    if result then
      -- Set informational headers
      local score = tonumber(result.anomaly_score) or 0
      kong.service.request.set_header(HEADER_SCORE, fmt("%.4f", score))

      if result.analysis_id then
        kong.service.request.set_header(HEADER_ID, result.analysis_id)
      end

      -- Store for log phase
      kong.ctx.plugin.anomaly_result = result

      -- Act on anomaly
      if score >= conf.anomaly_threshold then
        kong.log.warn(LOG_PREFIX, fmt(
          "anomaly detected: score=%.4f threshold=%.4f action=%s path=%s ip=%s",
          score, conf.anomaly_threshold, conf.anomaly_action,
          request_data.path, request_data.source_ip
        ))

        if conf.anomaly_action == "block" then
          return kong.response.exit(403, {
            message = "Request blocked: anomalous behaviour detected",
            error   = "anomaly_detected",
            score   = score,
          })
        elseif conf.anomaly_action == "header" then
          kong.service.request.set_header("X-AI-Anomaly-Warning", "true")
          kong.service.request.set_header("X-AI-Anomaly-Reasons",
            table.concat(result.reasons or {}, "; "))
        end
        -- "log" action: do nothing extra, log phase will record it
      end

      kong.service.request.set_header(HEADER_STATUS, "analyzed")
    else
      -- AI service failure
      if not handle_ai_failure(conf, "anomaly detection returned no result", "access:anomaly") then
        return kong.response.exit(503, {
          message = "AI anomaly detection service unavailable",
          error   = "ai_unavailable",
        })
      end
    end
  end

  -- -------------------------------------------------------------------
  -- 2. Smart routing
  -- -------------------------------------------------------------------
  if conf.enable_smart_routing then
    local decision = run_smart_routing(conf, request_data)

    if decision then
      kong.service.request.set_header(HEADER_ROUTE, decision.selected_backend or "default")

      -- Override upstream if a valid backend was selected
      if decision.selected_backend and decision.selected_backend ~= "" then
        local ok, set_err = pcall(function()
          kong.service.set_target(decision.selected_backend, 80)
        end)
        if not ok then
          kong.log.warn(LOG_PREFIX, fmt(
            "failed to set upstream target to '%s': %s",
            decision.selected_backend, set_err or "unknown"
          ))
        end
      end

      -- Inject any additional headers recommended by the AI
      if decision.headers_to_add then
        for k, v in pairs(decision.headers_to_add) do
          kong.service.request.set_header(k, v)
        end
      end

      kong.ctx.plugin.routing_decision = decision
    else
      if not handle_ai_failure(conf, "smart routing returned no result", "access:routing") then
        return kong.response.exit(503, {
          message = "AI routing service unavailable",
          error   = "ai_unavailable",
        })
      end
    end
  end

  -- -------------------------------------------------------------------
  -- 3. Request transformation
  -- -------------------------------------------------------------------
  if conf.enable_request_transform then
    local transform = run_request_transform(conf, request_data)

    if transform and transform.transformed_body then
      local new_body = transform.transformed_body
      if type(new_body) == "table" then
        new_body = cjson.encode(new_body)
      end

      if new_body then
        kong.service.request.set_raw_body(tostring(new_body))

        if transform.content_type then
          kong.service.request.set_header("Content-Type", transform.content_type)
        end
      end

      kong.ctx.plugin.request_transform = transform
    else
      if not handle_ai_failure(conf, "request transform returned no result", "access:transform") then
        return kong.response.exit(503, {
          message = "AI request transformation service unavailable",
          error   = "ai_unavailable",
        })
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- Body filter phase handler (response transformation)
-- ---------------------------------------------------------------------------
-- Collects the full response body across chunks, then sends it to the AI
-- transform endpoint. The transformed body replaces the original.
function AIGateway:body_filter(conf)
  if not conf.enable_response_transform then
    return
  end

  local rules = conf.response_transform_rules
  if not rules or rules == "" then
    return
  end

  -- Accumulate response body chunks
  local chunk = kong.response.get_raw_body()
  if not chunk then
    return
  end

  local ctx = kong.ctx.plugin
  ctx.response_body = (ctx.response_body or "") .. chunk

  -- Only proceed when we have the complete body (eof flag)
  if not ngx.arg[2] then
    -- Not the last chunk; suppress output until we have it all
    ngx.arg[1] = ""
    return
  end

  -- We have the full body -- send to AI for transformation
  local full_body = ctx.response_body or ""
  local content_type = kong.response.get_header("Content-Type") or "application/json"

  local payload = {
    body                 = full_body,
    content_type         = content_type,
    transformation_rules = rules,
    context = {
      status_code = kong.response.get_status(),
    },
  }

  local result, err = ai_request(conf, "/transform/response", payload)

  if result and result.transformed_body then
    local new_body = result.transformed_body
    if type(new_body) == "table" then
      new_body = cjson.encode(new_body)
    end
    ngx.arg[1] = tostring(new_body or full_body)
    ctx.response_transform = result
  else
    -- Transformation failed; pass original body through
    kong.log.warn(LOG_PREFIX, fmt("response transform failed: %s", err or "no result"))
    ngx.arg[1] = full_body
  end
end

-- ---------------------------------------------------------------------------
-- Log phase handler
-- ---------------------------------------------------------------------------
-- Emits structured log fields for AI decisions so they can be picked up by
-- Cribl, Prometheus, and other observability tools.
function AIGateway:log(conf)
  local ctx = kong.ctx.plugin

  -- Anomaly detection metadata
  if ctx.anomaly_result then
    local r = ctx.anomaly_result
    kong.log.set_serialize_value("ai.anomaly.score", r.anomaly_score)
    kong.log.set_serialize_value("ai.anomaly.is_anomalous", r.is_anomalous)
    kong.log.set_serialize_value("ai.anomaly.action", r.recommended_action)
    kong.log.set_serialize_value("ai.anomaly.analysis_id", r.analysis_id)
    if r.reasons then
      kong.log.set_serialize_value("ai.anomaly.reasons", table.concat(r.reasons, "; "))
    end
  end

  -- Routing decision metadata
  if ctx.routing_decision then
    local d = ctx.routing_decision
    kong.log.set_serialize_value("ai.routing.selected_backend", d.selected_backend)
    kong.log.set_serialize_value("ai.routing.confidence", d.confidence)
    kong.log.set_serialize_value("ai.routing.decision_id", d.decision_id)
    kong.log.set_serialize_value("ai.routing.reasoning", d.reasoning)
  end

  -- Request transform metadata
  if ctx.request_transform then
    local t = ctx.request_transform
    kong.log.set_serialize_value("ai.transform.request.transform_id", t.transform_id)
    kong.log.set_serialize_value("ai.transform.request.tokens_used", t.tokens_used)
    kong.log.set_serialize_value("ai.transform.request.summary", t.changes_summary)
  end

  -- Response transform metadata
  if ctx.response_transform then
    local t = ctx.response_transform
    kong.log.set_serialize_value("ai.transform.response.transform_id", t.transform_id)
    kong.log.set_serialize_value("ai.transform.response.tokens_used", t.tokens_used)
    kong.log.set_serialize_value("ai.transform.response.summary", t.changes_summary)
  end

  -- Summary flag indicating AI was involved in this request
  local ai_active = ctx.anomaly_result or ctx.routing_decision
      or ctx.request_transform or ctx.response_transform
  kong.log.set_serialize_value("ai.active", ai_active ~= nil)
end

return AIGateway
