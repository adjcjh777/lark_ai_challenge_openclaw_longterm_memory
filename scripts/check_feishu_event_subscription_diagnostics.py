#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
MESSAGE_EVENT_KEY = "im.message.receive_v1"
BOUNDARY = (
    "feishu_event_subscription_diagnostics_only; read-only lark-cli event status/list/schema checks, "
    "does not start a listener or prove live passive group delivery"
)
SECRET_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")

Runner = Callable[[list[str]], dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run read-only diagnostics for Feishu message event subscription prerequisites. "
            "This never starts lark-cli event consume."
        )
    )
    parser.add_argument(
        "--planned-listener",
        choices=("openclaw-websocket", "copilot-lark-cli", "legacy-lark-cli", "none"),
        default="openclaw-websocket",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_feishu_event_subscription_diagnostics(planned_listener=args.planned_listener)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_feishu_event_subscription_diagnostics(
    *,
    planned_listener: str = "openclaw-websocket",
    runner: Runner | None = None,
) -> dict[str, Any]:
    run = runner or _run_lark_cli
    status_result = run(["lark-cli", "event", "status", "--json"])
    list_result = run(["lark-cli", "event", "list", "--json"])
    schema_result = run(["lark-cli", "event", "schema", MESSAGE_EVENT_KEY, "--json"])

    status_payload = _parse_json_object(status_result.get("stdout", ""))
    list_payload = _parse_json_object(list_result.get("stdout", ""))
    schema_payload = _parse_json_object(schema_result.get("stdout", ""))
    apps = status_payload.get("apps") if isinstance(status_payload, dict) and isinstance(status_payload.get("apps"), list) else []
    active_buses = [app for app in apps if isinstance(app, dict) and app.get("running")]
    event_keys = _event_keys(list_payload)
    scopes = schema_payload.get("scopes") if isinstance(schema_payload, dict) and isinstance(schema_payload.get("scopes"), list) else []
    required_events = (
        schema_payload.get("required_console_events")
        if isinstance(schema_payload, dict) and isinstance(schema_payload.get("required_console_events"), list)
        else []
    )
    auth_types = (
        schema_payload.get("auth_types")
        if isinstance(schema_payload, dict) and isinstance(schema_payload.get("auth_types"), list)
        else []
    )
    listener_ok = _listener_status_ok(planned_listener=planned_listener, active_buses=active_buses)
    checks = {
        "event_status_readable": _check(status_result.get("returncode") == 0 and isinstance(status_payload, dict)),
        "event_list_readable": _check(list_result.get("returncode") == 0 and bool(event_keys)),
        "message_event_registered": _check(MESSAGE_EVENT_KEY in event_keys),
        "message_schema_readable": _check(schema_result.get("returncode") == 0 and isinstance(schema_payload, dict)),
        "message_schema_requires_console_event": _check(MESSAGE_EVENT_KEY in required_events),
        "message_schema_bot_auth": _check("bot" in auth_types),
        "listener_mode_consistent": _check(listener_ok),
    }
    warnings = []
    if not _has_group_message_scope(scopes):
        warnings.append(
            {
                "id": "message_schema_scope_does_not_list_group_msg_readonly",
                "detail": (
                    "lark-cli schema scopes do not list im:message.group_msg:readonly; verify Feishu console scopes "
                    "and event subscription if non-@ group messages still do not arrive."
                ),
            }
        )
    if planned_listener == "openclaw-websocket" and active_buses:
        warnings.append(
            {
                "id": "lark_cli_event_bus_running_with_openclaw_planned",
                "detail": "OpenClaw is planned owner, so lark-cli event bus should not also consume the same bot.",
            }
        )
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "planned_listener": planned_listener,
        "checks": checks,
        "failed_checks": failed,
        "warnings": warnings,
        "event_status": {
            "app_count": len(apps),
            "active_bus_count": len(active_buses),
            "active_bus_app_ids": [_redact_id(str(app.get("app_id") or "")) for app in active_buses],
        },
        "message_event_schema": {
            "key": MESSAGE_EVENT_KEY,
            "auth_types": auth_types,
            "scopes": scopes,
            "required_console_events": required_events,
            "has_group_message_scope": _has_group_message_scope(scopes),
        },
        "next_step": ""
        if not failed
        else "Fix lark-cli event status/list/schema diagnostics before rerunning live passive group message evidence.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Feishu Event Subscription Diagnostics",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        f"planned_listener: {report['planned_listener']}",
        f"failed_checks: {', '.join(report['failed_checks']) if report['failed_checks'] else 'none'}",
        f"warnings: {', '.join(item['id'] for item in report['warnings']) if report['warnings'] else 'none'}",
    ]
    return "\n".join(lines)


def _run_lark_cli(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=20, check=False)
    return {
        "returncode": completed.returncode,
        "stdout": _redact_secret_like(completed.stdout),
        "stderr": _redact_secret_like(completed.stderr),
    }


def _event_keys(payload: Any) -> set[str]:
    if not isinstance(payload, list):
        return set()
    keys = set()
    for item in payload:
        if isinstance(item, dict) and item.get("key"):
            keys.add(str(item["key"]))
    return keys


def _listener_status_ok(*, planned_listener: str, active_buses: list[dict[str, Any]]) -> bool:
    if planned_listener in {"openclaw-websocket", "none"}:
        return not active_buses
    return bool(active_buses)


def _has_group_message_scope(scopes: list[Any]) -> bool:
    return any("group_msg" in str(scope) or str(scope) == "im:message:readonly" for scope in scopes)


def _parse_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return value
    return None


def _check(ok: bool) -> dict[str, str]:
    return {"status": "pass" if ok else "fail"}


def _redact_id(value: str) -> str:
    if len(value) <= 8:
        return "***" if value else ""
    return f"{value[:4]}...{value[-4:]}"


def _redact_secret_like(value: str) -> str:
    redacted = value
    for marker in SECRET_MARKERS:
        if marker in redacted:
            redacted = redacted.replace(marker, f"{marker}<redacted>")
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
