"""Pydantic schemas and domain enums for Dhaba Support Triage."""

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class CategoryEnum(str, Enum):
    """Documented 10-category enum for ticket classification."""
    BILLING = "billing"
    TECHNICAL_ISSUE = "technical_issue"
    ACCOUNT = "account"
    CANCELLATION = "cancellation"
    PAYMENT_ISSUE = "payment_issue"
    FEATURE_REQUEST = "feature_request"
    INVOICE = "invoice"
    SUBSCRIPTION_QUESTION = "subscription_question"
    FRAUD = "fraud"
    UNKNOWN = "unknown"


class SeverityEnum(str, Enum):
    """Documented 4-level severity scale."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RefundDecisionEnum(str, Enum):
    """Deterministic refund policy decision outcomes."""
    APPROVED = "approved"
    REJECTED = "rejected"
    NO_REFUND = "no_refund"
    HUMAN_REVIEW = "human_review"


class Purchase(BaseModel):
    """Billing transaction history object."""
    id: str = Field(..., description="Unique transaction ID (e.g. pay_A1)")
    type: Literal["trial", "renewal"] = Field(..., description="Type of purchase")
    amount_inr: int = Field(..., ge=0, description="Transaction amount in INR")
    status: Literal["initiated", "failed", "successful"] = Field(..., description="Transaction status")
    at: str = Field(..., description="ISO-8601 timestamp string of purchase")


class TicketInput(BaseModel):
    """Input ticket schema matching dhaba_tickets.json structure exactly."""
    id: str = Field(..., min_length=1, description="Ticket identifier")
    received_at: str = Field(..., description="ISO-8601 timestamp of ticket receipt")
    subject: str = Field(..., description="Customer subject line")
    body: str = Field(..., description="Customer ticket body (untrusted content)")
    purchases: list[Purchase] = Field(default_factory=list, description="Billing transaction history")
    app_opens_since_renewal: int = Field(default=0, ge=0, description="Count of app opens since last renewal")


class RefundResult(BaseModel):
    """Structured refund decision outcome from deterministic engine."""
    decision: RefundDecisionEnum = Field(..., description="Outcome decision")
    amount_inr: int = Field(default=0, ge=0, description="Amount to refund in INR (0 if not approved)")
    reason: str = Field(..., min_length=1, description="Audit reason for decision")


class LLMClassificationOutput(BaseModel):
    """Strict schema for parsing and validating raw LLM output."""
    category: CategoryEnum = Field(..., description="Restricted ticket category")
    severity: SeverityEnum = Field(..., description="Restricted severity level")
    reply_draft: str = Field(..., min_length=1, description="Draft response in customer language")
    needs_human: bool = Field(..., description="Whether human review is required")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")

    @field_validator("confidence", mode="before")
    @classmethod
    def parse_confidence(cls, v):
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                raise ValueError(f"Invalid confidence float string: {v}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"Confidence must be numeric, got {type(v)}")
        return float(v)


class TriageResponse(BaseModel):
    """Final JSON response returned by POST /triage."""
    ticket_id: str = Field(..., description="Ticket ID")
    category: CategoryEnum = Field(..., description="Ticket category")
    severity: SeverityEnum = Field(..., description="Severity level")
    refund: RefundResult = Field(..., description="Deterministic refund policy result")
    reply_draft: str = Field(..., description="Draft reply addressed to user")
    needs_human: bool = Field(..., description="Flag indicating human review requirement")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    is_fallback: bool = Field(default=False, description="True if safe fallback was used")
    cached: bool = Field(default=False, description="True if response was retrieved from idempotency cache")
