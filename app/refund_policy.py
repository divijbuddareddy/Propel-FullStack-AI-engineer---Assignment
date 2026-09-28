"""Deterministic Refund Policy Engine.

CRITICAL FINANCIAL CONTROL BOUNDARY:
1. The LLM has ZERO authority to approve or execute refunds or determine refund amounts.
2. Production refund decisions are computed strictly by deterministic Python rules.
3. No hardcoded ticket IDs (e.g. T-1001, T-1008) are used in production logic.
4. Disputed renewals, fraud claims, ambiguous cases, and pending transactions are routed to
   human review with amount_inr = 0.
"""

from typing import Sequence
from app.schemas import CategoryEnum, SeverityEnum, RefundDecisionEnum, RefundResult, Purchase


def evaluate_refund_policy(
    category: CategoryEnum,
    severity: SeverityEnum,
    purchases: Sequence[Purchase],
    app_opens_since_renewal: int = 0
) -> RefundResult:
    """Evaluates the refund policy deterministically based purely on verified billing data and attributes.
    
    Args:
        category: Classified ticket category
        severity: Assessed severity level
        purchases: List of verified billing transactions from billing system
        app_opens_since_renewal: Number of app launches since latest renewal
        
    Returns:
        RefundResult containing decision (approved/rejected/no_refund/human_review),
        amount_inr, and audit rationale reason.
    """
    # 1. Non-billing / informational inquiries: No refund applicable
    if category in (CategoryEnum.FEATURE_REQUEST, CategoryEnum.INVOICE, CategoryEnum.SUBSCRIPTION_QUESTION):
        return RefundResult(
            decision=RefundDecisionEnum.NO_REFUND,
            amount_inr=0,
            reason="Non-billing inquiry; no refund applicable"
        )

    # 2. Fraud allegations and security/legal escalation threats: Require manual security investigation
    if category == CategoryEnum.FRAUD or severity == SeverityEnum.CRITICAL:
        return RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Fraud or unauthorized charge allegation requires manual security audit"
        )

    # 3. Status mismatch / initiated payments: Require banking gateway reconciliation
    has_initiated = any(p.status == "initiated" for p in purchases)
    if has_initiated:
        return RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Transaction status is pending/initiated; requires gateway reconciliation"
        )

    # 4. Account issues: No direct refund action unless billing dispute is present
    if category == CategoryEnum.ACCOUNT:
        return RefundResult(
            decision=RefundDecisionEnum.NO_REFUND,
            amount_inr=0,
            reason="Account issue; no refund applicable"
        )

    # 5. Technical issues: Investigate crash / technical bug with human support
    if category == CategoryEnum.TECHNICAL_ISSUE:
        return RefundResult(
            decision=RefundDecisionEnum.NO_REFUND,
            amount_inr=0,
            reason="Technical issue; routed for engineering support rather than automated refund"
        )

    # 6. Billing disputes, cancellations, payment issues, or unknown categories
    if category in (CategoryEnum.BILLING, CategoryEnum.CANCELLATION, CategoryEnum.PAYMENT_ISSUE, CategoryEnum.UNKNOWN):
        # Look for successful renewal charges
        successful_renewals = [p for p in purchases if p.type == "renewal" and p.status == "successful"]
        
        if successful_renewals:
            # Policy-sensitive dispute on existing renewal -> Route to human review with zero auto-payout
            return RefundResult(
                decision=RefundDecisionEnum.HUMAN_REVIEW,
                amount_inr=0,
                reason="Disputed renewal charge routed for human policy review"
            )
        
        # User only had trial or failed transactions
        successful_trials = [p for p in purchases if p.type == "trial" and p.status == "successful"]
        if successful_trials and category == CategoryEnum.CANCELLATION:
            # Cancellation during trial: cancel subscription, trial fee non-refundable
            return RefundResult(
                decision=RefundDecisionEnum.NO_REFUND,
                amount_inr=0,
                reason="Trial cancellation recorded; trial fee is non-refundable"
            )
        
        # In case of failed attempts only (e.g. perceived double charge where only 1 succeeded or 0 succeeded)
        successful_charges = [p for p in purchases if p.status == "successful"]
        if len(successful_charges) <= 1:
            return RefundResult(
                decision=RefundDecisionEnum.NO_REFUND,
                amount_inr=0,
                reason="No duplicate successful charge found on billing record"
            )

        return RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Billing inquiry with multiple transactions routed for human verification"
        )

    # Catch-all safe default
    return RefundResult(
        decision=RefundDecisionEnum.NO_REFUND,
        amount_inr=0,
        reason="No refund criteria matched"
    )
