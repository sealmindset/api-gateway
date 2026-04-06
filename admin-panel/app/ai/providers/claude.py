"""
Claude (Anthropic) provider implementation for AI-driven API gateway capabilities.

Uses Anthropic's Claude models to power anomaly detection, rate-limit advising,
smart routing, request/response transformation, and documentation generation.
Includes DOE self-annealing for model configuration error detection and correction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from .base import AIProvider
from ..prompt_resolver import resolve_prompt
# Hardcoded imports retained as fallback for sync contexts
from ..prompts import (
    ANOMALY_DETECTION_SYSTEM_PROMPT,
    RATE_LIMIT_ADVISOR_SYSTEM_PROMPT,
    SMART_ROUTING_SYSTEM_PROMPT,
    REQUEST_TRANSFORM_SYSTEM_PROMPT,
    DOCUMENTATION_SYSTEM_PROMPT,
    REQUEST_ANALYSIS_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DOE Self-Annealing: Model Configuration Error Detection
# =============================================================================

class ClaudeModelSelfAnnealing:
    """
    DOE Self-Annealing for Claude model configuration errors.

    Detects model mismatches from API errors and auto-corrects them
    to a known-good model identifier.
    """

    VALID_CLAUDE_MODELS = [
        # Direct Anthropic API models
        "claude-sonnet-4-20250514",
        "claude-opus-4-6",
        "claude-haiku-4-5-20251001",
        # Azure AI Foundry deployment names (prefix match)
        "cogdep-aifoundry-dev-eus2-claude-sonnet-4-5",
        "cogdep-aifoundry-dev-eus2-claude-opus-4-6",
        "cogdep-aifoundry-dev-eus2-claude-haiku-4-5",
    ]

    # Prefix for Azure AI Foundry deployment names
    AZURE_FOUNDRY_PREFIX = "cogdep-aifoundry-"

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self) -> None:
        self.corrections: list[dict[str, Any]] = []
        self.logger = logging.getLogger("DOE.SelfAnnealing.Claude")

    # -----------------------------------------------------------------

    def detect_model_error(self, error_message: str) -> bool:
        """Detect if an error is caused by an invalid model configuration."""
        error_lower = error_message.lower()

        invalid_prefixes = ["llama", "gpt-", "mistral", "gemma", "phi", "qwen"]
        if "model:" in error_lower:
            for prefix in invalid_prefixes:
                if prefix in error_lower:
                    return True

        if "not_found_error" in error_lower and "model" in error_lower:
            return True

        return False

    def extract_bad_model(self, error_message: str) -> Optional[str]:
        """Extract the invalid model name from an error message."""
        import re

        match = re.search(r"model:\s*(\S+)", error_message, re.IGNORECASE)
        if match:
            return match.group(1).strip("'\"")
        return None

    def correct_model(self, current_model: str, error_message: str) -> str:
        """Auto-correct to a valid Claude model and log the correction."""
        bad_model = self.extract_bad_model(error_message) or current_model

        correction = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_model": bad_model,
            "corrected_model": self.DEFAULT_MODEL,
            "error_trigger": error_message[:200],
            "reason": f"Model '{bad_model}' is not a valid Claude model",
        }
        self.corrections.append(correction)

        self.logger.warning(
            "DOE Self-Annealing: Detected invalid Claude model '%s' from API error. "
            "Auto-correcting to '%s'",
            bad_model,
            self.DEFAULT_MODEL,
        )
        return self.DEFAULT_MODEL

    def validate_model(self, model: str) -> str:
        """
        Validate a model name at initialisation time.

        Returns the model unchanged if valid, otherwise auto-corrects to
        the default model.
        """
        if not model:
            self.logger.warning(
                "DOE Self-Annealing: No model provided, defaulting to '%s'",
                self.DEFAULT_MODEL,
            )
            return self.DEFAULT_MODEL

        model_lower = model.lower()

        # Accept any Azure AI Foundry deployment name
        if model_lower.startswith(self.AZURE_FOUNDRY_PREFIX.lower()):
            return model

        # Check against known direct models
        for valid in self.VALID_CLAUDE_MODELS:
            if valid.lower() in model_lower or model_lower in valid.lower():
                return model

        # Model not recognised -- correct it
        self.logger.warning(
            "DOE Self-Annealing: Model '%s' does not appear to be a valid "
            "Claude model.  Correcting to '%s'",
            model,
            self.DEFAULT_MODEL,
        )
        self.corrections.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "original_model": model,
                "corrected_model": self.DEFAULT_MODEL,
                "reason": "Model validation at initialisation",
            }
        )
        return self.DEFAULT_MODEL


# Global self-annealing instance
_claude_model_annealing = ClaudeModelSelfAnnealing()


# =============================================================================
# Claude Provider
# =============================================================================

class ClaudeProvider(AIProvider):
    """
    Anthropic Claude provider for AI-driven API gateway capabilities.

    Supports anomaly detection, adaptive rate limiting, smart routing,
    request/response transformation, and documentation generation.
    """

    # Per-1M-token pricing (USD) -- updated for current models
    PRICING: dict[str, dict[str, float]] = {
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-opus-4-6": {"input": 15.00, "output": 75.00},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    }

    # Fallback pricing when the model is not in the pricing table
    _DEFAULT_PRICING: dict[str, float] = {"input": 3.00, "output": 15.00}

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        max_cost_per_analysis: float = 0.50,
    ) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic library not installed.  Install with: pip install anthropic"
            )

        # DOE Self-Annealing: validate and correct the model at init time
        validated_model = _claude_model_annealing.validate_model(model)

        super().__init__(
            api_key=api_key,
            model=validated_model,
            max_tokens=max_tokens,
            max_cost_per_analysis=max_cost_per_analysis,
        )
        self.client = AsyncAnthropic(api_key=api_key)
        logger.info("Initialised Claude provider with model: %s", validated_model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_prompt(self, slug: str, fallback: str) -> str:
        """Resolve a prompt from the DB, falling back to the hardcoded constant."""
        try:
            resolved = await resolve_prompt(slug)
            if resolved:
                return resolved
        except Exception as exc:
            logger.warning("Prompt resolution failed for '%s': %s", slug, exc)
        return fallback

    async def _call_api_with_retry(self, **kwargs: Any) -> Any:
        """
        Execute a Claude API call with retry logic for rate limits
        and DOE self-annealing for model errors.

        Retries up to 3 times with exponential backoff (5s, 10s, 20s)
        on 429 / rate-limit errors.
        """
        retries = 3
        base_delay = 5  # seconds
        model_corrected = False

        for attempt in range(retries + 1):
            try:
                return await self.client.messages.create(**kwargs)
            except Exception as exc:
                error_str = str(exc)
                error_lower = error_str.lower()

                # DOE Self-Annealing: model configuration error
                if (
                    _claude_model_annealing.detect_model_error(error_str)
                    and not model_corrected
                ):
                    corrected = _claude_model_annealing.correct_model(
                        self.model, error_str
                    )
                    logger.warning(
                        "DOE Self-Annealing: correcting model from '%s' to '%s'",
                        self.model,
                        corrected,
                    )
                    self.model = corrected
                    kwargs["model"] = corrected
                    model_corrected = True
                    continue

                # Rate-limit retry
                if "429" in error_lower or "rate_limit" in error_lower:
                    if attempt < retries:
                        delay = base_delay * (2 ** attempt)  # 5, 10, 20
                        logger.warning(
                            "Claude rate limit hit.  Retrying in %ds (attempt %d/%d)",
                            delay,
                            attempt + 1,
                            retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                logger.error("Claude API call failed: %s", exc)
                raise

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """
        Parse a JSON response from Claude, handling markdown code fences
        and common formatting issues.
        """
        cleaned = self._strip_markdown_fences(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Attempt to find the first JSON object in the text
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end])
                except json.JSONDecodeError:
                    pass
            logger.error("Failed to parse JSON from Claude response (length=%d)", len(text))
            raise ValueError(f"Could not parse JSON from model response: {text[:200]}")

    # ------------------------------------------------------------------
    # Implemented capabilities
    # ------------------------------------------------------------------

    async def analyze_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze an incoming API request for patterns and classify intent."""
        sanitized = self._sanitize_input(json.dumps(request_data, default=str))
        masked, pii_map = self._mask_pii(sanitized)
        system_prompt = await self._resolve_prompt("request-analysis", REQUEST_ANALYSIS_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": masked}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        content = self._unmask_pii(content, pii_map)

        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        return self._parse_json_response(content)

    # -----------------------------------------------------------------

    async def detect_anomaly(
        self,
        request_metrics: dict[str, Any],
        historical_baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Detect anomalies in request metrics against a historical baseline."""
        payload = {
            "current_metrics": request_metrics,
            "baseline": historical_baseline,
        }
        sanitized = self._sanitize_input(json.dumps(payload, default=str))
        system_prompt = await self._resolve_prompt("anomaly-detection", ANOMALY_DETECTION_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,  # deterministic for security decisions
            system=system_prompt,
            messages=[{"role": "user", "content": sanitized}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        result = self._parse_json_response(content)

        # Clamp score and confidence to [0, 1]
        result["score"] = max(0.0, min(1.0, float(result.get("score", 0.0))))
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

        return result

    # -----------------------------------------------------------------

    async def suggest_rate_limit(
        self,
        consumer_id: str,
        usage_history: list[dict[str, Any]],
        current_limits: dict[str, Any],
    ) -> dict[str, Any]:
        """Suggest adaptive rate limits for a consumer."""
        payload = {
            "consumer_id": consumer_id,
            "usage_history": usage_history,
            "current_limits": current_limits,
        }
        sanitized = self._sanitize_input(json.dumps(payload, default=str))
        system_prompt = await self._resolve_prompt("rate-limit-advisor", RATE_LIMIT_ADVISOR_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,  # deterministic for rate-limit decisions
            system=system_prompt,
            messages=[{"role": "user", "content": sanitized}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        result = self._parse_json_response(content)
        result.setdefault("consumer_id", consumer_id)
        return result

    # -----------------------------------------------------------------

    async def generate_routing_decision(
        self,
        request: dict[str, Any],
        available_backends: list[dict[str, Any]],
        backend_health: dict[str, Any],
    ) -> dict[str, Any]:
        """Decide which backend should handle the incoming request."""
        payload = {
            "request": request,
            "available_backends": available_backends,
            "backend_health": backend_health,
        }
        sanitized = self._sanitize_input(json.dumps(payload, default=str))
        system_prompt = await self._resolve_prompt("smart-routing", SMART_ROUTING_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.3,  # allow some flexibility in routing
            system=system_prompt,
            messages=[{"role": "user", "content": sanitized}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        return self._parse_json_response(content)

    # -----------------------------------------------------------------

    async def transform_request(
        self,
        request: dict[str, Any],
        transformation_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply AI-powered transformations to an API request."""
        payload = {
            "data": request,
            "transformation_rules": transformation_rules,
            "direction": "request",
        }
        sanitized = self._sanitize_input(json.dumps(payload, default=str))
        masked, pii_map = self._mask_pii(sanitized)
        system_prompt = await self._resolve_prompt("request-transform", REQUEST_TRANSFORM_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": masked}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        content = self._unmask_pii(content, pii_map)
        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        return self._parse_json_response(content)

    # -----------------------------------------------------------------

    async def transform_response(
        self,
        response_data: dict[str, Any],
        transformation_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply AI-powered transformations to an API response."""
        payload = {
            "data": response_data,
            "transformation_rules": transformation_rules,
            "direction": "response",
        }
        sanitized = self._sanitize_input(json.dumps(payload, default=str))
        masked, pii_map = self._mask_pii(sanitized)
        system_prompt = await self._resolve_prompt("response-transform", REQUEST_TRANSFORM_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": masked}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        content = self._unmask_pii(content, pii_map)
        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        return self._parse_json_response(content)

    # -----------------------------------------------------------------

    async def generate_documentation(
        self,
        openapi_spec_or_traffic_sample: dict[str, Any] | str,
    ) -> dict[str, Any]:
        """Auto-generate API documentation from an OpenAPI spec or traffic sample."""
        if isinstance(openapi_spec_or_traffic_sample, dict):
            raw = json.dumps(openapi_spec_or_traffic_sample, default=str)
        else:
            raw = str(openapi_spec_or_traffic_sample)

        sanitized = self._sanitize_input(raw)
        system_prompt = await self._resolve_prompt("api-documentation", DOCUMENTATION_SYSTEM_PROMPT)

        response = await self._call_api_with_retry(
            model=self.model,
            max_tokens=min(self.max_tokens, 8192),  # docs can be long
            temperature=0.5,  # creative for documentation
            system=system_prompt,
            messages=[{"role": "user", "content": sanitized}],
        )

        content = response.content[0].text
        content = self._validate_output(content)
        self._track_usage(response.usage.input_tokens, response.usage.output_tokens)

        return self._parse_json_response(content)

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate the cost of a Claude API call in USD.

        Uses per-model pricing when available, otherwise falls back to
        default Sonnet-class pricing.
        """
        pricing = self.PRICING.get(self.model, self._DEFAULT_PRICING)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
