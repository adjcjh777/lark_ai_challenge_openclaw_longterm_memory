from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .feishu_config import FeishuConfig, load_feishu_config, scope_for_chat
from .feishu_events import FeishuTextEvent, text_event_from_payload
from .feishu_messages import (
    format_help,
    format_recall_reply,
    format_remember_reply,
    format_versions_reply,
    parse_command,
)
from .feishu_publisher import DryRunPublisher, LarkCliPublisher
from .repository import MemoryRepository


SOURCE_TYPE = "feishu_message"


def replay_event(path: str | Path, *, db_path: str | Path | None = None) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    conn = connect(db_path)
    init_db(conn)
    try:
        event = text_event_from_payload(payload)
        if event is None:
            return {"ok": True, "ignored": True, "reason": "not a text message event"}
        return handle_text_event(conn, event, DryRunPublisher(), load_feishu_config())
    finally:
        conn.close()


def listen(*, db_path: str | Path | None = None, dry_run: bool = False) -> None:
    config = load_feishu_config()
    conn = connect(db_path)
    init_db(conn)
    publisher = DryRunPublisher() if dry_run else LarkCliPublisher(config)
    command = _event_subscribe_command(config)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                event = text_event_from_payload(payload)
                if event is None:
                    result = {"ok": True, "ignored": True, "reason": "not a text message event"}
                else:
                    result = handle_text_event(conn, event, publisher, config)
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "raw_line": line}
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        process.terminate()
    finally:
        conn.close()
        if process.poll() is None:
            process.terminate()


def handle_text_event(conn, event: FeishuTextEvent, publisher, config: FeishuConfig) -> dict[str, Any]:
    repo = MemoryRepository(conn)
    command = parse_command(event.text)
    if command is None:
        return {"ok": True, "ignored": True, "reason": "unsupported command", "text": event.text}

    if repo.has_source_event(SOURCE_TYPE, event.message_id):
        reply = "这条飞书消息已处理过，已跳过重复投递。"
        publish_result = publisher.publish(event, reply)
        return {"ok": publish_result.get("ok", False), "duplicate": True, "publish": publish_result}

    scope = scope_for_chat(event.chat_id, config)
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
    else:
        return {"ok": True, "ignored": True, "reason": "unsupported command", "text": event.text}

    publish_result = publisher.publish(event, reply)
    return {
        "ok": publish_result.get("ok", False),
        "message_id": event.message_id,
        "scope": scope,
        "command": command.name,
        "publish": publish_result,
    }


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
            "im.message.receive_v1",
            "--quiet",
        ]
    )
    return command
