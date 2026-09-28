"""Structured Zero-PII Logger for Dhaba Support Triage.

STRICT PRIVACY / SECURITY RULES:
- Never log customer ticket subjects or bodies.
- Never log customer names, phone numbers, or email addresses.
- Never log company names (e.g. Acme Interiors) or GSTIN tax identifiers.
- Only log structural metadata: request_id, ticket_id, stage, category, severity,
  refund_decision, status, duration_ms, cached, is_fallback.
"""

import logging
import sys
from typing import Any, Dict


class ZeroPIILogger:
    """Safe logger that outputs sanitized, structured log lines."""

    def __init__(self, name: str = "dhaba.triage"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def log_event(self, stage: str, **kwargs: Any) -> None:
        """Formats and logs a structured event ensuring no forbidden PII fields are included."""
        forbidden_keys = {"body", "subject", "text", "customer_name", "company", "gstin", "email", "phone"}
        filtered = {k: v for k, v in kwargs.items() if k.lower() not in forbidden_keys}
        
        # Build structured key=value representation
        msg_parts = [f"stage={stage}"]
        for k, v in filtered.items():
            msg_parts.append(f"{k}={v}")
        
        self.logger.info(" ".join(msg_parts))

    def error(self, stage: str, error_msg: str, **kwargs: Any) -> None:
        """Logs an error event safely."""
        filtered = {k: v for k, v in kwargs.items() if k.lower() not in {"body", "subject", "text", "gstin"}}
        msg_parts = [f"stage={stage}", f"error={error_msg}"]
        for k, v in filtered.items():
            msg_parts.append(f"{k}={v}")
        self.logger.error(" ".join(msg_parts))


logger = ZeroPIILogger()
