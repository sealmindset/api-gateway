"""Tests for app.ai.safety.validate -- AI output validation."""

import json

import pytest

from app.ai.safety.validate import (
    _sanitize_text,
    _validate_structured,
    validate_agent_output,
)


# ---------------------------------------------------------------------------
# validate_agent_output -- main entry point
# ---------------------------------------------------------------------------

class TestValidateAgentOutput:
    def test_empty_input(self):
        result = validate_agent_output("")
        assert result["sanitized_text"] == ""
        assert result["structured"] is False

    def test_plain_text(self):
        result = validate_agent_output("This is a normal response.")
        assert result["structured"] is False
        assert "This is a normal response." in result["sanitized_text"]

    def test_valid_json(self):
        data = {"score": 0.8, "action": "allow", "reason": "Normal traffic"}
        result = validate_agent_output(json.dumps(data))
        assert result["structured"] is True
        assert result["data"]["score"] == 0.8
        assert result["data"]["action"] == "allow"

    def test_invalid_json_falls_back_to_text(self):
        result = validate_agent_output("{invalid json")
        assert result["structured"] is False

    def test_xss_stripped_from_text(self):
        result = validate_agent_output("Hello <script>alert('xss')</script> world")
        assert "<script>" not in result["sanitized_text"]
        assert "[html-removed]" in result["sanitized_text"]

    def test_xss_stripped_from_json_values(self):
        data = {"reason": "See <script>alert(1)</script> for details"}
        result = validate_agent_output(json.dumps(data))
        assert result["structured"] is True
        assert "<script>" not in result["data"]["reason"]

    def test_system_prompt_leakage_redacted(self):
        result = validate_agent_output("You are an AI assistant trained to help.")
        assert "[system-prompt-content-redacted]" in result["sanitized_text"]

    def test_markdown_injection_stripped(self):
        result = validate_agent_output("Click ![img](javascript:alert(1))")
        assert "javascript:" not in result["sanitized_text"]
        assert "[md-injection-removed]" in result["sanitized_text"]


# ---------------------------------------------------------------------------
# Structured field validation
# ---------------------------------------------------------------------------

class TestValidateStructured:
    def test_score_clamped_high(self):
        result = _validate_structured({"score": 5.0})
        assert result["score"] == 1.0

    def test_score_clamped_low(self):
        result = _validate_structured({"score": -0.5})
        assert result["score"] == 0.0

    def test_score_normal(self):
        result = _validate_structured({"score": 0.75})
        assert result["score"] == 0.75

    def test_confidence_clamped(self):
        result = _validate_structured({"confidence": 1.5})
        assert result["confidence"] == 1.0

    def test_risk_score_clamped(self):
        result = _validate_structured({"risk_score": -1.0})
        assert result["risk_score"] == 0.0

    def test_anomaly_score_clamped(self):
        result = _validate_structured({"anomaly_score": 99.0})
        assert result["anomaly_score"] == 1.0

    def test_invalid_numeric_defaults_to_min(self):
        result = _validate_structured({"score": "not-a-number"})
        assert result["score"] == 0.0

    def test_valid_action_unchanged(self):
        result = _validate_structured({"action": "block"})
        assert result["action"] == "block"

    def test_invalid_action_defaults(self):
        result = _validate_structured({"action": "destroy"})
        # "unknown" is not in the action enum, so it should pick sorted(allowed)[0] = "alert"
        assert result["action"] == "alert"

    def test_valid_anomaly_type_unchanged(self):
        result = _validate_structured({"anomaly_type": "rate_spike"})
        assert result["anomaly_type"] == "rate_spike"

    def test_invalid_anomaly_type_defaults_to_unknown(self):
        result = _validate_structured({"anomaly_type": "cosmic_ray"})
        assert result["anomaly_type"] == "unknown"

    def test_unknown_fields_passed_through(self):
        result = _validate_structured({"custom_field": "untouched", "score": 0.5})
        assert result["custom_field"] == "untouched"
        assert result["score"] == 0.5


# ---------------------------------------------------------------------------
# Free-text sanitization
# ---------------------------------------------------------------------------

class TestSanitizeText:
    def test_script_tag(self):
        assert "[html-removed]" in _sanitize_text("<script>alert(1)</script>")

    def test_iframe_tag(self):
        assert "[html-removed]" in _sanitize_text('<iframe src="evil.com"></iframe>')

    def test_object_tag(self):
        assert "[html-removed]" in _sanitize_text('<object data="x"></object>')

    def test_safe_html_not_stripped(self):
        text = "<p>This is <b>safe</b> HTML</p>"
        assert _sanitize_text(text) == text

    def test_system_prompt_leakage_line_redacted(self):
        text = "Line one.\nYou are an AI assistant.\nLine three."
        result = _sanitize_text(text)
        lines = result.split("\n")
        assert lines[0] == "Line one."
        assert lines[1] == "[system-prompt-content-redacted]"
        assert lines[2] == "Line three."
