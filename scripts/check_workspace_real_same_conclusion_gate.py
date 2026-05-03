#!/usr/bin/env python3
"""Gate for real chat plus workspace same-conclusion corroboration.

This is stricter than the real chat/resource co-ingestion gate. It first
extracts a durable fact from a captured real chat message, then verifies that a
reviewed, lark-cli-fetched workspace source contains the same fact. Only then
does it route both pieces of evidence through CopilotService in a temporary DB
and require the workspace evidence to be added as corroborating evidence on the
active memory version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.copilot.schemas import ConfirmRequest, CreateCandidateRequest  # noqa: E402
from memory_engine.copilot.service import CopilotService  # noqa: E402
from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.document_ingestion import FeishuIngestionSource, extract_candidate_quotes  # noqa: E402
from memory_engine.feishu_workspace_fetcher import (  # noqa: E402
    WorkspaceActor,
    fetch_workspace_resource_sources,
    workspace_resource_from_spec,
)
from memory_engine.repository import MemoryRepository  # noqa: E402
from scripts.check_workspace_real_chat_resource_gate import (  # noqa: E402
    ChatInput,
    _chat_input_from_event_log,
)

BOUNDARY = (
    "real_same_conclusion_temp_db_gate; verifies captured real chat text and reviewed lark-cli-fetched "
    "workspace source contain the same fact before routing both through CopilotService; no production "
    "daemon claim, no full workspace ingestion claim"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check real chat + workspace same-conclusion corroboration.")
    parser.add_argument("--event-log", type=Path, help="Captured Feishu/OpenClaw event log.")
    parser.add_argument("--expected-chat-id")
    parser.add_argument("--chat-text")
    parser.add_argument("--message-id")
    parser.add_argument("--chat-id")
    parser.add_argument("--sender-id", default="manual_chat_sender")
    parser.add_argument("--expected-fact", help="Exact durable fact to verify in both chat and workspace sources.")
    parser.add_argument(
        "--resource",
        action="append",
        required=True,
        help="Reviewed workspace resource spec type:token[:title]. Resource identifiers are not echoed in the report.",
    )
    parser.add_argument("--scope", default="workspace:feishu")
    parser.add_argument("--actor-user-id")
    parser.add_argument("--actor-open-id")
    parser.add_argument("--tenant-id", default="tenant:demo")
    parser.add_argument("--organization-id", default="org:demo")
    parser.add_argument("--roles", default="member,reviewer")
    parser.add_argument("--profile")
    parser.add_argument("--as-identity", default="user")
    parser.add_argument("--max-sheet-rows", type=int, default=20)
    parser.add_argument("--max-bitable-records", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not (args.actor_user_id or args.actor_open_id):
        parser.error("--actor-user-id or --actor-open-id is required")
    if args.event_log:
        chat_input = _chat_input_from_event_log(args.event_log, expected_chat_id=args.expected_chat_id)
    else:
        if not (args.chat_text and args.message_id and args.chat_id):
            parser.error("--event-log or --chat-text plus --message-id plus --chat-id is required")
        chat_input = ChatInput(
            message_id=args.message_id,
            chat_id=args.chat_id,
            sender_id=args.sender_id,
            text=args.chat_text,
            created_at="manual_chat_input",
            source="explicit_chat_text",
        )

    actor = WorkspaceActor(
        user_id=args.actor_user_id,
        open_id=args.actor_open_id,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        roles=tuple(role.strip() for role in args.roles.split(",") if role.strip()),
    )
    resource_sources: list[FeishuIngestionSource] = []
    fetch_failures: list[str] = []
    for spec in args.resource:
        resource = workspace_resource_from_spec(spec)
        try:
            resource_sources.extend(
                fetch_workspace_resource_sources(
                    resource,
                    max_sheet_rows=args.max_sheet_rows,
                    max_bitable_records=args.max_bitable_records,
                    profile=args.profile,
                    as_identity=args.as_identity,
                )
            )
        except Exception as exc:
            fetch_failures.append(type(exc).__name__)

    with tempfile.TemporaryDirectory() as temp_dir:
        conn = connect(Path(temp_dir) / "real-same-conclusion.sqlite")
        try:
            init_db(conn)
            report = run_same_conclusion_gate(
                conn,
                chat_input=chat_input,
                resource_sources=resource_sources,
                fetch_failure_count=len(fetch_failures),
                actor=actor,
                scope=args.scope,
                expected_fact=args.expected_fact,
            )
        finally:
            conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_same_conclusion_gate(
    conn: sqlite3.Connection,
    *,
    chat_input: ChatInput,
    resource_sources: list[FeishuIngestionSource],
    fetch_failure_count: int,
    actor: WorkspaceActor,
    scope: str,
    expected_fact: str | None = None,
) -> dict[str, Any]:
    fact = _select_fact(chat_input.text, expected_fact=expected_fact)
    matching_sources = [source for source in resource_sources if fact and _contains_fact(source.text, fact)]
    preflight_checks = {
        "chat_has_candidate_fact": _equals_check(bool(fact), True),
        "fact_present_in_chat": _equals_check(bool(fact and _contains_fact(chat_input.text, fact)), True),
        "resource_fetch_succeeded": _equals_check(fetch_failure_count, 0),
        "workspace_source_count": _min_check(len(resource_sources), 1),
        "same_fact_found_in_workspace_source": _min_check(len(matching_sources), 1),
    }
    preflight_passed = all(check["status"] == "pass" for check in preflight_checks.values())

    chat_create: dict[str, Any] = {}
    confirm: dict[str, Any] = {}
    workspace_duplicates: list[dict[str, Any]] = []
    active_evidence_source_types: list[str] = []
    active_evidence_count = 0
    memory_id = ""

    if preflight_passed and fact:
        repo = MemoryRepository(conn)
        service = CopilotService(repository=repo, auto_init_cognee=False)
        chat_create = service.create_candidate(
            _candidate_request(
                fact,
                scope=scope,
                source_type="feishu_message",
                source_id=f"{chat_input.message_id}#same-conclusion",
                actor_id=_actor_id(actor, fallback=chat_input.sender_id),
                created_at=chat_input.created_at,
                current_context=_current_context(
                    actor=actor,
                    scope=scope,
                    action="memory.create_candidate",
                    entrypoint="feishu_live_event_log",
                    source_context={
                        "chat_id": chat_input.chat_id,
                        "message_id": chat_input.message_id,
                    },
                ),
            )
        )
        if chat_create.get("ok") and chat_create.get("candidate_id"):
            confirm = service.confirm(
                ConfirmRequest(
                    candidate_id=str(chat_create["candidate_id"]),
                    scope=scope,
                    actor_id=_actor_id(actor, fallback=chat_input.sender_id),
                    reason="real same-conclusion gate confirms captured chat fact",
                    current_context=_current_context(
                        actor=actor,
                        scope=scope,
                        action="memory.confirm",
                        entrypoint="real_same_conclusion_gate",
                        source_context={"chat_id": chat_input.chat_id, "message_id": chat_input.message_id},
                    ),
                )
            )
        if confirm.get("ok"):
            for source in matching_sources:
                workspace_duplicates.append(
                    service.create_candidate(
                        _candidate_request(
                            fact,
                            scope=scope,
                            source_type=source.source_type,
                            source_id=f"{source.source_id}#same-conclusion",
                            actor_id=_actor_id(actor, fallback=source.actor_id),
                            created_at=source.created_at,
                            current_context=_current_context(
                                actor=actor,
                                scope=scope,
                                action="memory.create_candidate",
                                entrypoint="workspace_same_conclusion_gate",
                                source_context={
                                    "workspace_id": scope,
                                    "source_type": source.source_type,
                                    "source_id": source.source_id,
                                },
                            ),
                        )
                    )
                )
        active_memory = _active_memory(conn)
        memory_id = str(active_memory["id"]) if active_memory is not None else ""
        evidence_rows = _evidence_rows(conn, memory_id)
        active_version_id = active_memory["active_version_id"] if active_memory is not None else None
        active_evidence_source_types = sorted(
            {str(row["source_type"]) for row in evidence_rows if row["version_id"] == active_version_id}
        )
        active_evidence_count = len([row for row in evidence_rows if row["version_id"] == active_version_id])

    action_checks = {}
    if preflight_passed:
        action_checks = {
            "chat_candidate_created": _equals_check(chat_create.get("action"), "created"),
            "chat_candidate_confirmed": _equals_check(
                bool(confirm.get("ok")) and confirm.get("status") == "active", True
            ),
            "workspace_same_fact_added_as_duplicate": _equals_check(
                any(item.get("action") == "duplicate" for item in workspace_duplicates),
                True,
            ),
            "active_evidence_has_chat_and_workspace": _equals_check(
                "feishu_message" in active_evidence_source_types
                and any(source_type != "feishu_message" for source_type in active_evidence_source_types),
                True,
            ),
        }
    checks = {**preflight_checks, **action_checks}
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    source_type_counts = _count_source_types(resource_sources)
    matching_source_type_counts = _count_source_types(matching_sources)
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "boundary": BOUNDARY,
        "mode": "real_same_conclusion_temp_db",
        "fact": {
            "sha256": hashlib.sha256(fact.encode("utf-8")).hexdigest() if fact else "",
            "length": len(fact),
            "source": "explicit" if expected_fact else "chat_candidate_extraction",
        },
        "summary": {
            "resource_source_count": len(resource_sources),
            "matching_resource_source_count": len(matching_sources),
            "resource_fetch_failure_count": fetch_failure_count,
            "active_evidence_count": active_evidence_count,
        },
        "source_type_counts": source_type_counts,
        "matching_source_type_counts": matching_source_type_counts,
        "active_evidence_source_types": active_evidence_source_types,
        "memory_id": memory_id,
        "checks": checks,
        "failures": failures,
        "actions": {
            "chat_create": _action_summary(chat_create),
            "confirm": _action_summary(confirm),
            "workspace_duplicates": [_action_summary(item) for item in workspace_duplicates],
        },
        "next_step": ""
        if not failures
        else "Capture or provide a real chat message whose durable fact also appears in a reviewed Feishu document, Sheet, or Bitable source.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Real Same-Conclusion Gate",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        f"resource_source_count: {report['summary']['resource_source_count']}",
        f"matching_resource_source_count: {report['summary']['matching_resource_source_count']}",
        f"active_evidence_source_types: {', '.join(report['active_evidence_source_types'])}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(
            f"  {name}: {check['status']} "
            f"(actual={check['actual']}, threshold={check['operator']} {check['threshold']})"
        )
    if report["failures"]:
        lines.append("")
        lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


def _select_fact(chat_text: str, *, expected_fact: str | None) -> str:
    if expected_fact:
        return _normalize_fact(expected_fact)
    candidates = extract_candidate_quotes(chat_text, limit=1)
    if not candidates:
        return ""
    return _normalize_fact(candidates[0])


def _normalize_fact(value: str) -> str:
    return " ".join(value.strip().split())


def _contains_fact(text: str, fact: str) -> bool:
    return _normalize_fact(fact) in _normalize_fact(text)


def _candidate_request(
    text: str,
    *,
    scope: str,
    source_type: str,
    source_id: str,
    actor_id: str,
    created_at: str,
    current_context: dict[str, Any],
) -> CreateCandidateRequest:
    return CreateCandidateRequest.from_payload(
        {
            "text": text,
            "scope": scope,
            "source": {
                "source_type": source_type,
                "source_id": source_id,
                "actor_id": actor_id,
                "created_at": created_at,
                "quote": text,
            },
            "current_context": current_context,
            "auto_confirm": False,
        }
    )


def _current_context(
    *,
    actor: WorkspaceActor,
    scope: str,
    action: str,
    entrypoint: str,
    source_context: dict[str, str],
) -> dict[str, Any]:
    actor_payload: dict[str, Any] = {
        "tenant_id": actor.tenant_id,
        "organization_id": actor.organization_id,
        "roles": list(actor.roles),
    }
    if actor.user_id:
        actor_payload["user_id"] = actor.user_id
    if actor.open_id:
        actor_payload["open_id"] = actor.open_id
    source = {"entrypoint": entrypoint, "workspace_id": scope}
    source.update(source_context)
    request_suffix = action.replace(".", "_")
    return {
        "scope": scope,
        "tenant_id": actor.tenant_id,
        "organization_id": actor.organization_id,
        "permission": {
            "request_id": f"req_real_same_conclusion_{request_suffix}",
            "trace_id": f"trace_real_same_conclusion_{request_suffix}",
            "actor": actor_payload,
            "source_context": source,
            "requested_action": action,
            "requested_visibility": "team",
            "timestamp": "2026-05-04T00:00:00+08:00",
        },
    }


def _actor_id(actor: WorkspaceActor, *, fallback: str) -> str:
    return actor.user_id or actor.open_id or fallback


def _active_memory(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, active_version_id, current_value, status
        FROM memories
        ORDER BY created_at
        LIMIT 1
        """
    ).fetchone()


def _evidence_rows(conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
    if not memory_id:
        return []
    return list(
        conn.execute(
            """
            SELECT version_id, source_type, quote
            FROM memory_evidence
            WHERE memory_id = ?
            ORDER BY created_at
            """,
            (memory_id,),
        )
    )


def _count_source_types(sources: list[FeishuIngestionSource]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        counts[source.source_type] = counts.get(source.source_type, 0) + 1
    return counts


def _action_summary(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": response.get("ok"),
        "action": response.get("action"),
        "status": response.get("status"),
        "candidate_id": response.get("candidate_id"),
        "memory_id": response.get("memory_id"),
    }


def _equals_check(actual: Any, expected: Any) -> dict[str, Any]:
    return {
        "status": "pass" if actual == expected else "fail",
        "actual": actual,
        "threshold": expected,
        "operator": "==",
    }


def _min_check(actual: int | float, threshold: int | float) -> dict[str, Any]:
    return {
        "status": "pass" if actual >= threshold else "fail",
        "actual": actual,
        "threshold": threshold,
        "operator": ">=",
    }


if __name__ == "__main__":
    raise SystemExit(main())
