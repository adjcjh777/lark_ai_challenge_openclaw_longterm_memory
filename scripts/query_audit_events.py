#!/usr/bin/env python3
"""Query and export memory_audit_events for operations review.

Usage examples:
    # List recent 10 events as JSON
    python3 scripts/query_audit_events.py --json --limit 10

    # Filter by event_type
    python3 scripts/query_audit_events.py --event-type permission_denied --json

    # Filter by actor
    python3 scripts/query_audit_events.py --actor-id u_demo --json

    # Filter by tenant
    python3 scripts/query_audit_events.py --tenant-id tenant:demo --json

    # Filter by time range (ISO 8601)
    python3 scripts/query_audit_events.py --since 2026-04-28T00:00:00 --until 2026-04-29T00:00:00 --json

    # Summary by event_type
    python3 scripts/query_audit_events.py --summary --json

    # Summary by permission_decision
    python3 scripts/query_audit_events.py --summary --group-by permission_decision --json

    # Export CSV
    python3 scripts/query_audit_events.py --format csv --limit 50 > audit_export.csv

    # Export JSON
    python3 scripts/query_audit_events.py --format json --limit 50 > audit_export.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = "data/memory.sqlite"


def get_connection() -> sqlite3.Connection:
    db_path = os.environ.get("MEMORY_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def query_events(
    conn: sqlite3.Connection,
    *,
    event_type: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    permission_decision: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query audit events with optional filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if actor_id:
        conditions.append("actor_id = ?")
        params.append(actor_id)
    if tenant_id:
        conditions.append("tenant_id = ?")
        params.append(tenant_id)
    if permission_decision:
        conditions.append("permission_decision = ?")
        params.append(permission_decision)
    if since:
        conditions.append("created_at >= ?")
        params.append(_iso_to_ms(since))
    if until:
        conditions.append("created_at <= ?")
        params.append(_iso_to_ms(until))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT audit_id, event_type, action, tool_name, target_type, target_id,
               memory_id, candidate_id, actor_id, actor_roles, tenant_id,
               organization_id, scope, permission_decision, reason_code,
               request_id, trace_id, visible_fields, redacted_fields,
               source_context, created_at
        FROM memory_audit_events
        {where}
        ORDER BY created_at DESC, audit_id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_events(
    conn: sqlite3.Connection,
    *,
    event_type: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    permission_decision: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> int:
    """Count audit events with optional filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if actor_id:
        conditions.append("actor_id = ?")
        params.append(actor_id)
    if tenant_id:
        conditions.append("tenant_id = ?")
        params.append(tenant_id)
    if permission_decision:
        conditions.append("permission_decision = ?")
        params.append(permission_decision)
    if since:
        conditions.append("created_at >= ?")
        params.append(_iso_to_ms(since))
    if until:
        conditions.append("created_at <= ?")
        params.append(_iso_to_ms(until))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT COUNT(*) FROM memory_audit_events {where}"
    return int(conn.execute(sql, params).fetchone()[0])


def summary_by_field(
    conn: sqlite3.Connection,
    *,
    group_by: str = "event_type",
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate audit event counts by a field."""
    allowed_fields = {"event_type", "permission_decision", "tenant_id", "organization_id", "action", "tool_name", "actor_id", "reason_code"}
    if group_by not in allowed_fields:
        raise ValueError(f"group_by must be one of {sorted(allowed_fields)}")

    conditions: list[str] = []
    params: list[Any] = []
    if since:
        conditions.append("created_at >= ?")
        params.append(_iso_to_ms(since))
    if until:
        conditions.append("created_at <= ?")
        params.append(_iso_to_ms(until))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT {group_by}, COUNT(*) as count
        FROM memory_audit_events
        {where}
        GROUP BY {group_by}
        ORDER BY count DESC
    """
    rows = conn.execute(sql, params).fetchall()
    return [{"group": str(row[group_by]), "count": int(row["count"])} for row in rows]


def summary_multi(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Produce a multi-dimensional summary of audit events."""
    return {
        "total": count_events(conn, since=since, until=until),
        "by_event_type": summary_by_field(conn, group_by="event_type", since=since, until=until),
        "by_permission_decision": summary_by_field(conn, group_by="permission_decision", since=since, until=until),
        "by_tenant_id": summary_by_field(conn, group_by="tenant_id", since=since, until=until),
        "by_action": summary_by_field(conn, group_by="action", since=since, until=until),
    }


def format_csv(events: list[dict[str, Any]]) -> str:
    """Format events as CSV."""
    if not events:
        return ""
    output = io.StringIO()
    fieldnames = list(events[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for event in events:
        # Flatten nested JSON fields for CSV
        row = {}
        for key, value in event.items():
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value, ensure_ascii=False)
            else:
                row[key] = value
        writer.writerow(row)
    return output.getvalue()


def format_json(data: Any) -> str:
    """Format data as JSON."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a dict, parsing JSON fields."""
    d = dict(row)
    for key in ("actor_roles", "visible_fields", "redacted_fields", "source_context"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    # Convert timestamp to ISO string for readability
    if "created_at" in d and isinstance(d["created_at"], int):
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(d["created_at"] / 1000, tz=timezone.utc)
        d["created_at_iso"] = dt.isoformat()
    return d


def _iso_to_ms(iso_str: str) -> int:
    """Convert ISO 8601 string to milliseconds timestamp."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        # Try adding timezone if missing
        try:
            dt = datetime.fromisoformat(iso_str + "+00:00")
        except ValueError:
            raise ValueError(f"Cannot parse ISO 8601 timestamp: {iso_str}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query and export memory_audit_events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON (default for --summary)")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format (default: json)")
    parser.add_argument("--limit", type=int, default=100, help="Max events to return (default: 100)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination (default: 0)")
    parser.add_argument("--event-type", help="Filter by event_type")
    parser.add_argument("--action", help="Filter by action")
    parser.add_argument("--actor-id", help="Filter by actor_id")
    parser.add_argument("--tenant-id", help="Filter by tenant_id")
    parser.add_argument("--permission-decision", help="Filter by permission_decision")
    parser.add_argument("--since", help="Start time (ISO 8601)")
    parser.add_argument("--until", help="End time (ISO 8601)")
    parser.add_argument("--summary", action="store_true", help="Show aggregated summary")
    parser.add_argument("--group-by", default="event_type", help="Field to group by in summary (default: event_type)")
    parser.add_argument("--count-only", action="store_true", help="Only output count")
    parser.add_argument("--db-path", help="SQLite database path (default: data/memory.sqlite)")

    args = parser.parse_args()

    if args.db_path:
        os.environ["MEMORY_DB_PATH"] = args.db_path

    conn = get_connection()
    try:
        if args.summary:
            if args.group_by and args.group_by != "event_type":
                result = summary_by_field(
                    conn,
                    group_by=args.group_by,
                    since=args.since,
                    until=args.until,
                )
            else:
                result = summary_multi(conn, since=args.since, until=args.until)

            if args.json or args.format == "json":
                print(format_json(result))
            else:
                # Table format for terminal
                if isinstance(result, dict) and "total" in result:
                    print(f"Total events: {result['total']}")
                    for section in ("by_event_type", "by_permission_decision", "by_tenant_id", "by_action"):
                        items = result.get(section, [])
                        if items:
                            print(f"\n{section}:")
                            for item in items:
                                print(f"  {item['group']}: {item['count']}")
                else:
                    for item in result:
                        print(f"{item['group']}: {item['count']}")
        elif args.count_only:
            count = count_events(
                conn,
                event_type=args.event_type,
                action=args.action,
                actor_id=args.actor_id,
                tenant_id=args.tenant_id,
                permission_decision=args.permission_decision,
                since=args.since,
                until=args.until,
            )
            if args.json or args.format == "json":
                print(format_json({"count": count}))
            else:
                print(count)
        else:
            events = query_events(
                conn,
                event_type=args.event_type,
                action=args.action,
                actor_id=args.actor_id,
                tenant_id=args.tenant_id,
                permission_decision=args.permission_decision,
                since=args.since,
                until=args.until,
                limit=args.limit,
                offset=args.offset,
            )
            output_format = "json" if args.json else args.format
            if output_format == "csv":
                print(format_csv(events))
            else:
                print(format_json(events))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
