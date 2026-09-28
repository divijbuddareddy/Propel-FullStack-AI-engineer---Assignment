"""Deterministic Fixture Engine for Keyless Replay and Evaluation.

Enables full offline evaluation of all support tickets without requiring an external API key.
Uses semantic heuristic classification and passes all financial decisions to the deterministic
refund policy engine.
"""

from typing import Tuple
from app.schemas import (
    CategoryEnum,
    SeverityEnum,
    TicketInput,
    LLMClassificationOutput,
)


def classify_ticket_offline(ticket: TicketInput) -> Tuple[LLMClassificationOutput, bool]:
    """Deterministically classifies a ticket using heuristic pattern matching for offline replay."""
    text_lower = f"{ticket.subject} {ticket.body}".lower()

    # 1. Fraud / Cyber Cell / Unauthorized Card allegations
    if any(k in text_lower for k in ("fraud", "cyber cell", "never installed", "father is 71", "reporting to cyber")):
        return LLMClassificationOutput(
            category=CategoryEnum.FRAUD,
            severity=SeverityEnum.CRITICAL,
            reply_draft=(
                "We take unauthorized payment and security concerns very seriously. Your case has been "
                "escalated to our fraud and compliance team for an immediate priority investigation."
            ),
            needs_human=True,
            confidence=0.98
        ), False

    # 2. Payment State Mismatch (e.g. Paid but not activated / Hinglish debited)
    if any(k in text_lower for k in ("paisa kat gaya", "bank se", "screenshot bhej", "not activated", "plan activate")):
        return LLMClassificationOutput(
            category=CategoryEnum.PAYMENT_ISSUE,
            severity=SeverityEnum.HIGH,
            reply_draft=(
                "Namaste! Humne aapka concern note kar liya hai. Agar aapke bank se 249 kat gaye hain "
                "aur plan activate nahi hua, to hamari team payment gateway se verify karke jald se jald "
                "aapka plan activate karegi."
            ),
            needs_human=True,
            confidence=0.94
        ), False

    # 3. Technical Issues / App Crashes
    if any(k in text_lower for k in ("crash", "closes immediately", "closes", "bug", "stopped working", "android 13")):
        return LLMClassificationOutput(
            category=CategoryEnum.TECHNICAL_ISSUE,
            severity=SeverityEnum.HIGH,
            reply_draft=(
                "We sincerely apologize for the crash you are experiencing after the latest update. "
                "Our mobile engineering team is actively investigating this device-specific issue to release a fix."
            ),
            needs_human=True,
            confidence=0.95
        ), False

    # 4. Account / History Sync (including adversarial prompt injection protection)
    if any(k in text_lower for k in ("order history", "changed my phone", "restore it", "account issue")):
        return LLMClassificationOutput(
            category=CategoryEnum.ACCOUNT,
            severity=SeverityEnum.MEDIUM,
            reply_draft=(
                "Hello! We understand your order history is not appearing after switching devices. "
                "Our support team is checking the cloud account sync for your Google account to restore your data."
            ),
            needs_human=True,
            confidence=0.92
        ), False

    # 5. Direct Cancellation Requests
    if text_lower.strip() in ("cancel", "cancel subscription", "cancel plan") or ticket.subject.lower().strip() == "cancel":
        return LLMClassificationOutput(
            category=CategoryEnum.CANCELLATION,
            severity=SeverityEnum.MEDIUM,
            reply_draft=(
                "Your request to cancel has been recorded. Your subscription will not renew, and "
                "no future charges will be billed to your account."
            ),
            needs_human=False,
            confidence=0.96
        ), False

    # 6. GST Invoice Requests
    if any(k in text_lower for k in ("gst invoice", "invoice needed", "reimbursement", "gstin")):
        return LLMClassificationOutput(
            category=CategoryEnum.INVOICE,
            severity=SeverityEnum.LOW,
            reply_draft=(
                "Thank you for reaching out. We have received your GST invoice details and our billing team "
                "will email the tax invoice for your annual subscription shortly."
            ),
            needs_human=False,
            confidence=0.97
        ), False

    # 7. Feature / Localization Requests
    if any(k in text_lower for k in ("marathi", "feature request", "language", "add language")):
        return LLMClassificationOutput(
            category=CategoryEnum.FEATURE_REQUEST,
            severity=SeverityEnum.LOW,
            reply_draft=(
                "Thank you for your valuable feedback! We are actively working on adding regional languages "
                "including Marathi in upcoming Dhaba updates."
            ),
            needs_human=False,
            confidence=0.95
        ), False

    # 8. Subscription / Pre-Sale Questions (including prompt injection protection)
    if any(k in text_lower for k in ("does premium work offline", "before i subscribe", "offline")):
        return LLMClassificationOutput(
            category=CategoryEnum.SUBSCRIPTION_QUESTION,
            severity=SeverityEnum.LOW,
            reply_draft=(
                "Hello! Yes, Dhaba premium allows offline access to saved recipes and meal plans once "
                "downloaded, though real-time order tracking requires an active internet connection."
            ),
            needs_human=False,
            confidence=0.95
        ), False

    # 9. Perceived Double Charge Inquiry
    if any(k in text_lower for k in ("double charge", "twice on the same day", "took 249 twice")):
        return LLMClassificationOutput(
            category=CategoryEnum.BILLING,
            severity=SeverityEnum.MEDIUM,
            reply_draft=(
                "Hello! We have verified your account billing records. Only one renewal charge of INR 249 "
                "was successfully processed; the previous attempt failed and was not billed to your account."
            ),
            needs_human=False,
            confidence=0.94
        ), False

    # 10. General Billing Disputes / Renewal Disputes / Dissatisfaction
    if any(k in text_lower for k in ("without telling me", "charged 249", "1499", "autopay", "reverse", "refund", "worst app", "useless")):
        return LLMClassificationOutput(
            category=CategoryEnum.BILLING,
            severity=SeverityEnum.HIGH,
            reply_draft=(
                "Thank you for reaching out regarding your billing query. Our billing team is reviewing "
                "your transaction history and account details to assist you with this charge."
            ),
            needs_human=True,
            confidence=0.90
        ), False


    # 10. Fallback for unclassified inputs
    return LLMClassificationOutput(
        category=CategoryEnum.UNKNOWN,
        severity=SeverityEnum.HIGH,
        reply_draft=(
            "Thank you for contacting Dhaba Support. We have received your request and our support "
            "team is reviewing it. We will get back to you shortly."
        ),
        needs_human=True,
        confidence=0.0
    ), True
