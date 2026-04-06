-- =============================================================================
-- Kong Plugin: subscription-validator
-- =============================================================================
-- Validates that the authenticated consumer holds an active subscription with
-- a tier that is authorized to access the requested endpoint. This plugin
-- runs in the "access" phase, after authentication plugins have identified
-- the consumer.
--
-- Behavior:
--   1. Extract the consumer identity from the Kong context (set by an
--      upstream auth plugin such as key-auth, oauth2, or basic-auth).
--   2. Check the local LRU cache for a recent validation result.
--   3. On cache miss, call the external subscription validation service.
--   4. If the subscription is active and the tier is permitted, allow the
--      request and inject subscription metadata headers.
--   5. If the subscription is expired, invalid, or the tier is insufficient,
--      return HTTP 403 with a descriptive error body.
--   6. Log the validation outcome for audit and observability.
--
-- Configuration (see schema.lua):
--   validation_endpoint  - URL of the subscription validation service
--   timeout              - HTTP timeout for validation calls (ms)
--   cache_ttl            - Seconds to cache a successful validation
--   allowed_tiers        - List of tiers permitted for the route/service
--   fail_open            - If true, allow requests when validation service
--                          is unreachable (use with caution)
--   header_prefix        - Prefix for subscription metadata headers
-- =============================================================================

local http = require "resty.http"
local cjson = require "cjson.safe"
local kong = kong
local ngx = ngx
local fmt = string.format

-- ---------------------------------------------------------------------------
-- Plugin metadata
-- ---------------------------------------------------------------------------
local SubscriptionValidator = {
  PRIORITY = 850,   -- Run after authentication (1000+) but before rate limiting (901)
  VERSION  = "1.0.0",
}

-- ---------------------------------------------------------------------------
-- Constants
-- ---------------------------------------------------------------------------
local CACHE_KEY_PREFIX = "subscription_validator:"
local LOG_PREFIX = "[subscription-validator] "

-- ---------------------------------------------------------------------------
-- Helper: Build a cache key from consumer identity
-- ---------------------------------------------------------------------------
-- Uses the consumer ID (UUID) as the primary cache key component. If no
-- consumer is authenticated, returns nil to signal that validation should
-- be skipped or denied.
--
-- @param consumer_id string  The Kong consumer UUID
-- @return string|nil         The cache key, or nil if no consumer
local function build_cache_key(consumer_id)
  if not consumer_id then
    return nil
  end
  return CACHE_KEY_PREFIX .. consumer_id
end

-- ---------------------------------------------------------------------------
-- Helper: Call the external subscription validation service
-- ---------------------------------------------------------------------------
-- Makes an HTTP GET request to the validation endpoint with the consumer's
-- identity. The validation service is expected to return JSON with at least:
--   {
--     "valid": true|false,
--     "tier": "free|standard|premium|enterprise",
--     "expires_at": "2026-12-31T23:59:59Z",
--     "subscription_id": "sub_abc123",
--     "features": ["feature1", "feature2"]
--   }
--
-- @param conf    table   Plugin configuration
-- @param consumer table  Kong consumer object
-- @return table|nil      Parsed response body, or nil on error
-- @return string|nil     Error message, or nil on success
local function call_validation_service(conf, consumer)
  local httpc = http.new()
  httpc:set_timeout(conf.timeout)

  local url = fmt(
    "%s?consumer_id=%s&custom_id=%s",
    conf.validation_endpoint,
    consumer.id or "",
    consumer.custom_id or ""
  )

  local res, err = httpc:request_uri(url, {
    method = "GET",
    headers = {
      ["Content-Type"]    = "application/json",
      ["Accept"]          = "application/json",
      ["X-Gateway"]       = "kong",
      ["X-Request-ID"]    = kong.request.get_header("X-Request-ID") or "",
    },
    ssl_verify = false,  -- Set to true if the validation service uses trusted TLS
  })

  if not res then
    return nil, fmt("validation service unreachable: %s", err or "unknown error")
  end

  if res.status ~= 200 then
    return nil, fmt("validation service returned HTTP %d", res.status)
  end

  local body, decode_err = cjson.decode(res.body)
  if not body then
    return nil, fmt("failed to parse validation response: %s", decode_err or "unknown")
  end

  return body, nil
end

-- ---------------------------------------------------------------------------
-- Helper: Check whether a tier is in the allowed list
-- ---------------------------------------------------------------------------
-- Performs a case-insensitive comparison of the consumer's subscription tier
-- against the list of tiers allowed by the plugin configuration.
--
-- @param tier          string   The consumer's subscription tier
-- @param allowed_tiers table    List of allowed tier names
-- @return boolean               True if the tier is allowed
local function is_tier_allowed(tier, allowed_tiers)
  if not tier or not allowed_tiers then
    return false
  end

  local lower_tier = tier:lower()
  for _, allowed in ipairs(allowed_tiers) do
    if allowed:lower() == lower_tier then
      return true
    end
  end
  return false
end

-- ---------------------------------------------------------------------------
-- Helper: Inject subscription metadata headers into the upstream request
-- ---------------------------------------------------------------------------
-- Adds headers with the configured prefix so upstream services can access
-- subscription information without making their own validation calls.
--
-- @param conf            table  Plugin configuration
-- @param subscription    table  Validated subscription data
local function set_subscription_headers(conf, subscription)
  local prefix = conf.header_prefix or "X-Subscription-"

  -- Core subscription fields
  if subscription.subscription_id then
    kong.service.request.set_header(prefix .. "ID", subscription.subscription_id)
  end

  if subscription.tier then
    kong.service.request.set_header(prefix .. "Tier", subscription.tier)
  end

  if subscription.expires_at then
    kong.service.request.set_header(prefix .. "Expires-At", subscription.expires_at)
  end

  -- Subscription status
  kong.service.request.set_header(prefix .. "Valid", tostring(subscription.valid or false))

  -- Feature flags as a comma-separated list
  if subscription.features and type(subscription.features) == "table" then
    kong.service.request.set_header(prefix .. "Features", table.concat(subscription.features, ","))
  end

  -- Organization or account context
  if subscription.organization_id then
    kong.service.request.set_header(prefix .. "Org-ID", subscription.organization_id)
  end
end

-- ---------------------------------------------------------------------------
-- Helper: Log subscription validation events
-- ---------------------------------------------------------------------------
-- Emits a structured log entry for auditing and observability. These entries
-- are picked up by Kong's configured log plugins (TCP/HTTP log to Cribl).
--
-- @param consumer      table    Kong consumer object
-- @param subscription  table    Subscription data (may be partial on error)
-- @param result        string   "allowed", "denied", or "error"
-- @param reason        string   Human-readable explanation
local function log_validation_event(consumer, subscription, result, reason)
  kong.log.info(LOG_PREFIX, fmt(
    "consumer=%s custom_id=%s tier=%s result=%s reason=%s subscription_id=%s",
    consumer.id or "unknown",
    consumer.custom_id or "unknown",
    (subscription and subscription.tier) or "unknown",
    result,
    reason or "none",
    (subscription and subscription.subscription_id) or "unknown"
  ))

  -- Set log serializer fields for structured logging. These appear in the
  -- log payload sent to Cribl and other log destinations.
  kong.log.set_serialize_value("subscription.consumer_id", consumer.id)
  kong.log.set_serialize_value("subscription.custom_id", consumer.custom_id)
  kong.log.set_serialize_value("subscription.result", result)
  kong.log.set_serialize_value("subscription.reason", reason)

  if subscription then
    kong.log.set_serialize_value("subscription.tier", subscription.tier)
    kong.log.set_serialize_value("subscription.subscription_id", subscription.subscription_id)
    kong.log.set_serialize_value("subscription.valid", subscription.valid)
  end
end

-- ---------------------------------------------------------------------------
-- Access phase handler
-- ---------------------------------------------------------------------------
-- This is the main entry point for the plugin. It runs after authentication
-- has identified the consumer and before the request is proxied upstream.
--
-- @param conf table  Plugin configuration
function SubscriptionValidator:access(conf)
  -- Retrieve the authenticated consumer. If no consumer is set, an
  -- authentication plugin either did not run or allowed anonymous access.
  local consumer = kong.client.get_consumer()
  if not consumer then
    kong.log.warn(LOG_PREFIX, "no authenticated consumer found; denying request")
    return kong.response.exit(403, {
      message = "Authentication required: no consumer identity found",
      error   = "missing_consumer",
    })
  end

  -- Build cache key and attempt cache lookup
  local cache_key = build_cache_key(consumer.id)
  local subscription = nil

  if cache_key then
    subscription = kong.cache:get(cache_key, { ttl = conf.cache_ttl }, function()
      -- Cache miss callback: call the validation service
      local result, err = call_validation_service(conf, consumer)
      if not result then
        -- Return nil + error; the cache will not store a nil value
        return nil, err
      end
      return result
    end)
  end

  -- Handle validation service errors
  if not subscription then
    if conf.fail_open then
      -- Fail-open mode: allow the request but log a warning
      kong.log.warn(LOG_PREFIX, fmt(
        "validation service unavailable for consumer=%s; fail_open=true, allowing request",
        consumer.id
      ))
      log_validation_event(consumer, nil, "allowed", "fail_open_service_unavailable")
      kong.service.request.set_header(
        (conf.header_prefix or "X-Subscription-") .. "Validated", "false"
      )
      return  -- Continue to upstream
    else
      kong.log.err(LOG_PREFIX, fmt(
        "validation service unavailable for consumer=%s; denying request",
        consumer.id
      ))
      log_validation_event(consumer, nil, "error", "service_unavailable")
      return kong.response.exit(503, {
        message = "Subscription validation service is temporarily unavailable",
        error   = "validation_service_unavailable",
      })
    end
  end

  -- Check whether the subscription is active
  if not subscription.valid then
    local reason = subscription.reason or "subscription is not active"
    kong.log.warn(LOG_PREFIX, fmt(
      "consumer=%s denied: %s", consumer.id, reason
    ))
    log_validation_event(consumer, subscription, "denied", reason)
    return kong.response.exit(403, {
      message = fmt("Subscription invalid: %s", reason),
      error   = "subscription_invalid",
      tier    = subscription.tier,
    })
  end

  -- Check whether the subscription's expiration date has passed
  if subscription.expires_at then
    local expires_epoch = ngx.parse_http_time(subscription.expires_at)
    if expires_epoch and expires_epoch < ngx.time() then
      local reason = fmt("subscription expired at %s", subscription.expires_at)
      kong.log.warn(LOG_PREFIX, fmt("consumer=%s denied: %s", consumer.id, reason))
      log_validation_event(consumer, subscription, "denied", reason)

      -- Invalidate the cached entry so the next request re-validates
      if cache_key then
        kong.cache:invalidate(cache_key)
      end

      return kong.response.exit(403, {
        message = fmt("Subscription expired on %s. Please renew your subscription.", subscription.expires_at),
        error   = "subscription_expired",
        tier    = subscription.tier,
      })
    end
  end

  -- Check whether the consumer's tier is authorized for this endpoint
  if not is_tier_allowed(subscription.tier, conf.allowed_tiers) then
    local reason = fmt(
      "tier '%s' is not authorized; allowed tiers: %s",
      subscription.tier or "none",
      table.concat(conf.allowed_tiers, ", ")
    )
    kong.log.warn(LOG_PREFIX, fmt("consumer=%s denied: %s", consumer.id, reason))
    log_validation_event(consumer, subscription, "denied", reason)
    return kong.response.exit(403, {
      message = fmt(
        "Your subscription tier (%s) does not have access to this endpoint. Required: %s",
        subscription.tier or "none",
        table.concat(conf.allowed_tiers, ", ")
      ),
      error          = "insufficient_tier",
      current_tier   = subscription.tier,
      required_tiers = conf.allowed_tiers,
    })
  end

  -- All checks passed -- inject subscription headers and proceed
  set_subscription_headers(conf, subscription)
  log_validation_event(consumer, subscription, "allowed", "valid_subscription")
end

return SubscriptionValidator
