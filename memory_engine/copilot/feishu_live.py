from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from memory_engine.db import connect, db_path_from_env, init_db
from memory_engine.feishu_cards import build_card_from_text
from memory_engine.feishu_config import FeishuConfig, load_feishu_config
from memory_engine.feishu_events import FeishuMessageEvent, message_event_from_payload
from memory_engine.feishu_publisher import DryRunPublisher, LarkCliPublisher
from memory_engine.feishu_runtime import FeishuRunLogger
from memory_engine.feishu_listener_guard import assert_single_feishu_listener
from memory_engine.repository import MemoryRepository

from .permissions import DEFAULT_ORGANIZATION_ID, DEFAULT_TENANT_ID
from .service import CopilotService
from .tools import handle_tool_request


DEFAULT_SCOPE = "project:feishu_ai_challenge"
SOURCE_TYPE = "feishu_message"
ENTRYPOINT = "feishu_test_group"
EVENT_TYPES = "im.message.receive_v1,card.action.trigger"

MEMORY_SIGNALS = (
    "记住",
    "请记一下",
    "以后",
    "统一",
    "规则",
    "决定",
    "约定",
    "约束",
    "风险",
    "负责人",
    "截止",
    "不对",
    "改成",
)
PREFETCH_SIGNALS = ("准备", "checklist", "清单", "计划", "执行前", "任务前", "上线前")


@dataclass(frozen=True)
class CopilotFeishuInvocation:
    tool_name: str
    payload: dict[str, Any]
    user_text: str
    reason: str


def listen(*, db_path: str | Path | None = None, dry_run: bool = False) -> None:
    active_listeners = assert_single_feishu_listener("copilot-lark-cli")
    config = load_feishu_config()
    conn = connect(db_path)
    init_db(conn)
    publisher = DryRunPublisher() if dry_run else LarkCliPublisher(config)
    command = _event_subscribe_command(config)
    run_logger = FeishuRunLogger(config.log_dir)
    run_logger.write(
        "copilot_live_listen_start",
        dry_run=dry_run,
        db_path=str(db_path or db_path_from_env()),
        command=_redact_command(command),
        profile=config.lark_profile,
        bot_mode=config.bot_mode,
        card_mode=config.card_mode,
        entrypoint=ENTRYPOINT,
        scope=_scope(config),
        listener_preflight=[process.__dict__ for process in active_listeners],
    )
    print(f"Memory Copilot live listener log: {run_logger.path}", file=sys.stderr, flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            run_logger.write("copilot_live_event_received", raw_line=line)
            try:
                payload = json.loads(line)
                event = message_event_from_payload(payload)
                if event is None:
                    result = {"ok": True, "ignored": True, "reason": "not a supported Feishu event"}
                else:
                    result = handle_copilot_message_event(conn, event, publisher, config, dry_run=dry_run)
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "raw_line": line}
                run_logger.write("copilot_live_event_error", error=str(exc), raw_line=line)
            run_logger.write(
                "copilot_live_event_result",
                ok=result.get("ok"),
                ignored=result.get("ignored", False),
                tool=result.get("tool"),
                message_id=result.get("message_id"),
                publish=_publish_log_summary(result.get("publish")),
                result=result,
            )
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        run_logger.write("copilot_live_listen_stop", reason="keyboard_interrupt")
        process.terminate()
    finally:
        conn.close()
        if process.poll() is None:
            process.terminate()
        run_logger.write("copilot_live_listen_exit", returncode=process.poll())


def handle_copilot_message_event(
    conn,
    event: FeishuMessageEvent,
    publisher,
    config: FeishuConfig,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    scope = _scope(config)
    if not _chat_allowed(event.chat_id):
        return {
            "ok": True,
            "ignored": True,
            "reason": "chat not in COPILOT_FEISHU_ALLOWED_CHAT_IDS",
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "entrypoint": ENTRYPOINT,
            "scope": scope,
        }

    if event.ignore_reason == "bot self message":
        return {
            "ok": True,
            "ignored": True,
            "reason": event.ignore_reason,
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "entrypoint": ENTRYPOINT,
        }

    if event.ignore_reason is not None:
        reply = _reply(
            "Memory Copilot 没有处理这条消息。",
            [
                "类型：消息处理",
                "入口：Feishu live sandbox",
                f"状态：ignored",
                f"原因：{event.ignore_reason}",
                "处理结果：未调用 CopilotService。",
            ],
        )
        publish_result = _publish(publisher, event, reply, config)
        return {
            "ok": publish_result.get("ok", False),
            "ignored": True,
            "reason": event.ignore_reason,
            "message_id": event.message_id,
            "scope": scope,
            "publish": publish_result,
        }

    invocation = invocation_from_event(event, scope=scope)
    if invocation.tool_name == "copilot.help":
        reply = _format_help()
        publish_result = _publish(publisher, event, reply, config)
        return _event_result(event, scope, invocation, {"ok": True, "tool": "copilot.help"}, publish_result)

    if invocation.tool_name == "copilot.health":
        reply = _format_health(scope=scope, db_path=str(db_path_from_env()), dry_run=dry_run, config=config)
        publish_result = _publish(publisher, event, reply, config)
        return _event_result(event, scope, invocation, {"ok": True, "tool": "copilot.health"}, publish_result)

    repo = MemoryRepository(conn)
    if invocation.tool_name == "memory.create_candidate" and repo.has_source_event(SOURCE_TYPE, event.message_id):
        reply = _reply(
            "Memory Copilot 已经处理过这条飞书消息。",
            [
                "类型：重复投递",
                "入口：Feishu live sandbox",
                "状态：duplicate",
                "处理结果：没有重复创建 candidate。",
            ],
        )
        publish_result = _publish(publisher, event, reply, config)
        return _event_result(event, scope, invocation, {"ok": True, "duplicate": True}, publish_result)

    service = CopilotService(repository=repo)
    tool_result = handle_tool_request(invocation.tool_name, invocation.payload, service=service)
    reply = format_tool_result(invocation, tool_result)
    publish_result = _publish(publisher, event, reply, config)
    return _event_result(event, scope, invocation, tool_result, publish_result)


def invocation_from_event(event: FeishuMessageEvent, *, scope: str) -> CopilotFeishuInvocation:
    text = _normalize_user_text(event.text)
    lowered = text.lower()
    if lowered in {"/help", "/copilot_help", "help", "帮助"}:
        return CopilotFeishuInvocation("copilot.help", {}, text, "help")
    if lowered in {"/health", "/copilot_health", "health", "状态"}:
        return CopilotFeishuInvocation("copilot.health", {}, text, "health")

    command_name, argument = _slash_command(text)
    if command_name in {"search", "recall"}:
        return _search_invocation(event, scope, argument or text, reason="explicit_search")
    if command_name in {"remember", "candidate", "create_candidate"}:
        return _candidate_invocation(event, scope, argument, reason="explicit_candidate")
    if command_name == "confirm":
        return _review_invocation(event, scope, "memory.confirm", argument, reason="explicit_confirm")
    if command_name == "reject":
        return _review_invocation(event, scope, "memory.reject", argument, reason="explicit_reject")
    if command_name in {"versions", "explain"}:
        return _versions_invocation(event, scope, argument, reason="explicit_versions")
    if command_name == "prefetch":
        return _prefetch_invocation(event, scope, argument or text, reason="explicit_prefetch")
    if command_name in {"heartbeat", "review_due"}:
        return _heartbeat_invocation(event, scope, reason="explicit_heartbeat")

    if text.startswith("确认 "):
        return _review_invocation(event, scope, "memory.confirm", text.removeprefix("确认 ").strip(), reason="natural_confirm")
    if text.startswith("拒绝 "):
        return _review_invocation(event, scope, "memory.reject", text.removeprefix("拒绝 ").strip(), reason="natural_reject")
    if _looks_like_candidate(text):
        return _candidate_invocation(event, scope, text, reason="natural_candidate")
    if _looks_like_prefetch(text):
        return _prefetch_invocation(event, scope, text, reason="natural_prefetch")
    return _search_invocation(event, scope, text, reason="default_search")


def format_tool_result(invocation: CopilotFeishuInvocation, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return _format_error(invocation, result)
    if invocation.tool_name == "memory.search":
        return _format_search(result)
    if invocation.tool_name == "memory.create_candidate":
        return _format_candidate(result)
    if invocation.tool_name == "memory.confirm":
        return _format_review(result, action="确认")
    if invocation.tool_name == "memory.reject":
        return _format_review(result, action="拒绝")
    if invocation.tool_name == "memory.explain_versions":
        return _format_versions(result)
    if invocation.tool_name == "memory.prefetch":
        return _format_prefetch(result)
    if invocation.tool_name == "heartbeat.review_due":
        return _format_heartbeat(result)
    return _reply(
        "Memory Copilot 已执行工具。",
        [
            f"工具：{invocation.tool_name}",
            f"状态：{result.get('status') or 'ok'}",
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ],
    )


def _search_invocation(event: FeishuMessageEvent, scope: str, query: str, *, reason: str) -> CopilotFeishuInvocation:
    tool = "memory.search"
    context = _current_context(event, scope, tool, intent="search", thread_topic=query)
    return CopilotFeishuInvocation(
        tool,
        {
            "query": query,
            "scope": scope,
            "top_k": 3,
            "filters": {"status": "active"},
            "current_context": context,
        },
        query,
        reason,
    )


def _candidate_invocation(event: FeishuMessageEvent, scope: str, text: str, *, reason: str) -> CopilotFeishuInvocation:
    tool = "memory.create_candidate"
    context = _current_context(event, scope, tool, intent="create_candidate", thread_topic=_subject_hint(text))
    return CopilotFeishuInvocation(
        tool,
        {
            "text": text,
            "scope": scope,
            "source": {
                "source_type": SOURCE_TYPE,
                "source_id": event.message_id,
                "actor_id": event.sender_id or "unknown_feishu_actor",
                "created_at": _event_time_iso(event),
                "quote": text,
                "source_chat_id": event.chat_id,
            },
            "current_context": context,
            "auto_confirm": False,
        },
        text,
        reason,
    )


def _review_invocation(
    event: FeishuMessageEvent,
    scope: str,
    tool: str,
    candidate_id: str,
    *,
    reason: str,
) -> CopilotFeishuInvocation:
    context = _current_context(event, scope, tool, intent="review_candidate", thread_topic=candidate_id)
    return CopilotFeishuInvocation(
        tool,
        {
            "candidate_id": candidate_id,
            "scope": scope,
            "actor_id": event.sender_id or "unknown_feishu_actor",
            "reason": "Feishu live sandbox reviewer action",
            "current_context": context,
        },
        candidate_id,
        reason,
    )


def _versions_invocation(event: FeishuMessageEvent, scope: str, memory_id: str, *, reason: str) -> CopilotFeishuInvocation:
    tool = "memory.explain_versions"
    context = _current_context(event, scope, tool, intent="explain_versions", thread_topic=memory_id)
    return CopilotFeishuInvocation(
        tool,
        {
            "memory_id": memory_id,
            "scope": scope,
            "include_archived": False,
            "current_context": context,
        },
        memory_id,
        reason,
    )


def _prefetch_invocation(event: FeishuMessageEvent, scope: str, task: str, *, reason: str) -> CopilotFeishuInvocation:
    tool = "memory.prefetch"
    context = _current_context(event, scope, tool, intent="prefetch", thread_topic=_subject_hint(task))
    context["metadata"] = {"current_message": task}
    return CopilotFeishuInvocation(
        tool,
        {
            "task": task,
            "scope": scope,
            "current_context": context,
            "top_k": 5,
        },
        task,
        reason,
    )


def _heartbeat_invocation(event: FeishuMessageEvent, scope: str, *, reason: str) -> CopilotFeishuInvocation:
    tool = "heartbeat.review_due"
    context = _current_context(event, scope, tool, intent="heartbeat", thread_topic="review due")
    return CopilotFeishuInvocation(
        tool,
        {
            "scope": scope,
            "current_context": context,
            "limit": 5,
        },
        event.text,
        reason,
    )


def _current_context(
    event: FeishuMessageEvent,
    scope: str,
    action: str,
    *,
    intent: str,
    thread_topic: str,
) -> dict[str, Any]:
    request_suffix = re.sub(r"[^A-Za-z0-9_]+", "_", action)
    return {
        "session_id": f"feishu:{event.chat_id}",
        "chat_id": event.chat_id,
        "scope": scope,
        "user_id": event.sender_id,
        "intent": intent,
        "thread_topic": thread_topic[:80],
        "allowed_scopes": [scope],
        "metadata": {
            "message_id": event.message_id,
            "chat_type": event.chat_type,
            "entrypoint": ENTRYPOINT,
        },
        "permission": {
            "request_id": f"req_feishu_{_short_id(event.message_id)}_{request_suffix}",
            "trace_id": f"trace_feishu_{_short_id(event.message_id)}",
            "actor": {
                "open_id": event.sender_id or "unknown_feishu_actor",
                "tenant_id": _mapped_env_value("COPILOT_FEISHU_ACTOR_TENANT_MAP", event.sender_id)
                or os.environ.get("COPILOT_FEISHU_TENANT_ID", DEFAULT_TENANT_ID),
                "organization_id": _mapped_env_value("COPILOT_FEISHU_ACTOR_ORGANIZATION_MAP", event.sender_id)
                or os.environ.get("COPILOT_FEISHU_ORGANIZATION_ID", DEFAULT_ORGANIZATION_ID),
                "roles": _roles_for_sender(event.sender_id),
            },
            "source_context": {
                "entrypoint": ENTRYPOINT,
                "workspace_id": scope,
                "chat_id": event.chat_id,
            },
            "requested_action": action,
            "requested_visibility": os.environ.get("COPILOT_FEISHU_VISIBILITY", "team"),
            "timestamp": _event_time_iso(event),
        },
    }


def _roles_for_sender(sender_id: str) -> list[str]:
    base = _csv_env("COPILOT_FEISHU_DEFAULT_ROLES") or ["member"]
    reviewers = _csv_env("COPILOT_FEISHU_REVIEWER_OPEN_IDS")
    if "*" in reviewers or (sender_id and sender_id in reviewers):
        return sorted(set(base + ["reviewer"]))
    return base


def _mapped_env_value(name: str, key: str) -> str | None:
    if not key:
        return None
    for item in _csv_env(name):
        mapped_key, separator, mapped_value = item.partition("=")
        if separator and mapped_key.strip() == key and mapped_value.strip():
            return mapped_value.strip()
    return None


def _format_search(result: dict[str, Any]) -> str:
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    if not rows:
        return _reply(
            "Memory Copilot 没找到当前有效记忆。",
            [
                "工具：memory.search",
                f"查询：{result.get('query') or '-'}",
                "状态：not_found",
                "处理结果：默认只搜索 active memory，没有返回 candidate/superseded/raw events。",
                f"trace：{_trace_summary(result)}",
                f"request_id：{_bridge_field(result, 'request_id')}",
                f"trace_id：{_bridge_field(result, 'trace_id')}",
            ],
        )
    lines = [
        "工具：memory.search",
        f"查询：{result.get('query') or '-'}",
        "状态：ok",
        "处理结果：只返回 active 当前结论。",
    ]
    for index, item in enumerate(rows[:3], start=1):
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        quote = "-"
        if evidence and isinstance(evidence[0], dict):
            quote = str(evidence[0].get("quote") or "-")
        lines.extend(
            [
                f"{index}. {item.get('subject') or '-'}",
                f"   结论：{item.get('current_value') or '-'}",
                f"   状态：{item.get('status') or '-'} / v{item.get('version') or '-'} / {item.get('layer') or '-'}",
                f"   证据：{_clip(quote)}",
                f"   命中：{', '.join(item.get('matched_via') or []) or '-'}",
                f"   memory_id：{item.get('memory_id') or '-'}",
            ]
        )
    lines.extend(
        [
            f"trace：{_trace_summary(result)}",
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return _reply("Memory Copilot 找到当前有效记忆。", lines)


def _format_candidate(result: dict[str, Any]) -> str:
    if result.get("action") == "ignored":
        return _reply(
            "Memory Copilot 没有把这条消息写入候选记忆。",
            [
                "工具：memory.create_candidate",
                "状态：not_candidate",
                f"理由：{result.get('reason') or '-'}",
                f"risk_flags：{', '.join(result.get('risk_flags') or []) or '-'}",
                f"request_id：{_bridge_field(result, 'request_id')}",
                f"trace_id：{_bridge_field(result, 'trace_id')}",
            ],
        )
    candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else {}
    candidate_id = result.get("candidate_id") or candidate.get("candidate_id") or result.get("memory_id")
    lines = [
        "工具：memory.create_candidate",
        f"状态：{candidate.get('status') or result.get('status') or 'candidate'}",
        "处理结果：已进入待确认队列，不会自动成为 active memory。",
        f"主题：{candidate.get('subject') or '-'}",
        f"候选结论：{candidate.get('current_value') or '-'}",
        f"candidate_id：{candidate_id or '-'}",
        f"推荐动作：/confirm {candidate_id} 或 /reject {candidate_id}" if candidate_id else "推荐动作：等待人工复核",
        f"risk_flags：{', '.join(result.get('risk_flags') or []) or '-'}",
        f"recommended_action：{result.get('recommended_action') or '-'}",
    ]
    if result.get("auto_confirm_ignored"):
        lines.append("说明：真实飞书来源不会自动 active，auto_confirm 已被忽略。")
    lines.extend(
        [
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return _reply("Memory Copilot 已创建待确认记忆。", lines)


def _format_review(result: dict[str, Any], *, action: str) -> str:
    memory = result.get("memory") if isinstance(result.get("memory"), dict) else {}
    return _reply(
        f"Memory Copilot 已{action}候选记忆。",
        [
            f"工具：memory.{'confirm' if action == '确认' else 'reject'}",
            f"状态：{memory.get('status') or result.get('status') or '-'}",
            f"处理结果：{result.get('action') or '-'}",
            f"结论：{memory.get('current_value') or '-'}",
            f"memory_id：{result.get('memory_id') or '-'}",
            f"candidate_id：{result.get('candidate_id') or '-'}",
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ],
    )


def _format_versions(result: dict[str, Any]) -> str:
    versions = result.get("versions") if isinstance(result.get("versions"), list) else []
    active = result.get("active_version") if isinstance(result.get("active_version"), dict) else {}
    lines = [
        "工具：memory.explain_versions",
        f"主题：{result.get('subject') or '-'}",
        f"当前结论：{active.get('value') or '-'}",
        f"状态：{result.get('status') or '-'}",
        f"版本数量：{len(versions)}",
    ]
    for item in versions[:6]:
        if isinstance(item, dict):
            lines.append(f"- v{item.get('version_no')} [{item.get('status')}] {item.get('value')}")
    lines.extend(
        [
            f"解释：{result.get('explanation') or '-'}",
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return _reply("Memory Copilot 已返回版本链。", lines)


def _format_prefetch(result: dict[str, Any]) -> str:
    pack = result.get("context_pack") if isinstance(result.get("context_pack"), dict) else {}
    memories = pack.get("relevant_memories") if isinstance(pack.get("relevant_memories"), list) else []
    lines = [
        "工具：memory.prefetch",
        f"任务：{result.get('task') or '-'}",
        f"摘要：{pack.get('summary') or '-'}",
        f"raw_events_included：{str(pack.get('raw_events_included')).lower()}",
        f"stale_superseded_filtered：{str(pack.get('stale_superseded_filtered')).lower()}",
    ]
    for item in memories[:3]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('subject')}: {item.get('current_value')}")
    lines.extend(
        [
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return _reply("Memory Copilot 已生成任务前上下文包。", lines)


def _format_heartbeat(result: dict[str, Any]) -> str:
    reminders = result.get("reminders") if isinstance(result.get("reminders"), list) else []
    lines = [
        "工具：heartbeat.review_due",
        f"状态：{result.get('status') or result.get('ok')}",
        "处理结果：只生成 reminder candidate，不真实推送给其他群。",
        f"候选数量：{len(reminders)}",
    ]
    for item in reminders[:3]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('title') or item.get('memory_id')}: {item.get('message') or '-'}")
    lines.extend(
        [
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return _reply("Memory Copilot 已生成提醒候选。", lines)


def _format_error(invocation: CopilotFeishuInvocation, result: dict[str, Any]) -> str:
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    return _reply(
        "Memory Copilot 安全拒绝了这次操作。",
        [
            f"工具：{invocation.tool_name}",
            f"状态：{error.get('code') or 'error'}",
            f"原因：{details.get('reason_code') or error.get('message') or '-'}",
            "处理结果：未展示未授权内容，未绕过 CopilotService。",
            f"request_id：{details.get('request_id') or _bridge_field(result, 'request_id')}",
            f"trace_id：{details.get('trace_id') or _bridge_field(result, 'trace_id')}",
        ],
    )


def _format_help() -> str:
    return _reply(
        "这里接入的是新的 Memory Copilot live sandbox，不是旧 Memory Engine handler。",
        [
            "入口：Feishu test group -> lark-cli event -> CopilotService -> OpenClaw tool contract",
            "默认搜索：@Bot 直接问历史决策，例如：生产部署 region 是什么？",
            "创建候选：@Bot /remember 规则：生产部署必须加 --canary",
            "人工确认：@Bot /confirm <candidate_id>",
            "拒绝候选：@Bot /reject <candidate_id>",
            "版本解释：@Bot /versions <memory_id>",
            "任务预取：@Bot /prefetch 生成今天上线 checklist",
            "健康检查：@Bot /health",
            "边界：真实飞书消息进入 candidate/review 流程；不会自动 active，也不是生产全量 workspace ingestion。",
        ],
    )


def _format_health(*, scope: str, db_path: str, dry_run: bool, config: FeishuConfig) -> str:
    return _reply(
        "Memory Copilot live sandbox 当前可用。",
        [
            "类型：健康检查",
            "入口：Feishu live sandbox",
            "状态：ok",
            "运行层：CopilotService / handle_tool_request",
            f"scope：{scope}",
            f"数据库：{db_path}",
            f"dry_run：{str(dry_run).lower()}",
            f"回复模式：{config.bot_mode}",
            f"卡片模式：{config.card_mode}",
            f"默认角色：{', '.join(_csv_env('COPILOT_FEISHU_DEFAULT_ROLES') or ['member'])}",
            f"群聊 allowlist：{_env_list_summary('COPILOT_FEISHU_ALLOWED_CHAT_IDS')}",
            f"reviewer 配置：{_env_list_summary('COPILOT_FEISHU_REVIEWER_OPEN_IDS')}",
        ],
    )


def _publish(publisher, event: FeishuMessageEvent, reply: str, config: FeishuConfig) -> dict[str, Any]:
    card = build_card_from_text(reply) if config.card_mode == "interactive" else None
    return publisher.publish(event, reply, card)


def _event_result(
    event: FeishuMessageEvent,
    scope: str,
    invocation: CopilotFeishuInvocation,
    tool_result: dict[str, Any],
    publish_result: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "ok": bool(publish_result.get("ok", False)) and bool(tool_result.get("ok", True)),
        "message_id": event.message_id,
        "scope": scope,
        "entrypoint": ENTRYPOINT,
        "tool": invocation.tool_name,
        "routing_reason": invocation.reason,
        "tool_result": tool_result,
        "publish": publish_result,
    }
    if tool_result.get("duplicate"):
        result["duplicate"] = True
    return result


def _scope(config: FeishuConfig) -> str:
    return (
        os.environ.get("COPILOT_FEISHU_SCOPE")
        or config.default_scope
        or os.environ.get("MEMORY_DEFAULT_SCOPE")
        or DEFAULT_SCOPE
    )


def _chat_allowed(chat_id: str) -> bool:
    allowed = _csv_env("COPILOT_FEISHU_ALLOWED_CHAT_IDS")
    return not allowed or chat_id in allowed


def _event_subscribe_command(config: FeishuConfig) -> list[str]:
    command = [config.lark_cli]
    if config.lark_profile:
        command.extend(["--profile", config.lark_profile])
    command.extend(["event", "+subscribe", "--as", config.lark_as, "--event-types", EVENT_TYPES, "--quiet"])
    return command


def _slash_command(text: str) -> tuple[str | None, str]:
    if not text.startswith("/"):
        return None, text
    head, _, tail = text.partition(" ")
    return head[1:].strip().lower(), tail.strip()


def _normalize_user_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _looks_like_candidate(text: str) -> bool:
    return any(signal in text for signal in MEMORY_SIGNALS)


def _looks_like_prefetch(text: str) -> bool:
    lowered = text.lower()
    return any(signal in lowered or signal in text for signal in PREFETCH_SIGNALS)


def _subject_hint(text: str) -> str:
    return text[:80]


def _event_time_iso(event: FeishuMessageEvent) -> str:
    if event.create_time:
        timestamp = event.create_time / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _short_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return cleaned[-24:] if len(cleaned) > 24 else cleaned


def _bridge_field(result: dict[str, Any], field: str) -> str:
    bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
    value = bridge.get(field)
    return str(value) if value else "-"


def _trace_summary(result: dict[str, Any]) -> str:
    trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
    layers = trace.get("layers") if isinstance(trace.get("layers"), list) else []
    return f"backend={trace.get('backend') or '-'} layers={','.join(layers) or '-'} reason={trace.get('final_reason') or '-'}"


def _reply(title: str, lines: list[str]) -> str:
    return "\n\n".join([title, *lines])


def _clip(value: str, limit: int = 140) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _csv_env(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_list_summary(name: str) -> str:
    values = _csv_env(name)
    if not values:
        return "(none)"
    if "*" in values:
        return "wildcard (*)"
    return f"configured ({len(values)})"


def _publish_log_summary(publish: Any) -> dict[str, Any] | None:
    if not isinstance(publish, dict):
        return None
    return {
        "ok": publish.get("ok"),
        "mode": publish.get("mode"),
        "fallback_used": publish.get("fallback_used"),
        "fallback_suppressed": publish.get("fallback_suppressed"),
        "latency_ms": publish.get("latency_ms"),
    }


def _redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            redacted.append("[REDACTED]")
            skip_next = False
            continue
        redacted.append(item)
        if item in {"--app-secret", "--secret", "--token"}:
            skip_next = True
    return redacted
