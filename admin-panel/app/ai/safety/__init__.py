"""
AI Safety Module for the API Gateway.

Provides four safety controls that integrate with the AI provider base class:

- **sanitize**: Prompt injection protection and input sanitization
- **validate**: AI output validation (structured + free-text)
- **pii_masker**: PII masking before AI submission and unmasking after
- **errors**: Provider error sanitization for safe client responses
"""

from app.ai.safety.sanitize import sanitize_prompt_input
from app.ai.safety.validate import validate_agent_output
from app.ai.safety.pii_masker import mask_pii, unmask_pii
from app.ai.safety.errors import sanitize_ai_error

__all__ = [
    "sanitize_prompt_input",
    "validate_agent_output",
    "mask_pii",
    "unmask_pii",
    "sanitize_ai_error",
]
