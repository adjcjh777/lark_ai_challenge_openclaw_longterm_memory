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
from memory_engine.copilot.group_policies import (  # noqa: E402
    disable_group_memory,
    enable_group_memory,
    ensure_group_policy,
    get_group_policy,
    group_policy_allows_passive_memory,
    record_group_policy_denied,
)
from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.feishu_cards import build_candidate_review_card, build_card_from_text, build_group_settings_card  # noqa: E402
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
    command_name, _argument = _slash_command(normalized_text)
    if command_name in {"settings", "group_settings"}:
        return route_gateway_group_settings(
            text=normalized_text,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            allowlist_chat_ids=allowlist_chat_ids,
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
    return {
        "ok": True,
        "tool": "copilot.group_settings",
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": "openclaw_gateway_group_settings",
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": build_group_settings_card(tool_result),
        "disposition": "reply",
        "message_disposition": {
            "memory_path": "group_settings",
            "candidate_path": "read_only",
            "reason_code": "openclaw_gateway_group_settings",
        },
        "publish": _reply_publish_result(message_id=message_id, chat_id=chat_id, text=reply),
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
    return {
        "ok": True,
        "tool": tool_name,
        "message_id": message_id,
        "chat_id": chat_id,
        "routing_reason": f"openclaw_gateway_group_memory_{action}",
        "source_entrypoint": "openclaw_gateway_live",
        "tool_result": tool_result,
        "card": build_card_from_text(reply),
        "disposition": "reply",
        "message_disposition": {
            "memory_path": "group_policy_write",
            "candidate_path": str(tool_result.get("status") or "unknown"),
            "reason_code": f"openclaw_gateway_group_memory_{action}",
        },
        "publish": _reply_publish_result(message_id=message_id, chat_id=chat_id, text=reply),
        "input_text": text,
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


def _slash_command(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, ""
    body = stripped[1:]
    if not body:
        return None, ""
    parts = body.split(maxsplit=1)
    return parts[0].strip().lower(), parts[1].strip() if len(parts) > 1 else ""


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
            "低风险、低重要性、无冲突可自动确认；"
            "项目进展重要、重要角色发言、敏感/高风险或冲突必须人工审核。"
        ),
        "onboarding_policy": (
            "新群默认 pending_onboarding，只登记群节点和群策略；"
            "执行 /enable_memory 后才对非 @ 消息做静默候选筛选。"
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


def _reply_publish_result(*, message_id: str, chat_id: str, text: str) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": False,
        "mode": "reply",
        "reply_to": message_id,
        "chat_id": chat_id,
        "text": text,
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
