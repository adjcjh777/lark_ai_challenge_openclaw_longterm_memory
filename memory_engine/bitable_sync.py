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
from .feishu_cards import candidate_review_payload, reminder_candidate_payload
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
    "false_reminder_rate",
    "duplicate_reminder_rate",
    "user_confirmation_burden",
    "avg_latency_ms",
    "failure_type_counts",
    "recommended_fix_summary",
    "updated_at",
    "summary_json",
]

CANDIDATE_REVIEW_FIELDS = [
    "sync_key",
    "candidate_id",
    "memory_id",
    "scope",
    "type",
    "subject",
    "status",
    "review_status",
    "source_type",
    "risk_level",
    "conflict_status",
    "queue_view",
    "new_value",
    "old_value",
    "evidence",
    "risk_flags",
    "recommended_action",
    "reviewer",
    "last_handler",
    "last_handled_at",
    "request_id",
    "trace_id",
    "permission_decision",
    "permission_reason",
    "updated_at",
]

REMINDER_CANDIDATE_FIELDS = [
    "sync_key",
    "reminder_id",
    "memory_id",
    "scope",
    "subject",
    "current_value",
    "reason",
    "status",
    "due_at",
    "evidence",
    "target_actor",
    "cooldown",
    "available_actions",
    "next_review_at",
    "mute_key",
    "recommended_action",
    "request_id",
    "trace_id",
    "permission_decision",
    "permission_reason",
    "updated_at",
]

DEFAULT_TABLES = {
    "ledger": "Memory Ledger",
    "versions": "Memory Versions",
    "candidate_review": "Candidate Review",
    "benchmark": "Benchmark Results",
    "reminder_candidates": "Reminder Candidates",
}

UPSERT_TABLE_KEYS = {
    "candidate_review": "sync_key",
    "reminder_candidates": "sync_key",
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
    candidate_review_outputs: list[dict[str, Any]] | None = None,
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
                "rows": candidate_review_output_rows(candidate_review_outputs or [], scope=scope),
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


def candidate_review_output_rows(outputs: list[dict[str, Any]], *, scope: str | None = None) -> list[list[Any]]:
    rows = []
    for output in outputs:
        payload = candidate_review_payload(output)
        output_scope = payload.get("scope") or output.get("scope")
        if scope is not None and output_scope != scope:
            continue
        permission_decision = (
            payload.get("permission_decision") if isinstance(payload.get("permission_decision"), dict) else {}
        )
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        conflict = payload.get("conflict") if isinstance(payload.get("conflict"), dict) else {}
        queue_views = payload.get("queue_views") if isinstance(payload.get("queue_views"), list) else []
        rows.append(
            [
                _candidate_review_sync_key(payload),
                payload.get("candidate_id"),
                payload.get("memory_id"),
                output_scope,
                payload.get("type"),
                payload.get("subject"),
                payload.get("status"),
                payload.get("review_status") or "",
                payload.get("source_type") or evidence.get("source_type") or "",
                payload.get("risk_level") or "",
                payload.get("conflict_status") or "",
                " / ".join(str(view) for view in queue_views),
                payload.get("new_value") or "",
                conflict.get("old_value") or "",
                evidence.get("quote") or "",
                ", ".join(payload.get("risk_flags") or []),
                payload.get("recommended_action"),
                payload.get("reviewer") or "",
                payload.get("last_handler") or "",
                _format_ms(payload.get("last_handled_at")) if isinstance(payload.get("last_handled_at"), int) else "",
                payload.get("request_id") or "",
                payload.get("trace_id") or "",
                permission_decision.get("decision") or "",
                payload.get("permission_reason") or permission_decision.get("reason_code") or "",
                _format_ms(int(time.time() * 1000)),
            ]
        )
    return rows


def reminder_candidate_rows(reminders: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for reminder in reminders:
        payload = reminder_candidate_payload(reminder)
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        permission_decision = (
            payload.get("permission_decision") if isinstance(payload.get("permission_decision"), dict) else {}
        )
        rows.append(
            [
                _reminder_candidate_sync_key(payload),
                payload.get("reminder_id"),
                payload.get("memory_id"),
                payload.get("scope"),
                payload.get("subject"),
                payload.get("current_value") or "",
                payload.get("reason") or "",
                payload.get("status"),
                payload.get("due_at"),
                evidence.get("quote") or "",
                _json_cell(payload.get("target_actor") if isinstance(payload.get("target_actor"), dict) else {}),
                _json_cell(payload.get("cooldown") if isinstance(payload.get("cooldown"), dict) else {}),
                ", ".join(
                    str(action.get("action"))
                    for action in (payload.get("buttons") if isinstance(payload.get("buttons"), list) else [])
                    if isinstance(action, dict) and action.get("action")
                ),
                payload.get("next_review_at") or "",
                payload.get("mute_key") or "",
                payload.get("recommended_action"),
                payload.get("request_id") or "",
                payload.get("trace_id") or "",
                permission_decision.get("decision") or "",
                payload.get("permission_reason") or permission_decision.get("reason_code") or "",
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
            summary.get("false_reminder_rate", 0.0),
            summary.get("duplicate_reminder_rate", 0.0),
            summary.get("user_confirmation_burden", 0.0),
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
    readback: bool = True,
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
    existing_records = _read_existing_upsert_records(payload, target, retries=retries)
    if existing_records["errors"]:
        return {
            "ok": False,
            "dry_run": False,
            "tables": _table_summary(payload),
            "results": existing_records["results"],
            "errors": existing_records["errors"],
            "error_summary": _error_summary(existing_records["errors"]),
        }
    commands = _commands_with_existing_record_ids(commands, existing_records["records"])
    for command in commands:
        result = _run_with_retry(command["argv"], command["body"], retries=retries)
        results.append(result)
        if not result["ok"]:
            errors.append(result)
    readback_result = _verify_upsert_readback(payload, target, retries=retries) if readback and not errors else None
    if readback_result is not None:
        results.extend(readback_result["results"])
        errors.extend(readback_result["errors"])

    return {
        "ok": not errors,
        "dry_run": False,
        "tables": _table_summary(payload),
        "results": results,
        "errors": errors,
        "error_summary": _error_summary(errors),
        **({"readback": readback_result["summary"]} if readback_result is not None else {}),
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
        if key in UPSERT_TABLE_KEYS:
            for row in rows:
                body = dict(zip(table["fields"], row))
                argv = [
                    target.lark_cli,
                    "base",
                    "+record-upsert",
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
                commands.append(
                    {"table": key, "argv": argv, "body": body, "sync_key": body.get(UPSERT_TABLE_KEYS[key])}
                )
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
                "suggested_views": ["待我审核", "冲突需判断", "高风险暂不建议确认"],
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
        fields = [{"name": field["name"], "type": field["type"]} for field in table["fields"]]
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
        "false_reminder_rate",
        "duplicate_reminder_rate",
        "user_confirmation_burden",
        "avg_latency_ms",
    }
    datetime_fields = {"updated_at", "last_handled_at"}
    return [
        {
            "name": field,
            "type": "number" if field in number_fields else "datetime" if field in datetime_fields else "text",
        }
        for field in fields
    ]


def _run_with_retry(argv: list[str], body: dict[str, Any], *, retries: int) -> dict[str, Any]:
    display_argv = list(argv)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", prefix=".bitable_sync_", suffix=".json", dir=".", delete=False
    ) as tmp:
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


def _read_existing_upsert_records(payload: dict[str, Any], target: BitableTarget, *, retries: int) -> dict[str, Any]:
    table_ids = _target_table_ids(target)
    records: dict[tuple[str, str], str] = {}
    results = []
    errors = []
    for key, field_name in UPSERT_TABLE_KEYS.items():
        table = payload["tables"].get(key)
        if not table or not table.get("rows"):
            continue
        result = _run_record_list(target, table_ids[key], field_name, retries=retries)
        results.append(result)
        if not result["ok"]:
            errors.append(result)
            continue
        for record in _records_from_stdout(result.get("stdout")):
            fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
            sync_key = fields.get(field_name)
            record_id = record.get("record_id") or record.get("id")
            if isinstance(sync_key, str) and sync_key and isinstance(record_id, str) and record_id:
                records[(key, sync_key)] = record_id
    return {"records": records, "results": results, "errors": errors}


def _commands_with_existing_record_ids(
    commands: list[dict[str, Any]],
    existing_records: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    updated = []
    for command in commands:
        next_command = dict(command)
        sync_key = command.get("sync_key")
        if isinstance(sync_key, str) and sync_key:
            record_id = existing_records.get((str(command.get("table")), sync_key))
            if record_id:
                argv = list(command["argv"])
                json_index = argv.index("--json")
                argv[json_index:json_index] = ["--record-id", record_id]
                next_command["argv"] = argv
                next_command["record_id"] = record_id
        updated.append(next_command)
    return updated


def _verify_upsert_readback(payload: dict[str, Any], target: BitableTarget, *, retries: int) -> dict[str, Any]:
    table_ids = _target_table_ids(target)
    results = []
    errors = []
    summary: dict[str, Any] = {"ok": True}
    for key, field_name in UPSERT_TABLE_KEYS.items():
        table = payload["tables"].get(key)
        expected_keys = _expected_sync_keys(table, field_name)
        if not expected_keys:
            continue
        result = _run_record_list(target, table_ids[key], field_name, retries=retries)
        results.append(result)
        if not result["ok"]:
            errors.append(result)
            summary[key] = {"ok": False, "verified_keys": [], "missing_keys": expected_keys}
            summary["ok"] = False
            continue
        found = {
            fields.get(field_name)
            for record in _records_from_stdout(result.get("stdout"))
            for fields in [record.get("fields") if isinstance(record.get("fields"), dict) else {}]
            if isinstance(fields.get(field_name), str)
        }
        missing = [key_value for key_value in expected_keys if key_value not in found]
        summary[key] = {
            "ok": not missing,
            "verified_keys": [key_value for key_value in expected_keys if key_value in found],
            "missing_keys": missing,
        }
        if missing:
            summary["ok"] = False
            errors.append(
                {
                    "ok": False,
                    "attempts": 1,
                    "argv": [
                        target.lark_cli,
                        "base",
                        "+record-list",
                        "--base-token",
                        target.base_token,
                        "--table-id",
                        table_ids[key],
                    ],
                    "returncode": 0,
                    "stdout": result.get("stdout", ""),
                    "stderr": f"readback missing {field_name}: {', '.join(missing)}",
                }
            )
    return {"summary": summary, "results": results, "errors": errors}


def _run_record_list(target: BitableTarget, table_id: str, field_name: str, *, retries: int) -> dict[str, Any]:
    argv = [
        target.lark_cli,
        "base",
        "+record-list",
        "--base-token",
        target.base_token,
        "--table-id",
        table_id,
        "--field-id",
        field_name,
        "--offset",
        "0",
        "--limit",
        "200",
    ]
    if target.profile:
        argv.extend(["--profile", target.profile])
    if target.as_identity:
        argv.extend(["--as", target.as_identity])
    return _run_plain_with_retry(argv, retries=retries)


def _run_plain_with_retry(argv: list[str], *, retries: int) -> dict[str, Any]:
    for attempt in range(1, retries + 2):
        try:
            completed = subprocess.run(argv, check=False, text=True, capture_output=True)
        except OSError as exc:
            return {
                "ok": False,
                "attempts": attempt,
                "argv": argv,
                "returncode": None,
                "stdout": "",
                "stderr": str(exc),
            }
        if completed.returncode == 0:
            return {"ok": True, "attempts": attempt, "argv": argv, "stdout": completed.stdout.strip()}
        if attempt <= retries:
            time.sleep(min(0.5 * attempt, 2.0))
            continue
        return {
            "ok": False,
            "attempts": attempt,
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }


def _records_from_stdout(stdout: object) -> list[dict[str, Any]]:
    if not isinstance(stdout, str) or not stdout.strip():
        return []
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    records = payload.get("records")
    if records is None and isinstance(payload.get("data"), dict):
        records = payload["data"].get("records") or payload["data"].get("items")
    if records is None:
        records = payload.get("items")
    return [record for record in records or [] if isinstance(record, dict)]


def _expected_sync_keys(table: dict[str, Any] | None, field_name: str) -> list[str]:
    if not table or field_name not in table.get("fields", []):
        return []
    index = table["fields"].index(field_name)
    keys = []
    for row in table.get("rows", []):
        if len(row) > index and isinstance(row[index], str) and row[index]:
            keys.append(row[index])
    return keys


def _table_summary(payload: dict[str, Any]) -> dict[str, int]:
    return {key: len(table["rows"]) for key, table in payload["tables"].items()}


def _target_table_ids(target: BitableTarget) -> dict[str, str]:
    return {
        "ledger": target.ledger_table,
        "versions": target.versions_table,
        "candidate_review": target.candidate_review_table,
        "benchmark": target.benchmark_table,
        "reminder_candidates": target.reminder_candidates_table,
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


def _json_cell(value: dict[str, Any]) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _candidate_review_sync_key(payload: dict[str, Any]) -> str:
    candidate_id = payload.get("candidate_id")
    if isinstance(candidate_id, str) and candidate_id:
        return candidate_id
    memory_id = payload.get("memory_id")
    request_id = payload.get("request_id")
    return "candidate_review:" + ":".join(str(part) for part in (memory_id or "unknown", request_id or "unknown"))


def _reminder_candidate_sync_key(payload: dict[str, Any]) -> str:
    reminder_id = payload.get("reminder_id")
    if isinstance(reminder_id, str) and reminder_id:
        return reminder_id
    memory_id = payload.get("memory_id")
    request_id = payload.get("request_id")
    return "reminder_candidate:" + ":".join(str(part) for part in (memory_id or "unknown", request_id or "unknown"))


def _chunks(rows: list[list[Any]], size: int) -> list[list[list[Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _scope_filter(alias: str, scope: str | None) -> tuple[str, tuple[Any, ...]]:
    if scope is None:
        return "", ()
    parsed = parse_scope(scope)
    return f"WHERE {alias}.scope_type = ? AND {alias}.scope_id = ?", (parsed.scope_type, parsed.scope_id)
