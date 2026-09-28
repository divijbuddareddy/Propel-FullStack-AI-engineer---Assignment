"""FastAPI Main Application and POST /triage Endpoint."""

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, Response, status
from dotenv import load_dotenv

from app.idempotency import init_db, get_persisted_triage, save_triage_result
from app.llm import GeminiClient
from app.fixture_engine import classify_ticket_offline
from app.refund_policy import evaluate_refund_policy
from app.logging_config import logger
from app.schemas import (
    TicketInput,
    TriageResponse,
    RefundResult,
    RefundDecisionEnum,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes SQLite tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="Dhaba Support Triage Service",
    description="Automated support ticket triage with deterministic financial controls and failure resilience.",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Health check endpoint for liveness and readiness monitoring."""
    return {"status": "ok", "service": "dhaba-triage"}


@app.post(
    "/triage",
    response_model=TriageResponse,
    status_code=status.HTTP_200_OK,
    summary="Triage a support ticket",
    description="Classifies support tickets, determines severity, applies deterministic refund policy, and drafts customer replies."
)
def triage_ticket(
    ticket: TicketInput,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID")
) -> TriageResponse:
    """Processes a ticket payload through validation, idempotency, LLM/fixture classification, and refund policy."""
    start_time = time.perf_counter()
    request_id = x_request_id or f"req_{uuid.uuid4().hex[:12]}"

    logger.log_event(
        stage="request_received",
        request_id=request_id,
        ticket_id=ticket.id
    )

    # 1. Idempotency Check (Duplicate request prevention)
    cached_result = get_persisted_triage(ticket.id)
    if cached_result:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.log_event(
            stage="idempotent_hit",
            request_id=request_id,
            ticket_id=ticket.id,
            category=cached_result.category.value,
            duration_ms=duration_ms
        )
        return cached_result

    # 2. Classification Engine (Live Gemini vs Keyless Fixture Replay)
    mode = os.getenv("TRIAGE_MODE", "live").lower()
    api_key = os.getenv("GOOGLE_API_KEY", "")

    if mode == "fixture" or not api_key:
        classification, is_fallback = classify_ticket_offline(ticket)
    else:
        gemini_client = GeminiClient(api_key=api_key)
        classification, is_fallback = gemini_client.classify_ticket(
            subject=ticket.subject,
            body=ticket.body
        )

    # 3. Deterministic Refund Policy Gate (Zero LLM authority over money)
    if is_fallback:
        # Strict safe fallback refund rule
        refund_result = RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Safe fallback due to model failure or degraded mode"
        )
    else:
        refund_result = evaluate_refund_policy(
            category=classification.category,
            severity=classification.severity,
            purchases=ticket.purchases,
            app_opens_since_renewal=ticket.app_opens_since_renewal
        )

    # 4. Assemble Final Response
    response = TriageResponse(
        ticket_id=ticket.id,
        category=classification.category,
        severity=classification.severity,
        refund=refund_result,
        reply_draft=classification.reply_draft,
        needs_human=classification.needs_human,
        confidence=classification.confidence,
        is_fallback=is_fallback,
        cached=False
    )

    # 5. Persist Result and Record Side Effect Idempotently
    save_triage_result(response, request_id=request_id)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    logger.log_event(
        stage="triage_completed",
        request_id=request_id,
        ticket_id=ticket.id,
        category=response.category.value,
        severity=response.severity.value,
        refund_decision=response.refund.decision.value,
        needs_human=response.needs_human,
        is_fallback=response.is_fallback,
        duration_ms=duration_ms
    )

    return response
