"""Tests for idempotency and duplicate refund prevention."""

import pytest
from app.schemas import (
    CategoryEnum,
    SeverityEnum,
    RefundDecisionEnum,
    RefundResult,
    TriageResponse,
)
from app.idempotency import (
    init_db,
    get_persisted_triage,
    save_triage_result,
    get_db_connection,
)


@pytest.fixture
def isolated_db(tmp_path):
    db_file = tmp_path / "idempotency_test.db"
    init_db(str(db_file))
    return str(db_file)


def test_idempotent_get_and_save(isolated_db):
    """Verifies that saving a triage response allows retrieving an identical cached response."""
    response = TriageResponse(
        ticket_id="T-IDEMP-01",
        category=CategoryEnum.BILLING,
        severity=SeverityEnum.HIGH,
        refund=RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Disputed renewal charge routed for human policy review"
        ),
        reply_draft="Hello customer",
        needs_human=True,
        confidence=0.92,
        is_fallback=False,
        cached=False
    )

    # 1. First save
    save_triage_result(response, request_id="req_1", db_path=isolated_db)

    # 2. Lookup
    cached = get_persisted_triage("T-IDEMP-01", db_path=isolated_db)
    assert cached is not None
    assert cached.ticket_id == "T-IDEMP-01"
    assert cached.category == CategoryEnum.BILLING
    assert cached.cached is True
    assert cached.refund.decision == RefundDecisionEnum.HUMAN_REVIEW


def test_duplicate_refund_prevention(isolated_db):
    """Verifies that multiple saves for the same ticket ID do not duplicate refund_actions entries."""
    response = TriageResponse(
        ticket_id="T-IDEMP-02",
        category=CategoryEnum.BILLING,
        severity=SeverityEnum.HIGH,
        refund=RefundResult(
            decision=RefundDecisionEnum.HUMAN_REVIEW,
            amount_inr=0,
            reason="Reviewing transaction"
        ),
        reply_draft="Draft",
        needs_human=True,
        confidence=0.90,
        is_fallback=False
    )

    # Save twice
    save_triage_result(response, request_id="req_first", db_path=isolated_db)
    save_triage_result(response, request_id="req_second", db_path=isolated_db)

    # Inspect refund_actions table directly
    conn = get_db_connection(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM refund_actions WHERE ticket_id = ?", ("T-IDEMP-02",))
    count = cursor.fetchone()["count"]
    conn.close()

    assert count == 1, "refund_actions must contain exactly 1 entry per ticket_id"
