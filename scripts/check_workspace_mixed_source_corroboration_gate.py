#!/usr/bin/env python3
"""Gate for mixed-source workspace corroboration and conflict behavior."""

from __future__ import annotations

import argparse
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
from memory_engine.repository import MemoryRepository  # noqa: E402

SCOPE = "project:feishu_ai_challenge"
TENANT = "tenant:demo"
ORG = "org:demo"
BOUNDARY = (
    "local_temp_sqlite_mixed_source_gate; no Feishu API writes, "
    "no full workspace ingestion claim, no production daemon claim"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that chat, document, and table sources share one governed memory ledger."
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp_dir:
        conn = connect(Path(temp_dir) / "mixed-source.sqlite")
        try:
            init_db(conn)
            report = build_report(conn)
        finally:
            conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    repo = MemoryRepository(conn)
    service = CopilotService(repository=repo, auto_init_cognee=False)

    chat_text = "决定：生产部署必须加 --canary --region cn-shanghai。"
    doc_text = "决定：生产部署必须加 --canary --region cn-shanghai。"
    bitable_text = "决定：生产部署必须加 --blue-green --region cn-shanghai。"

    chat_candidate = service.create_candidate(
        _candidate_request(
            chat_text,
            source_type="feishu_message",
            source_id="chat_msg_001",
            source_context={"entrypoint": "feishu_group_chat", "chat_id": "chat_workspace_gate"},
        )
    )
    confirmed = service.confirm(
        ConfirmRequest(
            candidate_id=str(chat_candidate.get("candidate_id") or ""),
            scope=SCOPE,
            actor_id="ou_workspace_gate_reviewer",
            reason="mixed-source gate confirms initial chat memory",
            current_context=_current_context("memory.confirm", entrypoint="workspace_mixed_source_gate"),
        )
    )
    doc_duplicate = service.create_candidate(
        _candidate_request(
            doc_text,
            source_type="document_feishu",
            source_id="doc_workspace_gate_001",
            source_context={
                "entrypoint": "workspace_document",
                "document_id": "doc_workspace_gate_001",
            },
        )
    )
    bitable_conflict = service.create_candidate(
        _candidate_request(
            bitable_text,
            source_type="lark_bitable",
            source_id="bitable_workspace_gate_rec_001",
            source_context={
                "entrypoint": "workspace_bitable",
                "bitable_app_token": "app_workspace_gate",
                "bitable_table_id": "tbl_workspace_gate",
                "bitable_record_id": "rec_workspace_gate",
            },
        )
    )

    active_memory = _active_memory(conn)
    active_memory_id = str(active_memory["id"]) if active_memory is not None else ""
    evidence_rows = _evidence_rows(conn, active_memory_id)
    version_rows = _version_rows(conn, active_memory_id)
    active_evidence_source_types = sorted(
        {
            str(row["source_type"])
            for row in evidence_rows
            if row["version_id"] == (active_memory["active_version_id"] if active_memory is not None else None)
        }
    )
    conflict_evidence_source_types = sorted(
        {
            str(row["source_type"])
            for row in evidence_rows
            if row["version_id"] != (active_memory["active_version_id"] if active_memory is not None else None)
        }
    )
    checks = {
        "chat_candidate_created": chat_candidate.get("action") == "created"
        and chat_candidate.get("status") == "candidate",
        "chat_candidate_confirmed": confirmed.get("ok") is True and confirmed.get("status") == "active",
        "document_same_value_added_as_evidence": doc_duplicate.get("action") == "duplicate"
        and {"feishu_message", "document_feishu"}.issubset(set(active_evidence_source_types)),
        "bitable_conflict_candidate_created": bitable_conflict.get("action") == "candidate_conflict"
        and bool((bitable_conflict.get("conflict") or {}).get("has_conflict")),
        "active_value_not_silently_overwritten": active_memory is not None
        and active_memory["current_value"] == chat_text,
        "conflict_evidence_points_to_bitable": "lark_bitable" in conflict_evidence_source_types,
        "single_governed_memory_row": len(_memory_rows(conn)) == 1,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "ok": not failures,
        "boundary": BOUNDARY,
        "scope": SCOPE,
        "memory_id": active_memory_id,
        "checks": checks,
        "failures": failures,
        "actions": {
            "chat_candidate": _action_summary(chat_candidate),
            "confirm": _action_summary(confirmed),
            "document_duplicate": _action_summary(doc_duplicate),
            "bitable_conflict": _action_summary(bitable_conflict),
        },
        "evidence": {
            "active_evidence_count": len(
                [
                    row
                    for row in evidence_rows
                    if row["version_id"] == (active_memory["active_version_id"] if active_memory is not None else None)
                ]
            ),
            "active_evidence_source_types": active_evidence_source_types,
            "conflict_evidence_source_types": conflict_evidence_source_types,
            "version_status_counts": _count_by(version_rows, "status"),
        },
        "summary": (
            "Chat evidence can create an active memory; document evidence with the same value adds corroboration; "
            "Bitable evidence with a different value becomes a conflict candidate without overwriting the active memory."
        ),
        "next_step": ""
        if not failures
        else "Fix mixed-source evidence routing before claiming workspace/chat memory corroboration works.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Mixed-Source Corroboration Gate",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"  {name}: {'pass' if passed else 'fail'}")
    lines.extend(
        [
            "",
            f"active_evidence_source_types: {', '.join(report['evidence']['active_evidence_source_types'])}",
            f"conflict_evidence_source_types: {', '.join(report['evidence']['conflict_evidence_source_types'])}",
        ]
    )
    if report["failures"]:
        lines.append("")
        lines.append("failures:")
        for failure in report["failures"]:
            lines.append(f"  - {failure}")
    return "\n".join(lines)


def _candidate_request(
    text: str,
    *,
    source_type: str,
    source_id: str,
    source_context: dict[str, str],
) -> CreateCandidateRequest:
    return CreateCandidateRequest.from_payload(
        {
            "text": text,
            "scope": SCOPE,
            "source": {
                "source_type": source_type,
                "source_id": source_id,
                "actor_id": "ou_workspace_gate_reviewer",
                "created_at": "2026-05-04T00:00:00+08:00",
                "quote": text,
            },
            "current_context": _current_context("memory.create_candidate", **source_context),
            "auto_confirm": False,
        }
    )


def _current_context(action: str, *, entrypoint: str, **source_context: str) -> dict[str, Any]:
    source = {"entrypoint": entrypoint, "workspace_id": SCOPE}
    source.update(source_context)
    return {
        "scope": SCOPE,
        "permission": {
            "request_id": f"req_workspace_mixed_source_{action.replace('.', '_')}",
            "trace_id": f"trace_workspace_mixed_source_{action.replace('.', '_')}",
            "actor": {
                "user_id": "ou_workspace_gate_reviewer",
                "tenant_id": TENANT,
                "organization_id": ORG,
                "roles": ["member", "reviewer"],
            },
            "source_context": source,
            "requested_action": action,
            "requested_visibility": "team",
            "timestamp": "2026-05-04T00:00:00+08:00",
        },
    }


def _active_memory(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, active_version_id, current_value, status
        FROM memories
        WHERE scope_type = 'project'
          AND scope_id = 'feishu_ai_challenge'
        ORDER BY created_at
        LIMIT 1
        """
    ).fetchone()


def _memory_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT id, status FROM memories ORDER BY created_at"))


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


def _version_rows(conn: sqlite3.Connection, memory_id: str) -> list[sqlite3.Row]:
    if not memory_id:
        return []
    return list(
        conn.execute(
            "SELECT id, status, value FROM memory_versions WHERE memory_id = ? ORDER BY version_no",
            (memory_id,),
        )
    )


def _count_by(rows: list[sqlite3.Row], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row[key] or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _action_summary(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": response.get("ok"),
        "action": response.get("action"),
        "status": response.get("status"),
        "candidate_id": response.get("candidate_id"),
        "memory_id": response.get("memory_id"),
        "conflict": response.get("conflict"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
