-- =============================================================================
-- Kong Plugin Schema: ai-gateway
-- =============================================================================
-- Defines the configuration schema for the ai-gateway plugin. This file is
-- loaded by Kong to validate plugin configuration at setup time.
-- =============================================================================

local typedefs = require "kong.db.schema.typedefs"

return {
  name = "ai-gateway",
  fields = {
    { protocols = typedefs.protocols_http },
    { consumer = typedefs.no_consumer },
    { config = {
        type = "record",
        fields = {
          -- -----------------------------------------------------------------
          -- AI service endpoint
          -- -----------------------------------------------------------------
          {
            ai_endpoint = {
              type = "string",
              default = "http://admin-panel:8080/api/ai",
              required = true,
              description = "Base URL of the AI gateway admin panel API",
            },
          },

          -- -----------------------------------------------------------------
          -- Feature toggles
          -- -----------------------------------------------------------------
          {
            enable_anomaly_detection = {
              type = "boolean",
              default = true,
              description = "Enable AI-powered anomaly detection on incoming requests",
            },
          },
          {
            enable_smart_routing = {
              type = "boolean",
              default = false,
              description = "Enable AI-powered smart routing to select optimal backend",
            },
          },
          {
            enable_request_transform = {
              type = "boolean",
              default = false,
              description = "Enable AI-powered request body transformation",
            },
          },
          {
            enable_response_transform = {
              type = "boolean",
              default = false,
              description = "Enable AI-powered response body transformation",
            },
          },

          -- -----------------------------------------------------------------
          -- Thresholds and tuning
          -- -----------------------------------------------------------------
          {
            anomaly_threshold = {
              type = "number",
              default = 0.7,
              between = { 0.0, 1.0 },
              description = "Anomaly score threshold above which requests are flagged (0.0-1.0)",
            },
          },
          {
            sampling_rate = {
              type = "number",
              default = 0.1,
              between = { 0.0, 1.0 },
              description = "Fraction of requests to analyze (0.0 = none, 1.0 = all)",
            },
          },

          -- -----------------------------------------------------------------
          -- Caching
          -- -----------------------------------------------------------------
          {
            cache_ttl = {
              type = "integer",
              default = 60,
              gt = 0,
              description = "Seconds to cache AI analysis results in Kong shared cache",
            },
          },

          -- -----------------------------------------------------------------
          -- HTTP client settings
          -- -----------------------------------------------------------------
          {
            timeout = {
              type = "integer",
              default = 5000,
              gt = 0,
              description = "Timeout in milliseconds for calls to the AI endpoint",
            },
          },

          -- -----------------------------------------------------------------
          -- Resilience
          -- -----------------------------------------------------------------
          {
            fail_open = {
              type = "boolean",
              default = true,
              description = "If true, allow requests through when the AI endpoint is unreachable",
            },
          },

          -- -----------------------------------------------------------------
          -- Request transformation rules (natural language)
          -- -----------------------------------------------------------------
          {
            request_transform_rules = {
              type = "string",
              default = "",
              description = "Natural-language rules for AI request transformation",
            },
          },
          {
            response_transform_rules = {
              type = "string",
              default = "",
              description = "Natural-language rules for AI response transformation",
            },
          },

          -- -----------------------------------------------------------------
          -- Smart routing backend list (JSON array string)
          -- -----------------------------------------------------------------
          {
            routing_backends = {
              type = "array",
              elements = { type = "string" },
              default = {},
              description = "List of backend names available for smart routing decisions",
            },
          },

          -- -----------------------------------------------------------------
          -- Anomaly action
          -- -----------------------------------------------------------------
          {
            anomaly_action = {
              type = "string",
              default = "header",
              one_of = { "block", "header", "log" },
              description = "Action when anomaly detected: block (403), header (warn), or log only",
            },
          },
        },
      },
    },
  },
}
