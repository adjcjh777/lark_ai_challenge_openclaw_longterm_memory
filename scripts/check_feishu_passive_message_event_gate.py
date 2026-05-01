#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.feishu_events import message_event_from_payload  # noqa: E402

BOUNDARY = (
    "Feishu passive group message event gate only; proves captured event delivery shape, "
    "not production long-running ingestion."
)
ID_PATTERN = re.compile(r"\b(?:ou|oc|om|cli|ou_|oc_|om_)[A-Za-z0-9_-]+\b")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check captured Feishu/OpenClaw event output for non-@ group text message delivery. "
            "Use this after sending a normal group message without mentioning the bot."
        )
    )
    parser.add_argument(
        "--event-log",
        type=Path,
        default=None,
        help="NDJSON/JSON log file. Defaults to stdin.",
    )
    parser.add_argument("--expected-chat-id", default=None, help="Optional chat_id/open_chat_id to require.")
    parser.add_argument("--min-passive-messages", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = args.event_log.read_text(encoding="utf-8") if args.event_log else sys.stdin.read()
    report = check_passive_message_events(
        text,
        expected_chat_id=args.expected_chat_id,
        min_passive_messages=args.min_passive_messages,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def check_passive_message_events(
    text: str,
    *,
    expected_chat_id: str | None = None,
    min_passive_messages: int = 1,
) -> dict[str, Any]:
    payloads = list(_payloads_from_text(text))
    summary = {
        "total_payloads": len(payloads),
        "passive_group_text_messages": 0,
        "mentioned_group_text_messages": 0,
        "direct_text_messages": 0,
        "reaction_events": 0,
        "non_text_or_ignored_messages": 0,
        "unknown_events": 0,
        "chat_mismatch": 0,
    }
    passive_examples: list[dict[str, Any]] = []
    event_types: dict[str, int] = {}

    for payload in payloads:
        event_type = _event_type(payload)
        event_types[event_type] = event_types.get(event_type, 0) + 1
        if "reaction" in event_type.lower():
            summary["reaction_events"] += 1
            continue

        event = message_event_from_payload(payload)
        if event is None:
            summary["unknown_events"] += 1
            continue
        if expected_chat_id and event.chat_id != expected_chat_id:
            summary["chat_mismatch"] += 1
            continue
        if event.ignore_reason:
            summary["non_text_or_ignored_messages"] += 1
            continue
        if event.chat_type == "group" and not event.bot_mentioned:
            summary["passive_group_text_messages"] += 1
            if len(passive_examples) < 3:
                passive_examples.append(
                    {
                        "message_id": _redacted_id(event.message_id),
                        "chat_id": _redacted_id(event.chat_id),
                        "sender_id": _redacted_id(event.sender_id),
                        "text_preview": _redact_text(event.text[:80]),
                    }
                )
            continue
        if event.chat_type == "group" and event.bot_mentioned:
            summary["mentioned_group_text_messages"] += 1
            continue
        summary["direct_text_messages"] += 1

    ok = summary["passive_group_text_messages"] >= min_passive_messages
    reason = "passive_group_message_seen" if ok else _failure_reason(summary)
    return {
        "ok": ok,
        "gate": "feishu_passive_group_message_event",
        "boundary": BOUNDARY,
        "required": {
            "min_passive_messages": min_passive_messages,
            "expected_chat_id_configured": bool(expected_chat_id),
        },
        "summary": summary,
        "event_types": event_types,
        "passive_examples": passive_examples,
        "reason": reason,
        "next_step": "" if ok else _next_step(reason),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"gate: {report['gate']}",
        f"ok: {str(report['ok']).lower()}",
        f"reason: {report['reason']}",
        f"boundary: {report['boundary']}",
        f"summary: {json.dumps(report['summary'], ensure_ascii=False, sort_keys=True)}",
    ]
    if report.get("next_step"):
        lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


def _payloads_from_text(text: str) -> Iterable[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    parsed = _parse_json(stripped)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        if isinstance(parsed.get("lines"), list):
            return [_payload_from_log_line(item) for item in parsed["lines"] if isinstance(item, dict)]
        return [parsed]

    payloads: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed_line = _parse_json(line)
        if isinstance(parsed_line, dict):
            payloads.append(_payload_from_log_line(parsed_line))
        else:
            payloads.append({"log_message": line})
    return payloads


def _payload_from_log_line(line: dict[str, Any]) -> dict[str, Any]:
    if "header" in line or ("event" in line and "message" in str(line.get("event"))):
        return line
    for key in ("payload", "data", "raw"):
        value = line.get(key)
        if isinstance(value, dict):
            return value
    message = line.get("message")
    if isinstance(message, dict):
        return message
    if isinstance(message, str):
        parsed = _parse_json(message)
        if isinstance(parsed, dict):
            return parsed
        return {"log_message": message}
    return line


def _event_type(payload: dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event_type = header.get("event_type") or payload.get("event_type") or payload.get("type")
    if event_type:
        return str(event_type)
    message = str(payload.get("log_message") or "")
    if "reaction" in message.lower():
        return "reaction_log_line"
    if "im.message.receive_v1" in message:
        return "im.message.receive_v1"
    return "unknown"


def _failure_reason(summary: dict[str, int]) -> str:
    if summary["reaction_events"] and not summary["passive_group_text_messages"]:
        return "reaction_only_no_passive_message_event"
    if summary["mentioned_group_text_messages"] and not summary["passive_group_text_messages"]:
        return "only_at_mention_group_messages_seen"
    if summary["direct_text_messages"] and not summary["passive_group_text_messages"]:
        return "only_direct_messages_seen"
    if summary["chat_mismatch"] and not summary["passive_group_text_messages"]:
        return "expected_chat_not_seen"
    return "passive_group_message_missing"


def _next_step(reason: str) -> str:
    if reason == "reaction_only_no_passive_message_event":
        return (
            "检查 Feishu app event subscription / scopes 是否包含普通群消息事件；"
            "重新发送一条不 @Bot 的群文本消息并导出 listener/OpenClaw event log 重跑。"
        )
    if reason == "only_at_mention_group_messages_seen":
        return "当前只证明 @Bot 群消息可达；需要发送不 @Bot 的普通群文本消息并重跑。"
    if reason == "expected_chat_not_seen":
        return "捕获到了事件但不是目标 chat；确认测试群 chat_id/open_chat_id 和日志来源。"
    return "确认单监听运行后，在已启用群策略的测试群发送普通非 @ 文本消息并重跑。"


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _redacted_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _redact_text(text: str) -> str:
    return ID_PATTERN.sub("<redacted_id>", text)


if __name__ == "__main__":
    raise SystemExit(main())
