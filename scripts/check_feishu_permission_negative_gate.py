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
    "Feishu live negative permission gate only; proves captured non-reviewer /enable_memory denial shape, "
    "not production long-running authorization or full RBAC."
)
ID_PATTERN = re.compile(r"\b(?:ou|oc|om|cli|ou_|oc_|om_)[A-Za-z0-9_-]+\b")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check captured Feishu/OpenClaw listener output for a non-reviewer /enable_memory denial. "
            "Use this after a second real user tries @Bot /enable_memory in a controlled group."
        )
    )
    parser.add_argument("--event-log", type=Path, default=None, help="NDJSON/JSON log file. Defaults to stdin.")
    parser.add_argument("--expected-chat-id", default=None, help="Optional chat_id/open_chat_id to require.")
    parser.add_argument("--expected-actor-id", default=None, help="Optional non-reviewer open_id/user_id to require.")
    parser.add_argument("--min-denied", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = args.event_log.read_text(encoding="utf-8") if args.event_log else sys.stdin.read()
    report = check_permission_negative_events(
        text,
        expected_chat_id=args.expected_chat_id,
        expected_actor_id=args.expected_actor_id,
        min_denied=args.min_denied,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def check_permission_negative_events(
    text: str,
    *,
    expected_chat_id: str | None = None,
    expected_actor_id: str | None = None,
    min_denied: int = 1,
) -> dict[str, Any]:
    payloads = list(_payloads_from_text(text))
    summary = {
        "total_payloads": len(payloads),
        "enable_memory_attempt_events": 0,
        "denied_enable_memory_results": 0,
        "allowed_enable_memory_results": 0,
        "denied_group_policy_audit_events": 0,
        "chat_mismatch": 0,
        "actor_mismatch": 0,
        "unsupported_payloads": 0,
    }
    denied_examples: list[dict[str, Any]] = []
    event_types: dict[str, int] = {}

    for payload in payloads:
        event_type = _event_type(payload)
        event_types[event_type] = event_types.get(event_type, 0) + 1

        result = _result_payload(payload)
        if result is not None:
            _classify_result(
                result,
                summary=summary,
                denied_examples=denied_examples,
                expected_chat_id=expected_chat_id,
                expected_actor_id=expected_actor_id,
            )
            continue

        if _is_group_policy_denied_audit(payload):
            if not _matches_expected(payload, expected_chat_id=expected_chat_id, expected_actor_id=expected_actor_id):
                continue
            summary["denied_group_policy_audit_events"] += 1
            continue

        event = message_event_from_payload(payload)
        if event is not None and not event.ignore_reason and event.text.strip().startswith("/enable_memory"):
            if expected_chat_id and event.chat_id != expected_chat_id:
                summary["chat_mismatch"] += 1
                continue
            if expected_actor_id and event.sender_id != expected_actor_id:
                summary["actor_mismatch"] += 1
                continue
            summary["enable_memory_attempt_events"] += 1
            continue

        summary["unsupported_payloads"] += 1

    ok = summary["denied_enable_memory_results"] >= min_denied
    reason = "non_reviewer_enable_memory_denied" if ok else _failure_reason(summary)
    return {
        "ok": ok,
        "gate": "feishu_permission_negative_live",
        "boundary": BOUNDARY,
        "required": {
            "min_denied": min_denied,
            "expected_chat_id_configured": bool(expected_chat_id),
            "expected_actor_id_configured": bool(expected_actor_id),
            "requires_denied_result_not_audit_only": True,
        },
        "summary": summary,
        "event_types": event_types,
        "denied_examples": denied_examples,
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


def _classify_result(
    result: dict[str, Any],
    *,
    summary: dict[str, int],
    denied_examples: list[dict[str, Any]],
    expected_chat_id: str | None,
    expected_actor_id: str | None,
) -> None:
    if result.get("tool") != "copilot.group_enable_memory":
        summary["unsupported_payloads"] += 1
        return
    if not _matches_expected(result, expected_chat_id=expected_chat_id, expected_actor_id=expected_actor_id):
        _record_expected_mismatch(
            result,
            summary=summary,
            expected_chat_id=expected_chat_id,
            expected_actor_id=expected_actor_id,
        )
        return
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    summary["enable_memory_attempt_events"] += 1
    denied = (
        tool_result.get("status") == "permission_denied"
        or tool_result.get("ok") is False
        and _error_code(tool_result) == "permission_denied"
    )
    if denied:
        summary["denied_enable_memory_results"] += 1
        if len(denied_examples) < 3:
            denied_examples.append(
                {
                    "message_id": _redacted_id(str(result.get("message_id") or "")),
                    "chat_id": _redacted_id(_chat_id(result)),
                    "actor_id": _redacted_id(_actor_id(result)),
                    "reason_code": _reason_code(tool_result),
                    "publish_mode": _publish_mode(result),
                }
            )
    elif tool_result.get("status") in {"enabled", "active"} or tool_result.get("ok") is True:
        summary["allowed_enable_memory_results"] += 1


def _result_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
    if result and ("tool" in result or "tool_result" in result):
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


def _is_group_policy_denied_audit(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("event_type") or "") == "feishu_group_policy_denied"
        and str(payload.get("permission_decision") or "") == "deny"
        and str(payload.get("reason_code") or "") == "reviewer_or_admin_required"
    )


def _matches_expected(
    payload: dict[str, Any],
    *,
    expected_chat_id: str | None,
    expected_actor_id: str | None,
) -> bool:
    chat_id = _chat_id(payload)
    actor_id = _actor_id(payload)
    if expected_chat_id and chat_id and chat_id != expected_chat_id:
        return False
    if expected_chat_id and not chat_id:
        return False
    if expected_actor_id and actor_id and actor_id != expected_actor_id:
        return False
    if expected_actor_id and not actor_id:
        return False
    return True


def _record_expected_mismatch(
    payload: dict[str, Any],
    *,
    summary: dict[str, int],
    expected_chat_id: str | None,
    expected_actor_id: str | None,
) -> None:
    chat_id = _chat_id(payload)
    actor_id = _actor_id(payload)
    if expected_chat_id and chat_id != expected_chat_id:
        summary["chat_mismatch"] += 1
    if expected_actor_id and actor_id != expected_actor_id:
        summary["actor_mismatch"] += 1


def _chat_id(payload: dict[str, Any]) -> str:
    publish = payload.get("publish") if isinstance(payload.get("publish"), dict) else {}
    tool_result = payload.get("tool_result") if isinstance(payload.get("tool_result"), dict) else {}
    group_policy = tool_result.get("group_policy") if isinstance(tool_result.get("group_policy"), dict) else {}
    source_context = payload.get("source_context")
    if isinstance(source_context, str):
        parsed = _parse_json(source_context)
        source_context = parsed if isinstance(parsed, dict) else {}
    if not isinstance(source_context, dict):
        source_context = {}
    return str(
        payload.get("chat_id")
        or publish.get("chat_id")
        or group_policy.get("chat_id")
        or source_context.get("chat_id")
        or ""
    ).strip()


def _actor_id(payload: dict[str, Any]) -> str:
    tool_result = payload.get("tool_result") if isinstance(payload.get("tool_result"), dict) else {}
    return str(payload.get("actor_id") or payload.get("sender_open_id") or tool_result.get("actor_id") or "").strip()


def _error_code(tool_result: dict[str, Any]) -> str:
    error = tool_result.get("error") if isinstance(tool_result.get("error"), dict) else {}
    return str(error.get("code") or "").strip()


def _reason_code(tool_result: dict[str, Any]) -> str:
    error = tool_result.get("error") if isinstance(tool_result.get("error"), dict) else {}
    return str(error.get("reason_code") or error.get("details", {}).get("reason_code") or "").strip()


def _publish_mode(result: dict[str, Any]) -> str:
    publish = result.get("publish") if isinstance(result.get("publish"), dict) else {}
    return str(publish.get("mode") or "").strip()


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
    if "result" in line or "tool" in line or "tool_result" in line or "event_type" in line:
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
        parsed = _parse_json(numbered)
        if isinstance(parsed, dict):
            return parsed
        embedded = _parse_embedded_json(numbered)
        if isinstance(embedded, dict):
            return embedded
    return line


def _event_type(payload: dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event_type = header.get("event_type") or payload.get("event_type") or payload.get("type")
    if event_type:
        return str(event_type)
    if _result_payload(payload) is not None:
        return "copilot_result"
    return "unknown"


def _failure_reason(summary: dict[str, int]) -> str:
    if summary["allowed_enable_memory_results"] and not summary["denied_enable_memory_results"]:
        return "only_authorized_enable_memory_seen"
    if summary["denied_group_policy_audit_events"] and not summary["denied_enable_memory_results"]:
        return "audit_only_no_denied_live_result"
    if summary["enable_memory_attempt_events"] and not summary["denied_enable_memory_results"]:
        return "enable_memory_attempt_without_denied_result"
    if summary["chat_mismatch"] and not summary["denied_enable_memory_results"]:
        return "expected_chat_not_seen"
    if summary["actor_mismatch"] and not summary["denied_enable_memory_results"]:
        return "expected_actor_not_seen"
    return "non_reviewer_enable_memory_denial_missing"


def _next_step(reason: str) -> str:
    if reason == "only_authorized_enable_memory_seen":
        return "当前只看到 reviewer/admin allow-path；需要第二个非 reviewer 真实用户发送 @Bot /enable_memory 并导出 result log。"
    if reason == "audit_only_no_denied_live_result":
        return "只看到 deny audit，不足以证明 live 回复/路由；请同时保留 copilot_live_event_result 或 OpenClaw gateway result。"
    if reason == "enable_memory_attempt_without_denied_result":
        return "捕获到 /enable_memory 尝试但没有 denial result；检查 listener/gateway 是否输出 result log。"
    if reason == "expected_chat_not_seen":
        return "捕获到了其他 chat 的事件；确认测试群 chat_id/open_chat_id 和日志来源。"
    if reason == "expected_actor_not_seen":
        return "捕获到了其他 actor 的事件；请用指定非 reviewer 账号重试。"
    return "请让非 reviewer 真实用户在受控测试群发送 @Bot /enable_memory，并用 listener/OpenClaw result log 重跑。"


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


def _redact_text(text: str) -> str:
    return ID_PATTERN.sub("<redacted_id>", text)


if __name__ == "__main__":
    raise SystemExit(main())
