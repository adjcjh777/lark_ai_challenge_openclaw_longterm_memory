from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_engine.db import connect, db_path_from_env, init_db
from memory_engine.feishu_cards import (
    build_candidate_review_card,
    build_card_from_text,
    build_prefetch_context_card,
    build_search_result_card,
    build_version_chain_card,
)
from memory_engine.feishu_config import FeishuConfig, load_feishu_config
from memory_engine.feishu_events import FeishuMessageEvent, message_event_from_payload
from memory_engine.feishu_listener_guard import assert_single_feishu_listener
from memory_engine.feishu_publisher import DryRunPublisher, LarkCliPublisher
from memory_engine.feishu_runtime import FeishuRunLogger
from memory_engine.models import parse_scope
from memory_engine.repository import MemoryRepository

from .admin import DEFAULT_ADMIN_HOST, DEFAULT_ADMIN_PORT, start_embedded_admin
from .graph_context import register_feishu_chat_node, register_feishu_message_context
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
    "负责人",
    "截止",
    "上线窗口",
    "回滚负责人",
)
PREFETCH_SIGNALS = ("准备", "checklist", "清单", "计划", "执行前", "任务前", "上线前")


@dataclass(frozen=True)
class CopilotFeishuInvocation:
    tool_name: str
    payload: dict[str, Any]
    user_text: str
    reason: str


def listen(
    *,
    db_path: str | Path | None = None,
    dry_run: bool = False,
    admin_enabled: bool | None = None,
    admin_host: str | None = None,
    admin_port: int | None = None,
) -> None:
    active_listeners = assert_single_feishu_listener("copilot-lark-cli")
    config = load_feishu_config()
    resolved_db_path = str(db_path or db_path_from_env())
    conn = connect(db_path)
    init_db(conn)
    admin_runtime = start_embedded_admin(
        host=admin_host or os.environ.get("COPILOT_ADMIN_HOST", DEFAULT_ADMIN_HOST),
        port=admin_port if admin_port is not None else int(os.environ.get("COPILOT_ADMIN_PORT", DEFAULT_ADMIN_PORT)),
        db_path=resolved_db_path,
        enabled=_admin_enabled(admin_enabled),
    )
    publisher = DryRunPublisher() if dry_run else LarkCliPublisher(config)
    command = _event_subscribe_command(config)
    run_logger = FeishuRunLogger(config.log_dir)
    run_logger.write(
        "copilot_live_listen_start",
        dry_run=dry_run,
        db_path=resolved_db_path,
        dashboard=admin_runtime.to_log_payload(),
        command=_redact_command(command),
        profile=config.lark_profile,
        bot_mode=config.bot_mode,
        card_mode=config.card_mode,
        entrypoint=ENTRYPOINT,
        scope=_scope(config),
        listener_preflight=[process.__dict__ for process in active_listeners],
    )
    print(f"Memory Copilot live listener log: {run_logger.path}", file=sys.stderr, flush=True)
    if admin_runtime.url:
        print(f"Memory Copilot dashboard: {admin_runtime.url}", file=sys.stderr, flush=True)
    elif admin_runtime.reason != "disabled":
        print(f"Memory Copilot dashboard not started: {admin_runtime.reason}", file=sys.stderr, flush=True)
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
        admin_runtime.stop()
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
    chat_allowed = _chat_allowed(event.chat_id)
    tenant_id, organization_id, visibility = _feishu_identity()
    with conn:
        graph_node = register_feishu_chat_node(
            conn,
            event,
            scope=scope,
            tenant_id=tenant_id,
            organization_id=organization_id,
            visibility_policy=visibility,
            entrypoint=ENTRYPOINT,
            allowed=chat_allowed,
        ).to_dict()

    if not chat_allowed:
        return {
            "ok": True,
            "ignored": True,
            "reason": "chat not in COPILOT_FEISHU_ALLOWED_CHAT_IDS",
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "entrypoint": ENTRYPOINT,
            "scope": scope,
            "graph_node": graph_node,
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
                "状态：ignored",
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

    with conn:
        message_graph = register_feishu_message_context(
            conn,
            event,
            scope=scope,
            tenant_id=tenant_id,
            organization_id=organization_id,
            visibility_policy=visibility,
            entrypoint=ENTRYPOINT,
            chat_node_id=graph_node.get("node_id"),
        ).to_dict()

    interaction_mode = _interaction_mode(event)
    invocation = _initial_invocation(event, scope=scope, interaction_mode=interaction_mode)
    if invocation.tool_name == "copilot.help":
        reply = _format_help()
        publish_result = _publish(publisher, event, reply, config)
        return _event_result(
            event,
            scope,
            invocation,
            {"ok": True, "tool": "copilot.help"},
            publish_result,
            graph_node,
            message_graph,
        )

    if invocation.tool_name == "copilot.health":
        reply = _format_health(scope=scope, db_path=str(db_path_from_env()), dry_run=dry_run, config=config)
        publish_result = _publish(publisher, event, reply, config)
        return _event_result(
            event,
            scope,
            invocation,
            {"ok": True, "tool": "copilot.health"},
            publish_result,
            graph_node,
            message_graph,
        )

    repo = MemoryRepository(conn)
    if invocation.tool_name == "memory.create_candidate" and repo.has_source_event(SOURCE_TYPE, event.message_id):
        publish_result = _publish_duplicate_result(
            publisher,
            event,
            config,
            interaction_mode=interaction_mode,
        )
        return _event_result(
            event,
            scope,
            invocation,
            {"ok": True, "duplicate": True},
            publish_result,
            graph_node,
            message_graph,
        )

    service = CopilotService(repository=repo)
    invocation = _resolve_contextual_invocation(invocation, event, repo, scope)
    tool_result = handle_tool_request(invocation.tool_name, invocation.payload, service=service)
    publish_result = _publish_tool_result(
        publisher,
        event,
        config,
        invocation=invocation,
        tool_result=tool_result,
        interaction_mode=interaction_mode,
    )
    return _event_result(event, scope, invocation, tool_result, publish_result, graph_node, message_graph)


def _admin_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    value = os.environ.get("COPILOT_ADMIN_ENABLED") or os.environ.get("FEISHU_MEMORY_COPILOT_ADMIN_ENABLED")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


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
    if command_name == "needs_evidence":
        return _review_invocation(event, scope, "memory.needs_evidence", argument, reason="explicit_needs_evidence")
    if command_name == "expire":
        return _review_invocation(event, scope, "memory.expire", argument, reason="explicit_expire")
    if command_name in {"versions", "explain"}:
        return _versions_invocation(event, scope, argument, reason="explicit_versions")
    if command_name == "prefetch":
        return _prefetch_invocation(event, scope, argument or text, reason="explicit_prefetch")
    if command_name in {"heartbeat", "review_due"}:
        return _heartbeat_invocation(event, scope, reason="explicit_heartbeat")
    if command_name == "task":
        return _task_invocation(event, scope, argument, reason="explicit_task")
    if command_name == "meeting":
        return _meeting_invocation(event, scope, argument, reason="explicit_meeting")
    if command_name == "bitable":
        return _bitable_invocation(event, scope, argument, reason="explicit_bitable")

    if _looks_like_confirm(text):
        target = _natural_review_target(text, "确认")
        return _review_invocation(
            event, scope, "memory.confirm", target, reason="natural_confirm"
        )
    if _looks_like_reject(text):
        target = _natural_review_target(text, "拒绝")
        return _review_invocation(
            event, scope, "memory.reject", target, reason="natural_reject"
        )
    if _looks_like_versions_question(text):
        return _versions_invocation(event, scope, "", reason="natural_versions")
    if _looks_like_candidate(text):
        return _candidate_invocation(event, scope, text, reason="natural_candidate")
    if _looks_like_prefetch(text):
        return _prefetch_invocation(event, scope, text, reason="natural_prefetch")
    return _search_invocation(event, scope, text, reason="default_search")


def format_tool_result(invocation: CopilotFeishuInvocation, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return _format_error(invocation, result)
    if invocation.tool_name == "memory.search":
        return _format_search(result, routing_reason=invocation.reason)
    if invocation.tool_name == "memory.create_candidate":
        return _format_candidate(result)
    if invocation.tool_name == "memory.confirm":
        return _format_review(result, action="确认")
    if invocation.tool_name == "memory.reject":
        return _format_review(result, action="拒绝")
    if invocation.tool_name == "memory.needs_evidence":
        return _format_review(result, action="要求补证据")
    if invocation.tool_name == "memory.expire":
        return _format_review(result, action="标记过期")
    if invocation.tool_name == "memory.explain_versions":
        return _format_versions(result)
    if invocation.tool_name == "memory.prefetch":
        return _format_prefetch(result)
    if invocation.tool_name == "heartbeat.review_due":
        return _format_heartbeat(result)
    if invocation.tool_name == "feishu.fetch_task":
        return _format_feishu_source(result, "飞书任务")
    if invocation.tool_name == "feishu.fetch_meeting":
        return _format_feishu_source(result, "飞书会议")
    if invocation.tool_name == "feishu.fetch_bitable":
        return _format_feishu_source(result, "Bitable 记录")
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


def _passive_candidate_invocation(event: FeishuMessageEvent, *, scope: str) -> CopilotFeishuInvocation:
    return _candidate_invocation(event, scope, event.text, reason="passive_candidate_probe")


def _interaction_mode(event: FeishuMessageEvent) -> str:
    if event.chat_type == "group" and not event.bot_mentioned:
        return "passive_candidate_probe"
    return "active_interaction"


def _initial_invocation(
    event: FeishuMessageEvent,
    *,
    scope: str,
    interaction_mode: str,
) -> CopilotFeishuInvocation:
    if interaction_mode == "passive_candidate_probe":
        return _passive_candidate_invocation(event, scope=scope)
    return invocation_from_event(event, scope=scope)


def _publish_duplicate_result(
    publisher,
    event: FeishuMessageEvent,
    config: FeishuConfig,
    *,
    interaction_mode: str,
) -> dict[str, Any]:
    if interaction_mode == "passive_candidate_probe":
        return _silent_publish_result(event)
    return _publish(
        publisher,
        event,
        _reply(
            "Memory Copilot 已经处理过这条飞书消息。",
            [
                "类型：重复投递",
                "入口：Feishu live sandbox",
                "状态：duplicate",
                "处理结果：没有重复创建 candidate。",
            ],
        ),
        config,
    )


def _publish_tool_result(
    publisher,
    event: FeishuMessageEvent,
    config: FeishuConfig,
    *,
    invocation: CopilotFeishuInvocation,
    tool_result: dict[str, Any],
    interaction_mode: str,
) -> dict[str, Any]:
    if interaction_mode == "passive_candidate_probe":
        return _silent_publish_result(event)
    reply = format_tool_result(invocation, tool_result)
    return _publish(
        publisher,
        event,
        reply,
        config,
        invocation=invocation,
        tool_result=tool_result,
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


def _versions_invocation(
    event: FeishuMessageEvent, scope: str, memory_id: str, *, reason: str
) -> CopilotFeishuInvocation:
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


def _task_invocation(event: FeishuMessageEvent, scope: str, task_id: str, *, reason: str) -> CopilotFeishuInvocation:
    """处理 /task <task_id> 命令，拉取飞书任务进入 candidate pipeline。"""
    tool = "feishu.fetch_task"
    context = _current_context(event, scope, "memory.create_candidate", intent="fetch_task", thread_topic=task_id)
    _extend_permission_source_context(context, task_id=task_id)
    return CopilotFeishuInvocation(
        tool,
        {
            "task_id": task_id,
            "scope": scope,
            "current_context": context,
        },
        task_id,
        reason,
    )


def _meeting_invocation(
    event: FeishuMessageEvent, scope: str, minute_token: str, *, reason: str
) -> CopilotFeishuInvocation:
    """处理 /meeting <minute_token> 命令，拉取飞书妙记进入 candidate pipeline。"""
    tool = "feishu.fetch_meeting"
    context = _current_context(event, scope, "memory.create_candidate", intent="fetch_meeting", thread_topic=minute_token)
    _extend_permission_source_context(context, meeting_id=minute_token)
    return CopilotFeishuInvocation(
        tool,
        {
            "minute_token": minute_token,
            "scope": scope,
            "current_context": context,
        },
        minute_token,
        reason,
    )


def _bitable_invocation(
    event: FeishuMessageEvent, scope: str, argument: str, *, reason: str
) -> CopilotFeishuInvocation:
    """处理 /bitable <app_token> <table_id> <record_id> 命令，拉取 Bitable 记录进入 candidate pipeline。"""
    tool = "feishu.fetch_bitable"
    parts = argument.split()
    if len(parts) < 3:
        # 参数不足，返回一个错误提示
        context = _current_context(event, scope, tool, intent="fetch_bitable", thread_topic="error")
        return CopilotFeishuInvocation(
            tool,
            {
                "error": "参数不足，需要: /bitable <app_token> <table_id> <record_id>",
                "scope": scope,
                "current_context": context,
            },
            argument,
            reason,
        )

    app_token, table_id, record_id = parts[0], parts[1], parts[2]
    context = _current_context(event, scope, "memory.create_candidate", intent="fetch_bitable", thread_topic=record_id)
    _extend_permission_source_context(
        context,
        bitable_app_token=app_token,
        bitable_table_id=table_id,
        bitable_record_id=record_id,
    )
    return CopilotFeishuInvocation(
        tool,
        {
            "app_token": app_token,
            "table_id": table_id,
            "record_id": record_id,
            "scope": scope,
            "current_context": context,
        },
        argument,
        reason,
    )


def _resolve_contextual_invocation(
    invocation: CopilotFeishuInvocation,
    event: FeishuMessageEvent,
    repo: MemoryRepository,
    scope: str,
) -> CopilotFeishuInvocation:
    review_tools = {
        "memory.confirm",
        "memory.reject",
        "memory.needs_evidence",
        "memory.expire",
    }
    if invocation.tool_name in review_tools and not invocation.payload.get("candidate_id"):
        candidate = _recent_candidate_id(repo, event, scope)
        if candidate:
            payload = dict(invocation.payload)
            payload["candidate_id"] = candidate["candidate_id"]
            context = dict(payload.get("current_context") or {})
            _grant_owner_role_if_applicable(repo, context, event.sender_id, candidate["candidate_id"])
            context["thread_topic"] = str(candidate.get("subject") or candidate["candidate_id"])[:80]
            context["metadata"] = {
                **dict(context.get("metadata") or {}),
                "resolved_from": "recent_candidate",
                "resolved_candidate_id": candidate["candidate_id"],
                "resolved_memory_id": candidate.get("memory_id"),
            }
            payload["current_context"] = context
            reason = f"{invocation.reason}_recent_candidate"
            return CopilotFeishuInvocation(invocation.tool_name, payload, invocation.user_text, reason)
    if invocation.tool_name in review_tools and invocation.payload.get("candidate_id"):
        payload = dict(invocation.payload)
        context = dict(payload.get("current_context") or {})
        _grant_owner_role_if_applicable(repo, context, event.sender_id, str(invocation.payload.get("candidate_id")))
        payload["current_context"] = context
        return CopilotFeishuInvocation(invocation.tool_name, payload, invocation.user_text, invocation.reason)
    if invocation.tool_name == "memory.explain_versions" and not invocation.payload.get("memory_id"):
        memory = _recent_memory_id(repo, event, scope)
        if memory:
            payload = dict(invocation.payload)
            payload["memory_id"] = memory["memory_id"]
            context = dict(payload.get("current_context") or {})
            context["thread_topic"] = str(memory.get("subject") or memory["memory_id"])[:80]
            context["metadata"] = {
                **dict(context.get("metadata") or {}),
                "resolved_from": "recent_memory",
                "resolved_memory_id": memory["memory_id"],
            }
            payload["current_context"] = context
            return CopilotFeishuInvocation(
                invocation.tool_name, payload, invocation.user_text, f"{invocation.reason}_recent_memory"
            )
    return invocation


def _grant_owner_role_if_applicable(
    repo: MemoryRepository,
    context: dict[str, Any],
    sender_id: str,
    candidate_id: str,
) -> None:
    owner_id = _candidate_owner_id(repo, candidate_id)
    if not owner_id or owner_id != sender_id:
        return
    permission = context.get("permission") if isinstance(context.get("permission"), dict) else {}
    actor = permission.get("actor") if isinstance(permission.get("actor"), dict) else {}
    roles = actor.get("roles") if isinstance(actor.get("roles"), list) else []
    if "owner" not in roles:
        actor["roles"] = sorted(set([*map(str, roles), "owner"]))
    permission["actor"] = actor
    context["permission"] = permission


def _candidate_owner_id(repo: MemoryRepository, candidate_id: str) -> str | None:
    row = repo.conn.execute("SELECT owner_id FROM memories WHERE id = ?", (candidate_id,)).fetchone()
    if row and isinstance(row["owner_id"], str) and row["owner_id"]:
        return str(row["owner_id"])
    version_row = repo.conn.execute(
        """
        SELECT m.owner_id
        FROM memory_versions mv
        JOIN memories m ON m.id = mv.memory_id
        WHERE mv.id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if version_row and isinstance(version_row["owner_id"], str) and version_row["owner_id"]:
        return str(version_row["owner_id"])
    return None


def _recent_candidate_id(repo: MemoryRepository, event: FeishuMessageEvent, scope: str) -> dict[str, Any] | None:
    parsed = parse_scope(scope)
    rows = repo.conn.execute(
        """
        SELECT m.id AS memory_id, m.subject, m.updated_at AS sort_time,
               m.source_event_id, m.status AS memory_status,
               m.active_version_id, re.raw_json
        FROM memories m
        LEFT JOIN raw_events re ON re.id = m.source_event_id
        WHERE m.scope_type = ?
          AND m.scope_id = ?
          AND m.status = 'candidate'
        ORDER BY m.updated_at DESC
        LIMIT 20
        """,
        (parsed.scope_type, parsed.scope_id),
    ).fetchall()
    candidates: list[dict[str, Any]] = [
        {
            "candidate_id": str(row["memory_id"]),
            "memory_id": str(row["memory_id"]),
            "subject": row["subject"],
            "sort_time": row["sort_time"],
            "raw_json": row["raw_json"],
        }
        for row in rows
    ]
    version_rows = repo.conn.execute(
        """
        SELECT mv.id AS candidate_id, mv.memory_id, m.subject, mv.created_at AS sort_time, re.raw_json
        FROM memory_versions mv
        JOIN memories m ON m.id = mv.memory_id
        LEFT JOIN raw_events re ON re.id = mv.source_event_id
        WHERE m.scope_type = ?
          AND m.scope_id = ?
          AND mv.status = 'candidate'
        ORDER BY mv.created_at DESC
        LIMIT 20
        """,
        (parsed.scope_type, parsed.scope_id),
    ).fetchall()
    candidates.extend(
        {
            "candidate_id": str(row["candidate_id"]),
            "memory_id": str(row["memory_id"]),
            "subject": row["subject"],
            "sort_time": row["sort_time"],
            "raw_json": row["raw_json"],
        }
        for row in version_rows
    )
    return _pick_contextual_row(candidates, event)


def _recent_memory_id(repo: MemoryRepository, event: FeishuMessageEvent, scope: str) -> dict[str, Any] | None:
    parsed = parse_scope(scope)
    rows = repo.conn.execute(
        """
        SELECT m.id AS memory_id, m.subject, m.updated_at AS sort_time, re.raw_json,
               COUNT(mv.id) AS version_count
        FROM memories m
        LEFT JOIN raw_events re ON re.id = m.source_event_id
        LEFT JOIN memory_versions mv ON mv.memory_id = m.id
        WHERE m.scope_type = ?
          AND m.scope_id = ?
          AND m.status = 'active'
        GROUP BY m.id
        ORDER BY CASE WHEN COUNT(mv.id) > 1 THEN 0 ELSE 1 END, m.updated_at DESC
        LIMIT 20
        """,
        (parsed.scope_type, parsed.scope_id),
    ).fetchall()
    candidates = [
        {
            "memory_id": str(row["memory_id"]),
            "subject": row["subject"],
            "sort_time": row["sort_time"],
            "raw_json": row["raw_json"],
            "version_count": row["version_count"],
        }
        for row in rows
    ]
    return _pick_contextual_row(candidates, event)


def _pick_contextual_row(rows: list[dict[str, Any]], event: FeishuMessageEvent) -> dict[str, Any] | None:
    if not rows:
        return None
    same_chat = [row for row in rows if _row_chat_id(row) == event.chat_id]
    pool = same_chat or rows
    same_sender = [row for row in pool if _row_sender_id(row) == event.sender_id]
    pool = same_sender or pool
    return sorted(pool, key=lambda item: int(item.get("sort_time") or 0), reverse=True)[0]


def _row_chat_id(row: dict[str, Any]) -> str | None:
    raw = _json_object(row.get("raw_json"))
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    context = raw.get("current_context") if isinstance(raw.get("current_context"), dict) else {}
    source_context = context.get("source_context") if isinstance(context.get("source_context"), dict) else {}
    return (
        _string_or_none(source.get("source_chat_id"))
        or _string_or_none(context.get("chat_id"))
        or _string_or_none(source_context.get("chat_id"))
    )


def _row_sender_id(row: dict[str, Any]) -> str | None:
    raw = _json_object(row.get("raw_json"))
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    context = raw.get("current_context") if isinstance(raw.get("current_context"), dict) else {}
    permission = context.get("permission") if isinstance(context.get("permission"), dict) else {}
    actor = permission.get("actor") if isinstance(permission.get("actor"), dict) else {}
    return _string_or_none(source.get("actor_id")) or _string_or_none(actor.get("open_id"))


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _current_context(
    event: FeishuMessageEvent,
    scope: str,
    action: str,
    *,
    intent: str,
    thread_topic: str,
) -> dict[str, Any]:
    request_suffix = re.sub(r"[^A-Za-z0-9_]+", "_", action)
    tenant_id, organization_id, visibility = _feishu_identity()
    return {
        "session_id": f"feishu:{event.chat_id}",
        "chat_id": event.chat_id,
        "scope": scope,
        "user_id": event.sender_id,
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "visibility_policy": visibility,
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
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "roles": _roles_for_sender(event.sender_id),
            },
            "source_context": {
                "entrypoint": ENTRYPOINT,
                "workspace_id": scope,
                "chat_id": event.chat_id,
            },
            "requested_action": action,
            "requested_visibility": visibility,
            "timestamp": _event_time_iso(event),
        },
    }


def _extend_permission_source_context(context: dict[str, Any], **values: str) -> None:
    permission = context.get("permission") if isinstance(context.get("permission"), dict) else {}
    source_context = permission.get("source_context") if isinstance(permission.get("source_context"), dict) else {}
    source_context.update({key: value for key, value in values.items() if value})
    permission["source_context"] = source_context
    context["permission"] = permission


def _roles_for_sender(sender_id: str) -> list[str]:
    base = _csv_env("COPILOT_FEISHU_DEFAULT_ROLES") or ["member"]
    reviewers = _csv_env("COPILOT_FEISHU_REVIEWER_OPEN_IDS")
    if "*" in reviewers or (sender_id and sender_id in reviewers):
        return sorted(set(base + ["reviewer"]))
    return base


def _format_search(result: dict[str, Any], *, routing_reason: str) -> str:
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    if not rows:
        lines = [
            "结论：没有找到可直接采用的当前有效结论。",
            "证据：默认只搜索 active memory，没有返回 candidate、superseded 或 raw events。",
            "下一步：可以补充更具体的主题，或先创建一条待确认记忆。",
        ]
        if routing_reason == "default_search":
            lines.insert(1, "候选判断：本次消息按查询处理，未尝试创建待确认记忆。")
        lines.extend(_audit_lines("memory.search", result, extra=[f"查询：{result.get('query') or '-'}", "状态：not_found"]))
        return _reply(
            "Memory Copilot 没找到当前有效记忆。",
            lines,
        )
    lines = [
        "结论：找到当前有效记忆，只返回 active 当前结论。",
    ]
    if routing_reason == "default_search":
        lines.append("候选判断：本次消息按查询处理，未尝试创建待确认记忆。")
    for index, item in enumerate(rows[:3], start=1):
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        quote = "-"
        if evidence and isinstance(evidence[0], dict):
            quote = str(evidence[0].get("quote") or "-")
        lines.extend(
            [
                f"{index}. {item.get('subject') or '-'}",
                f"   结论：{item.get('current_value') or '-'}",
                f"   证据：{_clip(quote)}",
                f"   下一步：按这条当前结论执行；如果要看旧值，回复“为什么旧值不用了”。",
            ]
        )
    lines.extend(
        _audit_lines("memory.search", result, extra=[f"查询：{result.get('query') or '-'}", f"trace：{_trace_summary(result)}"])
    )
    return _reply("Memory Copilot 找到当前有效记忆。", lines)


def _format_candidate(result: dict[str, Any]) -> str:
    if result.get("action") == "ignored":
        return _reply(
            "Memory Copilot 没有把这条消息写入候选记忆。",
            [
                "结论：这条消息没有进入待确认记忆。",
                f"证据：{result.get('reason') or '-'}",
                "下一步：如果确实要记录，请用“记住：...”重新描述成明确规则。",
                *_audit_lines(
                    "memory.create_candidate",
                    result,
                    extra=["状态：not_candidate", f"risk_flags：{', '.join(result.get('risk_flags') or []) or '-'}"],
                ),
            ],
        )
    candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else {}
    candidate_id = result.get("candidate_id") or candidate.get("candidate_id") or result.get("memory_id")
    lines = [
        "结论：已生成待确认记忆，不会自动成为 active memory。",
        f"主题：{candidate.get('subject') or '-'}",
        f"证据：{_clip(candidate.get('current_value') or '-')}",
        "下一步：你可以直接回复：确认这条 / 不要记这个 / 查看来源。",
        f"risk_flags：{', '.join(result.get('risk_flags') or []) or '-'}",
    ]
    if result.get("auto_confirm_ignored"):
        lines.append("说明：真实飞书来源不会自动 active，auto_confirm 已被忽略。")
    lines.extend(
        _audit_lines(
            "memory.create_candidate",
            result,
            extra=[
                f"状态：{candidate.get('status') or result.get('status') or 'candidate'}",
                f"candidate_id：{candidate_id or '-'}",
                f"recommended_action：{result.get('recommended_action') or '-'}",
            ],
        )
    )
    return _reply("Memory Copilot 已创建待确认记忆。", lines)


def _format_review(result: dict[str, Any], *, action: str) -> str:
    memory = result.get("memory") if isinstance(result.get("memory"), dict) else {}
    next_step_by_action = {
        "确认": "下一步：这条记忆已经成为当前有效结论。",
        "拒绝": "下一步：这条候选已拒绝，不会成为当前有效记忆。",
        "要求补证据": "下一步：这条候选已进入 needs_evidence，补齐证据前不会成为当前有效记忆。",
        "标记过期": "下一步：这条候选已标记 expired，不会进入默认审核队列或当前有效记忆。",
    }
    action_name_by_label = {
        "确认": "confirm",
        "拒绝": "reject",
        "要求补证据": "needs_evidence",
        "标记过期": "expire",
    }
    return _reply(
        f"Memory Copilot 已{action}候选记忆。",
        [
            f"结论：候选记忆已{action}。",
            f"结论：{memory.get('current_value') or '-'}",
            next_step_by_action.get(action, "下一步：候选状态已通过 CopilotService 更新。"),
            *_audit_lines(
                f"memory.{action_name_by_label.get(action, 'review')}",
                result,
                extra=[
                    f"状态：{memory.get('status') or result.get('status') or '-'}",
                    f"处理结果：{result.get('action') or '-'}",
                    f"memory_id：{result.get('memory_id') or '-'}",
                    f"candidate_id：{result.get('candidate_id') or '-'}",
                ],
            ),
        ],
    )


def _format_versions(result: dict[str, Any]) -> str:
    versions = result.get("versions") if isinstance(result.get("versions"), list) else []
    active = result.get("active_version") if isinstance(result.get("active_version"), dict) else {}
    lines = [
        f"结论：当前结论是 {active.get('value') or '-'}",
        f"证据：{result.get('explanation') or '-'}",
        "下一步：默认搜索只采用当前 active 版本；旧版本只作为版本证据保留。",
        "旧版本：",
    ]
    for item in versions[:6]:
        if isinstance(item, dict):
            lines.append(f"- v{item.get('version_no')} [{item.get('status')}] {item.get('value')}")
    lines.extend(
        _audit_lines(
            "memory.explain_versions",
            result,
            extra=[f"主题：{result.get('subject') or '-'}", f"状态：{result.get('status') or '-'}", f"版本数量：{len(versions)}"],
        )
    )
    return _reply("Memory Copilot 已返回版本链。", lines)


def _format_prefetch(result: dict[str, Any]) -> str:
    pack = result.get("context_pack") if isinstance(result.get("context_pack"), dict) else {}
    memories = pack.get("relevant_memories") if isinstance(pack.get("relevant_memories"), list) else []
    lines = [
        f"结论：已生成任务前上下文包。",
        f"证据：{pack.get('summary') or '-'}",
        "下一步：把下面相关记忆带入任务；缺失信息需要人工补充。",
    ]
    for item in memories[:3]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('subject')}: {item.get('current_value')}")
    lines.extend(
        _audit_lines(
            "memory.prefetch",
            result,
            extra=[
                f"任务：{result.get('task') or '-'}",
                f"raw_events_included：{str(pack.get('raw_events_included')).lower()}",
                f"stale_superseded_filtered：{str(pack.get('stale_superseded_filtered')).lower()}",
            ],
        )
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


def _format_feishu_source(result: dict[str, Any], source_label: str) -> str:
    """格式化飞书来源（任务、会议、Bitable）的拉取结果。"""
    if result.get("error"):
        error = result.get("error")
        if isinstance(error, str):
            error_message = error
        elif isinstance(error, dict):
            error_message = error.get("message", str(error))
        else:
            error_message = str(error)
        return _reply(
            f"Memory Copilot 拉取{source_label}失败。",
            [
                "状态：error",
                f"原因：{error_message}",
            ],
        )

    source = result.get("source", {})
    source_type = source.get("source_type", "")
    source_id = source.get("source_id", "")
    title = source.get("title", "")
    candidate_count = result.get("candidate_count", 0)
    duplicate_count = result.get("duplicate_count", 0)

    lines = [
        f"工具：feishu.fetch_{source_type}",
        "状态：ok",
        f"处理结果：已从{source_label}提取文本进入 candidate pipeline。",
        f"来源标题：{title}",
        f"来源 ID：{source_id}",
        f"候选数量：{candidate_count}",
        f"重复数量：{duplicate_count}",
        "注意：所有候选仍需人工确认，不会自动成为 active memory。",
    ]

    # 显示前 3 个候选
    candidates = result.get("candidates", [])
    if candidates:
        lines.append("\n候选列表：")
        for i, candidate in enumerate(candidates[:3], 1):
            if isinstance(candidate, dict):
                candidate_id = candidate.get("candidate_id", "")
                subject = candidate.get("subject", "")
                action = candidate.get("action", "")
                lines.append(f"{i}. {subject} ({action}) ID: {candidate_id}")

    lines.extend(
        [
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return _reply(f"Memory Copilot 已拉取{source_label}。", lines)


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
            "飞书任务：@Bot /task <task_id>",
            "飞书会议：@Bot /meeting <minute_token>",
            "多维表格：@Bot /bitable <app_token> <table_id> <record_id>",
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


def _publish(
    publisher,
    event: FeishuMessageEvent,
    reply: str,
    config: FeishuConfig,
    *,
    invocation: CopilotFeishuInvocation | None = None,
    tool_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = _interactive_card(invocation, tool_result, reply) if config.card_mode == "interactive" else None
    return publisher.publish(event, reply, card)


def _interactive_card(
    invocation: CopilotFeishuInvocation | None,
    tool_result: dict[str, Any] | None,
    reply: str,
) -> dict[str, Any]:
    if invocation is None or tool_result is None:
        return build_card_from_text(reply)
    if invocation.tool_name == "memory.search":
        return build_search_result_card(tool_result)
    if invocation.tool_name == "memory.create_candidate" and tool_result.get("action") != "ignored":
        return build_candidate_review_card(tool_result)
    if invocation.tool_name == "memory.explain_versions":
        return build_version_chain_card(tool_result)
    if invocation.tool_name == "memory.prefetch":
        return build_prefetch_context_card(tool_result)
    review_tools = {
        "memory.confirm",
        "memory.reject",
        "memory.needs_evidence",
        "memory.expire",
    }
    if invocation.tool_name in review_tools:
        return build_candidate_review_card(tool_result)
    return build_card_from_text(reply)


def _event_result(
    event: FeishuMessageEvent,
    scope: str,
    invocation: CopilotFeishuInvocation,
    tool_result: dict[str, Any],
    publish_result: dict[str, Any],
    graph_node: dict[str, Any] | None = None,
    message_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "ok": bool(publish_result.get("ok", False)) and bool(tool_result.get("ok", True)),
        "message_id": event.message_id,
        "scope": scope,
        "entrypoint": ENTRYPOINT,
        "tool": invocation.tool_name,
        "routing_reason": invocation.reason,
        "message_disposition": _message_disposition(invocation, tool_result),
        "tool_result": tool_result,
        "publish": publish_result,
    }
    if graph_node is not None:
        result["graph_node"] = graph_node
    if message_graph is not None:
        result["message_graph"] = message_graph
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


def _message_disposition(invocation: CopilotFeishuInvocation, tool_result: dict[str, Any]) -> dict[str, str]:
    if invocation.tool_name == "memory.search":
        return {
            "memory_path": "search_only",
            "candidate_path": "not_attempted",
            "reason_code": invocation.reason,
        }
    if invocation.tool_name == "memory.create_candidate":
        action = str(tool_result.get("action") or "")
        if invocation.reason == "passive_candidate_probe":
            return {
                "memory_path": "silent_candidate_probe",
                "candidate_path": action or "attempted",
                "reason_code": "passive_group_detection",
            }
        if action == "ignored":
            return {
                "memory_path": "candidate_ignored",
                "candidate_path": "ignored",
                "reason_code": "low_memory_signal",
            }
        return {
            "memory_path": "candidate_attempted",
            "candidate_path": action or "attempted",
            "reason_code": invocation.reason,
        }
    if invocation.tool_name in {"memory.confirm", "memory.reject", "memory.needs_evidence", "memory.expire"}:
        return {
            "memory_path": "candidate_review",
            "candidate_path": "reviewed",
            "reason_code": invocation.reason,
        }
    return {
        "memory_path": invocation.tool_name,
        "candidate_path": "not_applicable",
        "reason_code": invocation.reason,
    }


def _silent_publish_result(event: FeishuMessageEvent) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": False,
        "mode": "silent_no_reply",
        "reply_to": event.message_id,
        "chat_id": event.chat_id,
        "text": "",
        "card": None,
        "suppressed": True,
    }


def _chat_allowed(chat_id: str) -> bool:
    allowed = _csv_env("COPILOT_FEISHU_ALLOWED_CHAT_IDS")
    return not allowed or chat_id in allowed


def _feishu_identity() -> tuple[str, str, str]:
    return (
        os.environ.get("COPILOT_FEISHU_TENANT_ID", DEFAULT_TENANT_ID),
        os.environ.get("COPILOT_FEISHU_ORGANIZATION_ID", DEFAULT_ORGANIZATION_ID),
        os.environ.get("COPILOT_FEISHU_VISIBILITY", "team"),
    )


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


def _looks_like_confirm(text: str) -> bool:
    normalized = text.strip()
    return normalized in {"确认", "确认这条", "确认这个", "可以记", "记这个"} or normalized.startswith("确认 ")


def _looks_like_reject(text: str) -> bool:
    normalized = text.strip()
    return normalized in {"不要记这个", "不要记这条", "别记这个", "别记这条", "拒绝这条", "拒绝这个"} or normalized.startswith(
        "拒绝 "
    )


def _natural_review_target(text: str, verb: str) -> str:
    normalized = text.strip()
    if normalized.startswith(f"{verb} "):
        return normalized.removeprefix(f"{verb} ").strip()
    return ""


def _looks_like_versions_question(text: str) -> bool:
    return ("为什么" in text and any(word in text for word in ("旧值", "旧版本", "之前", "以前", "不用了", "覆盖"))) or (
        "版本" in text and any(word in text for word in ("解释", "为什么", "旧"))
    )


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


def _audit_lines(tool_name: str, result: dict[str, Any], *, extra: list[str] | None = None) -> list[str]:
    lines = ["审计详情", f"工具：{tool_name}"]
    lines.extend(extra or [])
    lines.extend(
        [
            f"permission_decision：{_permission_decision_summary(result)}",
            f"request_id：{_bridge_field(result, 'request_id')}",
            f"trace_id：{_bridge_field(result, 'trace_id')}",
        ]
    )
    return lines


def _permission_decision_summary(result: dict[str, Any]) -> str:
    bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
    decision = bridge.get("permission_decision")
    if isinstance(decision, dict):
        return f"{decision.get('decision') or '-'} / {decision.get('reason_code') or '-'}"
    return "-"


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
