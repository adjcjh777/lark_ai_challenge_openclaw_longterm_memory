from __future__ import annotations

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
from .feishu_messages import (
    format_duplicate_reply,
    format_candidate_action_reply,
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
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
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
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        process.terminate()
    finally:
        conn.close()
        if process.poll() is None:
            process.terminate()


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
        reply = format_candidate_action_reply(
            repo.confirm_candidate(command.argument),
            action="确认",
            candidate_id=command.argument,
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
        reply = format_candidate_action_reply(
            repo.reject_candidate(command.argument),
            action="拒绝",
            candidate_id=command.argument,
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
    }


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
