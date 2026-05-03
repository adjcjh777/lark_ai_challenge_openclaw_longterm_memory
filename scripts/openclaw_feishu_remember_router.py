from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.feishu_live import _event_time_iso  # noqa: E402
from memory_engine.copilot.group_policies import (  # noqa: E402
    disable_group_memory,
    enable_group_memory,
    ensure_group_policy,
    get_group_policy,
    group_policy_allows_passive_memory,
    record_group_policy_denied,
)
from memory_engine.copilot.local_env import load_local_env_files  # noqa: E402
from memory_engine.copilot.service import CopilotService  # noqa: E402
from memory_engine.copilot.tools import handle_tool_request  # noqa: E402
from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.feishu_cards import (  # noqa: E402
    build_candidate_review_card,
    build_card_from_text,
    build_compact_search_answer_card,
    build_group_settings_card,
    build_prefetch_context_card,
    build_review_inbox_card,
    build_search_result_card,
)
from memory_engine.feishu_config import load_feishu_config  # noqa: E402
from memory_engine.feishu_events import FeishuMessageEvent  # noqa: E402
from memory_engine.feishu_publisher import DryRunPublisher, LarkCliPublisher  # noqa: E402

SCOPE = "project:feishu_ai_challenge"
TENANT_ID = "tenant:demo"
ORGANIZATION_ID = "org:demo"
VISIBILITY = "team"
REVIEW_INBOX_DELIVERY_LIMIT = 3

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
PREFETCH_SIGNALS = (
    "准备",
    "checklist",
    "清单",
    "计划",
    "执行前",
    "任务前",
    "上线前",
    "收口",
    "按之前说的",
    "之前说的那套",
)
REVIEW_INBOX_SIGNALS = ("待审核", "审核队列", "审核收件箱", "看看审核", "需要我审核")
NATURAL_ENABLE_SIGNALS = ("开启记忆", "启用记忆", "打开记忆", "让这个群记忆", "让本群记忆")
NATURAL_DISABLE_SIGNALS = ("关闭记忆", "禁用记忆", "停止记忆", "不要记这个群", "不要记本群")
GROUP_SETTINGS_NATURAL_QUERIES = {
    "当前群记忆",
    "群记忆",
    "本群记忆",
    "当前群设置",
    "群记忆设置",
    "本群记忆设置",
    "这个群的记忆",
    "查看当前群记忆",
    "当前群记忆状态",
}


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
    card = build_candidate_review_card(tool_result)
    return {
        "ok": True,
        "tool": "memory.create_candidate",
        "routing_reason": "explicit_remember",
        "message_id": message_id,
        "chat_id": chat_id,
        "tool_result": tool_result,
        "card": card,
        "publish": {
            "ok": True,
            "dry_run": False,
            "mode": "interactive",
            "delivery_mode": "chat",
            "reply_to": message_id,
            "chat_id": chat_id,
            "text": "",
            "card": card,
            "suppressed": False,
        },
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

    normalized_text = _strip_leading_mention_command(text)
    command_name, _argument = _slash_command(normalized_text)
    if command_name in {"settings", "group_settings"} or _looks_like_group_settings_query(normalized_text):
        return route_gateway_group_settings(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            allowlist_chat_ids=allowlist_chat_ids,
            db_path=db_path,
        )
    if command_name in {"recall", "memory_search", "search_memory"}:
        return route_gateway_memory_search(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            query=_argument,
            db_path=db_path,
        )
    if command_name in {"prefetch", "memory_prefetch", "prefetch_memory"}:
        return route_gateway_memory_prefetch(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            task=_argument,
            db_path=db_path,
        )
    if command_name in {"review", "inbox", "review_inbox"}:
        return route_gateway_review_inbox(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            view=_argument,
            db_path=db_path,
        )
    if command_name in {"enable_memory", "memory_on", "enable_group_memory"}:
        return route_gateway_group_policy(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="enable",
            db_path=db_path,
        )
    if command_name in {"disable_memory", "memory_off", "disable_group_memory"}:
        return route_gateway_group_policy(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="disable",
            db_path=db_path,
        )

    if _is_explicit_remember(normalized_text):
        return route_remember_message(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            db_path=db_path,
        )

    if chat_type == "group" and not bot_mentioned:
        bot_mentioned = _infer_bot_mentioned_from_lark_message(message_id)

    if chat_type != "group" or bot_mentioned:
        return route_gateway_natural_interaction(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            chat_type=chat_type,
            bot_mentioned=bot_mentioned,
            allowlist_chat_ids=allowlist_chat_ids,
            db_path=db_path,
        )

    group_policy: dict[str, Any] | None = None
    if not _chat_allowed(chat_id, allowlist_chat_ids):
        group_policy = _gateway_group_policy_for_chat(
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            db_path=db_path,
        )
    if not (_chat_allowed(chat_id, allowlist_chat_ids) or group_policy_allows_passive_memory(group_policy)):
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


def route_gateway_group_settings(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    allowlist_chat_ids: Sequence[str] | None = None,
    db_path: str | None = None,
    scope: str = SCOPE,
) -> dict[str, Any]:
    load_local_env_files(root=ROOT, override=True)
    tenant_id, organization_id, visibility = _feishu_identity()
    with _open_conn(db_path) as conn:
        policy = ensure_group_policy(
            conn,
            chat_id=chat_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            scope=scope,
            visibility_policy=visibility,
            actor_id=sender_open_id,
        )
        chat_allowed = _chat_allowed(chat_id, allowlist_chat_ids) or group_policy_allows_passive_memory(policy)
        tool_result = _group_settings_result(
            scope=scope,
            visibility_policy=visibility,
            group_policy=policy,
            chat_allowed=chat_allowed,
        )
    reply = _format_group_settings(tool_result)
    card = build_group_settings_card(tool_result)
    return {
        "ok": True,
        "tool": "copilot.group_settings",
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": "openclaw_gateway_group_settings",
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": card,
        "disposition": "reply",
        "message_disposition": {
            "memory_path": "group_settings",
            "candidate_path": "read_only",
            "reason_code": "openclaw_gateway_group_settings",
        },
        "publish": _reply_publish_result(message_id=message_id, chat_id=chat_id, text=reply, card=card),
        "input_text": text,
    }


def route_gateway_group_policy(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    action: str,
    db_path: str | None = None,
    scope: str = SCOPE,
) -> dict[str, Any]:
    load_local_env_files(root=ROOT, override=True)
    tenant_id, organization_id, visibility = _feishu_identity()
    tool_name = "copilot.group_enable_memory" if action == "enable" else "copilot.group_disable_memory"
    actor_roles = _roles_for_sender(sender_open_id)
    with _open_conn(db_path) as conn:
        policy = get_group_policy(conn, chat_id=chat_id, tenant_id=tenant_id, organization_id=organization_id)
        if not _can_manage_group_policy(sender_open_id, actor_roles, policy):
            with conn:
                record_group_policy_denied(
                    conn,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    organization_id=organization_id,
                    scope=scope,
                    actor_id=sender_open_id or "unknown_feishu_actor",
                    actor_roles=actor_roles,
                    action=tool_name,
                    source_entrypoint="openclaw_gateway_live",
                )
            tool_result = {
                "ok": False,
                "tool": tool_name,
                "status": "permission_denied",
                "error": {"code": "permission_denied", "reason_code": "reviewer_or_admin_required"},
                "group_policy": _safe_group_policy_payload(policy),
                "production_boundary": "受控 OpenClaw gateway staging；不是生产长期运行。",
            }
        else:
            with conn:
                if action == "enable":
                    updated_policy = enable_group_memory(
                        conn,
                        chat_id=chat_id,
                        tenant_id=tenant_id,
                        organization_id=organization_id,
                        scope=scope,
                        visibility_policy=visibility,
                        actor_id=sender_open_id or "unknown_feishu_actor",
                        actor_roles=actor_roles,
                        reviewer_open_ids=_csv_env("COPILOT_FEISHU_REVIEWER_OPEN_IDS"),
                        source_entrypoint="openclaw_gateway_live",
                    )
                    status = "enabled"
                else:
                    updated_policy = disable_group_memory(
                        conn,
                        chat_id=chat_id,
                        tenant_id=tenant_id,
                        organization_id=organization_id,
                        scope=scope,
                        visibility_policy=visibility,
                        actor_id=sender_open_id or "unknown_feishu_actor",
                        actor_roles=actor_roles,
                        source_entrypoint="openclaw_gateway_live",
                    )
                    status = "disabled"
            tool_result = {
                "ok": True,
                "tool": tool_name,
                "status": status,
                "mode": "write",
                "group_policy": _safe_group_policy_payload(updated_policy),
                "production_boundary": "受控 OpenClaw gateway staging；不是生产长期运行。",
            }
    reply = _format_group_policy_result(tool_result)
    card = build_card_from_text(reply)
    return {
        "ok": True,
        "tool": tool_name,
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": f"openclaw_gateway_group_memory_{action}",
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": card,
        "disposition": "reply",
        "message_disposition": {
            "memory_path": "group_policy_write",
            "candidate_path": str(tool_result.get("status") or "unknown"),
            "reason_code": f"openclaw_gateway_group_memory_{action}",
        },
        "publish": _reply_publish_result(message_id=message_id, chat_id=chat_id, text=reply, card=card),
        "input_text": text,
    }


def route_gateway_memory_search(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    query: str,
    db_path: str | None = None,
    scope: str = SCOPE,
    routing_reason: str = "openclaw_gateway_memory_search",
    intent_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compact_answer = intent_resolution is not None and routing_reason == "openclaw_gateway_natural_search"
    normalized_query = (query or text).strip()
    if normalized_query.startswith("/"):
        _, normalized_query = _slash_command(normalized_query)
    normalized_query = normalized_query or "当前项目记忆"
    payload = {
        "query": normalized_query,
        "scope": scope,
        "top_k": 1 if compact_answer else 3,
        "filters": {"status": "active"},
        "current_context": _gateway_current_context(
            text=text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="memory.search",
            intent="search",
            thread_topic=normalized_query,
            scope=scope,
        ),
    }
    service = CopilotService(db_path=db_path)
    tool_result = handle_tool_request("memory.search", payload, service=service)
    if compact_answer:
        _enrich_search_evidence_context(tool_result, fallback_chat_id=chat_id)
    reply = _format_memory_search_result(tool_result)
    if tool_result.get("ok", True):
        card = build_compact_search_answer_card(tool_result) if compact_answer else build_search_result_card(tool_result)
    else:
        card = build_card_from_text(reply)
    result = {
        "ok": bool(tool_result.get("ok", True)),
        "tool": "memory.search",
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": routing_reason,
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": card,
        "disposition": "reply",
        "message_disposition": {
            "memory_path": "first_class_memory_search",
            "candidate_path": "read_only",
            "reason_code": routing_reason,
        },
        "publish": _reply_publish_result(message_id=message_id, chat_id=chat_id, text=reply, card=card),
        "input_text": text,
    }
    if intent_resolution is not None:
        result["intent_resolution"] = intent_resolution
    return result


def route_gateway_memory_prefetch(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    task: str,
    db_path: str | None = None,
    scope: str = SCOPE,
    routing_reason: str = "openclaw_gateway_memory_prefetch",
    intent_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_task = (task or text).strip()
    if normalized_task.startswith("/"):
        _, normalized_task = _slash_command(normalized_task)
    normalized_task = normalized_task or "当前任务"
    payload = {
        "task": normalized_task,
        "scope": scope,
        "top_k": 5,
        "current_context": _gateway_current_context(
            text=text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="memory.prefetch",
            intent="prefetch",
            thread_topic=normalized_task,
            scope=scope,
            metadata={"current_message": normalized_task},
        ),
    }
    service = CopilotService(db_path=db_path)
    tool_result = handle_tool_request("memory.prefetch", payload, service=service)
    reply = _format_memory_prefetch_result(tool_result)
    card = build_prefetch_context_card(tool_result) if tool_result.get("ok", True) else build_card_from_text(reply)
    result = {
        "ok": bool(tool_result.get("ok", True)),
        "tool": "memory.prefetch",
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": routing_reason,
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": card,
        "disposition": "reply",
        "message_disposition": {
            "memory_path": "first_class_memory_prefetch",
            "candidate_path": "read_only",
            "reason_code": routing_reason,
        },
        "publish": _reply_publish_result(message_id=message_id, chat_id=chat_id, text=reply, card=card),
        "input_text": text,
    }
    if intent_resolution is not None:
        result["intent_resolution"] = intent_resolution
    return result


def route_gateway_natural_interaction(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    chat_type: str,
    bot_mentioned: bool,
    allowlist_chat_ids: Sequence[str] | None = None,
    db_path: str | None = None,
    scope: str = SCOPE,
) -> dict[str, Any]:
    """Route visible natural-language Feishu chat into a Copilot tool reply.

    This path is intentionally separate from the passive group-message probe:
    if a user mentions the bot or sends a DM, silence is a product bug. The
    optional LLM classifier can refine the intent, but deterministic fallback
    still returns a visible reply when the LLM is unavailable or slow.
    """

    normalized_text = _strip_leading_mention_command(text)
    if not normalized_text:
        return _ignored_result(message_id=message_id, chat_id=chat_id, reason_code="empty_natural_language")

    intent = _classify_natural_language_intent(normalized_text)
    resolution = {
        "mode": "natural_language",
        "intent": intent["intent"],
        "resolver": intent["resolver"],
        "latency_class": "natural_language_slow_path",
        "visible_reply_required": True,
        "llm_error": intent.get("error"),
        "bot_mentioned": bot_mentioned,
        "chat_type": chat_type,
    }
    resolved_query = str(intent.get("query") or normalized_text).strip() or normalized_text

    if intent["intent"] == "group_settings":
        result = route_gateway_group_settings(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            allowlist_chat_ids=allowlist_chat_ids,
            db_path=db_path,
            scope=scope,
        )
        result["routing_reason"] = "openclaw_gateway_natural_group_settings"
        result["intent_resolution"] = resolution
        result["message_disposition"]["reason_code"] = "openclaw_gateway_natural_group_settings"
        return result
    if intent["intent"] == "enable_memory":
        result = route_gateway_group_policy(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="enable",
            db_path=db_path,
            scope=scope,
        )
        result["routing_reason"] = "openclaw_gateway_natural_group_memory_enable"
        result["intent_resolution"] = resolution
        result["message_disposition"]["reason_code"] = "openclaw_gateway_natural_group_memory_enable"
        return result
    if intent["intent"] == "disable_memory":
        result = route_gateway_group_policy(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="disable",
            db_path=db_path,
            scope=scope,
        )
        result["routing_reason"] = "openclaw_gateway_natural_group_memory_disable"
        result["intent_resolution"] = resolution
        result["message_disposition"]["reason_code"] = "openclaw_gateway_natural_group_memory_disable"
        return result
    if intent["intent"] == "review_inbox":
        result = route_gateway_review_inbox(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            view=resolved_query,
            db_path=db_path,
            scope=scope,
        )
        result["routing_reason"] = "openclaw_gateway_natural_review_inbox"
        result["intent_resolution"] = resolution
        result["message_disposition"]["reason_code"] = "openclaw_gateway_natural_review_inbox"
        return result
    if intent["intent"] == "prefetch":
        return route_gateway_memory_prefetch(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            task=resolved_query,
            db_path=db_path,
            scope=scope,
            routing_reason="openclaw_gateway_natural_prefetch",
            intent_resolution=resolution,
        )
    if intent["intent"] == "create_candidate":
        result = route_remember_message(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            db_path=db_path,
        )
        result["routing_reason"] = "openclaw_gateway_natural_candidate"
        result["source_entrypoint"] = "openclaw_gateway_live"
        result["intent_resolution"] = resolution
        result["message_disposition"] = {
            "memory_path": "candidate_review",
            "candidate_path": str(result.get("tool_result", {}).get("action") or "attempted"),
            "reason_code": "openclaw_gateway_natural_candidate",
        }
        return result

    return route_gateway_memory_search(
        text=normalized_text,
        message_id=message_id,
        chat_id=chat_id,
        sender_open_id=sender_open_id,
        query=resolved_query,
        db_path=db_path,
        scope=scope,
        routing_reason="openclaw_gateway_natural_search",
        intent_resolution=resolution,
    )


def route_gateway_review_inbox(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    view: str,
    db_path: str | None = None,
    scope: str = SCOPE,
) -> dict[str, Any]:
    normalized_view = _review_inbox_view(view)
    payload = {
        "scope": scope,
        "view": normalized_view,
        "limit": REVIEW_INBOX_DELIVERY_LIMIT,
        "current_context": _gateway_current_context(
            text=text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            action="memory.review_inbox",
            intent="review_inbox",
            thread_topic=normalized_view,
            scope=scope,
        ),
    }
    service = CopilotService(db_path=db_path)
    tool_result = handle_tool_request("memory.review_inbox", payload, service=service)
    reply = _format_review_inbox_result(tool_result)
    card = build_review_inbox_card(tool_result) if tool_result.get("ok", True) else build_card_from_text(reply)
    event = FeishuMessageEvent(
        message_id=message_id,
        chat_id=chat_id,
        chat_type="group",
        sender_id=sender_open_id,
        sender_type="user",
        message_type="text",
        text=text,
        create_time=0,
        raw={},
        ignore_reason=None,
        bot_mentioned=True,
    )
    publisher = DryRunPublisher() if _review_delivery_dry_run() else LarkCliPublisher(load_feishu_config())
    publish = publisher.publish(event, reply, card)
    return {
        "ok": bool(tool_result.get("ok", True)),
        "tool": "memory.review_inbox",
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": "openclaw_gateway_review_inbox",
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": card,
        "disposition": "private_review_dm",
        "message_disposition": {
            "memory_path": "review_inbox",
            "candidate_path": "read_only",
            "reason_code": "openclaw_gateway_review_inbox",
        },
        "publish": publish,
        "input_text": text,
    }


def _review_inbox_view(argument: str) -> str:
    value = (argument or "").strip().lower()
    aliases = {
        "": "mine",
        "mine": "mine",
        "我": "mine",
        "我的": "mine",
        "all": "all",
        "全部": "all",
        "conflict": "conflicts",
        "conflicts": "conflicts",
        "冲突": "conflicts",
        "high_risk": "high_risk",
        "risk": "high_risk",
        "高风险": "high_risk",
    }
    return aliases.get(value, "mine")


def _review_delivery_dry_run() -> bool:
    value = os.environ.get("OPENCLAW_FEISHU_REVIEW_DRY_RUN", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _gateway_group_policy_for_chat(
    *,
    chat_id: str,
    sender_open_id: str,
    db_path: str | None,
    scope: str = SCOPE,
) -> dict[str, Any] | None:
    load_local_env_files(root=ROOT, override=True)
    tenant_id, organization_id, visibility = _feishu_identity()
    with _open_conn(db_path) as conn:
        return ensure_group_policy(
            conn,
            chat_id=chat_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            scope=scope,
            visibility_policy=visibility,
            actor_id=sender_open_id or "unknown_feishu_actor",
        )


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


def _classify_natural_language_intent(text: str) -> dict[str, Any]:
    llm_result = _classify_natural_language_intent_with_llm(text)
    if llm_result:
        return llm_result
    return _classify_natural_language_intent_fallback(text, resolver="deterministic_fallback")


def _classify_natural_language_intent_with_llm(text: str) -> dict[str, Any] | None:
    if not _truthy_env("OPENCLAW_FEISHU_NL_INTENT_LLM_ENABLED"):
        return None
    endpoint = (
        os.environ.get("OPENCLAW_FEISHU_NL_INTENT_ENDPOINT")
        or os.environ.get("LLM_ENDPOINT")
        or os.environ.get("OPENAI_BASE_URL")
    )
    model = os.environ.get("OPENCLAW_FEISHU_NL_INTENT_MODEL") or os.environ.get("LLM_MODEL")
    api_key = (
        os.environ.get("OPENCLAW_FEISHU_NL_INTENT_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not endpoint or not model or not api_key:
        return None
    try:
        timeout = float(os.environ.get("OPENCLAW_FEISHU_NL_INTENT_TIMEOUT_SECONDS", "3"))
    except ValueError:
        timeout = 3.0
    try:
        response = httpx.post(
            _chat_completions_url(endpoint),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是 Feishu Memory Copilot 的意图分类器。"
                            "只输出 JSON：{\"intent\":\"search|create_candidate|prefetch|review_inbox|"
                            "group_settings|enable_memory|disable_memory\",\"query\":\"...\"}。"
                            "问题、历史决策查询、当前有效值查询默认 search；明确要记住/约定/决定且不是问题时 create_candidate；"
                            "任务前、checklist、计划类请求 prefetch。"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        content = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            content = str(message.get("content") or "").strip()
        parsed = _json_from_llm_content(content)
        intent = str(parsed.get("intent") or "").strip()
        if intent not in {
            "search",
            "create_candidate",
            "prefetch",
            "review_inbox",
            "group_settings",
            "enable_memory",
            "disable_memory",
        }:
            return _classify_natural_language_intent_fallback(
                text,
                resolver="deterministic_fallback_after_llm_invalid",
                error=f"invalid_llm_intent:{intent or 'empty'}",
            )
        query = str(parsed.get("query") or text).strip() or text
        return {"intent": intent, "query": query, "resolver": "llm"}
    except Exception as exc:
        return _classify_natural_language_intent_fallback(
            text,
            resolver="deterministic_fallback_after_llm_error",
            error=exc.__class__.__name__,
        )


def _classify_natural_language_intent_fallback(
    text: str,
    *,
    resolver: str,
    error: str | None = None,
) -> dict[str, Any]:
    normalized = text.strip()
    if _looks_like_group_settings_query(normalized):
        intent = "group_settings"
    elif _looks_like_natural_group_enable(normalized):
        intent = "enable_memory"
    elif _looks_like_natural_group_disable(normalized):
        intent = "disable_memory"
    elif _looks_like_review_inbox(normalized):
        intent = "review_inbox"
    elif _looks_like_prefetch(normalized):
        intent = "prefetch"
    elif _has_enterprise_memory_signal(normalized):
        intent = "create_candidate"
    else:
        intent = "search"
    result = {"intent": intent, "query": normalized, "resolver": resolver}
    if error:
        result["error"] = error
    return result


def _looks_like_review_inbox(text: str) -> bool:
    return any(signal in text for signal in REVIEW_INBOX_SIGNALS)


def _looks_like_prefetch(text: str) -> bool:
    lowered = text.lower()
    return any(signal in text or signal in lowered for signal in PREFETCH_SIGNALS)


def _looks_like_natural_group_enable(text: str) -> bool:
    return any(signal in text for signal in NATURAL_ENABLE_SIGNALS)


def _looks_like_natural_group_disable(text: str) -> bool:
    return any(signal in text for signal in NATURAL_DISABLE_SIGNALS)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _chat_completions_url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _json_from_llm_content(content: str) -> dict[str, Any]:
    if not content:
        return {}
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _infer_bot_mentioned_from_lark_message(message_id: str) -> bool:
    if not message_id.startswith("om_x"):
        return False
    lark_cli = os.environ.get("LARK_CLI") or os.environ.get("COPILOT_LARK_CLI") or "lark-cli"
    command = [
        lark_cli,
        "im",
        "+messages-mget",
        "--message-ids",
        message_id,
        "--format",
        "json",
        "--as",
        os.environ.get("OPENCLAW_FEISHU_MENTION_LOOKUP_AS", "bot"),
    ]
    profile = os.environ.get("OPENCLAW_FEISHU_MENTION_LOOKUP_PROFILE") or os.environ.get("LARK_PROFILE")
    if profile:
        command[1:1] = ["--profile", profile]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=3)
    except Exception:
        return False
    if completed.returncode != 0:
        return False
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False
    data = payload.get("data") if isinstance(payload, dict) else {}
    messages = data.get("messages") if isinstance(data, dict) else []
    if not isinstance(messages, list) or not messages:
        return False
    message = messages[0] if isinstance(messages[0], dict) else {}
    content = str(message.get("content") or "")
    if content.startswith("@Feishu Memory Engine bot") or content.startswith("@Feishu Memory Copilot"):
        return True
    mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
    for mention in mentions:
        if not isinstance(mention, dict):
            continue
        name = str(mention.get("name") or "")
        mention_id = str(mention.get("id") or "")
        if "Feishu Memory" in name or mention_id in _known_bot_ids():
            return True
    return False


def _enrich_search_evidence_context(result: dict[str, Any], *, fallback_chat_id: str) -> None:
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    if not rows:
        return
    first = rows[0] if isinstance(rows[0], dict) else {}
    evidence = first.get("evidence") if isinstance(first.get("evidence"), list) else []
    if not evidence or not isinstance(evidence[0], dict):
        return
    item = evidence[0]
    source_type = str(item.get("source_type") or "")
    source_id = str(item.get("source_id") or "")
    should_use_current_chat = source_type == "feishu_message" or source_id.startswith("om_x")
    source_chat_id = str(item.get("source_chat_id") or (fallback_chat_id if should_use_current_chat else "") or "")
    if source_chat_id and not item.get("source_chat_name"):
        item["source_chat_name"] = _lookup_lark_chat_name(source_chat_id) or source_chat_id
    if item.get("created_at"):
        item["created_at"] = _display_time(str(item["created_at"]))
    elif source_id.startswith("om_x"):
        message_time = _lookup_lark_message_time(source_id)
        if message_time:
            item["created_at"] = message_time


def _lookup_lark_chat_name(chat_id: str) -> str | None:
    if not chat_id.startswith("oc_"):
        return None
    lark_cli = os.environ.get("LARK_CLI") or os.environ.get("COPILOT_LARK_CLI") or "lark-cli"
    command = [
        lark_cli,
        "im",
        "chats",
        "get",
        "--params",
        json.dumps({"chat_id": chat_id}, ensure_ascii=False),
        "--format",
        "json",
        "--as",
        os.environ.get("OPENCLAW_FEISHU_EVIDENCE_LOOKUP_AS", "bot"),
    ]
    profile = os.environ.get("OPENCLAW_FEISHU_EVIDENCE_LOOKUP_PROFILE") or os.environ.get("LARK_PROFILE")
    if profile:
        command[1:1] = ["--profile", profile]
    payload = _run_lark_json(command)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("name", "chat_name"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _lookup_lark_message_time(message_id: str) -> str | None:
    lark_cli = os.environ.get("LARK_CLI") or os.environ.get("COPILOT_LARK_CLI") or "lark-cli"
    command = [
        lark_cli,
        "im",
        "+messages-mget",
        "--message-ids",
        message_id,
        "--format",
        "json",
        "--as",
        os.environ.get("OPENCLAW_FEISHU_EVIDENCE_LOOKUP_AS", "bot"),
    ]
    profile = os.environ.get("OPENCLAW_FEISHU_EVIDENCE_LOOKUP_PROFILE") or os.environ.get("LARK_PROFILE")
    if profile:
        command[1:1] = ["--profile", profile]
    payload = _run_lark_json(command)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    messages = data.get("messages") if isinstance(data.get("messages"), list) else []
    message = messages[0] if messages and isinstance(messages[0], dict) else {}
    value = message.get("create_time")
    return _display_time(str(value)) if value else None


def _run_lark_json(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=3)
    except Exception:
        return {}
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _display_time(value: str) -> str:
    normalized = value.strip()
    if "T" in normalized:
        return normalized.replace("T", " ")[:16]
    return normalized


def _known_bot_ids() -> set[str]:
    values = _csv_env("OPENCLAW_FEISHU_BOT_IDS")
    values.extend(["cli_a961a18dbebadcd1", "ou_09341ad938b76680c036bfea8dc2c62c"])
    return {value for value in values if value}


def _looks_like_question(text: str) -> bool:
    lowered = text.lower()
    return any(marker in text or marker in lowered for marker in QUESTION_MARKERS)


def _looks_like_group_settings_query(text: str) -> bool:
    normalized = text.strip().strip("。.!！?？")
    return normalized in GROUP_SETTINGS_NATURAL_QUERIES


def _gateway_current_context(
    *,
    text: str,
    message_id: str,
    chat_id: str,
    sender_open_id: str,
    action: str,
    intent: str,
    thread_topic: str,
    scope: str = SCOPE,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant_id, organization_id, visibility = _feishu_identity()
    safe_action = action.replace(".", "_")
    merged_metadata = {
        "message_id": message_id,
        "chat_type": "group",
        "entrypoint": "openclaw_gateway_live",
    }
    if metadata:
        merged_metadata.update(metadata)
    return {
        "session_id": f"feishu:{chat_id}",
        "chat_id": chat_id,
        "scope": scope,
        "user_id": sender_open_id,
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "visibility_policy": visibility,
        "intent": intent,
        "thread_topic": thread_topic[:80],
        "allowed_scopes": [scope],
        "metadata": merged_metadata,
        "permission": {
            "request_id": f"req_openclaw_{_short_id(message_id)}_{safe_action}",
            "trace_id": f"trace_openclaw_{_short_id(message_id)}",
            "actor": {
                "open_id": sender_open_id or "unknown_feishu_actor",
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "roles": _roles_for_sender(sender_open_id),
            },
            "source_context": {
                "entrypoint": "openclaw_gateway_live",
                "workspace_id": scope,
                "chat_id": chat_id,
            },
            "requested_action": action,
            "requested_visibility": visibility,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }


def _short_id(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum())[-8:] or "unknown"


def _format_memory_search_result(result: dict[str, Any]) -> str:
    bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    lines = [
        "Memory Copilot 已执行记忆检索。",
        f"工具：{bridge.get('tool') or 'fmc_memory_search'}",
        f"状态：{'ok' if result.get('ok', True) else 'failed'}",
        f"命中数：{len(rows)}",
    ]
    for item in rows[:3]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('subject') or '-'}：{item.get('current_value') or '-'}")
    lines.extend(_bridge_trace_lines(bridge))
    return "\n".join(lines)


def _format_memory_prefetch_result(result: dict[str, Any]) -> str:
    bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
    pack = result.get("context_pack") if isinstance(result.get("context_pack"), dict) else {}
    memories = pack.get("relevant_memories") if isinstance(pack.get("relevant_memories"), list) else []
    lines = [
        "Memory Copilot 已生成任务前上下文包。",
        f"工具：{bridge.get('tool') or 'fmc_memory_prefetch'}",
        f"状态：{'ok' if result.get('ok', True) else 'failed'}",
        f"相关记忆：{len(memories)}",
    ]
    summary = pack.get("summary")
    if summary:
        lines.append(f"摘要：{summary}")
    lines.extend(_bridge_trace_lines(bridge))
    return "\n".join(lines)


def _format_review_inbox_result(result: dict[str, Any]) -> str:
    items = result.get("items") if isinstance(result.get("items"), list) else []
    if not result.get("ok", True):
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        return "\n".join(
            [
                "Memory Copilot 审核收件箱不可用。",
                f"原因：{error.get('reason_code') or error.get('code') or 'unknown'}",
            ]
        )
    return "\n".join(
        [
            "Memory Copilot 已生成审核收件箱。",
            "投递方式：私聊审核卡片",
            f"待审核数量：{len(items)}",
            f"view：{result.get('view') or 'mine'}",
        ]
    )


def _bridge_trace_lines(bridge: dict[str, Any]) -> list[str]:
    decision = bridge.get("permission_decision") if isinstance(bridge.get("permission_decision"), dict) else {}
    return [
        f"request_id：{bridge.get('request_id') or '-'}",
        f"trace_id：{bridge.get('trace_id') or '-'}",
        f"permission：{decision.get('decision') or '-'}",
    ]


def _slash_command(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, ""
    body = stripped[1:]
    if not body:
        return None, ""
    parts = body.split(maxsplit=1)
    return parts[0].strip().lower(), parts[1].strip() if len(parts) > 1 else ""


def _strip_leading_mention_command(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("@"):
        return stripped
    slash_index = stripped.find("/")
    if slash_index <= 0:
        known_prefixes = (
            "@Feishu Memory Engine bot",
            "@Feishu Memory Copilot",
            "@Memory Copilot",
        )
        for prefix in known_prefixes:
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip()
        bot_index = stripped.lower().find(" bot ")
        if 0 < bot_index < 80:
            return stripped[bot_index + len(" bot ") :].strip()
        return stripped.split(maxsplit=1)[1].strip() if len(stripped.split(maxsplit=1)) > 1 else ""
    return stripped[slash_index:].strip()


def _open_conn(db_path: str | None):
    conn = connect(Path(db_path) if db_path else None)
    init_db(conn)
    return conn


def _feishu_identity() -> tuple[str, str, str]:
    return (
        os.environ.get("COPILOT_FEISHU_TENANT_ID", TENANT_ID),
        os.environ.get("COPILOT_FEISHU_ORGANIZATION_ID", ORGANIZATION_ID),
        os.environ.get("COPILOT_FEISHU_VISIBILITY", VISIBILITY),
    )


def _roles_for_sender(sender_open_id: str) -> list[str]:
    base = _csv_env("COPILOT_FEISHU_DEFAULT_ROLES") or ["member"]
    reviewers = _csv_env("COPILOT_FEISHU_REVIEWER_OPEN_IDS")
    admins = _csv_env("COPILOT_FEISHU_GROUP_POLICY_ADMIN_OPEN_IDS")
    if "*" in admins or (sender_open_id and sender_open_id in admins):
        return sorted(set(base + ["admin", "reviewer"]))
    if "*" in reviewers or (sender_open_id and sender_open_id in reviewers):
        return sorted(set(base + ["reviewer"]))
    return base


def _can_manage_group_policy(
    sender_open_id: str,
    actor_roles: list[str],
    group_policy: dict[str, Any] | None,
) -> bool:
    if "admin" in actor_roles or "reviewer" in actor_roles:
        return True
    admins = _csv_env("COPILOT_FEISHU_GROUP_POLICY_ADMIN_OPEN_IDS")
    if "*" in admins or (sender_open_id and sender_open_id in admins):
        return True
    owners = group_policy.get("owner_open_ids") if isinstance(group_policy, dict) else []
    return bool(sender_open_id and sender_open_id in owners and group_policy_allows_passive_memory(group_policy))


def _group_settings_result(
    *,
    scope: str,
    visibility_policy: str,
    group_policy: dict[str, Any] | None,
    chat_allowed: bool,
) -> dict[str, Any]:
    allowlist_summary = _allowlist_summary()
    safe_policy = _safe_group_policy_payload(group_policy)
    return {
        "ok": True,
        "tool": "copilot.group_settings",
        "mode": "read_only",
        "scope": scope,
        "visibility_policy": visibility_policy,
        "chat_policy": safe_policy,
        "chat_status": safe_policy.get("status") or "pending_onboarding",
        "passive_memory_enabled": bool(safe_policy.get("passive_memory_enabled")),
        "chat_allowed": chat_allowed,
        "allowlist_summary": allowlist_summary,
        "silent_screening": _group_silent_screening_status(allowlist_summary, group_policy),
        "review_delivery": "DM/private 定向给相关 owner/reviewer；本卡不修改实际投递路由。",
        "auto_confirm_policy": (
            "低风险、低重要性、无冲突可自动确认；项目进展重要、重要角色发言、敏感/高风险或冲突必须人工审核。"
        ),
        "onboarding_policy": (
            "新群默认 pending_onboarding，只登记群节点和群策略；执行 /enable_memory 后才对非 @ 消息做静默候选筛选。"
        ),
        "production_boundary": "受控 OpenClaw gateway staging；不是生产长期运行。",
    }


def _format_group_settings(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "群级记忆设置（只读）。",
            f"当前群状态：{result.get('chat_status')}；passive_memory_enabled={str(bool(result.get('passive_memory_enabled'))).lower()}",
            f"allowlist 群静默筛选：{result.get('silent_screening')}；allowlist={result.get('allowlist_summary')}",
            f"审核投递方式：{result.get('review_delivery')}",
            f"auto-confirm policy：{result.get('auto_confirm_policy')}",
            f"onboarding policy：{result.get('onboarding_policy')}",
            f"scope：{result.get('scope')}",
            f"visibility：{result.get('visibility_policy')}",
            f"运行边界：{result.get('production_boundary')}",
            "写入动作：/enable_memory 启用当前群静默筛选；/disable_memory 关闭。写入需要 reviewer/admin 授权。",
        ]
    )


def _format_group_policy_result(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return "\n".join(
            [
                "群级记忆设置未修改。",
                "原因：需要 reviewer/admin 权限。",
                f"状态：{result.get('status')}",
                f"运行边界：{result.get('production_boundary')}",
            ]
        )
    policy = result.get("group_policy") if isinstance(result.get("group_policy"), dict) else {}
    title = "已启用当前群静默候选筛选。" if result.get("status") == "enabled" else "已关闭当前群静默候选筛选。"
    next_step = (
        "后续非 @ 群消息会先做企业记忆信号筛选。"
        if result.get("status") == "enabled"
        else "后续非 @ 群消息不会进入 passive candidate screening。"
    )
    return "\n".join(
        [
            title,
            f"群策略状态：{policy.get('status')}",
            f"passive_memory_enabled：{str(bool(policy.get('passive_memory_enabled'))).lower()}",
            f"scope：{policy.get('scope')}",
            f"visibility：{policy.get('visibility_policy')}",
            f"下一步：{next_step}",
            f"运行边界：{result.get('production_boundary')}",
        ]
    )


def _safe_group_policy_payload(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not policy:
        return {}
    return {
        "id": policy.get("id"),
        "tenant_id": policy.get("tenant_id"),
        "organization_id": policy.get("organization_id"),
        "chat_id_redacted": _redacted_id(str(policy.get("chat_id") or "")),
        "scope": policy.get("scope"),
        "visibility_policy": policy.get("visibility_policy"),
        "status": policy.get("status"),
        "passive_memory_enabled": bool(policy.get("passive_memory_enabled")),
        "reviewer_count": len(policy.get("reviewer_open_ids") or []),
        "owner_count": len(policy.get("owner_open_ids") or []),
        "created_at": policy.get("created_at"),
        "updated_at": policy.get("updated_at"),
        "last_enabled_at": policy.get("last_enabled_at"),
        "disabled_at": policy.get("disabled_at"),
    }


def _group_silent_screening_status(allowlist_summary: str, group_policy: dict[str, Any] | None = None) -> str:
    if group_policy_allows_passive_memory(group_policy):
        return "enabled_for_current_group_policy"
    if allowlist_summary.startswith("configured"):
        return "enabled_for_allowlist_groups"
    if allowlist_summary == "wildcard (*)":
        return "enabled_for_wildcard_groups"
    return "unrestricted_without_allowlist"


def _allowlist_summary() -> str:
    values = _env_allowlist()
    if not values:
        return "(none)"
    if "*" in values:
        return "wildcard (*)"
    return f"configured ({len(values)})"


def _csv_env(name: str) -> list[str]:
    return _csv_values(os.environ.get(name, ""))


def _redacted_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _reply_publish_result(
    *,
    message_id: str,
    chat_id: str,
    text: str,
    card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": False,
        "mode": "interactive" if card else "reply",
        "delivery_mode": "chat",
        "reply_to": message_id,
        "chat_id": chat_id,
        "text": "" if card else text,
        "card": card,
        "fallback_used": False,
        "suppressed": False,
    }


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
