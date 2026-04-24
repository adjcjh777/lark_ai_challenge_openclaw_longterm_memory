from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeishuTextEvent:
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    text: str
    create_time: int
    raw: dict[str, Any]


def text_event_from_payload(payload: dict[str, Any]) -> FeishuTextEvent | None:
    payload = _unwrap_payload(payload)
    event_type = _event_type(payload)
    if event_type and event_type != "im.message.receive_v1":
        return None

    message = _message(payload)
    if not message:
        message = payload
    message_type = _string(message.get("message_type"))
    has_text = bool(message.get("content") or payload.get("content") or payload.get("text"))
    if message_type and message_type != "text":
        return None
    if not message_type and not has_text:
        return None

    sender = _sender(payload)
    sender_type = _string(sender.get("sender_type") or payload.get("sender_type"))
    if sender_type == "bot":
        return None

    message_id = _string(message.get("message_id") or payload.get("message_id"))
    chat_id = _string(message.get("chat_id") or payload.get("chat_id"))
    if not message_id or not chat_id:
        return None

    text = _content_text(message.get("content") or payload.get("content") or payload.get("text"))
    text = _strip_mentions(text, message.get("mentions") or payload.get("mentions") or [])
    if not text:
        return None

    return FeishuTextEvent(
        message_id=message_id,
        chat_id=chat_id,
        chat_type=_string(message.get("chat_type") or payload.get("chat_type") or "unknown"),
        sender_id=_sender_id(sender, payload),
        text=text,
        create_time=_int(message.get("create_time") or payload.get("create_time")),
        raw=payload,
    )


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "payload"):
        nested = payload.get(key)
        if isinstance(nested, dict) and ("event" in nested or "message_id" in nested):
            return nested
    return payload


def _event_type(payload: dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    return _string(header.get("event_type") or payload.get("event_type") or payload.get("type"))


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    return message


def _sender(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    return sender


def _sender_id(sender: dict[str, Any], payload: dict[str, Any]) -> str:
    sender_id = sender.get("sender_id")
    if isinstance(sender_id, dict):
        for key in ("open_id", "union_id", "user_id"):
            value = _string(sender_id.get(key))
            if value:
                return value
    return _string(payload.get("sender_id") or sender.get("open_id") or sender.get("user_id"))


def _content_text(content: Any) -> str:
    if isinstance(content, dict):
        return _string(content.get("text"))
    if not isinstance(content, str):
        return ""
    stripped = content.strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(parsed, dict):
        return _string(parsed.get("text"))
    return stripped


def _strip_mentions(text: str, mentions: Any) -> str:
    result = text
    if isinstance(mentions, list):
        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            key = _string(mention.get("key"))
            name = _string(mention.get("name"))
            if key:
                result = result.replace(key, "")
            if name:
                result = result.replace(f"@{name}", "")
    result = re.sub(r"^@\S+\s*", "", result.strip())
    return result.strip()


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
