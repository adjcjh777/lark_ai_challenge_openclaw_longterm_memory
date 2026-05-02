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
GROUP_MESSAGE_SCOPE_OPTIONS = ("im:message.group_msg", "im:message.group_msg:readonly")
PRIMARY_GROUP_MESSAGE_SCOPE = GROUP_MESSAGE_SCOPE_OPTIONS[0]
DEFAULT_OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
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
        help="Fail if the message event schema or enabled app scopes do not list a group-message scope.",
    )
    parser.add_argument(
        "--target-chat-id",
        default="",
        help="Optional oc_ chat_id for a read-only bot identity group-message access probe.",
    )
    parser.add_argument(
        "--openclaw-config",
        type=Path,
        default=DEFAULT_OPENCLAW_CONFIG,
        help=(
            "Optional OpenClaw config path for a read-only Feishu group policy safety check. "
            "Only non-secret policy fields are reported."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_feishu_event_subscription_diagnostics(
        planned_listener=args.planned_listener,
        require_group_message_scope=args.require_group_message_scope,
        target_chat_id=args.target_chat_id or None,
        openclaw_config_path=args.openclaw_config,
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
    openclaw_config_path: Path | None = None,
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
    openclaw_policy_probe = _openclaw_feishu_policy_probe(
        planned_listener=planned_listener,
        config_path=openclaw_config_path,
    )
    if bot_group_access_probe:
        checks["target_bot_group_messages_readable"] = _check(bot_group_access_probe["ok"])
    if openclaw_policy_probe and openclaw_policy_probe.get("status") != "warning":
        checks["openclaw_feishu_group_policy_safe"] = _check(bool(openclaw_policy_probe.get("ok")))
    has_schema_group_scope = _has_group_message_scope(scopes)
    has_enabled_group_scope = _has_group_message_scope(enabled_scopes)
    has_target_group_access = bool(bot_group_access_probe and bot_group_access_probe["ok"])
    has_group_scope = has_schema_group_scope or has_enabled_group_scope or has_target_group_access
    if require_group_message_scope:
        checks["message_schema_group_message_scope"] = _check(has_group_scope)
    warnings = []
    if not has_schema_group_scope and has_enabled_group_scope:
        warnings.append(
            {
                "id": "message_schema_scope_missing_but_enabled_scope_present",
                "detail": (
                    "lark-cli event schema scopes still omit a group-message scope, but app enabled scopes "
                    f"include one of {', '.join(GROUP_MESSAGE_SCOPE_OPTIONS)}. Continue with live non-@ message capture, and keep "
                    "Feishu event-log verification as the final proof."
                ),
            }
        )
    elif not has_schema_group_scope and has_target_group_access:
        warnings.append(
            {
                "id": "message_schema_scope_missing_but_target_group_readable",
                "detail": (
                    "lark-cli event schema and enabled scope metadata still omit a group-message scope, but "
                    "bot identity can read recent messages in the target group. Continue with live non-@ "
                    "message capture, and keep Feishu event-log verification as the final proof."
                ),
            }
        )
    elif not has_group_scope:
        warnings.append(
            {
                "id": "message_schema_scope_does_not_list_group_msg",
                "detail": (
                    f"Neither lark-cli event schema scopes nor enabled app scopes list one of {', '.join(GROUP_MESSAGE_SCOPE_OPTIONS)}. "
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
                    f"{PRIMARY_GROUP_MESSAGE_SCOPE} is not enabled/published for the app, or the app needs "
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
    if openclaw_policy_probe:
        if not openclaw_policy_probe.get("ok"):
            warnings.append(
                {
                    "id": "openclaw_group_policy_open_without_require_mention",
                    "detail": (
                        "OpenClaw Feishu groupPolicy=open without requireMention=true dispatches ordinary non-@ "
                        "group messages to the main agent. That can prove event delivery, but it is not the "
                        "Copilot passive silent-screening path."
                    ),
                }
            )
        elif openclaw_policy_probe.get("status") == "warning":
            warnings.append(
                {
                    "id": "openclaw_config_unavailable_for_group_policy_probe",
                    "detail": str(openclaw_policy_probe.get("message") or "OpenClaw Feishu policy was not checked."),
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
        openclaw_policy_probe=openclaw_policy_probe,
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
            "has_group_message_access_from_target_probe": has_target_group_access,
        },
        "openclaw_feishu_policy": openclaw_policy_probe,
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
    return any(str(scope) in GROUP_MESSAGE_SCOPE_OPTIONS for scope in scopes)


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
    openclaw_policy_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_scopes = [str(scope) for scope in scopes]
    current_enabled_scopes = [str(scope) for scope in enabled_scopes]
    missing_group_scope = not has_group_scope
    listener_conflict = planned_listener == "openclaw-websocket" and bool(active_buses)
    target_group_unreadable = bool(bot_group_access_probe and not bot_group_access_probe["ok"])
    openclaw_group_policy_unsafe = bool(openclaw_policy_probe and not openclaw_policy_probe.get("ok"))
    steps: list[str] = []
    if missing_group_scope or target_group_unreadable:
        steps.extend(
            [
                "In the Feishu/Lark developer console for this same bot app, enable or verify one group-message permission.",
                f"Preferred current scope: {PRIMARY_GROUP_MESSAGE_SCOPE}; legacy/offline fallback: im:message.group_msg:readonly.",
                f"Keep event subscription for {MESSAGE_EVENT_KEY} enabled for bot auth, then publish or reauthorize the app if the console requires it.",
                "Rerun this diagnostic with --require-group-message-scope and --target-chat-id before sending another non-@ group test message.",
            ]
        )
    if listener_conflict:
        steps.append("Stop the lark-cli event bus before using OpenClaw websocket as the planned single listener.")
    if openclaw_group_policy_unsafe:
        steps.append(
            "Change OpenClaw Feishu group handling so ordinary non-@ group messages are not dispatched to the "
            "generic main agent; for live passive evidence use requireMention=true or a Copilot-owned route that "
            "calls handle_tool_request() / CopilotService silently."
        )
    if not steps:
        if (has_enabled_group_scope or bool(bot_group_access_probe and bot_group_access_probe["ok"])) and not has_schema_group_scope:
            steps.append(
                "Enabled app scopes include group-message permission even though event schema "
                "metadata may be stale, or bot target-group access has been verified; continue with a real "
                "non-@ group text and preserve the single-listener log."
            )
        else:
            steps.append(
                "Event subscription prerequisites look ready; send a real non-@ group text and preserve the single-listener log."
            )

    if target_group_unreadable:
        summary = (
            f"Bot identity cannot read target group messages; fix {PRIMARY_GROUP_MESSAGE_SCOPE} app permissions, "
            "publish/reinstall if needed, then retest passive group delivery."
        )
    elif missing_group_scope:
        summary = (
            "Feishu message event schema lacks group-message scope; fix app permissions/event subscription, "
            "rerun diagnostics, then retest passive group delivery."
        )
    elif listener_conflict:
        summary = "Stop the conflicting lark-cli event bus before retesting with OpenClaw websocket as owner."
    elif openclaw_group_policy_unsafe:
        summary = (
            "OpenClaw Feishu groupPolicy=open is dispatching non-@ group messages to the generic agent; "
            "switch to a safe Copilot-owned passive route before treating the evidence as productized."
        )
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
        "openclaw_group_policy_action_required": openclaw_group_policy_unsafe,
        "steps": steps,
        "summary": summary,
    }


def _openclaw_feishu_policy_probe(
    *,
    planned_listener: str,
    config_path: Path | None,
) -> dict[str, Any] | None:
    if planned_listener != "openclaw-websocket" or config_path is None:
        return None
    path = config_path.expanduser()
    if not path.exists():
        return {
            "ok": True,
            "status": "warning",
            "path": str(path),
            "message": "OpenClaw config path does not exist; skipped Feishu group policy probe.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "fail",
            "path": str(path),
            "message": f"Unable to read OpenClaw config JSON: {exc}",
        }
    feishu = payload.get("channels", {}).get("feishu") if isinstance(payload, dict) else None
    if not isinstance(feishu, dict):
        return {
            "ok": True,
            "status": "warning",
            "path": str(path),
            "configured": False,
            "message": "OpenClaw config does not contain channels.feishu.",
        }
    group_policy = feishu.get("groupPolicy")
    require_mention = feishu.get("requireMention")
    unsafe_open_dispatch = str(group_policy or "").lower() == "open" and require_mention is not True
    return {
        "ok": not unsafe_open_dispatch,
        "status": "pass" if not unsafe_open_dispatch else "fail",
        "path": str(path),
        "configured": True,
        "groupPolicy": group_policy,
        "requireMention": require_mention,
        "message": (
            "OpenClaw Feishu group policy is safe for passive evidence capture."
            if not unsafe_open_dispatch
            else "groupPolicy=open without requireMention=true dispatches non-@ group messages to the main agent."
        ),
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
