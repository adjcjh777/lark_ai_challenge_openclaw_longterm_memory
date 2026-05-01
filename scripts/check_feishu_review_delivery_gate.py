#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.feishu_live import handle_copilot_message_event  # noqa: E402
from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.feishu_config import FeishuConfig  # noqa: E402
from memory_engine.feishu_events import message_event_from_payload  # noqa: E402
from memory_engine.feishu_publisher import DryRunPublisher  # noqa: E402

CHAT_ID = "oc_review_delivery_gate"
USER_OPEN_ID = "ou_review_delivery_owner"
SCOPE = "project:feishu_ai_challenge"
BOUNDARY = (
    "Local Feishu review delivery gate only; proves CopilotService review routing, "
    "private review-card addressing, and card-action update-token handling in-process. "
    "It does not prove production long-running Feishu DM/card delivery."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a local review inbox DM/card-action safety gate for Feishu Memory Copilot."
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = check_review_delivery_gate()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def check_review_delivery_gate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    config = FeishuConfig(
        bot_mode="reply",
        default_scope=SCOPE,
        lark_cli="lark-cli",
        lark_profile="feishu-ai-challenge",
        lark_as="bot",
        reply_in_thread=False,
        card_mode="interactive",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        conn = connect(Path(temp_dir) / "memory.sqlite")
        init_db(conn)
        try:
            with _temporary_env(
                {
                    "COPILOT_FEISHU_ALLOWED_CHAT_IDS": CHAT_ID,
                    "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "",
                }
            ):
                created = _handle(
                    conn,
                    config,
                    _message_payload(
                        "om_review_gate_create",
                        "/remember 决定：评委演示审核卡片必须私聊投递，并且点击后只更新原卡片。",
                    ),
                )
                candidate_id = str(created.get("tool_result", {}).get("candidate_id") or "")
                _record_check(
                    checks,
                    failures,
                    "candidate_created",
                    bool(created.get("ok"))
                    and created.get("tool") == "memory.create_candidate"
                    and bool(candidate_id)
                    and created.get("publish", {}).get("mode") == "interactive",
                    {
                        "tool": created.get("tool"),
                        "publish_mode": created.get("publish", {}).get("mode"),
                        "candidate_id_present": bool(candidate_id),
                    },
                )

                review = _handle(conn, config, _message_payload("om_review_gate_inbox", "/review"))
                review_card = review.get("publish", {}).get("card") if isinstance(review.get("publish"), dict) else {}
                _record_check(
                    checks,
                    failures,
                    "review_inbox_private_dm_targeted",
                    bool(review.get("ok"))
                    and review.get("tool") == "memory.review_inbox"
                    and review.get("publish", {}).get("delivery_mode") == "dm"
                    and review.get("publish", {}).get("targets") == [USER_OPEN_ID]
                    and isinstance(review_card, dict)
                    and review_card.get("open_ids") == [USER_OPEN_ID],
                    {
                        "tool": review.get("tool"),
                        "delivery_mode": review.get("publish", {}).get("delivery_mode"),
                        "targets": review.get("publish", {}).get("targets"),
                        "card_open_ids": review_card.get("open_ids") if isinstance(review_card, dict) else None,
                    },
                )

                confirm_value = _button_value(review_card, "确认第1条") or _button_value(review_card, "确认保存")
                confirmed = _handle(
                    conn,
                    config,
                    _card_action_payload(confirm_value, token="card_token_review_gate"),
                )
                _record_check(
                    checks,
                    failures,
                    "card_action_updates_original_card",
                    bool(confirmed.get("ok"))
                    and confirmed.get("tool") == "memory.confirm"
                    and confirmed.get("publish", {}).get("mode") == "update_card"
                    and confirmed.get("publish", {}).get("card_update_token") == "card_token_review_gate"
                    and confirmed.get("tool_result", {}).get("memory", {}).get("status") == "active",
                    {
                        "tool": confirmed.get("tool"),
                        "publish_mode": confirmed.get("publish", {}).get("mode"),
                        "card_update_token_present": bool(confirmed.get("publish", {}).get("card_update_token")),
                        "memory_status": confirmed.get("tool_result", {}).get("memory", {}).get("status"),
                    },
                )

                missing_conn = connect(Path(temp_dir) / "missing-token.sqlite")
                init_db(missing_conn)
                try:
                    missing_token_created = _handle(
                        missing_conn,
                        config,
                        _message_payload(
                            "om_review_gate_missing_token_create",
                            "/remember 决定：缺少卡片 token 的点击必须 fail closed。",
                        ),
                    )
                    missing_candidate_id = str(missing_token_created.get("tool_result", {}).get("candidate_id") or "")
                    missing_card = missing_token_created.get("publish", {}).get("card")
                    missing_confirm_value = _button_value(missing_card, "确认保存")
                    missing_token_click = _handle(
                        missing_conn,
                        config,
                        _card_action_payload(missing_confirm_value, token=None),
                    )
                    row = missing_conn.execute(
                        "SELECT status FROM memories WHERE id = ?",
                        (missing_candidate_id,),
                    ).fetchone()
                finally:
                    missing_conn.close()
                _record_check(
                    checks,
                    failures,
                    "missing_card_token_does_not_mutate",
                    bool(missing_token_click.get("ignored"))
                    and missing_token_click.get("reason") == "card action update token missing"
                    and missing_token_click.get("publish", {}).get("mode") == "card_action_update_token_missing"
                    and row is not None
                    and row["status"] == "candidate",
                    {
                        "ignored": bool(missing_token_click.get("ignored")),
                        "reason": missing_token_click.get("reason"),
                        "publish_mode": missing_token_click.get("publish", {}).get("mode"),
                        "candidate_status": row["status"] if row is not None else None,
                    },
                )
        finally:
            conn.close()

    return {
        "ok": not failures,
        "gate": "feishu_review_delivery_gate",
        "boundary": BOUNDARY,
        "checks": checks,
        "failures": failures,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"gate: {report['gate']}",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
    ]
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status']}")
    if report["failures"]:
        lines.append(f"failures: {', '.join(report['failures'])}")
    return "\n".join(lines)


def _handle(conn: Any, config: FeishuConfig, payload: dict[str, Any]) -> dict[str, Any]:
    event = message_event_from_payload(payload)
    if event is None:
        return {"ok": False, "error": "payload did not parse into a Feishu event"}
    return handle_copilot_message_event(conn, event, DryRunPublisher(), config, dry_run=True)


def _record_check(
    checks: list[dict[str, Any]],
    failures: list[str],
    name: str,
    passed: bool,
    details: dict[str, Any],
) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail", "details": details})
    if not passed:
        failures.append(name)


def _message_payload(message_id: str, text: str) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": USER_OPEN_ID},
                "sender_type": "user",
            },
            "message": {
                "message_id": message_id,
                "chat_id": CHAT_ID,
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": f"@_user_1 {text}"}, ensure_ascii=False),
                "mentions": [
                    {
                        "id": {"open_id": "ou_bot_open_id"},
                        "key": "@_user_1",
                        "mentioned_type": "bot",
                        "name": "Feishu Memory Engine bot",
                    }
                ],
                "create_time": "1777647600000",
            },
        },
    }


def _card_action_payload(action_value: dict[str, Any] | None, *, token: str | None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "operator": {"open_id": USER_OPEN_ID},
        "context": {"open_chat_id": CHAT_ID},
        "action": {"value": action_value or {}},
    }
    if token is not None:
        event["token"] = token
    return {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger"},
        "event": event,
    }


def _button_value(card: Any, label: str) -> dict[str, Any] | None:
    if not isinstance(card, dict):
        return None
    for element in card.get("elements", []):
        if not isinstance(element, dict) or element.get("tag") != "action":
            continue
        for action in element.get("actions", []):
            if not isinstance(action, dict):
                continue
            text = action.get("text") if isinstance(action.get("text"), dict) else {}
            if text.get("content") == label and isinstance(action.get("value"), dict):
                return action["value"]
    return None


@contextmanager
def _temporary_env(values: dict[str, str]) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


if __name__ == "__main__":
    raise SystemExit(main())
