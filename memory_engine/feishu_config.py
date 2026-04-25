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
    card_mode: str = "interactive"
    card_retry_count: int = 3
    card_timeout_seconds: float = 2.0


def load_feishu_config() -> FeishuConfig:
    return FeishuConfig(
        bot_mode=os.environ.get("FEISHU_BOT_MODE", "reply").strip() or "reply",
        default_scope=_blank_to_none(os.environ.get("MEMORY_DEFAULT_SCOPE")),
        lark_cli=os.environ.get("LARK_CLI_BIN", "lark-cli").strip() or "lark-cli",
        lark_profile=_blank_to_none(os.environ.get("LARK_CLI_PROFILE")),
        lark_as=os.environ.get("LARK_CLI_AS", "bot").strip() or "bot",
        reply_in_thread=os.environ.get("FEISHU_REPLY_IN_THREAD", "").lower() in {"1", "true", "yes"},
        card_mode=os.environ.get("FEISHU_CARD_MODE", "interactive").strip().lower() or "interactive",
        card_retry_count=_positive_int(os.environ.get("FEISHU_CARD_RETRY_COUNT"), default=3),
        card_timeout_seconds=_positive_float(os.environ.get("FEISHU_CARD_TIMEOUT_SECONDS"), default=2.0),
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


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float(value: str | None, *, default: float) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
