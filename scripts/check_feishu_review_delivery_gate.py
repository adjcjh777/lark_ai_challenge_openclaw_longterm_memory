#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

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
LOG_BOUNDARY = (
    "Feishu review delivery evidence gate only; proves captured listener/OpenClaw result shape "
    "for candidate review card, private review DM, and original-card update. "
    "It does not prove production long-running Feishu DM/card delivery."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local review inbox DM/card-action safety gate for Feishu Memory Copilot, "
            "or audit captured Feishu/OpenClaw result logs with --event-log."
        )
    )
    parser.add_argument(
        "--event-log",
        type=Path,
        default=None,
        help="NDJSON/JSON log file to audit for real Feishu review delivery evidence. Defaults to local gate.",
    )
    parser.add_argument(
        "--expected-reviewer-open-id",
        default="",
        help="Optional reviewer/owner open_id/user_id required as the /review private DM target.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.event_log:
        report = check_review_delivery_log_events(
            args.event_log.read_text(encoding="utf-8"),
            expected_reviewer_open_id=args.expected_reviewer_open_id or None,
        )
    else:
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


def check_review_delivery_log_events(text: str, *, expected_reviewer_open_id: str | None = None) -> dict[str, Any]:
    payloads = list(_payloads_from_text(text))
    summary = {
        "total_payloads": len(payloads),
        "candidate_review_cards": 0,
        "review_inbox_results": 0,
        "private_review_dm_results": 0,
        "card_action_update_results": 0,
        "missing_token_fail_closed_results": 0,
        "card_action_triggers_without_result": 0,
        "private_review_target_mismatch": 0,
        "unsupported_payloads": 0,
    }
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    examples: list[dict[str, Any]] = []
    event_types: dict[str, int] = {}

    for payload in payloads:
        event_type = _event_type(payload)
        event_types[event_type] = event_types.get(event_type, 0) + 1

        result = _result_payload(payload)
        if result is None:
            handled_log_event = False
            if event_type == "card.action.trigger" or _is_openclaw_card_action_trigger_log(payload):
                summary["card_action_triggers_without_result"] += 1
                handled_log_event = True
            if _is_openclaw_card_action_update_log(payload):
                summary["card_action_update_results"] += 1
                handled_log_event = True
            if not handled_log_event:
                summary["unsupported_payloads"] += 1
            continue

        if _is_candidate_review_card(result):
            summary["candidate_review_cards"] += 1
            _append_example(examples, result, "candidate_review_card")
        if result.get("tool") == "memory.review_inbox":
            summary["review_inbox_results"] += 1
            if _is_private_review_dm(result):
                if _private_review_targets_expected(result, expected_reviewer_open_id):
                    summary["private_review_dm_results"] += 1
                    _append_example(examples, result, "private_review_dm")
                else:
                    summary["private_review_target_mismatch"] += 1
        if _is_card_action_update(result):
            summary["card_action_update_results"] += 1
            _append_example(examples, result, "card_action_update")
        if _is_missing_token_fail_closed(result):
            summary["missing_token_fail_closed_results"] += 1
            _append_example(examples, result, "missing_token_fail_closed")

    _record_check(
        checks,
        failures,
        "candidate_review_card_seen",
        summary["candidate_review_cards"] >= 1,
        {"count": summary["candidate_review_cards"]},
    )
    _record_check(
        checks,
        failures,
        "private_review_dm_seen",
        summary["private_review_dm_results"] >= 1,
        {
            "review_inbox_results": summary["review_inbox_results"],
            "private_review_dm_results": summary["private_review_dm_results"],
            "private_review_target_mismatch": summary["private_review_target_mismatch"],
            "expected_reviewer_open_id_configured": bool(expected_reviewer_open_id),
        },
    )
    _record_check(
        checks,
        failures,
        "card_action_updates_original_card_seen",
        summary["card_action_update_results"] >= 1,
        {
            "card_action_update_results": summary["card_action_update_results"],
            "card_action_triggers_without_result": summary["card_action_triggers_without_result"],
        },
    )
    _record_check(
        checks,
        failures,
        "missing_card_token_fail_closed_seen",
        summary["missing_token_fail_closed_results"] >= 1,
        {"count": summary["missing_token_fail_closed_results"]},
    )

    reason = "review_delivery_e2e_evidence_seen" if not failures else _log_failure_reason(summary)
    return {
        "ok": not failures,
        "gate": "feishu_review_delivery_evidence",
        "boundary": LOG_BOUNDARY,
        "checks": checks,
        "summary": summary,
        "event_types": event_types,
        "examples": examples,
        "failures": failures,
        "reason": reason,
        "next_step": "" if not failures else _log_next_step(reason),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"gate: {report['gate']}",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
    ]
    if report.get("reason"):
        lines.append(f"reason: {report['reason']}")
    if report.get("summary"):
        lines.append(f"summary: {json.dumps(report['summary'], ensure_ascii=False, sort_keys=True)}")
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status']}")
    if report["failures"]:
        lines.append(f"failures: {', '.join(report['failures'])}")
    if report.get("next_step"):
        lines.append(f"next_step: {report['next_step']}")
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
        return [_payload_from_log_line(parsed)]

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
    if "result" in line or "tool" in line or "tool_result" in line or "header" in line:
        return line
    raw_line = line.get("raw_line")
    if isinstance(raw_line, str):
        parsed = _parse_json(raw_line)
        if isinstance(parsed, dict):
            return parsed
        return {"log_message": raw_line}
    for key in ("payload", "data", "raw", "message"):
        value = line.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            parsed = _parse_json(value)
            if isinstance(parsed, dict):
                return parsed
            embedded = _parse_embedded_json(value)
            if isinstance(embedded, dict):
                return embedded
    numbered = _numbered_field_text(line)
    if numbered:
        if "card-action intercept" in numbered:
            return line
        parsed = _parse_json(numbered)
        if isinstance(parsed, dict):
            return parsed
        embedded = _parse_embedded_json(numbered)
        if isinstance(embedded, dict):
            return embedded
    return line


def _result_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
    if result and ("tool" in result or "tool_result" in result or "publish" in result):
        return result
    if "tool" in payload or "tool_result" in payload:
        return payload
    for key in ("payload", "data", "message"):
        value = payload.get(key)
        if isinstance(value, dict):
            nested = _result_payload(value)
            if nested is not None:
                return nested
        if isinstance(value, str):
            parsed = _parse_json(value)
            if not isinstance(parsed, dict):
                parsed = _parse_embedded_json(value)
            if isinstance(parsed, dict):
                nested = _result_payload(parsed)
                if nested is not None:
                    return nested
    numbered = _numbered_field_text(payload)
    if numbered:
        parsed = _parse_json(numbered)
        if not isinstance(parsed, dict):
            parsed = _parse_embedded_json(numbered)
        if isinstance(parsed, dict):
            nested = _result_payload(parsed)
            if nested is not None:
                return nested
    return None


def _event_type(payload: dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event_type = header.get("event_type") or payload.get("event_type") or payload.get("type") or payload.get("event")
    if event_type:
        return str(event_type)
    if _result_payload(payload) is not None:
        return "copilot_result"
    return "unknown"


def _is_candidate_review_card(result: dict[str, Any]) -> bool:
    publish = _publish(result)
    return (
        result.get("tool") == "memory.create_candidate"
        and str(publish.get("mode") or "") in {"interactive", "reply_card", "send_card"}
        and _card_has_memory_action(_card(result))
    )


def _is_private_review_dm(result: dict[str, Any]) -> bool:
    publish = _publish(result)
    targets = publish.get("targets")
    card_open_ids = _card(result).get("open_ids")
    return (
        publish.get("delivery_mode") == "dm"
        and isinstance(targets, list)
        and bool(targets)
        and isinstance(card_open_ids, list)
        and card_open_ids == targets
    )


def _private_review_targets_expected(result: dict[str, Any], expected_reviewer_open_id: str | None) -> bool:
    if not expected_reviewer_open_id:
        return True
    publish = _publish(result)
    targets = publish.get("targets")
    card_open_ids = _card(result).get("open_ids")
    return targets == [expected_reviewer_open_id] and card_open_ids == [expected_reviewer_open_id]


def _is_card_action_update(result: dict[str, Any]) -> bool:
    publish = _publish(result)
    return (
        str(result.get("tool") or "").startswith("memory.")
        and publish.get("mode") == "update_card"
        and bool(publish.get("card_update_token"))
    )


def _is_openclaw_card_action_trigger_log(payload: dict[str, Any]) -> bool:
    text = _log_message_text(payload)
    return (
        "card-action intercept acknowledged immediately" in text
        or "card-action intercept invalid JSON" in text
    )


def _is_openclaw_card_action_update_log(payload: dict[str, Any]) -> bool:
    return "card-action intercept asynchronously updated original card via repo helper" in _log_message_text(payload)


def _is_missing_token_fail_closed(result: dict[str, Any]) -> bool:
    publish = _publish(result)
    return (
        bool(result.get("ignored"))
        and result.get("reason") == "card action update token missing"
        and publish.get("mode") == "card_action_update_token_missing"
    )


def _publish(result: dict[str, Any]) -> dict[str, Any]:
    publish = result.get("publish") if isinstance(result.get("publish"), dict) else {}
    return publish


def _card(result: dict[str, Any]) -> dict[str, Any]:
    publish = _publish(result)
    card = publish.get("card") if isinstance(publish.get("card"), dict) else {}
    return card


def _card_has_memory_action(card: dict[str, Any]) -> bool:
    for element in card.get("elements", []):
        if not isinstance(element, dict) or element.get("tag") != "action":
            continue
        for action in element.get("actions", []):
            if not isinstance(action, dict):
                continue
            value = action.get("value")
            if isinstance(value, dict) and value.get("memory_engine_action"):
                return True
    return False


def _log_message_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("log_message", "message", "raw_line", "payload", "data"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
    numbered = _numbered_field_text(payload)
    if numbered:
        parts.append(numbered)
    return " ".join(parts)


def _append_example(examples: list[dict[str, Any]], result: dict[str, Any], kind: str) -> None:
    if len(examples) >= 4:
        return
    publish = _publish(result)
    examples.append(
        {
            "kind": kind,
            "tool": str(result.get("tool") or ""),
            "message_id": _redacted_id(str(result.get("message_id") or "")),
            "publish_mode": str(publish.get("mode") or ""),
            "delivery_mode": str(publish.get("delivery_mode") or ""),
            "targets": _redacted_ids(publish.get("targets")),
            "card_update_token_present": bool(publish.get("card_update_token")),
        }
    )


def _log_failure_reason(summary: dict[str, int]) -> str:
    if summary["private_review_target_mismatch"] and not summary["private_review_dm_results"]:
        return "private_review_dm_target_mismatch"
    if summary["candidate_review_cards"] and not summary["private_review_dm_results"]:
        return "candidate_card_only_no_private_review_dm"
    if summary["private_review_dm_results"] and not summary["card_action_update_results"]:
        return "private_review_dm_without_card_action_update"
    if summary["card_action_triggers_without_result"] and not summary["card_action_update_results"]:
        return "card_action_trigger_without_update_result"
    if summary["card_action_update_results"] and not summary["missing_token_fail_closed_results"]:
        return "card_action_update_without_missing_token_negative"
    return "review_delivery_e2e_evidence_missing"


def _log_next_step(reason: str) -> str:
    if reason == "private_review_dm_target_mismatch":
        return "当前看到 /review DM，但不是本次 reviewer 目标；请用 expected reviewer 账号重跑并保留 private DM result log。"
    if reason == "candidate_card_only_no_private_review_dm":
        return "当前只看到候选审核卡；请在受控群触发 /review，并保留 private DM delivery result log。"
    if reason == "private_review_dm_without_card_action_update":
        return "当前看到 /review DM；请真实点击审核卡按钮，并保留 card.action -> update_card result log。"
    if reason == "card_action_trigger_without_update_result":
        return "捕获到 card.action.trigger 但没有 update_card result；检查 card action router/listener result 输出。"
    if reason == "card_action_update_without_missing_token_negative":
        return "正向点击已见；如需完整 safety gate，请补一条缺 update token 的 fail-closed 回归证据。"
    return "请在受控群创建候选、触发 /review 私聊、真实点击审核卡，并导出 listener/OpenClaw result log 重跑。"


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_embedded_json(text: str) -> Any:
    route_marker = "feishu-memory-copilot route result "
    marker_index = text.find(route_marker)
    if marker_index >= 0:
        route_json = text[marker_index + len(route_marker) :].strip()
        parsed = _parse_json(route_json)
        if isinstance(parsed, dict):
            return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return _parse_json(text[start : end + 1])


def _numbered_field_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in sorted((key for key in payload.keys() if str(key).isdigit()), key=lambda value: int(str(value))):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return " ".join(parts)


def _redacted_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _redacted_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_redacted_id(str(item)) for item in value[:3]]


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
