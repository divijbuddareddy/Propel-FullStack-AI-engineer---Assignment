"""Tests for deterministic refund policy gate.

Ensures:
1. LLM output has zero direct authority over money.
2. Production refund policy code evaluates attributes, not hardcoded ticket IDs.
3. Disputed renewals, fraud allegations, and pending payments route to human review with ₹0 auto-refund.
"""

from app.schemas import CategoryEnum, SeverityEnum, RefundDecisionEnum, Purchase
from app.refund_policy import evaluate_refund_policy


def test_non_billing_categories_return_no_refund():
    """Verifies that non-billing categories (e.g. invoice, feature requests) return NO_REFUND."""
    purchases = [
        Purchase(id="p1", type="renewal", amount_inr=1499, status="successful", at="2026-08-28T11:20:00+05:30")
    ]
    result = evaluate_refund_policy(
        category=CategoryEnum.INVOICE,
        severity=SeverityEnum.LOW,
        purchases=purchases,
        app_opens_since_renewal=27
    )
    assert result.decision == RefundDecisionEnum.NO_REFUND
    assert result.amount_inr == 0


def test_fraud_allegations_routed_to_human_review():
    """Verifies that fraud allegations require human review and do NOT auto-refund."""
    purchases = [
        Purchase(id="p1", type="trial", amount_inr=1, status="successful", at="2026-07-09T21:12:00+05:30"),
        Purchase(id="p2", type="renewal", amount_inr=249, status="successful", at="2026-07-10T21:14:00+05:30"),
        Purchase(id="p3", type="renewal", amount_inr=249, status="successful", at="2026-08-10T21:13:00+05:30")
    ]
    result = evaluate_refund_policy(
        category=CategoryEnum.FRAUD,
        severity=SeverityEnum.CRITICAL,
        purchases=purchases,
        app_opens_since_renewal=0
    )
    assert result.decision == RefundDecisionEnum.HUMAN_REVIEW
    assert result.amount_inr == 0
    assert "fraud" in result.reason.lower() or "security" in result.reason.lower()


def test_initiated_pending_payment_routed_to_human_review():
    """Verifies that unconfirmed/initiated payments route to human review for gateway reconciliation."""
    purchases = [
        Purchase(id="p1", type="trial", amount_inr=1, status="successful", at="2026-09-02T19:44:00+05:30"),
        Purchase(id="p2", type="renewal", amount_inr=249, status="initiated", at="2026-09-03T19:45:00+05:30")
    ]
    result = evaluate_refund_policy(
        category=CategoryEnum.PAYMENT_ISSUE,
        severity=SeverityEnum.HIGH,
        purchases=purchases,
        app_opens_since_renewal=6
    )
    assert result.decision == RefundDecisionEnum.HUMAN_REVIEW
    assert result.amount_inr == 0


def test_disputed_renewal_routed_to_human_review():
    """Verifies that disputed renewal charges route to human review with zero auto-refund."""
    purchases = [
        Purchase(id="p1", type="trial", amount_inr=1, status="successful", at="2026-08-31T20:02:00+05:30"),
        Purchase(id="p2", type="renewal", amount_inr=249, status="successful", at="2026-09-01T20:04:00+05:30")
    ]
    result = evaluate_refund_policy(
        category=CategoryEnum.BILLING,
        severity=SeverityEnum.HIGH,
        purchases=purchases,
        app_opens_since_renewal=0
    )
    assert result.decision == RefundDecisionEnum.HUMAN_REVIEW
    assert result.amount_inr == 0


def test_trial_cancellation_returns_no_refund():
    """Verifies that cancellation during trial returns NO_REFUND."""
    purchases = [
        Purchase(id="p1", type="trial", amount_inr=1, status="successful", at="2026-09-03T17:58:00+05:30")
    ]
    result = evaluate_refund_policy(
        category=CategoryEnum.CANCELLATION,
        severity=SeverityEnum.MEDIUM,
        purchases=purchases,
        app_opens_since_renewal=1
    )
    assert result.decision == RefundDecisionEnum.NO_REFUND
    assert result.amount_inr == 0


def test_perceived_double_charge_single_success_returns_no_refund():
    """Verifies that perceived double charge with 1 failed + 1 successful charge returns NO_REFUND."""
    purchases = [
        Purchase(id="p1", type="renewal", amount_inr=249, status="failed", at="2026-09-05T06:00:00+05:30"),
        Purchase(id="p2", type="renewal", amount_inr=249, status="successful", at="2026-09-05T06:03:00+05:30")
    ]
    result = evaluate_refund_policy(
        category=CategoryEnum.BILLING,
        severity=SeverityEnum.MEDIUM,
        purchases=purchases,
        app_opens_since_renewal=3
    )
    assert result.decision == RefundDecisionEnum.NO_REFUND
    assert result.amount_inr == 0
