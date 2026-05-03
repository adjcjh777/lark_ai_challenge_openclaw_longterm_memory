from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.feishu_live import _grant_owner_role_if_applicable  # noqa: E402
from memory_engine.copilot.local_env import load_local_env_files  # noqa: E402
from memory_engine.copilot.service import CopilotService  # noqa: E402
from memory_engine.copilot.tools import handle_tool_request  # noqa: E402
from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.feishu_cards import build_candidate_review_card  # noqa: E402
from memory_engine.repository import MemoryRepository  # noqa: E402

SCOPE = "project:feishu_ai_challenge"
TENANT_ID = "tenant:demo"
ORGANIZATION_ID = "org:demo"
VISIBILITY = "team"

ACTION_TO_TOOL = {
    "confirm": "memory.confirm",
    "merge": "memory.confirm",
    "reject": "memory.reject",
    "needs_evidence": "memory.needs_evidence",
    "expire": "memory.expire",
    "undo": "memory.undo_review",
}


def route_card_action(
    *,
    action: str,
    candidate_id: str,
    chat_id: str,
    operator_open_id: str,
    token: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    load_local_env_files(root=ROOT, override=True)
    tool_name = ACTION_TO_TOOL[action]
    conn = connect(db_path)
    init_db(conn)
    repo = MemoryRepository(conn)
    if _action_token_seen(repo, token):
        idempotent_result = _current_candidate_result(
            repo=repo,
            candidate_id=candidate_id,
            action="duplicate_card_action_ignored",
            review_status=None,
        )
        conn.close()
        if idempotent_result is None:
            return {"ok": False, "tool_result": {"ok": False, "error": {"code": "candidate_not_found"}}}
        idempotent_result["idempotent"] = True
        idempotent_result["idempotent_reason"] = "card_action_token_already_processed"
        return {
            "ok": True,
            "tool_result": idempotent_result,
            "card": build_candidate_review_card(idempotent_result),
        }
    context = {
        "session_id": f"feishu:{chat_id}",
        "chat_id": chat_id,
        "scope": SCOPE,
        "user_id": operator_open_id,
        "tenant_id": TENANT_ID,
        "organization_id": ORGANIZATION_ID,
        "visibility_policy": VISIBILITY,
        "intent": "review_candidate",
        "thread_topic": candidate_id[:80],
        "allowed_scopes": [SCOPE],
        "metadata": {
            "entrypoint": "feishu_chat_card_action",
            "card_token": token,
        },
        "permission": {
            "request_id": token,
            "trace_id": f"card-action-{token[-12:]}",
            "actor": {
                "open_id": operator_open_id,
                "tenant_id": TENANT_ID,
                "organization_id": ORGANIZATION_ID,
                "roles": ["member"],
            },
            "source_context": {
                "entrypoint": "feishu_chat",
                "workspace_id": SCOPE,
                "chat_id": chat_id,
            },
            "requested_action": tool_name,
            "requested_visibility": VISIBILITY,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }
    _grant_owner_role_if_applicable(repo, context, operator_open_id, candidate_id)
    payload = {
        "candidate_id": candidate_id,
        "scope": SCOPE,
        "actor_id": operator_open_id,
        "reason": "Feishu card action",
        "current_context": context,
    }
    service = CopilotService(repository=repo)
    tool_result = handle_tool_request(tool_name, payload, service=service)
    if not tool_result.get("ok"):
        idempotent_result = _already_reviewed_result(
            repo=repo,
            tool_result=tool_result,
            candidate_id=candidate_id,
        )
        if idempotent_result is not None:
            conn.close()
            return {
                "ok": True,
                "tool_result": idempotent_result,
                "card": build_candidate_review_card(idempotent_result),
            }
    conn.close()
    if not tool_result.get("ok"):
        return {"ok": False, "tool_result": tool_result}
    return {
        "ok": True,
        "tool_result": tool_result,
        "card": build_candidate_review_card(tool_result),
    }


def _already_reviewed_result(
    *,
    repo: MemoryRepository,
    tool_result: dict[str, Any],
    candidate_id: str,
) -> dict[str, Any] | None:
    error = tool_result.get("error") if isinstance(tool_result.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    if error.get("code") != "candidate_not_confirmable":
        return None
    status = str(details.get("status") or "")
    review_status = _review_status(status)
    if review_status is None:
        return None

    memory = _memory_for_candidate(repo, candidate_id)
    if memory is None:
        return None

    response = _current_candidate_result(
        repo=repo,
        candidate_id=candidate_id,
        action=review_status,
        review_status=review_status,
    )
    bridge = tool_result.get("bridge")
    if isinstance(bridge, dict):
        response["bridge"] = bridge
    response["idempotent"] = True
    response["idempotent_reason"] = "candidate_already_reviewed"
    return response


def _action_token_seen(repo: MemoryRepository, token: str) -> bool:
    if not token:
        return False
    row = repo.conn.execute(
        """
        SELECT 1
        FROM memory_audit_events
        WHERE request_id = ?
        LIMIT 1
        """,
        (token,),
    ).fetchone()
    return row is not None


def _review_status(status: str) -> str | None:
    return {
        "active": "confirmed",
        "rejected": "rejected",
        "needs_evidence": "needs_evidence",
        "expired": "expired",
    }.get(status)


def _memory_for_candidate(repo: MemoryRepository, candidate_id: str) -> Any | None:
    memory = repo.conn.execute("SELECT * FROM memories WHERE id = ?", (candidate_id,)).fetchone()
    if memory is not None:
        return memory
    version = repo.conn.execute(
        """
        SELECT memory_id
        FROM memory_versions
        WHERE id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if version is None:
        return None
    return repo.conn.execute("SELECT * FROM memories WHERE id = ?", (str(version["memory_id"]),)).fetchone()


def _current_candidate_result(
    *,
    repo: MemoryRepository,
    candidate_id: str,
    action: str,
    review_status: str | None,
) -> dict[str, Any] | None:
    memory = _memory_for_candidate(repo, candidate_id)
    if memory is None:
        return None
    return _status_result_from_memory(
        repo=repo,
        memory=memory,
        candidate_id=candidate_id,
        action=action,
        review_status=review_status or _review_status(str(memory["status"])) or "pending",
    )


def _status_result_from_memory(
    *,
    repo: MemoryRepository,
    memory: Any,
    candidate_id: str,
    action: str,
    review_status: str,
) -> dict[str, Any]:
    evidence = _latest_evidence(repo, str(memory["id"]), memory["active_version_id"])
    return {
        "ok": True,
        "action": action,
        "candidate_id": candidate_id,
        "memory_id": str(memory["id"]),
        "version_id": memory["active_version_id"],
        "status": str(memory["status"]),
        "review_status": review_status,
        "last_handler": memory["updated_by"],
        "last_handled_at": int(memory["updated_at"] or 0),
        "memory": {
            "memory_id": str(memory["id"]),
            "type": str(memory["type"]),
            "subject": str(memory["subject"]),
            "current_value": str(memory["current_value"]),
            "owner_id": memory["owner_id"],
            "status": str(memory["status"]),
            "version_id": memory["active_version_id"],
            "summary": memory["reason"],
            "evidence": evidence,
        },
        "evidence": evidence,
    }


def _latest_evidence(repo: MemoryRepository, memory_id: str, version_id: str | None) -> dict[str, Any]:
    row = repo.conn.execute(
        """
        SELECT source_type, source_event_id, quote
        FROM memory_evidence
        WHERE memory_id = ?
          AND version_id IS ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (memory_id, version_id),
    ).fetchone()
    if row is None:
        return {"source_type": "unknown", "source_id": None, "quote": None}
    return {
        "source_type": row["source_type"],
        "source_id": row["source_event_id"],
        "quote": row["quote"],
    }


def main() -> int:
    raw = sys.stdin.read().strip()
    envelope = json.loads(raw) if raw else {}
    noisy_stdout = io.StringIO()
    with contextlib.redirect_stdout(noisy_stdout):
        result = route_card_action(
            action=str(envelope.get("action") or ""),
            candidate_id=str(envelope.get("candidate_id") or ""),
            chat_id=str(envelope.get("chat_id") or ""),
            operator_open_id=str(envelope.get("operator_open_id") or ""),
            token=str(envelope.get("token") or ""),
            db_path=str(envelope.get("db_path")) if envelope.get("db_path") else None,
        )
    captured = noisy_stdout.getvalue().strip()
    if captured:
        print(captured, file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
