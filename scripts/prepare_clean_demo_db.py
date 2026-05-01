#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.db import connect, db_path_from_env, init_db
from memory_engine.repository import MemoryRepository
from scripts.demo_seed import DEFAULT_SCOPE, build_replay, seed_demo_memories

DEMO_ALLOWED_SOURCE_TYPES = {"demo_seed"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an isolated clean demo SQLite DB seeded with fixed replay data. "
            "The source DB is only inspected, never modified."
        )
    )
    parser.add_argument("--output-db", required=True, help="Path for the clean demo SQLite DB to create.")
    parser.add_argument("--source-db", default=str(db_path_from_env()), help="Existing DB to inspect for live-test noise.")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="Demo scope to seed.")
    parser.add_argument("--force", action="store_true", help="Replace --output-db if it already exists.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    try:
        report = prepare_clean_demo_db(
            source_db=Path(args.source_db),
            output_db=Path(args.output_db),
            scope=args.scope,
            force=args.force,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"SQLite error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def prepare_clean_demo_db(
    *,
    source_db: Path,
    output_db: Path,
    scope: str = DEFAULT_SCOPE,
    force: bool = False,
) -> dict[str, Any]:
    source_path = source_db.expanduser().resolve()
    output_path = output_db.expanduser().resolve()
    if source_path == output_path:
        raise ValueError("Refusing to use the same path for --source-db and --output-db.")
    if output_path.exists() and not force:
        raise ValueError(f"Output DB already exists: {output_path}. Pass --force to replace it.")

    source_counts = inspect_db_counts(source_path) if source_path.exists() else {"exists": False}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_name(f".{output_path.name}.tmp")
    if temp_output.exists():
        temp_output.unlink()

    conn = connect(temp_output)
    try:
        init_db(conn)
        seed_demo_memories(conn, scope)
        repo = MemoryRepository(conn)
        replay = build_replay(repo, scope, str(temp_output), persistent=True)
        output_counts = inspect_connection_counts(conn)
    finally:
        conn.close()

    if output_path.exists():
        output_path.unlink()
    temp_output.replace(output_path)

    failed_steps = [
        step.get("name", "unnamed")
        for step in replay.get("steps", [])
        if not (isinstance(step.get("output"), dict) and step["output"].get("ok") is True)
    ]
    disallowed_sources = sorted(
        source_type
        for source_type in output_counts["source_type_counts"]
        if source_type not in DEMO_ALLOWED_SOURCE_TYPES
    )
    clean = not failed_steps and not disallowed_sources and output_counts["feishu_group_policy_total"] == 0
    return {
        "ok": clean,
        "scope": scope,
        "source_db": str(source_path),
        "output_db": str(output_path),
        "source_db_modified": False,
        "source_counts": source_counts,
        "output_counts": output_counts,
        "demo_replay": {
            "ok": not failed_steps,
            "failed_steps": failed_steps,
            "step_count": len(replay.get("steps") or []),
            "production_feishu_write": bool(replay.get("production_feishu_write")),
        },
        "cleanliness": {
            "allowed_source_types": sorted(DEMO_ALLOWED_SOURCE_TYPES),
            "disallowed_source_types": disallowed_sources,
            "group_policies_carried_over": output_counts["feishu_group_policy_total"],
            "audit_events_after_replay": output_counts["audit_total"],
        },
        "boundary": (
            "Creates an isolated demo DB only; does not delete live/staging evidence and does not prove "
            "production deployment or productized live."
        ),
        "next_step": (
            f"Run demo commands with MEMORY_DB_PATH={output_path}"
            if clean
            else "Inspect output_counts and failed_steps before using this DB for judging."
        ),
    }


def inspect_db_counts(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return inspect_connection_counts(conn) | {"exists": True}
    finally:
        conn.close()


def inspect_connection_counts(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "memory_total": _table_count(conn, "memories"),
        "raw_event_total": _table_count(conn, "raw_events"),
        "audit_total": _table_count(conn, "memory_audit_events"),
        "feishu_group_policy_total": _table_count(conn, "feishu_group_policies"),
        "knowledge_graph_node_total": _table_count(conn, "knowledge_graph_nodes"),
        "knowledge_graph_edge_total": _table_count(conn, "knowledge_graph_edges"),
        "source_type_counts": _count_by(conn, "raw_events", "source_type"),
        "memory_status_counts": _count_by(conn, "memories", "status"),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Clean Demo DB Preparation",
        f"ok: {str(report['ok']).lower()}",
        f"output_db: {report['output_db']}",
        f"source_db_modified: {str(report['source_db_modified']).lower()}",
        f"demo_failed_steps: {report['demo_replay']['failed_steps']}",
        f"output_source_types: {json.dumps(report['output_counts']['source_type_counts'], ensure_ascii=False)}",
        f"group_policies_carried_over: {report['cleanliness']['group_policies_carried_over']}",
        f"audit_events_after_replay: {report['cleanliness']['audit_events_after_replay']}",
        f"boundary: {report['boundary']}",
        f"next_step: {report['next_step']}",
    ]
    return "\n".join(lines)


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _count_by(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    if not _table_exists(conn, table):
        return {}
    rows = conn.execute(f"SELECT {column}, COUNT(*) AS count FROM {table} GROUP BY {column}").fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


if __name__ == "__main__":
    raise SystemExit(main())
