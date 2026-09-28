"""SQLite persistence and idempotency manager for Dhaba Support Triage.

Guarantees:
1. Exact repeatability: A second submission of the same ticket ID returns the cached result.
2. Duplicate refund prevention: SQLite UNIQUE constraint on refund_actions(ticket_id)
   ensures financial side effects can never occur twice for the same ticket.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.schemas import (
    CategoryEnum,
    SeverityEnum,
    RefundDecisionEnum,
    RefundResult,
    TriageResponse,
)

DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "triage.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Creates a connection to SQLite with WAL mode enabled."""
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Enable Write-Ahead Logging for concurrency
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes tables for triage results and refund actions."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS triage_results (
                ticket_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL,
                reply_draft TEXT NOT NULL,
                needs_human INTEGER NOT NULL,
                refund_decision TEXT NOT NULL,
                refund_amount INTEGER NOT NULL,
                refund_reason TEXT NOT NULL,
                is_fallback INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refund_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE NOT NULL,
                decision TEXT NOT NULL,
                amount_inr INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES triage_results(ticket_id)
            );

            CREATE INDEX IF NOT EXISTS idx_triage_category ON triage_results(category);
            CREATE INDEX IF NOT EXISTS idx_triage_created_at ON triage_results(created_at);
            """)
    finally:
        conn.close()


def get_persisted_triage(ticket_id: str, db_path: Optional[str] = None) -> Optional[TriageResponse]:
    """Retrieves an existing triage result if already processed (idempotency hit)."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ticket_id, category, severity, confidence, reply_draft,
                   needs_human, refund_decision, refund_amount, refund_reason, is_fallback
            FROM triage_results
            WHERE ticket_id = ?
            """,
            (ticket_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        return TriageResponse(
            ticket_id=row["ticket_id"],
            category=CategoryEnum(row["category"]),
            severity=SeverityEnum(row["severity"]),
            refund=RefundResult(
                decision=RefundDecisionEnum(row["refund_decision"]),
                amount_inr=row["refund_amount"],
                reason=row["refund_reason"]
            ),
            reply_draft=row["reply_draft"],
            needs_human=bool(row["needs_human"]),
            confidence=float(row["confidence"]),
            is_fallback=bool(row["is_fallback"]),
            cached=True
        )
    finally:
        conn.close()


def save_triage_result(
    response: TriageResponse,
    request_id: str,
    db_path: Optional[str] = None
) -> None:
    """Atomically persists the triage result and records the refund action under a unique ticket constraint."""
    conn = get_db_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            # 1. Insert or replace triage result
            conn.execute(
                """
                INSERT OR REPLACE INTO triage_results (
                    ticket_id, request_id, category, severity, confidence,
                    reply_draft, needs_human, refund_decision, refund_amount,
                    refund_reason, is_fallback, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response.ticket_id,
                    request_id,
                    response.category.value,
                    response.severity.value,
                    response.confidence,
                    response.reply_draft,
                    1 if response.needs_human else 0,
                    response.refund.decision.value,
                    response.refund.amount_inr,
                    response.refund.reason,
                    1 if response.is_fallback else 0,
                    now_iso,
                    now_iso,
                )
            )

            # 2. Record refund action idempotently (ignore duplicate if already present)
            conn.execute(
                """
                INSERT OR IGNORE INTO refund_actions (
                    ticket_id, decision, amount_inr, status, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    response.ticket_id,
                    response.refund.decision.value,
                    response.refund.amount_inr,
                    "recorded",
                    now_iso,
                )
            )
    finally:
        conn.close()
