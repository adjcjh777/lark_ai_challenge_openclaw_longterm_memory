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
        if card and _is_card_action_without_update_token(event):
            return _card_action_update_token_missing_result(event, card, dry_run=True)
        direct_targets = _card_direct_targets(card) if card and not update_token else []
        return {
            "ok": True,
            "dry_run": True,
            "reply_to": event.message_id,
            "chat_id": None if direct_targets else event.chat_id,
            "text": text,
            "card": card,
            "mode": ("update_card" if update_token else ("interactive" if card else "text")),
            "card_update_token": update_token,
            "delivery_mode": "dm" if direct_targets else "chat",
            "direct_mode": "direct_interactive" if direct_targets else None,
            "targets": direct_targets,
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
        if _is_card_action_without_update_token(event):
            return _card_action_update_token_missing_result(event, card, dry_run=False)

        direct_targets = _card_direct_targets(card)
        if direct_targets and not _card_update_token(event):
            return self._publish_direct_interactive_with_text_fallback(event, text, card, direct_targets)

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

        if _card_targets_specific_users(card):
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
                "stderr": "interactive card failed; text fallback suppressed for targeted review card",
                "timed_out": False,
                "latency_ms": sum(float(attempt.get("latency_ms") or 0) for attempt in attempts),
                "card_attempts": attempts,
                "fallback_used": False,
                "fallback_suppressed": True,
                "fallback_reason": "targeted_review_card_text_fallback_suppressed",
                "card_timeout_seconds": self.config.card_timeout_seconds,
            }

        fallback = self._publish_text(event, text, idempotency_key=idempotency_key)
        fallback["card_attempts"] = attempts
        fallback["fallback_used"] = True
        fallback["fallback_reason"] = "interactive_card_failed_after_retries"
        return fallback

    def _publish_direct_interactive_with_text_fallback(
        self,
        event: FeishuTextEvent,
        text: str,
        card: dict[str, Any],
        targets: list[str],
    ) -> dict[str, Any]:
        target_results: list[dict[str, Any]] = []
        for target in targets:
            target_results.append(self._publish_direct_interactive_target(event, text, card, target))

        ok = all(bool(result.get("ok")) for result in target_results)
        return {
            "ok": ok,
            "dry_run": False,
            "mode": "direct_interactive",
            "delivery_mode": "dm",
            "reply_to": None,
            "chat_id": None,
            "targets": targets,
            "text": text if not ok else "",
            "card": card,
            "returncode": 0 if ok else 1,
            "stdout": "",
            "stderr": "" if ok else "one or more targeted DM deliveries failed",
            "timed_out": any(bool(result.get("timed_out")) for result in target_results),
            "latency_ms": sum(float(result.get("latency_ms") or 0) for result in target_results),
            "target_results": target_results,
            "fallback_used": any(bool(result.get("fallback_used")) for result in target_results),
            "fallback_suppressed": any(bool(result.get("fallback_suppressed")) for result in target_results),
            "card_timeout_seconds": self.config.card_timeout_seconds,
        }

    def _publish_direct_interactive_target(
        self,
        event: FeishuTextEvent,
        text: str,
        card: dict[str, Any],
        target: str,
    ) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        for attempt_no in range(1, self.config.card_retry_count + 1):
            result = self._send_direct_card(
                event,
                target,
                card,
                idempotency_key=self._direct_idempotency_key(event, target, "card"),
                timeout=self.config.card_timeout_seconds,
            )
            attempts.append(_attempt_summary(result, attempt_no))
            if result["ok"]:
                result["card_attempts"] = attempts
                result["fallback_used"] = False
                result["target"] = target
                return result

        timed_out = any(attempt.get("timed_out") for attempt in attempts)
        if timed_out:
            return {
                "ok": False,
                "dry_run": False,
                "mode": "send_direct_card",
                "delivery_mode": "dm",
                "reply_to": None,
                "chat_id": None,
                "target": target,
                "text": "",
                "card": card,
                "returncode": None,
                "stdout": "",
                "stderr": "direct interactive card result unknown after timeout; text fallback suppressed",
                "timed_out": True,
                "latency_ms": sum(float(attempt.get("latency_ms") or 0) for attempt in attempts),
                "card_attempts": attempts,
                "fallback_used": False,
                "fallback_suppressed": True,
                "fallback_reason": "direct_interactive_card_timeout_ambiguous",
                "card_timeout_seconds": self.config.card_timeout_seconds,
            }

        fallback = self._send_direct_text(
            event,
            target,
            text,
            idempotency_key=self._direct_idempotency_key(event, target, "text"),
        )
        fallback["card_attempts"] = attempts
        fallback["fallback_used"] = True
        fallback["fallback_reason"] = "direct_interactive_card_failed_after_retries"
        fallback["target"] = target
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

    def _send_direct_text(
        self,
        event: FeishuTextEvent,
        target: str,
        text: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = self._base_command() + [
            "im",
            "+messages-send",
            "--as",
            self.config.lark_as,
            "--user-id",
            target,
            "--text",
            text,
            "--idempotency-key",
            idempotency_key,
        ]
        result = self._run(command, "send_direct_text", event, text)
        result["chat_id"] = None
        result["delivery_mode"] = "dm"
        result["target"] = target
        return result

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

    def _send_direct_card(
        self,
        event: FeishuTextEvent,
        target: str,
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
            "--user-id",
            target,
            "--msg-type",
            "interactive",
            "--content",
            json.dumps(card, ensure_ascii=False, separators=(",", ":")),
            "--idempotency-key",
            idempotency_key,
        ]
        result = self._run(command, "send_direct_card", event, "", card=card, timeout=timeout)
        result["chat_id"] = None
        result["delivery_mode"] = "dm"
        result["target"] = target
        return result

    def _update_card(
        self,
        event: FeishuTextEvent,
        card: dict[str, Any],
        *,
        token: str,
        timeout: float,
    ) -> dict[str, Any]:
        update_card = _with_card_open_ids(card, event.sender_id)
        command = self._base_command() + [
            "api",
            "POST",
            "/open-apis/interactive/v1/card/update",
            "--as",
            self.config.lark_as,
            "--data",
            json.dumps({"token": token, "card": update_card}, ensure_ascii=False, separators=(",", ":")),
        ]
        result = self._run(command, "update_card", event, "", card=update_card, timeout=timeout)
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
        if len(key) <= 50:
            return key
        digest = hashlib.sha1(event.message_id.encode("utf-8")).hexdigest()[:32]
        return f"feishu-memory-{digest}"

    def _direct_idempotency_key(self, event: FeishuTextEvent, target: str, kind: str) -> str:
        event_digest = hashlib.sha1(f"{event.message_id}:{target}:{kind}".encode("utf-8")).hexdigest()[:32]
        return f"feishu-memory-{event_digest}"


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


def _is_card_action_without_update_token(event: FeishuTextEvent) -> bool:
    return getattr(event, "message_type", None) == "card_action" and _card_update_token(event) is None


def _card_action_update_token_missing_result(
    event: FeishuTextEvent,
    card: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": dry_run,
        "mode": "card_action_update_token_missing",
        "reply_to": event.message_id,
        "chat_id": event.chat_id,
        "text": "",
        "card": card,
        "returncode": None,
        "stdout": "",
        "stderr": "card action update token missing; duplicate card/text fallback suppressed",
        "timed_out": False,
        "latency_ms": 0,
        "card_attempts": [],
        "fallback_used": False,
        "fallback_suppressed": True,
        "fallback_reason": "card_action_update_token_missing",
        "card_update_token": None,
    }


def _with_card_open_ids(card: dict[str, Any], open_id: str) -> dict[str, Any]:
    if not open_id:
        return card
    existing = card.get("open_ids")
    if isinstance(existing, list) and open_id in existing:
        update_card = dict(card)
    else:
        open_ids = [item for item in existing if isinstance(item, str)] if isinstance(existing, list) else []
        update_card = dict(card)
        update_card["open_ids"] = [*open_ids, open_id]
    config = update_card.get("config")
    if isinstance(config, dict):
        update_card["config"] = {**config, "update_multi": False}
    else:
        update_card["config"] = {"update_multi": False}
    return update_card


def _card_targets_specific_users(card: dict[str, Any]) -> bool:
    return bool(_card_direct_targets(card))


def _card_direct_targets(card: dict[str, Any] | None) -> list[str]:
    if not isinstance(card, dict):
        return []
    targets: list[str] = []
    for key in ("open_ids", "user_ids"):
        value = card.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, str):
                continue
            target = item.strip()
            if target and target not in targets:
                targets.append(target)
    return targets


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
