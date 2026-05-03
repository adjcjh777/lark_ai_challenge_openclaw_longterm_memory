#!/usr/bin/env python3
"""Find real chat/workspace samples that can prove same-conclusion evidence.

The checker scans captured Feishu/OpenClaw message logs and reviewed workspace
resources fetched through lark-cli. It looks for an exact durable-fact match
between a real chat candidate fact and a fetched doc/sheet/Bitable source. If a
match is found, it immediately runs the strict same-conclusion gate in a
temporary SQLite DB. Reports stay redacted: no raw message text, resource
tokens, chat ids, message ids, record ids, or matched fact text are printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.document_ingestion import FeishuIngestionSource, extract_candidate_quotes  # noqa: E402
from memory_engine.feishu_events import message_event_from_payload  # noqa: E402
from memory_engine.feishu_workspace_fetcher import (  # noqa: E402
    WorkspaceActor,
    WorkspaceResource,
    discover_drive_folder_resources,
    discover_wiki_space_resources,
    discover_workspace_resources,
    fetch_workspace_resource_sources,
    workspace_resource_from_spec,
)
from scripts.check_feishu_passive_message_event_gate import _payloads_from_text  # noqa: E402
from scripts.check_workspace_real_chat_resource_gate import ChatInput  # noqa: E402
from scripts.check_workspace_real_same_conclusion_gate import run_same_conclusion_gate  # noqa: E402

BOUNDARY = (
    "real_same_conclusion_sample_finder; scans captured real Feishu/OpenClaw chat logs and reviewed "
    "lark-cli-fetched workspace resources for exact durable-fact matches; no production daemon claim, "
    "no full workspace ingestion claim"
)


@dataclass(frozen=True)
class ChatFact:
    chat_index: int
    fact: str


@dataclass(frozen=True)
class FactMatch:
    chat_index: int
    resource_index: int
    source_type: str
    fact: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Find real same-conclusion chat/workspace evidence samples.")
    parser.add_argument("--event-log", type=Path, action="append", required=True)
    parser.add_argument("--expected-chat-id")
    parser.add_argument(
        "--resource",
        action="append",
        default=[],
        help="Reviewed workspace resource spec type:token[:title]. Resource identifiers are not echoed in the report.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Optional read-only Drive search query for reviewed resource expansion.",
    )
    parser.add_argument("--doc-types", default="doc,docx,wiki,sheet,bitable")
    parser.add_argument("--opened-since", default="90d")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--folder-walk-root", action="store_true")
    parser.add_argument("--folder-walk-tokens")
    parser.add_argument("--wiki-space-walk-ids")
    parser.add_argument("--walk-max-depth", type=int, default=2)
    parser.add_argument("--walk-page-size", type=int, default=50)
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
    parser.add_argument("--candidate-limit-per-chat", type=int, default=5)
    parser.add_argument("--min-matches", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not (args.actor_user_id or args.actor_open_id):
        parser.error("--actor-user-id or --actor-open-id is required")
    if not (args.resource or args.query or args.folder_walk_root or args.folder_walk_tokens or args.wiki_space_walk_ids):
        parser.error(
            "at least one reviewed resource input is required: --resource, --query, "
            "--folder-walk-root, --folder-walk-tokens, or --wiki-space-walk-ids"
        )

    chats = chat_inputs_from_event_logs(args.event_log, expected_chat_id=args.expected_chat_id)
    resource_sources: list[FeishuIngestionSource] = []
    required_fetch_failures: list[str] = []
    optional_fetch_failures: list[str] = []
    resources = collect_reviewed_resources(
        specs=args.resource,
        queries=args.query,
        doc_types=_doc_types(args.doc_types),
        opened_since=args.opened_since,
        limit=args.limit,
        max_pages=args.max_pages,
        folder_walk_root=args.folder_walk_root,
        folder_walk_tokens=args.folder_walk_tokens,
        wiki_space_walk_ids=args.wiki_space_walk_ids,
        walk_max_depth=args.walk_max_depth,
        walk_page_size=args.walk_page_size,
        profile=args.profile,
        as_identity=args.as_identity,
    )
    for resource in resources:
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
            if _is_explicit_resource(resource):
                required_fetch_failures.append(type(exc).__name__)
            else:
                optional_fetch_failures.append(type(exc).__name__)

    actor = WorkspaceActor(
        user_id=args.actor_user_id,
        open_id=args.actor_open_id,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        roles=tuple(role.strip() for role in args.roles.split(",") if role.strip()),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        conn = connect(Path(temp_dir) / "same-conclusion-sample-finder.sqlite")
        try:
            init_db(conn)
            report = run_sample_finder(
                conn,
                chats=chats,
                resource_sources=resource_sources,
                fetch_failure_count=len(required_fetch_failures),
                optional_fetch_failure_count=len(optional_fetch_failures),
                actor=actor,
                scope=args.scope,
                candidate_limit_per_chat=args.candidate_limit_per_chat,
                min_matches=args.min_matches,
            )
        finally:
            conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def chat_inputs_from_event_logs(paths: list[Path], *, expected_chat_id: str | None = None) -> list[ChatInput]:
    chats: list[ChatInput] = []
    seen_message_ids: set[str] = set()
    for path in paths:
        for payload in _payloads_from_text(path.read_text(encoding="utf-8")):
            event = message_event_from_payload(payload)
            if event is None or event.ignore_reason:
                continue
            if expected_chat_id and event.chat_id != expected_chat_id:
                continue
            if event.message_id in seen_message_ids:
                continue
            seen_message_ids.add(event.message_id)
            chats.append(
                ChatInput(
                    message_id=event.message_id,
                    chat_id=event.chat_id,
                    sender_id=event.sender_id,
                    text=event.text,
                    created_at=str(event.create_time or "event_log"),
                    source="event_log",
                )
            )
    return chats


def collect_reviewed_resources(
    *,
    specs: list[str],
    queries: list[str],
    doc_types: list[str],
    opened_since: str | None,
    limit: int,
    max_pages: int,
    folder_walk_root: bool,
    folder_walk_tokens: str | None,
    wiki_space_walk_ids: str | None,
    walk_max_depth: int,
    walk_page_size: int,
    profile: str | None,
    as_identity: str | None,
) -> list[WorkspaceResource]:
    """Collect reviewed resources without exposing identifiers in the report."""

    resources = [workspace_resource_from_spec(spec) for spec in specs]
    for query in queries:
        resources.extend(
            discover_workspace_resources(
                query=query,
                doc_types=doc_types,
                limit=limit,
                max_pages=max_pages,
                opened_since=opened_since,
                sort="edit_time",
                profile=profile,
                as_identity=as_identity,
            )
        )
    if folder_walk_root or folder_walk_tokens:
        resources.extend(
            discover_drive_folder_resources(
                folder_tokens=_split_csv(folder_walk_tokens),
                include_root=folder_walk_root,
                doc_types=doc_types,
                limit=limit,
                max_depth=walk_max_depth,
                page_size=walk_page_size,
                profile=profile,
                as_identity=as_identity,
            )
        )
    if wiki_space_walk_ids:
        resources.extend(
            discover_wiki_space_resources(
                space_ids=_split_csv(wiki_space_walk_ids),
                doc_types=doc_types,
                limit=limit,
                max_depth=walk_max_depth,
                page_size=walk_page_size,
                profile=profile,
                as_identity=as_identity,
            )
        )
    return _dedupe_resources(resources)


def run_sample_finder(
    conn: sqlite3.Connection,
    *,
    chats: list[ChatInput],
    resource_sources: list[FeishuIngestionSource],
    fetch_failure_count: int,
    optional_fetch_failure_count: int = 0,
    actor: WorkspaceActor,
    scope: str,
    candidate_limit_per_chat: int = 5,
    min_matches: int = 1,
) -> dict[str, Any]:
    chat_facts = _chat_facts(chats, limit_per_chat=candidate_limit_per_chat)
    matches = _fact_matches(chat_facts, resource_sources)
    gate_report: dict[str, Any] | None = None
    if matches:
        first = matches[0]
        gate_report = run_same_conclusion_gate(
            conn,
            chat_input=chats[first.chat_index],
            resource_sources=[resource_sources[first.resource_index]],
            fetch_failure_count=0,
            actor=actor,
            scope=scope,
            expected_fact=first.fact,
        )
    checks = {
        "event_logs_have_chat_messages": _min_check(len(chats), 1),
        "chat_candidate_fact_count": _min_check(len(chat_facts), 1),
        "explicit_resource_fetch_succeeded": _equals_check(fetch_failure_count, 0),
        "workspace_source_count": _min_check(len(resource_sources), 1),
        "same_fact_match_count": _min_check(len(matches), min_matches),
    }
    if matches:
        checks["strict_same_conclusion_gate_passed"] = _equals_check(bool(gate_report and gate_report.get("ok")), True)
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "boundary": BOUNDARY,
        "mode": "real_same_conclusion_sample_finder",
        "summary": {
            "chat_message_count": len(chats),
            "chat_candidate_fact_count": len(chat_facts),
            "workspace_source_count": len(resource_sources),
            "resource_fetch_failure_count": fetch_failure_count,
            "optional_resource_fetch_failure_count": optional_fetch_failure_count,
            "total_resource_fetch_failure_count": fetch_failure_count + optional_fetch_failure_count,
            "same_fact_match_count": len(matches),
        },
        "source_type_counts": _count_source_types(resource_sources),
        "matching_source_type_counts": _count_source_types(
            [resource_sources[match.resource_index] for match in matches]
        ),
        "matches": [_redacted_match(match) for match in matches[:10]],
        "checks": checks,
        "failures": failures,
        "strict_gate": _redacted_gate_report(gate_report),
        "next_step": ""
        if not failures
        else "Capture a real chat message that repeats a durable fact already present in a reviewed Feishu document, Sheet, or Bitable source, then rerun this finder.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Real Same-Conclusion Sample Finder",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        f"chat_message_count: {report['summary']['chat_message_count']}",
        f"workspace_source_count: {report['summary']['workspace_source_count']}",
        f"same_fact_match_count: {report['summary']['same_fact_match_count']}",
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


def _chat_facts(chats: list[ChatInput], *, limit_per_chat: int) -> list[ChatFact]:
    facts: list[ChatFact] = []
    seen: set[tuple[int, str]] = set()
    for index, chat in enumerate(chats):
        for fact in extract_candidate_quotes(chat.text, limit=limit_per_chat):
            normalized = _normalize_fact(fact)
            key = (index, normalized)
            if normalized and key not in seen:
                seen.add(key)
                facts.append(ChatFact(chat_index=index, fact=normalized))
    return facts


def _fact_matches(chat_facts: list[ChatFact], resource_sources: list[FeishuIngestionSource]) -> list[FactMatch]:
    matches: list[FactMatch] = []
    seen: set[tuple[int, int, str]] = set()
    for fact in chat_facts:
        for resource_index, source in enumerate(resource_sources):
            if not _contains_fact(source.text, fact.fact):
                continue
            key = (fact.chat_index, resource_index, fact.fact)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                FactMatch(
                    chat_index=fact.chat_index,
                    resource_index=resource_index,
                    source_type=source.source_type,
                    fact=fact.fact,
                )
            )
    return matches


def _redacted_match(match: FactMatch) -> dict[str, Any]:
    return {
        "chat_index": match.chat_index,
        "resource_index": match.resource_index,
        "source_type": match.source_type,
        "fact_sha256": hashlib.sha256(match.fact.encode("utf-8")).hexdigest(),
        "fact_length": len(match.fact),
    }


def _redacted_gate_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    return {
        "status": report.get("status"),
        "checks": {
            key: value.get("status") if isinstance(value, dict) else value
            for key, value in (report.get("checks") or {}).items()
        },
        "active_evidence_source_types": report.get("active_evidence_source_types"),
        "matching_source_type_counts": report.get("matching_source_type_counts"),
    }


def _normalize_fact(value: str) -> str:
    return " ".join(value.strip().split())


def _contains_fact(text: str, fact: str) -> bool:
    return _normalize_fact(fact) in _normalize_fact(text)


def _count_source_types(sources: list[FeishuIngestionSource]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        counts[source.source_type] = counts.get(source.source_type, 0) + 1
    return counts


def _doc_types(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe_resources(resources: list[WorkspaceResource]) -> list[WorkspaceResource]:
    seen: set[tuple[str, str, str | None]] = set()
    result: list[WorkspaceResource] = []
    for resource in resources:
        key = (resource.route_type, resource.token, resource.table_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(resource)
    return result


def _is_explicit_resource(resource: WorkspaceResource) -> bool:
    raw = resource.raw or {}
    return bool(raw.get("explicit_resource_spec"))


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
