#!/usr/bin/env python3
"""Check audit event alerts for the Memory Copilot.

Evaluates alert conditions against audit data and outputs structured alerts.

Alert rules:
    1. consecutive_permission_deny: >= N consecutive permission deny events
    2. ingestion_failure_rate: ingestion failure rate > X% in time window
    3. high_deny_rate: deny rate > X% in time window
    4. no_audit_events: no audit events in last T minutes

Usage:
    python3 scripts/check_audit_alerts.py --json
    python3 scripts/check_audit_alerts.py --window-minutes 60
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_PATH = "data/memory.sqlite"

# Default thresholds
DEFAULT_CONSECUTIVE_DENY_THRESHOLD = 5
DEFAULT_DENY_RATE_THRESHOLD = 0.3  # 30%
DEFAULT_INGESTION_FAILURE_RATE_THRESHOLD = 0.1  # 10%
DEFAULT_WINDOW_MINUTES = 60
DEFAULT_MIN_AUDIT_GAP_MINUTES = 30


def get_connection() -> sqlite3.Connection:
    db_path = os.environ.get("MEMORY_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def check_consecutive_denies(
    conn: sqlite3.Connection,
    threshold: int = DEFAULT_CONSECUTIVE_DENY_THRESHOLD,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> dict[str, Any] | None:
    """Check for N or more consecutive permission deny events."""
    since_ms = _minutes_ago_ms(window_minutes)
    rows = conn.execute(
        """
        SELECT permission_decision, created_at
        FROM memory_audit_events
        WHERE created_at >= ?
        ORDER BY created_at ASC
        """,
        (since_ms,),
    ).fetchall()

    max_consecutive = 0
    current_consecutive = 0
    window_start = None

    for row in rows:
        if row["permission_decision"] == "deny":
            current_consecutive += 1
            if current_consecutive >= threshold and window_start is None:
                window_start = row["created_at"]
        else:
            current_consecutive = 0

    max_consecutive = current_consecutive

    if max_consecutive >= threshold:
        return {
            "alert_type": "consecutive_permission_deny",
            "severity": "warning" if max_consecutive < threshold * 2 else "critical",
            "count": max_consecutive,
            "threshold": threshold,
            "window_minutes": window_minutes,
            "message": f"Detected {max_consecutive} consecutive permission deny events (threshold: {threshold})",
        }
    return None


def check_deny_rate(
    conn: sqlite3.Connection,
    threshold: float = DEFAULT_DENY_RATE_THRESHOLD,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> dict[str, Any] | None:
    """Check if deny rate exceeds threshold in time window."""
    since_ms = _minutes_ago_ms(window_minutes)
    total = int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_audit_events WHERE created_at >= ?",
            (since_ms,),
        ).fetchone()[0]
    )

    if total == 0:
        return None

    denies = int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_audit_events WHERE created_at >= ? AND permission_decision = 'deny'",
            (since_ms,),
        ).fetchone()[0]
    )

    rate = denies / total
    if rate > threshold:
        return {
            "alert_type": "high_deny_rate",
            "severity": "warning" if rate < threshold * 2 else "critical",
            "count": denies,
            "total": total,
            "rate": round(rate, 4),
            "threshold": threshold,
            "window_minutes": window_minutes,
            "message": f"Deny rate {rate:.1%} exceeds threshold {threshold:.1%} ({denies}/{total} events)",
        }
    return None


def check_ingestion_failure_rate(
    conn: sqlite3.Connection,
    threshold: float = DEFAULT_INGESTION_FAILURE_RATE_THRESHOLD,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> dict[str, Any] | None:
    """Check if ingestion failure rate exceeds threshold."""
    since_ms = _minutes_ago_ms(window_minutes)
    ingestion_total = int(
        conn.execute(
            """
        SELECT COUNT(*) FROM memory_audit_events
        WHERE created_at >= ? AND action IN ('memory.create_candidate', 'source.revoked')
        """,
            (since_ms,),
        ).fetchone()[0]
    )

    if ingestion_total == 0:
        return None

    ingestion_failures = int(
        conn.execute(
            """
        SELECT COUNT(*) FROM memory_audit_events
        WHERE created_at >= ?
          AND action IN ('memory.create_candidate', 'source.revoked')
          AND (reason_code LIKE '%failed%' OR reason_code LIKE '%error%' OR permission_decision = 'deny')
        """,
            (since_ms,),
        ).fetchone()[0]
    )

    rate = ingestion_failures / ingestion_total
    if rate > threshold:
        return {
            "alert_type": "ingestion_failure_rate",
            "severity": "warning" if rate < threshold * 2 else "critical",
            "count": ingestion_failures,
            "total": ingestion_total,
            "rate": round(rate, 4),
            "threshold": threshold,
            "window_minutes": window_minutes,
            "message": f"Ingestion failure rate {rate:.1%} exceeds threshold {threshold:.1%} ({ingestion_failures}/{ingestion_total})",
        }
    return None


def check_audit_gap(
    conn: sqlite3.Connection,
    gap_minutes: int = DEFAULT_MIN_AUDIT_GAP_MINUTES,
) -> dict[str, Any] | None:
    """Check if there's an unusually long gap without audit events."""
    row = conn.execute("SELECT MAX(created_at) as last_event_at FROM memory_audit_events").fetchone()

    if row is None or row["last_event_at"] is None:
        return {
            "alert_type": "no_audit_events",
            "severity": "info",
            "count": 0,
            "message": "No audit events found in database",
        }

    last_ms = row["last_event_at"]
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    gap_ms = now_ms - last_ms
    gap_minutes_actual = gap_ms / 60000

    if gap_minutes_actual > gap_minutes:
        return {
            "alert_type": "audit_gap",
            "severity": "warning" if gap_minutes_actual < gap_minutes * 3 else "critical",
            "gap_minutes": round(gap_minutes_actual, 1),
            "threshold_minutes": gap_minutes,
            "last_event_at": datetime.fromtimestamp(last_ms / 1000, tz=timezone.utc).isoformat(),
            "message": f"Audit gap of {gap_minutes_actual:.0f} minutes exceeds threshold {gap_minutes} minutes",
        }
    return None


def check_all_alerts(
    *,
    consecutive_deny_threshold: int = DEFAULT_CONSECUTIVE_DENY_THRESHOLD,
    deny_rate_threshold: float = DEFAULT_DENY_RATE_THRESHOLD,
    ingestion_failure_rate_threshold: float = DEFAULT_INGESTION_FAILURE_RATE_THRESHOLD,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    gap_minutes: int = DEFAULT_MIN_AUDIT_GAP_MINUTES,
) -> dict[str, Any]:
    """Run all alert checks and return structured results."""
    conn = get_connection()
    try:
        alerts: list[dict[str, Any]] = []

        alert = check_consecutive_denies(conn, threshold=consecutive_deny_threshold, window_minutes=window_minutes)
        if alert:
            alerts.append(alert)

        alert = check_deny_rate(conn, threshold=deny_rate_threshold, window_minutes=window_minutes)
        if alert:
            alerts.append(alert)

        alert = check_ingestion_failure_rate(
            conn, threshold=ingestion_failure_rate_threshold, window_minutes=window_minutes
        )
        if alert:
            alerts.append(alert)

        alert = check_audit_gap(conn, gap_minutes=gap_minutes)
        if alert:
            alerts.append(alert)

        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: severity_order.get(a.get("severity", "info"), 2))

        has_critical = any(a.get("severity") == "critical" for a in alerts)
        has_warning = any(a.get("severity") == "warning" for a in alerts)

        return {
            "ok": not has_critical and not has_warning,
            "alert_count": len(alerts),
            "alerts": alerts,
            "thresholds": {
                "consecutive_deny": consecutive_deny_threshold,
                "deny_rate": deny_rate_threshold,
                "ingestion_failure_rate": ingestion_failure_rate_threshold,
                "window_minutes": window_minutes,
                "audit_gap_minutes": gap_minutes,
            },
        }
    finally:
        conn.close()


def _minutes_ago_ms(minutes: int) -> int:
    """Get milliseconds timestamp for N minutes ago."""
    now = datetime.now(tz=timezone.utc)
    from datetime import timedelta

    ago = now - timedelta(minutes=minutes)
    return int(ago.timestamp() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check audit event alerts")
    parser.add_argument("--json", action="store_true", help="Output as JSON (default)")
    parser.add_argument("--consecutive-deny-threshold", type=int, default=DEFAULT_CONSECUTIVE_DENY_THRESHOLD)
    parser.add_argument("--deny-rate-threshold", type=float, default=DEFAULT_DENY_RATE_THRESHOLD)
    parser.add_argument(
        "--ingestion-failure-rate-threshold", type=float, default=DEFAULT_INGESTION_FAILURE_RATE_THRESHOLD
    )
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES)
    parser.add_argument("--gap-minutes", type=int, default=DEFAULT_MIN_AUDIT_GAP_MINUTES)
    parser.add_argument("--db-path", help="SQLite database path")

    args = parser.parse_args()

    if args.db_path:
        os.environ["MEMORY_DB_PATH"] = args.db_path

    result = check_all_alerts(
        consecutive_deny_threshold=args.consecutive_deny_threshold,
        deny_rate_threshold=args.deny_rate_threshold,
        ingestion_failure_rate_threshold=args.ingestion_failure_rate_threshold,
        window_minutes=args.window_minutes,
        gap_minutes=args.gap_minutes,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Exit code: 0 = ok, 1 = has warnings, 2 = has critical alerts
    if not result["ok"]:
        has_critical = any(a.get("severity") == "critical" for a in result["alerts"])
        sys.exit(2 if has_critical else 1)


if __name__ == "__main__":
    main()
