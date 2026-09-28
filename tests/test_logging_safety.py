"""Tests for safe zero-PII logging."""

import logging
from app.logging_config import logger


def test_zero_pii_logging_filters_sensitive_fields(caplog):
    """Verifies that ticket body, subject, names, company names, and GSTIN are never logged."""
    with caplog.at_level(logging.INFO):
        logger.log_event(
            stage="triage_test",
            ticket_id="T-1010",
            subject="invoice needed",
            body="Acme Interiors, 29ABCDE1234F1Z5",
            company="Acme Interiors",
            gstin="29ABCDE1234F1Z5",
            category="invoice",
            severity="low",
            duration_ms=45.2
        )

    log_output = caplog.text

    # Must contain safe metadata
    assert "stage=triage_test" in log_output
    assert "ticket_id=T-1010" in log_output
    assert "category=invoice" in log_output
    assert "severity=low" in log_output

    # Must NOT contain forbidden PII
    assert "Acme Interiors" not in log_output
    assert "29ABCDE1234F1Z5" not in log_output
    assert "invoice needed" not in log_output
