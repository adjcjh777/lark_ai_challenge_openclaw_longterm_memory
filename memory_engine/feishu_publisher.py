from __future__ import annotations

import hashlib
import json
import subprocess
import time
from typing import Any

from .feishu_config import FeishuConfig
from .feishu_events import FeishuTextEvent


class DryRunPublisher:
    def publish(self, event: FeishuTextEvent, text: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
        update_token = _card_update_token(event) if card else None
        return {
            "ok": True,
            "dry_run": True,
            "reply_to": event.message_id,
            "chat_id": event.chat_id,
            "text": text,
            "card": card,
            "mode": "update_card" if update_token else ("interactive" if card else "text"),
            "card_update_token": update_token,
        }


class LarkCliPublisher:
    def __init__(self, config: FeishuConfig):
        self.config = config

    def publish(self, event: FeishuTextEvent, text: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
        if card is not None and self.config.card_mode == "interactive":
            return self._publish_interactive_with_text_fallback(event, text, card)
        return self._publish_text(event, text, idempotency_key=self._idempotency_key(event))

    def _publish_text(self, event: FeishuTextEvent, text: str, *, idempotency_key: str) -> dict[str, Any]:
        if self.config.bot_mode == "send":
            return self._send_text(event, text, idempotency_key=idempotency_key)
        result = self._reply_text(event, text, idempotency_key=idempotency_key)
        if result["ok"]:
            return result
        fallback = self._send_text(event, text, idempotency_key=idempotency_key)
        fallback["reply_error"] = result
        return fallback

    def _publish_interactive_with_text_fallback(
        self, event: FeishuTextEvent, text: str, card: dict[str, Any]
    ) -> dict[str, Any]:
        idempotency_key = self._idempotency_key(event)
        attempts: list[dict[str, Any]] = []
        for attempt_no in range(1, self.config.card_retry_count + 1):
            timeout = self.config.card_timeout_seconds
            update_token = _card_update_token(event)
            if update_token:
                result = self._update_card(event, card, token=update_token, timeout=timeout)
            elif self.config.bot_mode == "send" or event.message_type == "card_action":
                result = self._send_card(event, card, idempotency_key=idempotency_key, timeout=timeout)
            else:
                result = self._reply_card(event, card, idempotency_key=idempotency_key, timeout=timeout)
                if not result["ok"] and _reply_target_missing(result):
                    result = self._send_card(event, card, idempotency_key=idempotency_key, timeout=timeout)
            attempts.append(_attempt_summary(result, attempt_no))
            if result["ok"]:
                return {
                    **result,
                    "card_attempts": attempts,
                    "fallback_used": False,
                    "card_timeout_seconds": timeout,
                }

        if any(attempt.get("timed_out") for attempt in attempts):
            return {
                "ok": False,
                "dry_run": False,
                "mode": "interactive_card",
                "reply_to": event.message_id,
                "chat_id": event.chat_id,
                "text": "",
                "card": card,
                "returncode": None,
                "stdout": "",
                "stderr": "interactive card result unknown after timeout; text fallback suppressed to avoid double-send",
                "timed_out": True,
                "latency_ms": sum(float(attempt.get("latency_ms") or 0) for attempt in attempts),
                "card_attempts": attempts,
                "fallback_used": False,
                "fallback_suppressed": True,
                "fallback_reason": "interactive_card_timeout_ambiguous",
                "card_timeout_seconds": self.config.card_timeout_seconds,
            }

        fallback = self._publish_text(event, text, idempotency_key=idempotency_key)
        fallback["card_attempts"] = attempts
        fallback["fallback_used"] = True
        fallback["fallback_reason"] = "interactive_card_failed_after_retries"
        return fallback

    def _reply_text(self, event: FeishuTextEvent, text: str, *, idempotency_key: str) -> dict[str, Any]:
        command = self._base_command() + [
            "im",
            "+messages-reply",
            "--as",
            self.config.lark_as,
            "--message-id",
            event.message_id,
            "--text",
            text,
            "--idempotency-key",
            idempotency_key,
        ]
        if self.config.reply_in_thread:
            command.append("--reply-in-thread")
        return self._run(command, "reply_text", event, text)

    def _send_text(self, event: FeishuTextEvent, text: str, *, idempotency_key: str) -> dict[str, Any]:
        command = self._base_command() + [
            "im",
            "+messages-send",
            "--as",
            self.config.lark_as,
            "--chat-id",
            event.chat_id,
            "--text",
            text,
            "--idempotency-key",
            idempotency_key,
        ]
        return self._run(command, "send_text", event, text)

    def _reply_card(
        self,
        event: FeishuTextEvent,
        card: dict[str, Any],
        *,
        idempotency_key: str,
        timeout: float,
    ) -> dict[str, Any]:
        command = self._base_command() + [
            "im",
            "+messages-reply",
            "--as",
            self.config.lark_as,
            "--message-id",
            event.message_id,
            "--msg-type",
            "interactive",
            "--content",
            json.dumps(card, ensure_ascii=False, separators=(",", ":")),
            "--idempotency-key",
            idempotency_key,
        ]
        if self.config.reply_in_thread:
            command.append("--reply-in-thread")
        return self._run(command, "reply_card", event, "", card=card, timeout=timeout)

    def _send_card(
        self,
        event: FeishuTextEvent,
        card: dict[str, Any],
        *,
        idempotency_key: str,
        timeout: float,
    ) -> dict[str, Any]:
        command = self._base_command() + [
            "im",
            "+messages-send",
            "--as",
            self.config.lark_as,
            "--chat-id",
            event.chat_id,
            "--msg-type",
            "interactive",
            "--content",
            json.dumps(card, ensure_ascii=False, separators=(",", ":")),
            "--idempotency-key",
            idempotency_key,
        ]
        return self._run(command, "send_card", event, "", card=card, timeout=timeout)

    def _update_card(
        self,
        event: FeishuTextEvent,
        card: dict[str, Any],
        *,
        token: str,
        timeout: float,
    ) -> dict[str, Any]:
        command = self._base_command() + [
            "api",
            "POST",
            "/open-apis/interactive/v1/card/update",
            "--as",
            self.config.lark_as,
            "--data",
            json.dumps({"token": token, "card": card}, ensure_ascii=False, separators=(",", ":")),
        ]
        result = self._run(command, "update_card", event, "", card=card, timeout=timeout)
        result["card_update_token"] = token
        return result

    def _base_command(self) -> list[str]:
        command = [self.config.lark_cli]
        if self.config.lark_profile:
            command.extend(["--profile", self.config.lark_profile])
        return command

    def _run(
        self,
        command: list[str],
        mode: str,
        event: FeishuTextEvent,
        text: str,
        *,
        card: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "dry_run": False,
                "mode": mode,
                "reply_to": event.message_id if mode.startswith("reply") else None,
                "chat_id": event.chat_id,
                "text": text,
                "card": card,
                "returncode": None,
                "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "").strip() if isinstance(exc.stderr, str) else "",
                "timed_out": True,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            }
        return {
            "ok": completed.returncode == 0,
            "dry_run": False,
            "mode": mode,
            "reply_to": event.message_id if mode.startswith("reply") else None,
            "chat_id": event.chat_id,
            "text": text,
            "card": card,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "timed_out": False,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
        }

    def _idempotency_key(self, event: FeishuTextEvent) -> str:
        key = f"feishu-memory-{event.message_id}"
        if len(key) <= 64:
            return key
        digest = hashlib.sha1(event.message_id.encode("utf-8")).hexdigest()[:32]
        return f"feishu-memory-{digest}"


def _reply_target_missing(result: dict[str, Any]) -> bool:
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    return "230011" in text or "231003" in text


def _card_update_token(event: FeishuTextEvent) -> str | None:
    if getattr(event, "message_type", None) != "card_action":
        return None
    raw = getattr(event, "raw", None)
    if not isinstance(raw, dict):
        return None
    payload_event = raw.get("event") if isinstance(raw.get("event"), dict) else raw
    token = payload_event.get("token") if isinstance(payload_event, dict) else None
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _attempt_summary(result: dict[str, Any], attempt_no: int) -> dict[str, Any]:
    return {
        "attempt": attempt_no,
        "ok": bool(result.get("ok")),
        "mode": result.get("mode"),
        "returncode": result.get("returncode"),
        "timed_out": bool(result.get("timed_out")),
        "latency_ms": result.get("latency_ms"),
        "stdout": _clip(result.get("stdout")),
        "stderr": _clip(result.get("stderr")),
    }


def _clip(value: Any, limit: int = 300) -> str:
    text = "" if value is None else str(value).strip()
    return text if len(text) <= limit else f"{text[:limit]}..."
