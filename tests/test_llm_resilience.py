"""Tests for LLM parsing, validation, retry mechanism, and safe fallback."""

import pytest
from app.schemas import CategoryEnum, SeverityEnum, LLMClassificationOutput
from app.llm import (
    extract_json_text,
    parse_and_validate_llm_json,
    create_safe_fallback,
    GeminiClient,
)


def test_extract_json_from_markdown_fences():
    """Verifies that markdown code blocks are cleanly stripped."""
    raw_fenced = '```json\n{"category": "billing", "severity": "high", "reply_draft": "Hello", "needs_human": true, "confidence": 0.9}\n```'
    clean = extract_json_text(raw_fenced)
    assert clean.startswith("{")
    assert clean.endswith("}")


def test_parse_valid_json():
    """Verifies parsing of valid LLM JSON output."""
    raw = '{"category": "technical_issue", "severity": "high", "reply_draft": "We are fixing this.", "needs_human": true, "confidence": 0.95}'
    parsed = parse_and_validate_llm_json(raw)
    assert parsed.category == CategoryEnum.TECHNICAL_ISSUE
    assert parsed.severity == SeverityEnum.HIGH
    assert parsed.needs_human is True
    assert parsed.confidence == 0.95


def test_parse_invalid_category_raises():
    """Verifies that an unapproved category is rejected during validation."""
    raw = '{"category": "invented_category", "severity": "high", "reply_draft": "Hello", "needs_human": true, "confidence": 0.95}'
    with pytest.raises(Exception):
        parse_and_validate_llm_json(raw)


def test_parse_invalid_confidence_range_raises():
    """Verifies that confidence outside [0.0, 1.0] is rejected."""
    raw = '{"category": "billing", "severity": "high", "reply_draft": "Hello", "needs_human": true, "confidence": 1.5}'
    with pytest.raises(Exception):
        parse_and_validate_llm_json(raw)


def test_safe_fallback_contract():
    """Verifies that safe fallback adheres strictly to the defined contract."""
    fallback, is_fallback = create_safe_fallback()
    assert is_fallback is True
    assert fallback.category == CategoryEnum.UNKNOWN
    assert fallback.severity == SeverityEnum.HIGH
    assert fallback.confidence == 0.0
    assert fallback.needs_human is True
    assert len(fallback.reply_draft) > 0


def test_gemini_client_retry_and_fallback(monkeypatch):
    """Simulates a malformed first response followed by a successful retry."""
    client = GeminiClient(api_key="test_key")

    call_count = 0

    def mock_call(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt returns malformed JSON
            return "This is malformed prose without JSON"
        # Second attempt (retry) returns valid JSON
        return '{"category": "billing", "severity": "medium", "reply_draft": "Help on the way", "needs_human": false, "confidence": 0.88}'

    monkeypatch.setattr(client, "_call_gemini_raw", mock_call)

    output, is_fallback = client.classify_ticket("Help", "Billing problem")
    assert call_count == 2
    assert is_fallback is False
    assert output.category == CategoryEnum.BILLING
    assert output.confidence == 0.88


def test_gemini_client_exhausted_retries_produces_fallback(monkeypatch):
    """Simulates persistent model failures triggering safe degraded fallback."""
    client = GeminiClient(api_key="test_key")

    def mock_call_failing(prompt):
        raise RuntimeError("API Connection Timeout")

    monkeypatch.setattr(client, "_call_gemini_raw", mock_call_failing)

    output, is_fallback = client.classify_ticket("Help", "Problem")
    assert is_fallback is True
    assert output.category == CategoryEnum.UNKNOWN
    assert output.severity == SeverityEnum.HIGH
    assert output.confidence == 0.0
    assert output.needs_human is True


def test_low_confidence_forces_needs_human(monkeypatch):
    """Verifies that confidence below threshold (0.75) forces needs_human=True."""
    client = GeminiClient(api_key="test_key")

    def mock_call_low_conf(prompt):
        return '{"category": "billing", "severity": "low", "reply_draft": "Maybe", "needs_human": false, "confidence": 0.60}'

    monkeypatch.setattr(client, "_call_gemini_raw", mock_call_low_conf)

    output, is_fallback = client.classify_ticket("Ambiguous", "Not sure")
    assert output.confidence == 0.60
    assert output.needs_human is True
