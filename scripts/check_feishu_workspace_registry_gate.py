#!/usr/bin/env python3
"""Read-only gate for Feishu workspace ingestion registry evidence."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.db import db_path_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Feishu workspace ingestion registry evidence")
    parser.add_argument("--workspace-id", default="project:feishu_ai_challenge")
    parser.add_argument("--tenant-id", default="tenant:demo")
    parser.add_argument("--organization-id", default="org:demo")
    parser.add_argument("--filter-key", help="Restrict checks to one discovery filter key")
    parser.add_argument("--min-runs", type=int, default=1)
    parser.add_argument("--require-ingested", action="store_true")
    parser.add_argument("--require-skipped", action="store_true")
    parser.add_argument("--require-stale", action="store_true")
    parser.add_argument("--require-failed", action="store_true")
    parser.add_argument("--require-cursor", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(db_path_from_env())
    conn.row_factory = sqlite3.Row
    try:
        payload = build_report(
            conn,
            workspace_id=args.workspace_id,
            tenant_id=args.tenant_id,
            organization_id=args.organization_id,
            filter_key=args.filter_key,
            min_runs=args.min_runs,
            require_ingested=args.require_ingested,
            require_skipped=args.require_skipped,
            require_stale=args.require_stale,
            require_failed=args.require_failed,
            require_cursor=args.require_cursor,
        )
    finally:
        conn.close()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ok: {str(payload['ok']).lower()}")
        print(f"run_count: {payload['run_count']}")
        print(f"registry_count: {payload['registry_count']}")
        print(f"cursor_count: {payload['cursor_count']}")
        if payload["failures"]:
            print("failures:")
            for failure in payload["failures"]:
                print(f"- {failure}")
    return 0 if payload["ok"] else 1


def build_report(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str | None = None,
    min_runs: int = 1,
    require_ingested: bool = False,
    require_skipped: bool = False,
    require_stale: bool = False,
    require_failed: bool = False,
    require_cursor: bool = False,
) -> dict[str, Any]:
    scope_where, scope_params = _scope_filter(
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
        filter_key=filter_key,
    )
    runs = [_row_dict(row) for row in conn.execute(f"{_RUN_SQL} {scope_where} ORDER BY started_at DESC", scope_params)]
    registry_rows = [
        _row_dict(row) for row in conn.execute(f"{_REGISTRY_SQL} {scope_where} ORDER BY last_seen_at DESC", scope_params)
    ]
    cursor_rows = [
        _row_dict(row) for row in conn.execute(f"{_CURSOR_SQL} {scope_where} ORDER BY updated_at DESC", scope_params)
    ]

    latest_run = runs[0] if runs else None
    status_counts = _count_by(registry_rows, "status")
    route_counts = _count_by(registry_rows, "route_type")
    filters = sorted({str(row["discovery_filter_key"]) for row in runs + registry_rows + cursor_rows})
    totals = {
        "resources": sum(int(row.get("resource_count") or 0) for row in runs),
        "fetched": sum(int(row.get("fetched_count") or 0) for row in runs),
        "ingested": sum(int(row.get("ingested_count") or 0) for row in runs),
        "skipped_unchanged": sum(int(row.get("skipped_unchanged_count") or 0) for row in runs),
        "failed": sum(int(row.get("failed_count") or 0) for row in runs),
        "stale_marked": sum(int(row.get("stale_marked_count") or 0) for row in runs),
    }
    evidence = {
        "has_ingested": totals["ingested"] > 0 or status_counts.get("ingested", 0) > 0,
        "has_skipped": totals["skipped_unchanged"] > 0,
        "has_stale": totals["stale_marked"] > 0 or status_counts.get("stale", 0) > 0,
        "has_failed": totals["failed"] > 0 or any(row.get("error_code") for row in registry_rows),
        "has_cursor": bool(cursor_rows),
    }
    failures: list[str] = []
    if len(runs) < min_runs:
        failures.append(f"run_count_below_min:{len(runs)}<{min_runs}")
    if require_ingested and not evidence["has_ingested"]:
        failures.append("missing_ingested_evidence")
    if require_skipped and not evidence["has_skipped"]:
        failures.append("missing_skipped_unchanged_evidence")
    if require_stale and not evidence["has_stale"]:
        failures.append("missing_stale_evidence")
    if require_failed and not evidence["has_failed"]:
        failures.append("missing_failed_evidence")
    if require_cursor and not evidence["has_cursor"]:
        failures.append("missing_cursor_evidence")

    return {
        "ok": not failures,
        "boundary": "read_only_workspace_registry_gate_no_fetch_no_write",
        "workspace_id": workspace_id,
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "filter_key": filter_key,
        "run_count": len(runs),
        "registry_count": len(registry_rows),
        "cursor_count": len(cursor_rows),
        "filters": filters,
        "latest_run": latest_run,
        "totals": totals,
        "evidence": evidence,
        "status_counts": status_counts,
        "route_counts": route_counts,
        "cursor_status_counts": _count_by(cursor_rows, "status"),
        "failures": failures,
    }


_RUN_SQL = """
SELECT run_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
       mode, status, boundary, started_at, finished_at, resource_count,
       fetched_count, ingested_count, skipped_unchanged_count, failed_count,
       stale_marked_count
FROM feishu_workspace_ingestion_runs
"""

_REGISTRY_SQL = """
SELECT registry_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
       source_key, resource_type, route_type, source_type, source_id, title,
       revision, status, candidate_count, duplicate_count, error_code,
       last_seen_run_id, last_fetched_at, last_ingested_at, stale_at, revoked_at
FROM feishu_workspace_source_registry
"""

_CURSOR_SQL = """
SELECT cursor_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
       page_token, status, page_count, resource_count, last_run_id, updated_at,
       completed_at
FROM feishu_workspace_discovery_cursors
"""


def _scope_filter(
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str | None,
) -> tuple[str, list[Any]]:
    conditions = ["tenant_id = ?", "organization_id = ?", "workspace_id = ?"]
    params: list[Any] = [tenant_id, organization_id, workspace_id]
    if filter_key:
        conditions.append("discovery_filter_key = ?")
        params.append(filter_key)
    return "WHERE " + " AND ".join(conditions), params


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            continue
        result[value] = result.get(value, 0) + 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
