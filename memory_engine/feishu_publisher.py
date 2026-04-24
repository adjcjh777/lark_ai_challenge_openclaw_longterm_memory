from __future__ import annotations

import subprocess
from typing import Any

from .feishu_config import FeishuConfig
from .feishu_events import FeishuTextEvent


class DryRunPublisher:
    def publish(self, event: FeishuTextEvent, text: str) -> dict[str, Any]:
        return {
            "ok": True,
            "dry_run": True,
            "reply_to": event.message_id,
            "chat_id": event.chat_id,
            "text": text,
        }


class LarkCliPublisher:
    def __init__(self, config: FeishuConfig):
        self.config = config

    def publish(self, event: FeishuTextEvent, text: str) -> dict[str, Any]:
        if self.config.bot_mode == "send":
            return self._send(event, text)
        result = self._reply(event, text)
        if result["ok"]:
            return result
        fallback = self._send(event, text)
        fallback["reply_error"] = result
        return fallback

    def _reply(self, event: FeishuTextEvent, text: str) -> dict[str, Any]:
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
            f"feishu-memory-{event.message_id}",
        ]
        if self.config.reply_in_thread:
            command.append("--reply-in-thread")
        return self._run(command, "reply", event, text)

    def _send(self, event: FeishuTextEvent, text: str) -> dict[str, Any]:
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
            f"feishu-memory-{event.message_id}",
        ]
        return self._run(command, "send", event, text)

    def _base_command(self) -> list[str]:
        command = [self.config.lark_cli]
        if self.config.lark_profile:
            command.extend(["--profile", self.config.lark_profile])
        return command

    def _run(self, command: list[str], mode: str, event: FeishuTextEvent, text: str) -> dict[str, Any]:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        return {
            "ok": completed.returncode == 0,
            "dry_run": False,
            "mode": mode,
            "reply_to": event.message_id if mode == "reply" else None,
            "chat_id": event.chat_id,
            "text": text,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
