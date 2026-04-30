from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

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

ENTERPRISE_MEMORY_SIGNALS = (
    "记住",
    "请记一下",
    "以后",
    "统一",
    "规则",
    "决定",
    "约定",
    "约束",
    "负责人",
    "截止",
    "上线窗口",
    "回滚负责人",
    "不对",
    "改成",
)
QUESTION_MARKERS = ("？", "?", "是什么", "怎么", "是否", "吗", "是不是")


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


def route_gateway_message(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    chat_type: str = "group",
    bot_mentioned: bool = False,
    allowlist_chat_ids: Sequence[str] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Route one OpenClaw gateway Feishu message.

    Explicit /remember keeps the existing interactive-card path. Unmentioned
    allowlist group messages are only probed silently when they carry durable
    enterprise memory signals.
    """

    normalized_text = text.strip()
    if _is_explicit_remember(normalized_text):
        return route_remember_message(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            db_path=db_path,
        )

    if chat_type != "group" or bot_mentioned:
        return _ignored_result(
            message_id=message_id,
            chat_id=chat_id,
            reason_code="not_passive_group_message",
        )

    if not _chat_allowed(chat_id, allowlist_chat_ids):
        return _ignored_result(
            message_id=message_id,
            chat_id=chat_id,
            reason_code="chat_not_allowlisted",
        )

    if not _has_enterprise_memory_signal(normalized_text):
        return _ignored_result(
            message_id=message_id,
            chat_id=chat_id,
            reason_code="low_memory_signal",
        )

    load_local_env_files(root=ROOT, override=True)
    payload = build_remember_payload(
        text=normalized_text,
        message_id=message_id,
        chat_id=chat_id,
        sender_open_id=sender_open_id,
    )
    context = payload["current_context"]
    context["intent"] = "silent_candidate_probe"
    context["metadata"]["entrypoint"] = "openclaw_gateway_live"
    context["metadata"]["bot_mentioned"] = False
    context["permission"]["requested_action"] = "memory.create_candidate"
    context["permission"]["source_context"]["entrypoint"] = "openclaw_gateway_live"

    service = CopilotService(db_path=db_path)
    tool_result = handle_tool_request("memory.create_candidate", payload, service=service)
    action = str(tool_result.get("action") or "")
    return {
        "ok": bool(tool_result.get("ok")),
        "tool": "memory.create_candidate",
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": "passive_candidate_probe",
        "tool_result": tool_result,
        "card": None,
        "disposition": "silent_no_reply",
        "message_disposition": {
            "memory_path": "silent_candidate_probe",
            "candidate_path": action or "attempted",
            "reason_code": "passive_group_detection",
        },
        "publish": _silent_publish_result(message_id=message_id, chat_id=chat_id),
    }


def _is_explicit_remember(text: str) -> bool:
    lowered = text.lower()
    return lowered == "/remember" or lowered.startswith("/remember ")


def _chat_allowed(chat_id: str, allowlist_chat_ids: Sequence[str] | None) -> bool:
    if isinstance(allowlist_chat_ids, str):
        allowlist = _csv_values(allowlist_chat_ids)
    elif allowlist_chat_ids is not None:
        allowlist = [str(item).strip() for item in allowlist_chat_ids if str(item).strip()]
    else:
        allowlist = _env_allowlist()
    return bool(chat_id) and chat_id in allowlist


def _env_allowlist() -> list[str]:
    raw = os.environ.get("OPENCLAW_FEISHU_ALLOWED_CHAT_IDS") or os.environ.get("COPILOT_FEISHU_ALLOWED_CHAT_IDS") or ""
    return _csv_values(raw)


def _csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _has_enterprise_memory_signal(text: str) -> bool:
    stripped = text.strip()
    if not stripped or _looks_like_question(stripped):
        return False
    return any(signal in stripped for signal in ENTERPRISE_MEMORY_SIGNALS)


def _looks_like_question(text: str) -> bool:
    lowered = text.lower()
    return any(marker in text or marker in lowered for marker in QUESTION_MARKERS)


def _ignored_result(*, message_id: str, chat_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "ok": True,
        "ignored": True,
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": reason_code,
        "card": None,
        "disposition": "silent_no_reply",
        "message_disposition": {
            "memory_path": "ignored",
            "candidate_path": "not_attempted",
            "reason_code": reason_code,
        },
        "publish": _silent_publish_result(message_id=message_id, chat_id=chat_id),
    }


def _silent_publish_result(*, message_id: str, chat_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": False,
        "mode": "silent_no_reply",
        "reply_to": message_id,
        "chat_id": chat_id,
        "text": "",
        "card": None,
        "suppressed": True,
    }


def main() -> int:
    raw = sys.stdin.read().strip()
    envelope = json.loads(raw) if raw else {}
    result = route_gateway_message(
        text=str(envelope.get("text") or ""),
        message_id=str(envelope.get("message_id") or ""),
        chat_id=str(envelope.get("chat_id") or ""),
        sender_open_id=str(envelope.get("sender_open_id") or ""),
        chat_type=str(envelope.get("chat_type") or "group"),
        bot_mentioned=bool(envelope.get("bot_mentioned", False)),
        allowlist_chat_ids=envelope.get("allowlist_chat_ids"),
        db_path=str(envelope.get("db_path")) if envelope.get("db_path") else None,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
