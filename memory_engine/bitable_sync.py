from __future__ import annotations

import json
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .benchmark import run_benchmark
from .models import parse_scope


LEDGER_FIELDS = [
    "memory_id",
    "scope",
    "type",
    "subject",
    "current_value",
    "status",
    "version",
    "source",
    "updated_at",
    "reason",
    "confidence",
    "importance",
    "recall_count",
]

VERSION_FIELDS = [
    "version_id",
    "memory_id",
    "scope",
    "type",
    "subject",
    "current_value",
    "status",
    "version",
    "source",
    "updated_at",
    "created_by",
    "supersedes_version_id",
]

BENCHMARK_FIELDS = [
    "run_id",
    "benchmark_name",
    "benchmark_type",
    "source",
    "case_count",
    "case_pass_rate",
    "recall_at_3",
    "conflict_accuracy",
    "candidate_precision",
    "candidate_recall",
    "agent_task_context_use_rate",
    "l1_hot_recall_p95_ms",
    "stale_leakage_rate",
    "evidence_coverage",
    "sensitive_reminder_leakage_rate",
    "avg_latency_ms",
    "failure_type_counts",
    "recommended_fix_summary",
    "updated_at",
    "summary_json",
]

CANDIDATE_REVIEW_FIELDS = [
    "candidate_id",
    "memory_id",
    "scope",
    "type",
    "subject",
    "status",
    "new_value",
    "old_value",
    "evidence",
    "risk_flags",
    "recommended_action",
    "updated_at",
]

REMINDER_CANDIDATE_FIELDS = [
    "reminder_id",
    "memory_id",
    "scope",
    "subject",
    "current_value",
    "reason",
    "status",
    "due_at",
    "evidence",
    "recommended_action",
    "updated_at",
]

DEFAULT_TABLES = {
    "ledger": "Memory Ledger",
    "versions": "Memory Versions",
    "candidate_review": "Candidate Review",
    "benchmark": "Benchmark Results",
    "reminder_candidates": "Reminder Candidates",
}


@dataclass(frozen=True)
class BitableTarget:
    base_token: str
    ledger_table: str = DEFAULT_TABLES["ledger"]
    versions_table: str = DEFAULT_TABLES["versions"]
    candidate_review_table: str = DEFAULT_TABLES["candidate_review"]
    benchmark_table: str = DEFAULT_TABLES["benchmark"]
    reminder_candidates_table: str = DEFAULT_TABLES["reminder_candidates"]
    lark_cli: str = "lark-cli"
    profile: str | None = None
    as_identity: str | None = None


def collect_sync_payload(
    conn,
    *,
    scope: str | None = None,
    benchmark_json: str | Path | None = None,
    benchmark_cases: str | Path | None = None,
    benchmark_name: str | None = None,
    reminder_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "tables": {
            "ledger": {
                "table": DEFAULT_TABLES["ledger"],
                "fields": LEDGER_FIELDS,
                "rows": ledger_rows(conn, scope=scope),
            },
            "versions": {
                "table": DEFAULT_TABLES["versions"],
                "fields": VERSION_FIELDS,
                "rows": version_rows(conn, scope=scope),
            },
            "candidate_review": {
                "table": DEFAULT_TABLES["candidate_review"],
                "fields": CANDIDATE_REVIEW_FIELDS,
                "rows": candidate_review_rows(conn, scope=scope),
            },
            "benchmark": {
                "table": DEFAULT_TABLES["benchmark"],
                "fields": BENCHMARK_FIELDS,
                "rows": benchmark_rows(
                    benchmark_json=benchmark_json,
                    benchmark_cases=benchmark_cases,
                    benchmark_name=benchmark_name,
                ),
            },
            "reminder_candidates": {
                "table": DEFAULT_TABLES["reminder_candidates"],
                "fields": REMINDER_CANDIDATE_FIELDS,
                "rows": reminder_candidate_rows(reminder_candidates or []),
            },
        }
    }
    return payload


def ledger_rows(conn, *, scope: str | None = None) -> list[list[Any]]:
    where_sql, params = _scope_filter("m", scope)
    rows = conn.execute(
        f"""
        SELECT
          m.id AS memory_id,
          m.scope_type || ':' || m.scope_id AS scope,
          m.type,
          m.subject,
          m.current_value,
          m.status,
          mv.version_no AS version,
          COALESCE(re.source_type, e.source_type, 'unknown') AS source_type,
          re.source_id AS source_id,
          m.updated_at,
          m.reason,
          m.confidence,
          m.importance,
          m.recall_count
        FROM memories m
        LEFT JOIN memory_versions mv ON mv.id = m.active_version_id
        LEFT JOIN memory_evidence e ON e.id = (
          SELECT latest_e.id
          FROM memory_evidence latest_e
          WHERE latest_e.memory_id = m.id
            AND latest_e.version_id = m.active_version_id
          ORDER BY latest_e.created_at DESC
          LIMIT 1
        )
        LEFT JOIN raw_events re ON re.id = COALESCE(e.source_event_id, m.source_event_id)
        {where_sql}
        ORDER BY m.updated_at DESC, m.id
        """,
        params,
    ).fetchall()
    return [
        [
            row["memory_id"],
            row["scope"],
            row["type"],
            row["subject"],
            row["current_value"],
            row["status"],
            row["version"],
            _source(row["source_type"], row["source_id"]),
            _format_ms(row["updated_at"]),
            row["reason"],
            row["confidence"],
            row["importance"],
            row["recall_count"],
        ]
        for row in rows
    ]


def version_rows(conn, *, scope: str | None = None) -> list[list[Any]]:
    where_sql, params = _scope_filter("m", scope)
    rows = conn.execute(
        f"""
        SELECT
          mv.id AS version_id,
          mv.memory_id,
          m.scope_type || ':' || m.scope_id AS scope,
          m.type,
          m.subject,
          mv.value AS current_value,
          mv.status,
          mv.version_no AS version,
          COALESCE(re.source_type, e.source_type, 'unknown') AS source_type,
          re.source_id AS source_id,
          mv.created_at AS updated_at,
          mv.created_by,
          mv.supersedes_version_id
        FROM memory_versions mv
        JOIN memories m ON m.id = mv.memory_id
        LEFT JOIN memory_evidence e ON e.id = (
          SELECT latest_e.id
          FROM memory_evidence latest_e
          WHERE latest_e.memory_id = mv.memory_id
            AND latest_e.version_id = mv.id
          ORDER BY latest_e.created_at DESC
          LIMIT 1
        )
        LEFT JOIN raw_events re ON re.id = COALESCE(e.source_event_id, mv.source_event_id)
        {where_sql}
        ORDER BY mv.created_at DESC, mv.memory_id, mv.version_no
        """,
        params,
    ).fetchall()
    return [
        [
            row["version_id"],
            row["memory_id"],
            row["scope"],
            row["type"],
            row["subject"],
            row["current_value"],
            row["status"],
            row["version"],
            _source(row["source_type"], row["source_id"]),
            _format_ms(row["updated_at"]),
            row["created_by"],
            row["supersedes_version_id"],
        ]
        for row in rows
    ]


def candidate_review_rows(conn, *, scope: str | None = None) -> list[list[Any]]:
    where_sql, params = _scope_filter("m", scope)
    candidate_where = f"{where_sql} AND" if where_sql else "WHERE"
    rows = conn.execute(
        f"""
        SELECT
          m.id AS memory_id,
          m.scope_type || ':' || m.scope_id AS scope,
          m.type,
          m.subject,
          m.current_value,
          m.status,
          mv.id AS candidate_id,
          mv.value AS candidate_value,
          mv.status AS candidate_status,
          mv.supersedes_version_id,
          old_mv.value AS old_value,
          e.quote AS evidence_quote,
          mv.created_at AS updated_at
        FROM memories m
        JOIN memory_versions mv ON mv.memory_id = m.id
        LEFT JOIN memory_versions old_mv ON old_mv.id = mv.supersedes_version_id
        LEFT JOIN memory_evidence e ON e.id = (
          SELECT latest_e.id
          FROM memory_evidence latest_e
          WHERE latest_e.memory_id = mv.memory_id
            AND latest_e.version_id = mv.id
          ORDER BY latest_e.created_at DESC
          LIMIT 1
        )
        {candidate_where} mv.status = 'candidate'
        ORDER BY mv.created_at DESC, mv.id
        """,
        params,
    ).fetchall()
    return [
        [
            row["candidate_id"],
            row["memory_id"],
            row["scope"],
            row["type"],
            row["subject"],
            row["candidate_status"],
            row["candidate_value"],
            row["old_value"],
            row["evidence_quote"],
            "conflict_candidate" if row["supersedes_version_id"] else "",
            "review_conflict" if row["supersedes_version_id"] else "review_candidate",
            _format_ms(row["updated_at"]),
        ]
        for row in rows
    ]


def reminder_candidate_rows(reminders: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for reminder in reminders:
        evidence = reminder.get("evidence") if isinstance(reminder.get("evidence"), dict) else {}
        rows.append(
            [
                reminder.get("reminder_id"),
                reminder.get("memory_id"),
                reminder.get("scope"),
                reminder.get("subject"),
                reminder.get("current_value"),
                reminder.get("reason"),
                reminder.get("status"),
                reminder.get("due_at"),
                evidence.get("quote"),
                reminder.get("recommended_action"),
                _format_ms(int(time.time() * 1000)),
            ]
        )
    return rows


def benchmark_rows(
    *,
    benchmark_json: str | Path | None = None,
    benchmark_cases: str | Path | None = None,
    benchmark_name: str | None = None,
) -> list[list[Any]]:
    if benchmark_json is None and benchmark_cases is None:
        return []

    if benchmark_cases is not None:
        result = run_benchmark(benchmark_cases)
        source = str(benchmark_cases)
        default_name = Path(benchmark_cases).stem
    else:
        source = str(benchmark_json)
        default_name = Path(benchmark_json).stem if benchmark_json is not None else "benchmark"
        result = json.loads(Path(benchmark_json).read_text(encoding="utf-8"))

    summary = result.get("summary", result)
    now = _format_ms(int(time.time() * 1000))
    run_id = f"bench_{int(time.time() * 1000)}"
    failure_type_counts = summary.get("failure_type_counts") or {}
    return [
        [
            run_id,
            benchmark_name or default_name,
            result.get("benchmark_type", summary.get("benchmark_type", "")),
            source,
            summary.get("case_count", 0),
            summary.get("case_pass_rate", 0.0),
            summary.get("recall_at_3", 0.0),
            summary.get("conflict_accuracy", 0.0),
            summary.get("candidate_precision", 0.0),
            summary.get("candidate_recall", 0.0),
            summary.get("agent_task_context_use_rate", 0.0),
            summary.get("l1_hot_recall_p95_ms", 0.0),
            summary.get("stale_leakage_rate", 0.0),
            summary.get("evidence_coverage", 0.0),
            summary.get("sensitive_reminder_leakage_rate", 0.0),
            summary.get("avg_latency_ms", 0.0),
            json.dumps(failure_type_counts, ensure_ascii=False, sort_keys=True),
            _recommended_fix_summary(failure_type_counts),
            now,
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
        ]
    ]


def sync_payload(
    payload: dict[str, Any],
    target: BitableTarget,
    *,
    dry_run: bool = True,
    retries: int = 2,
) -> dict[str, Any]:
    if not dry_run and target.base_token == "app_xxx":
        return {
            "ok": False,
            "dry_run": False,
            "tables": _table_summary(payload),
            "results": [],
            "errors": [{"ok": False, "stderr": "Set --base-token or BITABLE_BASE_TOKEN before using --write."}],
            "error_summary": "Set --base-token or BITABLE_BASE_TOKEN before using --write.",
        }
    commands = build_commands(payload, target)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "commands": [command["argv"] for command in commands],
            "tables": _table_summary(payload),
            "errors": [],
        }

    results = []
    errors = []
    for command in commands:
        result = _run_with_retry(command["argv"], command["body"], retries=retries)
        results.append(result)
        if not result["ok"]:
            errors.append(result)

    return {
        "ok": not errors,
        "dry_run": False,
        "tables": _table_summary(payload),
        "results": results,
        "errors": errors,
        "error_summary": _error_summary(errors),
    }


def build_commands(payload: dict[str, Any], target: BitableTarget) -> list[dict[str, Any]]:
    table_ids = {
        "ledger": target.ledger_table,
        "versions": target.versions_table,
        "candidate_review": target.candidate_review_table,
        "benchmark": target.benchmark_table,
        "reminder_candidates": target.reminder_candidates_table,
    }
    commands = []
    for key, table in payload["tables"].items():
        rows = table["rows"]
        if not rows:
            continue
        for chunk in _chunks(rows, 200):
            body = {"fields": table["fields"], "rows": chunk}
            argv = [
                target.lark_cli,
                "base",
                "+record-batch-create",
                "--base-token",
                target.base_token,
                "--table-id",
                table_ids[key],
                "--json",
                "<temp-json>",
            ]
            if target.profile:
                argv.extend(["--profile", target.profile])
            if target.as_identity:
                argv.extend(["--as", target.as_identity])
            commands.append({"table": key, "argv": argv, "body": body})
    return commands


def table_schema_spec() -> dict[str, Any]:
    return {
        "tables": [
            {
                "name": DEFAULT_TABLES["ledger"],
                "purpose": "当前有效记忆台账，一行对应一个 memory_id 的当前状态。",
                "fields": _schema_fields(LEDGER_FIELDS),
                "suggested_views": ["Active by status", "By type", "Recently updated"],
            },
            {
                "name": DEFAULT_TABLES["versions"],
                "purpose": "版本链，一行对应一个 memory version，可展示 active / superseded。",
                "fields": _schema_fields(VERSION_FIELDS),
                "suggested_views": ["Version status", "By memory_id", "Recently updated"],
            },
            {
                "name": DEFAULT_TABLES["candidate_review"],
                "purpose": "候选记忆审核队列，只展示 Copilot service 输出，不直接改变记忆状态。",
                "fields": _schema_fields(CANDIDATE_REVIEW_FIELDS),
                "suggested_views": ["Pending review", "Conflict candidates", "By subject"],
            },
            {
                "name": DEFAULT_TABLES["benchmark"],
                "purpose": "Benchmark 汇总，一行对应一次评测运行。",
                "fields": _schema_fields(BENCHMARK_FIELDS),
                "suggested_views": ["Latest runs", "Pass rate trend"],
            },
            {
                "name": DEFAULT_TABLES["reminder_candidates"],
                "purpose": "Heartbeat reminder 候选队列，本阶段只保留 dry-run 字段设计。",
                "fields": _schema_fields(REMINDER_CANDIDATE_FIELDS),
                "suggested_views": ["Pending reminder", "By subject"],
            },
        ]
    }


def setup_commands(target: BitableTarget) -> list[list[str]]:
    commands = []
    for table in table_schema_spec()["tables"]:
        fields = [
            {"name": field["name"], "type": field["type"]}
            for field in table["fields"]
        ]
        argv = [
            target.lark_cli,
            "base",
            "+table-create",
            "--base-token",
            target.base_token,
            "--name",
            table["name"],
            "--fields",
            json.dumps(fields, ensure_ascii=False),
        ]
        if target.profile:
            argv.extend(["--profile", target.profile])
        if target.as_identity:
            argv.extend(["--as", target.as_identity])
        commands.append(argv)
    return commands


def _schema_fields(fields: list[str]) -> list[dict[str, str]]:
    number_fields = {
        "version",
        "confidence",
        "importance",
        "recall_count",
        "case_count",
        "case_pass_rate",
        "recall_at_3",
        "conflict_accuracy",
        "candidate_precision",
        "candidate_recall",
        "agent_task_context_use_rate",
        "l1_hot_recall_p95_ms",
        "stale_leakage_rate",
        "evidence_coverage",
        "sensitive_reminder_leakage_rate",
        "avg_latency_ms",
    }
    datetime_fields = {"updated_at"}
    return [
        {
            "name": field,
            "type": "number" if field in number_fields else "datetime" if field in datetime_fields else "text",
        }
        for field in fields
    ]


def _run_with_retry(argv: list[str], body: dict[str, Any], *, retries: int) -> dict[str, Any]:
    display_argv = list(argv)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix=".bitable_sync_", suffix=".json", dir=".", delete=False) as tmp:
        json.dump(body, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name)
        tmp_arg = f"@./{tmp_path.name}"

    run_argv = [tmp_arg if part == "<temp-json>" else part for part in argv]
    display_argv = [tmp_arg if part == "<temp-json>" else part for part in display_argv]
    try:
        for attempt in range(1, retries + 2):
            try:
                completed = subprocess.run(
                    run_argv,
                    check=False,
                    text=True,
                    capture_output=True,
                )
            except OSError as exc:
                return {
                    "ok": False,
                    "attempts": attempt,
                    "argv": display_argv,
                    "returncode": None,
                    "stdout": "",
                    "stderr": str(exc),
                }
            if completed.returncode == 0:
                return {
                    "ok": True,
                    "attempts": attempt,
                    "argv": display_argv,
                    "stdout": completed.stdout.strip(),
                }
            if attempt <= retries:
                time.sleep(min(0.5 * attempt, 2.0))
                continue
            return {
                "ok": False,
                "attempts": attempt,
                "argv": display_argv,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
    finally:
        tmp_path.unlink(missing_ok=True)


def _table_summary(payload: dict[str, Any]) -> dict[str, int]:
    return {
        key: len(table["rows"])
        for key, table in payload["tables"].items()
    }


def _error_summary(errors: list[dict[str, Any]]) -> str | None:
    if not errors:
        return None
    parts = []
    for error in errors:
        stderr = error.get("stderr") or error.get("stdout") or "unknown error"
        parts.append(f"{error['argv'][:4]} failed after {error['attempts']} attempts: {stderr[:240]}")
    return "\n".join(parts)


def _recommended_fix_summary(failure_type_counts: dict[str, Any]) -> str:
    if not failure_type_counts:
        return "当前样例无失败；保留边界样例继续观察。"
    return "; ".join(f"{name}:{count}" for name, count in sorted(failure_type_counts.items()))


def _source(source_type: str | None, source_id: str | None) -> str:
    if source_id:
        return f"{source_type}:{source_id}"
    return source_type or "unknown"


def _format_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _chunks(rows: list[list[Any]], size: int) -> list[list[list[Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _scope_filter(alias: str, scope: str | None) -> tuple[str, tuple[Any, ...]]:
    if scope is None:
        return "", ()
    parsed = parse_scope(scope)
    return f"WHERE {alias}.scope_type = ? AND {alias}.scope_id = ?", (parsed.scope_type, parsed.scope_id)
