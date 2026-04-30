from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.feishu_live import _event_time_iso  # noqa: E402
from memory_engine.copilot.local_env import load_local_env_files  # noqa: E402
from memory_engine.copilot.service import CopilotService  # noqa: E402
from memory_engine.copilot.tools import handle_tool_request  # noqa: E402
from memory_engine.feishu_cards import build_candidate_review_card  # noqa: E402
from memory_engine.feishu_events import FeishuMessageEvent  # noqa: E402

SCOPE = "project:feishu_ai_challenge"
TENANT_ID = "tenant:demo"
ORGANIZATION_ID = "org:demo"
VISIBILITY = "team"


def build_remember_payload(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    scope: str = SCOPE,
) -> dict[str, Any]:
    normalized_text = text.strip()
    if normalized_text.lower().startswith("/remember "):
        normalized_text = normalized_text.split(" ", 1)[1].strip()

    event = FeishuMessageEvent(
        message_id=message_id,
        chat_id=chat_id,
        chat_type="group",
        sender_id=sender_open_id,
        sender_type="user",
        message_type="text",
        text=normalized_text,
        create_time=0,
        raw={},
        ignore_reason=None,
        bot_mentioned=True,
    )

    return {
        "text": normalized_text,
        "scope": scope,
        "source": {
            "source_type": "feishu_message",
            "source_id": message_id,
            "actor_id": sender_open_id,
            "created_at": _event_time_iso(event),
            "quote": normalized_text,
            "source_chat_id": chat_id,
        },
        "current_context": {
            "session_id": f"feishu:{chat_id}",
            "chat_id": chat_id,
            "scope": scope,
            "user_id": sender_open_id,
            "tenant_id": TENANT_ID,
            "organization_id": ORGANIZATION_ID,
            "visibility_policy": VISIBILITY,
            "intent": "create_candidate",
            "thread_topic": normalized_text[:80],
            "allowed_scopes": [scope],
            "metadata": {
                "message_id": message_id,
                "chat_type": "group",
                "entrypoint": "feishu_chat",
            },
            "permission": {
                "request_id": message_id,
                "trace_id": f"remember-router-{message_id[-12:]}",
                "actor": {
                    "open_id": sender_open_id,
                    "tenant_id": TENANT_ID,
                    "organization_id": ORGANIZATION_ID,
                    "roles": ["member"],
                },
                "source_context": {
                    "entrypoint": "feishu_chat",
                    "workspace_id": scope,
                    "chat_id": chat_id,
                },
                "requested_action": "fmc_memory_create_candidate",
                "requested_visibility": VISIBILITY,
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
        },
        "auto_confirm": False,
    }


def route_remember_message(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    load_local_env_files(root=ROOT, override=True)
    payload = build_remember_payload(
        text=text,
        message_id=message_id,
        chat_id=chat_id,
        sender_open_id=sender_open_id,
    )
    service = CopilotService(db_path=db_path)
    tool_result = handle_tool_request("memory.create_candidate", payload, service=service)
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
    result = route_remember_message(
        text=str(envelope.get("text") or ""),
        message_id=str(envelope.get("message_id") or ""),
        chat_id=str(envelope.get("chat_id") or ""),
        sender_open_id=str(envelope.get("sender_open_id") or ""),
        db_path=str(envelope.get("db_path")) if envelope.get("db_path") else None,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
