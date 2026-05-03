#!/usr/bin/env python3
"""Gate for real Feishu chat plus real workspace resource co-ingestion.

The gate uses a temporary SQLite DB. It can read a captured Feishu/OpenClaw
event log or explicit chat text, creates a `feishu_message` source from that
real chat payload, then fetches reviewed workspace resources through lark-cli
and sends everything through the same candidate pipeline.

This proves co-ingestion into one governed ledger. It does not prove production
long-running ingestion, and it does not prove same-conclusion corroboration
unless the supplied chat and resources actually contain the same durable fact.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.document_ingestion import FeishuIngestionSource, ingest_feishu_source  # noqa: E402
from memory_engine.feishu_events import FeishuMessageEvent, message_event_from_payload  # noqa: E402
from memory_engine.feishu_workspace_fetcher import (  # noqa: E402
    WorkspaceActor,
    fetch_workspace_resource_sources,
    workspace_current_context,
    workspace_resource_from_spec,
)
from memory_engine.repository import MemoryRepository  # noqa: E402
from scripts.check_feishu_passive_message_event_gate import _payloads_from_text  # noqa: E402

BOUNDARY = (
    "real_chat_plus_workspace_temp_db_gate; uses captured Feishu/OpenClaw chat event and real lark-cli "
    "workspace fetches; no production daemon claim, no full workspace ingestion claim"
)


@dataclass(frozen=True)
class ChatInput:
    message_id: str
    chat_id: str
    sender_id: str
    text: str
    created_at: str
    source: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Check real chat + workspace resource co-ingestion.")
    parser.add_argument("--event-log", type=Path, help="Captured Feishu/OpenClaw event log.")
    parser.add_argument("--expected-chat-id")
    parser.add_argument("--chat-text")
    parser.add_argument("--message-id")
    parser.add_argument("--chat-id")
    parser.add_argument("--sender-id", default="manual_chat_sender")
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
    parser.add_argument("--candidate-limit", type=int, default=8)
    parser.add_argument("--min-chat-candidates", type=int, default=1)
    parser.add_argument("--min-resource-sources", type=int, default=1)
    parser.add_argument("--min-resource-candidates", type=int, default=1)
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

    resources = [workspace_resource_from_spec(spec) for spec in args.resource]
    actor = WorkspaceActor(
        user_id=args.actor_user_id,
        open_id=args.actor_open_id,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        roles=tuple(role.strip() for role in args.roles.split(",") if role.strip()),
    )
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp_dir:
        conn = connect(Path(temp_dir) / "real-chat-workspace.sqlite")
        try:
            init_db(conn)
            report = run_gate(
                conn,
                chat_input=chat_input,
                resources=resources,
                actor=actor,
                scope=args.scope,
                max_sheet_rows=args.max_sheet_rows,
                max_bitable_records=args.max_bitable_records,
                candidate_limit=args.candidate_limit,
                min_chat_candidates=args.min_chat_candidates,
                min_resource_sources=args.min_resource_sources,
                min_resource_candidates=args.min_resource_candidates,
                profile=args.profile,
                as_identity=args.as_identity,
            )
        finally:
            conn.close()
    report["summary"]["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_gate(
    conn: sqlite3.Connection,
    *,
    chat_input: ChatInput,
    resources: list[Any],
    actor: WorkspaceActor,
    scope: str,
    max_sheet_rows: int,
    max_bitable_records: int,
    candidate_limit: int,
    min_chat_candidates: int,
    min_resource_sources: int,
    min_resource_candidates: int,
    profile: str | None,
    as_identity: str | None,
) -> dict[str, Any]:
    repo = MemoryRepository(conn)
    chat_source = FeishuIngestionSource(
        source_type="feishu_message",
        source_id=chat_input.message_id,
        title="Feishu group message",
        text=chat_input.text,
        actor_id=chat_input.sender_id,
        created_at=chat_input.created_at,
        metadata={"chat_id": chat_input.chat_id, "message_id": chat_input.message_id},
    )
    chat_result = ingest_feishu_source(
        repo,
        chat_source,
        scope=scope,
        current_context=_chat_current_context(scope=scope, actor=actor, chat_input=chat_input),
        limit=candidate_limit,
    )

    resource_results: list[dict[str, Any]] = []
    failed_count = 0
    for resource in resources:
        try:
            sources = fetch_workspace_resource_sources(
                resource,
                max_sheet_rows=max_sheet_rows,
                max_bitable_records=max_bitable_records,
                profile=profile,
                as_identity=as_identity,
            )
        except Exception as exc:
            failed_count += 1
            resource_results.append(
                {
                    "resource": _redacted_resource(resource),
                    "ok": False,
                    "stage": "fetch",
                    "error": str(exc),
                }
            )
            continue
        if not sources:
            resource_results.append(
                {
                    "resource": _redacted_resource(resource),
                    "ok": True,
                    "stage": "no_sources",
                    "candidate_count": 0,
                    "duplicate_count": 0,
                }
            )
            continue
        for source in sources:
            result = ingest_feishu_source(
                repo,
                source,
                scope=scope,
                current_context=workspace_current_context(scope=scope, actor=actor, source=source),
                limit=candidate_limit,
            )
            resource_results.append(
                {
                    "resource": _redacted_resource(resource),
                    "source": {
                        "source_type": source.source_type,
                    },
                    "ok": bool(result.get("ok")),
                    "candidate_count": int(result.get("candidate_count") or 0),
                    "duplicate_count": int(result.get("duplicate_count") or 0),
                    "error": result.get("error"),
                }
            )

    return build_real_chat_workspace_report(
        chat_result=chat_result,
        resource_results=resource_results,
        failed_count=failed_count,
        min_chat_candidates=min_chat_candidates,
        min_resource_sources=min_resource_sources,
        min_resource_candidates=min_resource_candidates,
        chat_source=chat_input.source,
    )


def build_real_chat_workspace_report(
    *,
    chat_result: dict[str, Any],
    resource_results: list[dict[str, Any]],
    failed_count: int,
    min_chat_candidates: int,
    min_resource_sources: int,
    min_resource_candidates: int,
    chat_source: str,
) -> dict[str, Any]:
    resource_source_count = sum(1 for item in resource_results if item.get("source"))
    resource_candidate_count = sum(int(item.get("candidate_count") or 0) for item in resource_results)
    resource_duplicate_count = sum(int(item.get("duplicate_count") or 0) for item in resource_results)
    chat_candidate_count = int(chat_result.get("candidate_count") or 0)
    chat_duplicate_count = int(chat_result.get("duplicate_count") or 0)
    source_type_counts: dict[str, int] = {}
    if chat_result.get("source"):
        source_type = str((chat_result.get("source") or {}).get("source_type") or "feishu_message")
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
    for item in resource_results:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_type = source.get("source_type")
        if source_type:
            key = str(source_type)
            source_type_counts[key] = source_type_counts.get(key, 0) + 1
    checks = {
        "chat_ingest_ok": _equals_check(bool(chat_result.get("ok")), True),
        "min_chat_candidates": _min_check(chat_candidate_count, min_chat_candidates),
        "min_resource_sources": _min_check(resource_source_count, min_resource_sources),
        "min_resource_candidates": _min_check(resource_candidate_count, min_resource_candidates),
        "no_resource_fetch_failures": _equals_check(failed_count, 0),
        "same_temp_db_has_chat_and_workspace_sources": _equals_check(
            bool(source_type_counts.get("feishu_message")) and resource_source_count > 0,
            True,
        ),
    }
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "boundary": BOUNDARY,
        "mode": "real_chat_plus_workspace_temp_db",
        "chat_source": chat_source,
        "summary": {
            "chat_candidate_count": chat_candidate_count,
            "chat_duplicate_count": chat_duplicate_count,
            "resource_source_count": resource_source_count,
            "resource_candidate_count": resource_candidate_count,
            "resource_duplicate_count": resource_duplicate_count,
            "resource_failed_count": failed_count,
        },
        "source_type_counts": source_type_counts,
        "checks": checks,
        "resource_results": resource_results,
        "failures": failures,
        "next_step": ""
        if not failures
        else "Capture a durable real chat message and reviewed workspace resources, then rerun this gate.",
        "corroboration_boundary": (
            "This gate proves real chat and real workspace sources share the candidate pipeline. "
            "Same-conclusion evidence corroboration still requires the chat and resource contents to state the same fact."
        ),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Real Chat Resource Gate",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        f"chat_candidate_count: {report['summary']['chat_candidate_count']}",
        f"resource_source_count: {report['summary']['resource_source_count']}",
        f"resource_candidate_count: {report['summary']['resource_candidate_count']}",
        f"source_type_counts: {json.dumps(report['source_type_counts'], ensure_ascii=False, sort_keys=True)}",
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


def _chat_input_from_event_log(path: Path, *, expected_chat_id: str | None) -> ChatInput:
    text = path.read_text(encoding="utf-8")
    for payload in _payloads_from_text(text):
        event = message_event_from_payload(payload)
        if event is None or event.ignore_reason:
            continue
        if expected_chat_id and event.chat_id != expected_chat_id:
            continue
        return _chat_input_from_event(event)
    raise ValueError("no usable Feishu text message found in event log")


def _chat_input_from_event(event: FeishuMessageEvent) -> ChatInput:
    return ChatInput(
        message_id=event.message_id,
        chat_id=event.chat_id,
        sender_id=event.sender_id,
        text=event.text,
        created_at=str(event.create_time or "event_log"),
        source="event_log",
    )


def _chat_current_context(*, scope: str, actor: WorkspaceActor, chat_input: ChatInput) -> dict[str, Any]:
    actor_payload: dict[str, Any] = {
        "tenant_id": actor.tenant_id,
        "organization_id": actor.organization_id,
        "roles": list(actor.roles),
    }
    if actor.user_id:
        actor_payload["user_id"] = actor.user_id
    if actor.open_id:
        actor_payload["open_id"] = actor.open_id
    return {
        "scope": scope,
        "tenant_id": actor.tenant_id,
        "organization_id": actor.organization_id,
        "permission": {
            "request_id": f"req_real_chat_workspace_{_safe_id(chat_input.message_id)}",
            "trace_id": f"trace_real_chat_workspace_{_safe_id(chat_input.message_id)}",
            "actor": actor_payload,
            "source_context": {
                "entrypoint": "feishu_live_event_log",
                "workspace_id": scope,
                "chat_id": chat_input.chat_id,
                "message_id": chat_input.message_id,
            },
            "requested_action": "memory.create_candidate",
            "requested_visibility": "team",
            "timestamp": chat_input.created_at,
        },
    }


def _redacted_resource(resource: Any) -> dict[str, Any]:
    return {
        "resource_type": resource.resource_type,
        "route_type": resource.route_type,
        "title": resource.title,
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


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)[:64] or "source"


if __name__ == "__main__":
    raise SystemExit(main())
