from __future__ import annotations

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
    "reject": "memory.reject",
    "needs_evidence": "memory.needs_evidence",
    "expire": "memory.expire",
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
    conn.close()
    if not tool_result.get("ok"):
        return {"ok": False, "tool_result": tool_result}
    return {
        "ok": True,
        "tool_result": tool_result,
        "card": build_candidate_review_card(tool_result),
    }


def main() -> int:
    raw = sys.stdin.read().strip()
    envelope = json.loads(raw) if raw else {}
    result = route_card_action(
        action=str(envelope.get("action") or ""),
        candidate_id=str(envelope.get("candidate_id") or ""),
        chat_id=str(envelope.get("chat_id") or ""),
        operator_open_id=str(envelope.get("operator_open_id") or ""),
        token=str(envelope.get("token") or ""),
        db_path=str(envelope.get("db_path")) if envelope.get("db_path") else None,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
