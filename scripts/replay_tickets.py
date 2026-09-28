"""Replay CLI script for processing the official 12 Dhaba tickets.

Supports:
- Fixture Mode (default): Zero API key required, runs locally and deterministically.
- Live Mode: Invokes Google Gemini API when GOOGLE_API_KEY is provided.

Usage:
    python scripts/replay_tickets.py --mode fixture
    python scripts/replay_tickets.py --mode live
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import TicketInput, TriageResponse, RefundResult, RefundDecisionEnum
from app.fixture_engine import classify_ticket_offline
from app.llm import GeminiClient
from app.refund_policy import evaluate_refund_policy
from app.idempotency import init_db, save_triage_result, get_persisted_triage


def process_ticket(ticket: TicketInput, mode: str = "fixture", db_path: str = "triage.db") -> TriageResponse:
    """Processes a single ticket through the triage engine in fixture or live mode."""
    # 1. Check idempotency
    cached = get_persisted_triage(ticket.id, db_path=db_path)
    if cached:
        return cached

    # 2. Classification
    if mode == "fixture" or not os.getenv("GOOGLE_API_KEY"):
        classification, is_fallback = classify_ticket_offline(ticket)
    else:
        client = GeminiClient()
        classification, is_fallback = client.classify_ticket(ticket.subject, ticket.body)

    # 3. Deterministic Refund Gate
    if is_fallback:
        refund_res = RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Safe fallback due to model failure or degraded mode"
        )
    else:
        refund_res = evaluate_refund_policy(
            category=classification.category,
            severity=classification.severity,
            purchases=ticket.purchases,
            app_opens_since_renewal=ticket.app_opens_since_renewal
        )

    # 4. Construct Response
    response = TriageResponse(
        ticket_id=ticket.id,
        category=classification.category,
        severity=classification.severity,
        refund=refund_res,
        reply_draft=classification.reply_draft,
        needs_human=classification.needs_human,
        confidence=classification.confidence,
        is_fallback=is_fallback,
        cached=False
    )

    # 5. Persist
    save_triage_result(response, request_id="replay_cli", db_path=db_path)
    return response


def main():
    parser = argparse.ArgumentParser(description="Replay Dhaba support tickets through triage service.")
    parser.add_argument("--file", default="dhaba_tickets.json", help="Path to dhaba_tickets.json")
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture", help="Triage mode (fixture or live)")
    parser.add_argument("--db", default="triage.db", help="SQLite database path")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: Fixture file not found at {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tickets_data = data.get("tickets", [])
    print(f"\n=======================================================")
    print(f" Dhaba Support Triage — Replay Engine")
    print(f" Mode: {args.mode.upper()} | Total Tickets: {len(tickets_data)}")
    print(f"=======================================================\n")

    init_db(db_path=args.db)

    results = []
    # Print formatted table header
    header_fmt = "{:<8} | {:<20} | {:<10} | {:<16} | {:<12} | {:<8}"
    print(header_fmt.format("Ticket", "Category", "Severity", "Refund Decision", "Needs Human", "Conf."))
    print("-" * 88)

    # Reconfigure stdout encoding for safe Unicode output on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    for raw in tickets_data:
        ticket = TicketInput.model_validate(raw)
        result = process_ticket(ticket, mode=args.mode, db_path=args.db)
        results.append(result)

        refund_str = f"{result.refund.decision.value} (INR {result.refund.amount_inr})"
        print(header_fmt.format(
            result.ticket_id,
            result.category.value,
            result.severity.value,
            refund_str,
            str(result.needs_human),
            f"{result.confidence:.2f}"
        ))


    print("-" * 88)
    print(f"\nSuccessfully processed {len(results)} tickets in {args.mode} mode.\n")


if __name__ == "__main__":
    main()
