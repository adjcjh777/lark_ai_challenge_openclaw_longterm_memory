from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeishuTextEvent:
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    sender_type: str
    message_type: str
    text: str
    create_time: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class FeishuMessageEvent:
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    sender_type: str
    message_type: str
    text: str
    create_time: int
    raw: dict[str, Any]
    ignore_reason: str | None = None

    def as_text_event(self) -> FeishuTextEvent:
        return FeishuTextEvent(
            message_id=self.message_id,
            chat_id=self.chat_id,
            chat_type=self.chat_type,
            sender_id=self.sender_id,
            sender_type=self.sender_type,
            message_type=self.message_type,
            text=self.text,
            create_time=self.create_time,
            raw=self.raw,
        )


def text_event_from_payload(payload: dict[str, Any]) -> FeishuTextEvent | None:
    event = message_event_from_payload(payload)
    if event is None or event.ignore_reason is not None:
        return None
    return event.as_text_event()


def message_event_from_payload(payload: dict[str, Any]) -> FeishuMessageEvent | None:
    payload = _unwrap_payload(payload)
    event_type = _event_type(payload)
    if event_type == "card.action.trigger":
        return _card_action_event_from_payload(payload)
    if event_type and event_type != "im.message.receive_v1":
        return None

    message = _message(payload)
    if not message:
        message = payload
    message_type = _string(message.get("message_type"))
    has_text = bool(message.get("content") or payload.get("content") or payload.get("text"))
    if not message_type and not has_text:
        return None

    sender = _sender(payload)
    sender_type = _string(sender.get("sender_type") or payload.get("sender_type"))

    message_id = _string(message.get("message_id") or payload.get("message_id"))
    chat_id = _string(message.get("chat_id") or payload.get("chat_id"))
    if not message_id or not chat_id:
        return None

    text = _content_text(message.get("content") or payload.get("content") or payload.get("text"))
    text = _strip_mentions(text, message.get("mentions") or payload.get("mentions") or [])
    ignore_reason = None
    if sender_type == "bot":
        ignore_reason = "bot self message"
    elif message_type and message_type != "text":
        ignore_reason = f"non-text message: {message_type}"
    elif not text:
        ignore_reason = "empty text message"

    return FeishuMessageEvent(
        message_id=message_id,
        chat_id=chat_id,
        chat_type=_string(message.get("chat_type") or payload.get("chat_type") or "unknown"),
        sender_id=_sender_id(sender, payload),
        sender_type=sender_type or "unknown",
        message_type=message_type or "text",
        text=text,
        create_time=_int(message.get("create_time") or payload.get("create_time")),
        raw=payload,
        ignore_reason=ignore_reason,
    )


def _card_action_event_from_payload(payload: dict[str, Any]) -> FeishuMessageEvent | None:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    value = action.get("value") if isinstance(action.get("value"), dict) else {}
    command = _command_from_card_value(value)
    if not command:
        return None

    context = event.get("context") if isinstance(event.get("context"), dict) else {}
    operator = event.get("operator") if isinstance(event.get("operator"), dict) else {}
    chat_id = _string(
        context.get("open_chat_id")
        or context.get("chat_id")
        or event.get("open_chat_id")
        or event.get("chat_id")
    )
    if not chat_id:
        return None

    token = _string(event.get("token") or action.get("action_id") or action.get("name"))
    if not token:
        token = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    sender_id = _string(operator.get("open_id") or operator.get("operator_id") or event.get("operator_id"))
    return FeishuMessageEvent(
        message_id=f"card_action_{token}",
        chat_id=chat_id,
        chat_type="group",
        sender_id=sender_id or "card_operator",
        sender_type="user",
        message_type="card_action",
        text=command,
        create_time=_int(event.get("create_time") or payload.get("create_time")),
        raw=payload,
        ignore_reason=None,
    )


def _command_from_card_value(value: dict[str, Any]) -> str:
    action = _string(value.get("memory_engine_action") or value.get("command") or value.get("action"))
    if action in {"confirm", "reject"}:
        candidate_id = _string(value.get("candidate_id") or value.get("memory_id"))
        return f"/{action} {candidate_id}" if candidate_id else ""
    if action == "versions":
        memory_id = _string(value.get("memory_id"))
        return f"/versions {memory_id}" if memory_id else ""
    return ""


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
