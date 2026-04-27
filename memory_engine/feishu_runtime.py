from __future__ import annotations

from datetime import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .db import connect, db_path_from_env, init_db
from .document_ingestion import ingest_document_source
from .feishu_cards import build_card_from_text
from .feishu_config import FeishuConfig, load_feishu_config, scope_for_chat
from .feishu_events import FeishuMessageEvent, FeishuTextEvent, message_event_from_payload
from .copilot.service import CopilotService
from .copilot.tools import handle_tool_request
from .copilot.permissions import demo_permission_context
from .feishu_messages import (
    format_duplicate_reply,
    format_help,
    format_health,
    format_ignored_reply,
    format_ingest_doc_reply,
    format_recall_reply,
    format_remember_reply,
    format_unknown_command_reply,
    format_versions_reply,
    parse_command,
)
from .feishu_publisher import DryRunPublisher, LarkCliPublisher
from .repository import MemoryRepository


SOURCE_TYPE = "feishu_message"


class FeishuRunLogger:
    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = _timestamp()
        file_stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        self.path = self.log_dir / f"feishu-listen-{file_stamp}.ndjson"

    def write(self, event: str, **fields: Any) -> None:
        record = {"ts": _timestamp(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def replay_event(path: str | Path, *, db_path: str | Path | None = None) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    conn = connect(db_path)
    init_db(conn)
    try:
        event = message_event_from_payload(payload)
        if event is None:
            return {"ok": True, "ignored": True, "reason": "not a text message event"}
        return handle_message_event(
            conn,
            event,
            DryRunPublisher(),
            load_feishu_config(),
            db_path=db_path,
            dry_run=True,
        )
    finally:
        conn.close()


def listen(*, db_path: str | Path | None = None, dry_run: bool = False) -> None:
    config = load_feishu_config()
    conn = connect(db_path)
    init_db(conn)
    publisher = DryRunPublisher() if dry_run else LarkCliPublisher(config)
    command = _event_subscribe_command(config)
    run_logger = FeishuRunLogger(config.log_dir)
    run_logger.write(
        "listen_start",
        dry_run=dry_run,
        db_path=str(db_path or db_path_from_env()),
        command=_redact_command(command),
        profile=config.lark_profile,
        bot_mode=config.bot_mode,
        card_mode=config.card_mode,
        card_retry_count=config.card_retry_count,
        card_timeout_seconds=config.card_timeout_seconds,
    )
    print(f"Feishu listener log: {run_logger.path}", file=sys.stderr, flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            run_logger.write("event_received", raw_line=line)
            try:
                payload = json.loads(line)
                event = message_event_from_payload(payload)
                if event is None:
                    result = {"ok": True, "ignored": True, "reason": "not a text message event"}
                else:
                    result = handle_message_event(
                        conn,
                        event,
                        publisher,
                        config,
                        db_path=db_path,
                        dry_run=dry_run,
                    )
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "raw_line": line}
                run_logger.write("event_error", error=str(exc), raw_line=line)
            run_logger.write(
                "event_result",
                ok=result.get("ok"),
                ignored=result.get("ignored", False),
                command=result.get("command"),
                message_id=result.get("message_id"),
                duplicate=result.get("duplicate", False),
                publish=_publish_log_summary(result.get("publish")),
                result=result,
            )
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        run_logger.write("listen_stop", reason="keyboard_interrupt")
        process.terminate()
    finally:
        conn.close()
        if process.poll() is None:
            process.terminate()
        run_logger.write("listen_exit", returncode=process.poll())


def handle_text_event(conn, event: FeishuTextEvent, publisher, config: FeishuConfig) -> dict[str, Any]:
    return handle_message_event(
        conn,
        FeishuMessageEvent(
            message_id=event.message_id,
            chat_id=event.chat_id,
            chat_type=event.chat_type,
            sender_id=event.sender_id,
            sender_type=event.sender_type,
            message_type=event.message_type,
            text=event.text,
            create_time=event.create_time,
            raw=event.raw,
        ),
        publisher,
        config,
    )


def handle_message_event(
    conn,
    event: FeishuMessageEvent,
    publisher,
    config: FeishuConfig,
    *,
    db_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo = MemoryRepository(conn)
    scope = scope_for_chat(event.chat_id, config)

    if event.ignore_reason == "bot self message":
        return {
            "ok": True,
            "ignored": True,
            "reason": event.ignore_reason,
            "message_id": event.message_id,
            "chat_id": event.chat_id,
        }

    if repo.has_source_event(SOURCE_TYPE, event.message_id):
        reply = format_duplicate_reply()
        publish_result = publisher.publish(event, reply, build_card_from_text(reply))
        return {"ok": publish_result.get("ok", False), "duplicate": True, "publish": publish_result}

    if event.ignore_reason is not None:
        _record_handled_event(repo, scope, event, f"[{event.ignore_reason}]")
        reply = format_ignored_reply(event.ignore_reason)
        publish_result = publisher.publish(event, reply, build_card_from_text(reply))
        return {
            "ok": publish_result.get("ok", False),
            "ignored": True,
            "reason": event.ignore_reason,
            "message_id": event.message_id,
            "scope": scope,
            "publish": publish_result,
        }

    command = parse_command(event.text)
    if command is None:
        _record_handled_event(repo, scope, event, event.text)
        reply = format_unknown_command_reply(None)
        publish_result = publisher.publish(event, reply, build_card_from_text(reply))
        return {
            "ok": publish_result.get("ok", False),
            "ignored": True,
            "reason": "unsupported command",
            "text": event.text,
            "publish": publish_result,
        }

    if command.name == "help":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        reply = format_help(command.argument)
    elif command.name == "health":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        reply = format_health(
            db_path=str(Path(db_path) if db_path else db_path_from_env()),
            default_scope=scope,
            dry_run=dry_run,
            bot_mode=config.bot_mode,
        )
    elif command.name == "remember":
        result = repo.remember(
            scope,
            command.argument,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            created_by=event.sender_id,
        )
        reply = format_remember_reply(result)
    elif command.name == "recall":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        reply = format_recall_reply(repo.recall(scope, command.argument))
    elif command.name == "versions":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        reply = format_versions_reply(command.argument, repo.versions(command.argument))
    elif command.name == "ingest_doc":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        result = ingest_document_source(
            repo,
            command.argument,
            scope=scope,
            lark_cli=config.lark_cli,
            profile=config.lark_profile,
            as_identity=config.lark_as,
        )
        reply = format_ingest_doc_reply(result)
    elif command.name == "confirm":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        tool_result = _handle_review_tool_action(
            repo,
            event,
            tool_name="memory.confirm",
            candidate_id=command.argument,
            scope=scope,
        )
        reply = _format_review_tool_reply(
            tool_result,
            action="确认",
            candidate_label=_candidate_label_from_card_action(event),
        )
    elif command.name == "reject":
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        tool_result = _handle_review_tool_action(
            repo,
            event,
            tool_name="memory.reject",
            candidate_id=command.argument,
            scope=scope,
        )
        reply = _format_review_tool_reply(
            tool_result,
            action="拒绝",
            candidate_label=_candidate_label_from_card_action(event),
        )
    else:
        repo.record_raw_event(
            scope,
            event.text,
            source_type=SOURCE_TYPE,
            source_id=event.message_id,
            sender_id=event.sender_id,
            raw_json=event.raw,
            event_time=event.create_time or None,
        )
        reply = format_unknown_command_reply(command.raw_name)

    publish_result = publisher.publish(event, reply, build_card_from_text(reply))
    return {
        "ok": publish_result.get("ok", False),
        "message_id": event.message_id,
        "scope": scope,
        "command": command.name,
        "publish": publish_result,
        **({"tool_result": tool_result} if command.name in {"confirm", "reject"} else {}),
    }


def _handle_review_tool_action(
    repo: MemoryRepository,
    event: FeishuMessageEvent,
    *,
    tool_name: str,
    candidate_id: str,
    scope: str,
) -> dict[str, Any]:
    value = _card_action_value(event)
    current_context = value.get("current_context") if isinstance(value.get("current_context"), dict) else None
    if current_context is None and not _has_card_action(event):
        current_context = demo_permission_context(
            tool_name,
            scope,
            actor_id=event.sender_id or "feishu_runtime",
            roles=["member", "reviewer"],
            entrypoint="feishu_runtime",
        )
    payload = {
        "candidate_id": candidate_id,
        "scope": value.get("scope") if isinstance(value.get("scope"), str) and value.get("scope") else scope,
        "reason": value.get("reason") if isinstance(value.get("reason"), str) else "Feishu review surface action",
        "current_context": current_context,
    }
    service = CopilotService(repository=repo)
    return handle_tool_request(tool_name, payload, service=service)


def _format_review_tool_reply(tool_result: dict[str, Any], *, action: str, candidate_label: str | None = None) -> str:
    label_line = f"候选序号：{candidate_label}" if candidate_label else None
    if not tool_result.get("ok"):
        error = tool_result.get("error") if isinstance(tool_result.get("error"), dict) else {}
        details = error.get("details") if isinstance(error.get("details"), dict) else {}
        lines = [
            f"类型：候选记忆{action}",
            "卡片：候选确认卡片",
            "结论：权限不足，已安全拒绝",
            f"理由：{details.get('reason_code') or error.get('code') or 'permission_denied'}",
            f"主题：{details.get('candidate_id') or '-'}",
            "状态：permission_denied",
            "版本：-",
            "来源：CopilotService",
            "是否被覆盖：-",
            f"request_id：{details.get('request_id') or (tool_result.get('bridge') or {}).get('request_id') or '-'}",
            f"trace_id：{details.get('trace_id') or (tool_result.get('bridge') or {}).get('trace_id') or '-'}",
            "处理结果：candidate 状态未改变；未展示未授权内容或证据。",
        ]
        if label_line:
            lines.insert(5, label_line)
        return "\n".join(["候选记忆审核卡片：权限不足，动作已拒绝。", *lines])

    memory = tool_result.get("memory") if isinstance(tool_result.get("memory"), dict) else {}
    lines = [
        f"类型：候选记忆{action}",
        "卡片：候选确认卡片",
        f"结论：{memory.get('current_value') or '-'}",
        f"理由：通过 CopilotService 执行 memory.{_candidate_action_command(action)}，不是直接改 repository 状态",
        f"主题：{memory.get('subject') or tool_result.get('memory_id')}",
        f"状态：{memory.get('status') or tool_result.get('status')}",
        "版本：Phase 3",
        "来源：CopilotService",
        f"是否被覆盖：{_overwritten_label(memory.get('status') or tool_result.get('status'))}",
        f"memory_id：{tool_result.get('memory_id')}",
        f"处理结果：{tool_result.get('action')}",
        f"request_id：{(tool_result.get('bridge') or {}).get('request_id') or '-'}",
        f"trace_id：{(tool_result.get('bridge') or {}).get('trace_id') or '-'}",
    ]
    if label_line:
        lines.insert(5, label_line)
    return "\n".join([f"候选记忆{action}卡片：{candidate_label + ' ' if candidate_label else ''}候选状态已更新。", *lines])


def _card_action_value(event: FeishuMessageEvent) -> dict[str, Any]:
    raw_event = event.raw.get("event") if isinstance(event.raw.get("event"), dict) else event.raw
    action = raw_event.get("action") if isinstance(raw_event.get("action"), dict) else {}
    value = action.get("value") if isinstance(action.get("value"), dict) else {}
    return dict(value)


def _has_card_action(event: FeishuMessageEvent) -> bool:
    raw_event = event.raw.get("event") if isinstance(event.raw.get("event"), dict) else event.raw
    return isinstance(raw_event.get("action"), dict)


def _candidate_action_command(action: str) -> str:
    return "confirm" if action == "确认" else "reject"


def _overwritten_label(status: object) -> str:
    if status == "active":
        return "否（当前 active 版本）"
    if status == "rejected":
        return "是（已拒绝，不进入默认召回）"
    if status == "superseded":
        return "是（已被后续版本覆盖）"
    return "-"


def _record_handled_event(repo: MemoryRepository, scope: str, event: FeishuMessageEvent, content: str) -> None:
    repo.record_raw_event(
        scope,
        content,
        source_type=SOURCE_TYPE,
        source_id=event.message_id,
        sender_id=event.sender_id,
        raw_json=event.raw,
        event_time=event.create_time or None,
    )


def _candidate_label_from_card_action(event: FeishuMessageEvent) -> str | None:
    if event.message_type != "card_action":
        return None
    payload_event = event.raw.get("event") if isinstance(event.raw.get("event"), dict) else event.raw
    action = payload_event.get("action") if isinstance(payload_event.get("action"), dict) else {}
    value = action.get("value") if isinstance(action.get("value"), dict) else {}
    label = str(value.get("candidate_label") or "").strip()
    if label:
        return label
    index = str(value.get("candidate_index") or "").strip()
    return f"候选 {index}" if index else None


def _event_subscribe_command(config: FeishuConfig) -> list[str]:
    command = [config.lark_cli]
    if config.lark_profile:
        command.extend(["--profile", config.lark_profile])
    command.extend(
        [
            "event",
            "+subscribe",
            "--as",
            config.lark_as,
            "--event-types",
            "im.message.receive_v1,card.action.trigger",
            "--quiet",
        ]
    )
    return command


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _publish_log_summary(publish: Any) -> dict[str, Any] | None:
    if not isinstance(publish, dict):
        return None
    return {
        "ok": publish.get("ok"),
        "mode": publish.get("mode"),
        "fallback_used": publish.get("fallback_used"),
        "fallback_suppressed": publish.get("fallback_suppressed"),
        "latency_ms": publish.get("latency_ms"),
        "card_attempts": publish.get("card_attempts"),
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
