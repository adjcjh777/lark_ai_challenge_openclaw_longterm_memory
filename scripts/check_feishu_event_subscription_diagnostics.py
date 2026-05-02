#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
MESSAGE_EVENT_KEY = "im.message.receive_v1"
GROUP_MESSAGE_SCOPE_OPTIONS = ("im:message.group_msg:readonly",)
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
    parser.add_argument(
        "--require-group-message-scope",
        action="store_true",
        help="Fail if the message event schema does not list a group-message readonly scope.",
    )
    parser.add_argument(
        "--target-chat-id",
        default="",
        help="Optional oc_ chat_id for a read-only bot identity group-message access probe.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_feishu_event_subscription_diagnostics(
        planned_listener=args.planned_listener,
        require_group_message_scope=args.require_group_message_scope,
        target_chat_id=args.target_chat_id or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_feishu_event_subscription_diagnostics(
    *,
    planned_listener: str = "openclaw-websocket",
    require_group_message_scope: bool = False,
    target_chat_id: str | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    run = runner or _run_lark_cli
    status_result = run(["lark-cli", "event", "status", "--json"])
    list_result = run(["lark-cli", "event", "list", "--json"])
    schema_result = run(["lark-cli", "event", "schema", MESSAGE_EVENT_KEY, "--json"])
    auth_scopes_result = run(["lark-cli", "auth", "scopes", "--format", "json"])
    bot_group_messages_result = None
    if target_chat_id:
        bot_group_messages_result = run(
            [
                "lark-cli",
                "im",
                "+chat-messages-list",
                "--as",
                "bot",
                "--chat-id",
                target_chat_id,
                "--page-size",
                "1",
                "--sort",
                "desc",
                "--format",
                "json",
            ]
        )

    status_payload = _parse_json_object(status_result.get("stdout", ""))
    list_payload = _parse_json_object(list_result.get("stdout", ""))
    schema_payload = _parse_json_object(schema_result.get("stdout", ""))
    auth_scopes_payload = _parse_json_object(auth_scopes_result.get("stdout", ""))
    bot_group_messages_payload = _parse_command_json_payload(bot_group_messages_result)
    apps = (
        status_payload.get("apps")
        if isinstance(status_payload, dict) and isinstance(status_payload.get("apps"), list)
        else []
    )
    active_buses = [app for app in apps if isinstance(app, dict) and app.get("running")]
    event_keys = _event_keys(list_payload)
    scopes = (
        schema_payload.get("scopes")
        if isinstance(schema_payload, dict) and isinstance(schema_payload.get("scopes"), list)
        else []
    )
    enabled_scopes = _enabled_scopes(auth_scopes_payload)
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
        "auth_scopes_readable": _check(
            auth_scopes_result.get("returncode") == 0 and isinstance(auth_scopes_payload, dict)
        ),
        "message_schema_requires_console_event": _check(MESSAGE_EVENT_KEY in required_events),
        "message_schema_bot_auth": _check("bot" in auth_types),
        "listener_mode_consistent": _check(listener_ok),
    }
    bot_group_access_probe = _bot_group_access_probe(
        target_chat_id=target_chat_id,
        result=bot_group_messages_result,
        payload=bot_group_messages_payload,
    )
    if bot_group_access_probe:
        checks["target_bot_group_messages_readable"] = _check(bot_group_access_probe["ok"])
    has_schema_group_scope = _has_group_message_scope(scopes)
    has_enabled_group_scope = _has_group_message_scope(enabled_scopes)
    has_group_scope = has_schema_group_scope or has_enabled_group_scope
    if require_group_message_scope:
        checks["message_schema_group_message_scope"] = _check(has_group_scope)
    warnings = []
    if not has_schema_group_scope and has_enabled_group_scope:
        warnings.append(
            {
                "id": "message_schema_scope_missing_but_enabled_scope_present",
                "detail": (
                    "lark-cli event schema scopes still omit group-message readonly scope, but app enabled scopes "
                    "include im:message.group_msg:readonly. Continue with live non-@ message capture, and keep "
                    "Feishu event-log verification as the final proof."
                ),
            }
        )
    elif not has_group_scope:
        warnings.append(
            {
                "id": "message_schema_scope_does_not_list_group_msg_readonly",
                "detail": (
                    "Neither lark-cli event schema scopes nor enabled app scopes list im:message.group_msg:readonly. "
                    "Broad im:message:readonly or user get_as_user scopes are not sufficient for bot-owned passive "
                    "group delivery in this live gate."
                ),
            }
        )
    if bot_group_access_probe and not bot_group_access_probe["ok"]:
        warnings.append(
            {
                "id": "target_bot_group_messages_unreadable",
                "detail": (
                    "Bot identity cannot read recent messages in the target group. This usually means "
                    "im:message.group_msg:readonly is not enabled/published for the app or the app needs "
                    "to be reinstalled in the tenant."
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
    remediation = _remediation(
        planned_listener=planned_listener,
        scopes=scopes,
        enabled_scopes=enabled_scopes,
        has_group_scope=has_group_scope,
        has_schema_group_scope=has_schema_group_scope,
        has_enabled_group_scope=has_enabled_group_scope,
        active_buses=active_buses,
        bot_group_access_probe=bot_group_access_probe,
    )
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "planned_listener": planned_listener,
        "require_group_message_scope": require_group_message_scope,
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
            "enabled_scopes": _relevant_message_scopes(enabled_scopes),
            "required_console_events": required_events,
            "has_group_message_scope": has_group_scope,
            "has_group_message_scope_from_schema": has_schema_group_scope,
            "has_group_message_scope_from_enabled_scopes": has_enabled_group_scope,
        },
        "target_group_probe": bot_group_access_probe,
        "remediation": remediation,
        "next_step": "" if not failed else remediation["summary"],
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
    remediation = report.get("remediation") if isinstance(report.get("remediation"), dict) else {}
    if remediation.get("summary"):
        lines.append(f"next_step: {remediation['summary']}")
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
    return any(str(scope) == "im:message.group_msg:readonly" for scope in scopes)


def _remediation(
    *,
    planned_listener: str,
    scopes: list[Any],
    enabled_scopes: list[Any],
    has_group_scope: bool,
    has_schema_group_scope: bool,
    has_enabled_group_scope: bool,
    active_buses: list[dict[str, Any]],
    bot_group_access_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_scopes = [str(scope) for scope in scopes]
    current_enabled_scopes = [str(scope) for scope in enabled_scopes]
    missing_group_scope = not has_group_scope
    listener_conflict = planned_listener == "openclaw-websocket" and bool(active_buses)
    target_group_unreadable = bool(bot_group_access_probe and not bot_group_access_probe["ok"])
    steps: list[str] = []
    if missing_group_scope or target_group_unreadable:
        steps.extend(
            [
                "In the Feishu/Lark developer console for this same bot app, enable or verify one group-message readonly permission.",
                f"Acceptable scope options: {', '.join(GROUP_MESSAGE_SCOPE_OPTIONS)}.",
                f"Keep event subscription for {MESSAGE_EVENT_KEY} enabled for bot auth, then publish or reauthorize the app if the console requires it.",
                "Rerun this diagnostic with --require-group-message-scope and --target-chat-id before sending another non-@ group test message.",
            ]
        )
    if listener_conflict:
        steps.append("Stop the lark-cli event bus before using OpenClaw websocket as the planned single listener.")
    if not steps:
        if has_enabled_group_scope and not has_schema_group_scope:
            steps.append(
                "Enabled app scopes include group-message readonly permission even though event schema "
                "metadata is stale; continue with a real non-@ group text and preserve the single-listener log."
            )
        else:
            steps.append(
                "Event subscription prerequisites look ready; send a real non-@ group text and preserve the single-listener log."
            )

    if target_group_unreadable:
        summary = (
            "Bot identity cannot read target group messages; fix im:message.group_msg:readonly app permissions, "
            "publish/reinstall if needed, then retest passive group delivery."
        )
    elif missing_group_scope:
        summary = (
            "Feishu message event schema lacks group-message readonly scope; fix app permissions/event subscription, "
            "rerun diagnostics, then retest passive group delivery."
        )
    elif listener_conflict:
        summary = "Stop the conflicting lark-cli event bus before retesting with OpenClaw websocket as owner."
    else:
        summary = ""
    return {
        "requires_external_console_change": missing_group_scope or target_group_unreadable,
        "target_group_access_action_required": target_group_unreadable,
        "required_scopes_any_of": list(GROUP_MESSAGE_SCOPE_OPTIONS),
        "current_scopes": current_scopes,
        "enabled_scopes": _relevant_message_scopes(current_enabled_scopes),
        "message_event_key": MESSAGE_EVENT_KEY,
        "single_listener_action_required": listener_conflict,
        "steps": steps,
        "summary": summary,
    }


def _bot_group_access_probe(
    *,
    target_chat_id: str | None,
    result: dict[str, Any] | None,
    payload: Any,
) -> dict[str, Any] | None:
    if not target_chat_id:
        return None
    ok = bool(result and result.get("returncode") == 0 and isinstance(payload, dict))
    error = payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), dict) else {}
    return {
        "ok": ok,
        "target_chat_id": _redact_id(target_chat_id),
        "identity": "bot",
        "returncode": result.get("returncode") if result else None,
        "error_code": error.get("code"),
        "error_type": error.get("type"),
        "message": (
            "Bot identity can read recent target group messages."
            if ok
            else str(error.get("message") or "Bot identity cannot read recent target group messages.")
        ),
    }


def _enabled_scopes(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    scopes: list[Any] = []
    for key in ("tenantScopes", "userScopes", "appScopes", "scopes", "granted"):
        value = payload.get(key)
        if isinstance(value, list):
            scopes.extend(value)
    return scopes


def _relevant_message_scopes(scopes: list[Any]) -> list[str]:
    relevant = []
    for scope in scopes:
        text = str(scope)
        if text.startswith("im:message"):
            relevant.append(text)
    return sorted(set(relevant))


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


def _parse_command_json_payload(result: dict[str, Any] | None) -> Any:
    if not result:
        return None
    return _parse_json_object(str(result.get("stdout") or "")) or _parse_json_object(str(result.get("stderr") or ""))


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
