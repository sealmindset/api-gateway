"""Tests for app.ai.safety.pii_masker -- PII detection and masking."""

import pytest

from app.ai.safety.pii_masker import mask_pii, unmask_pii


class TestMaskPii:
    def test_empty_input(self):
        masked, mappings = mask_pii("")
        assert masked == ""
        assert mappings == {}

    def test_no_pii(self):
        text = "This is a normal API request with no PII."
        masked, mappings = mask_pii(text)
        assert masked == text
        assert mappings == {}

    # -- Email --
    def test_email_masked(self):
        masked, mappings = mask_pii("Contact rob@example.com for details.")
        assert "rob@example.com" not in masked
        assert "[EMAIL_1]" in masked
        assert any(v == "rob@example.com" for v in mappings.values())

    def test_multiple_emails(self):
        text = "Send to alice@example.com and bob@example.com"
        masked, mappings = mask_pii(text)
        assert "alice@example.com" not in masked
        assert "bob@example.com" not in masked
        assert len([k for k in mappings if "EMAIL" in k]) == 2

    # -- SSN --
    def test_ssn_masked(self):
        masked, mappings = mask_pii("SSN: 123-45-6789")
        assert "123-45-6789" not in masked
        assert "[SSN_1]" in masked

    # -- Credit Cards --
    def test_visa_masked(self):
        masked, mappings = mask_pii("Card: 4111111111111111")
        assert "4111111111111111" not in masked
        assert "[CREDIT_CARD_1]" in masked

    def test_amex_masked(self):
        masked, mappings = mask_pii("Card: 371449635398431")
        assert "371449635398431" not in masked
        assert "[CREDIT_CARD_1]" in masked

    # -- Phone --
    def test_us_phone_masked(self):
        masked, mappings = mask_pii("Call 555-123-4567")
        assert "555-123-4567" not in masked
        assert "[PHONE_1]" in masked

    # -- IP Address --
    def test_ipv4_masked(self):
        masked, mappings = mask_pii("Source IP: 192.168.1.100")
        assert "192.168.1.100" not in masked
        assert "[IP_ADDRESS_1]" in masked

    # -- AWS Key --
    def test_aws_key_masked(self):
        masked, mappings = mask_pii("Key: AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in masked
        assert "[AWS_KEY_1]" in masked

    # -- API Key --
    def test_api_key_masked(self):
        masked, mappings = mask_pii("Token: sk-abc123def456ghi789jkl012mno")
        assert "sk-abc123def456ghi789jkl012mno" not in masked
        assert "[API_KEY_1]" in masked


class TestUnmaskPii:
    def test_empty_mappings(self):
        assert unmask_pii("Hello [EMAIL_1]", {}) == "Hello [EMAIL_1]"

    def test_empty_text(self):
        assert unmask_pii("", {"[EMAIL_1]": "a@b.com"}) == ""

    def test_round_trip(self):
        original = "Contact rob@example.com, SSN 123-45-6789, IP 10.0.0.1"
        masked, mappings = mask_pii(original)
        restored = unmask_pii(masked, mappings)
        assert "rob@example.com" in restored
        assert "123-45-6789" in restored
        assert "10.0.0.1" in restored

    def test_round_trip_multiple_types(self):
        original = "User alice@test.com from 192.168.0.1 card 4111111111111111"
        masked, mappings = mask_pii(original)
        # Verify all PII was masked
        assert "alice@test.com" not in masked
        assert "192.168.0.1" not in masked
        assert "4111111111111111" not in masked
        # Verify round-trip restores everything
        restored = unmask_pii(masked, mappings)
        assert "alice@test.com" in restored
        assert "192.168.0.1" in restored
        assert "4111111111111111" in restored
