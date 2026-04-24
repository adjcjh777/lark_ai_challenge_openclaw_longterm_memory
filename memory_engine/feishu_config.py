from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FeishuConfig:
    bot_mode: str
    default_scope: str | None
    lark_cli: str
    lark_profile: str | None
    lark_as: str
    reply_in_thread: bool


def load_feishu_config() -> FeishuConfig:
    return FeishuConfig(
        bot_mode=os.environ.get("FEISHU_BOT_MODE", "reply").strip() or "reply",
        default_scope=_blank_to_none(os.environ.get("MEMORY_DEFAULT_SCOPE")),
        lark_cli=os.environ.get("LARK_CLI_BIN", "lark-cli").strip() or "lark-cli",
        lark_profile=_blank_to_none(os.environ.get("LARK_CLI_PROFILE")),
        lark_as=os.environ.get("LARK_CLI_AS", "bot").strip() or "bot",
        reply_in_thread=os.environ.get("FEISHU_REPLY_IN_THREAD", "").lower() in {"1", "true", "yes"},
    )


def scope_for_chat(chat_id: str, config: FeishuConfig) -> str:
    if config.default_scope:
        return config.default_scope
    return f"chat:{chat_id}"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
