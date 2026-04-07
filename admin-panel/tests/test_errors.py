"""Tests for app.ai.safety.errors -- AI error sanitization."""

import pytest

from app.ai.safety.errors import sanitize_ai_error


class TestSanitizeAiError:
    def test_rate_limit_error(self):
        result = sanitize_ai_error(Exception("429 Too Many Requests"))
        assert result["status_code"] == 429
        assert result["safe"] is True
        assert result["retry"] is True
        assert "busy" in result["message"].lower()

    def test_auth_error(self):
        result = sanitize_ai_error(Exception("401 Unauthorized: invalid api key"))
        assert result["status_code"] == 503
        assert result["safe"] is True
        assert result["retry"] is True  # 503 is retryable
        assert "administrator" in result["message"].lower()

    def test_timeout_error(self):
        result = sanitize_ai_error(Exception("Request timed out"))
        assert result["status_code"] == 504
        assert result["retry"] is True

    def test_content_filter_error(self):
        result = sanitize_ai_error(Exception("Content blocked by safety filter"))
        assert result["status_code"] == 422
        assert result["retry"] is False
        assert "content restrictions" in result["message"].lower()

    def test_model_not_found(self):
        result = sanitize_ai_error(Exception("not_found_error: model claude-9 does not exist"))
        assert result["status_code"] == 503
        assert "administrator" in result["message"].lower()

    def test_overloaded(self):
        result = sanitize_ai_error(Exception("503 Service Unavailable: overloaded"))
        assert result["status_code"] == 503
        assert result["retry"] is True

    def test_token_limit(self):
        result = sanitize_ai_error(Exception("Token limit exceeded: 200000 tokens"))
        assert result["status_code"] == 413
        assert "too large" in result["message"].lower()

    def test_unknown_error_fallback(self):
        result = sanitize_ai_error(Exception("Something completely unexpected"))
        assert result["status_code"] == 500
        assert result["safe"] is True
        assert result["retry"] is True
        assert "try again" in result["message"].lower()

    def test_api_key_not_leaked(self):
        """The safe message should never contain the original API key."""
        result = sanitize_ai_error(
            Exception("401 Unauthorized with key sk-abcdefghijklmnopqrstuvwxyz1234567890")
        )
        assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in result["message"]

    def test_provider_url_not_leaked(self):
        result = sanitize_ai_error(
            Exception("Failed to connect to https://api.anthropic.com/v1/messages")
        )
        assert "anthropic.com" not in result["message"]
