#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.feishu_listener_guard import (  # noqa: E402
    FeishuListenerConflict,
    assert_single_feishu_listener,
)

BOUNDARY = (
    "OpenClaw Feishu websocket staging evidence only; no production deployment, "
    "no full Feishu workspace ingestion, no productized live claim."
)
STATUS_ORDER = ("pass", "fail", "warning")
ID_PATTERN = re.compile(r"\b(?:ou|oc|om|cli)_[A-Za-z0-9_-]+\b")
LOG_PATTERNS = {
    "websocket_start": "starting feishu[default] (mode: websocket)",
    "websocket_client_started": "WebSocket client started",
    "websocket_client_ready": "ws client ready",
    "inbound_message_seen": "received message",
    "dispatching_to_agent": "dispatching to agent",
    "dispatch_complete": "dispatch complete",
    "network_disconnect_seen": "Client network socket disconnected",
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], int], CommandResult]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check OpenClaw Feishu websocket running evidence without exposing Feishu IDs."
    )
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON.")
    parser.add_argument("--timeout", type=int, default=30, help="Command timeout in seconds.")
    parser.add_argument("--log-lines", type=int, default=120, help="Feishu channel log lines to inspect.")
    parser.add_argument(
        "--allow-missing-dispatch",
        action="store_true",
        help="Pass without recent inbound/dispatch log evidence. Use only for config-only debugging.",
    )
    args = parser.parse_args()

    report = run_openclaw_feishu_websocket_check(
        timeout=args.timeout,
        log_lines=args.log_lines,
        require_dispatch=not args.allow_missing_dispatch,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
        print("")
        print("JSON: python3 scripts/check_openclaw_feishu_websocket.py --json")
    return 0 if report["ok"] else 1


def run_openclaw_feishu_websocket_check(
    *,
    timeout: int = 30,
    log_lines: int = 120,
    require_dispatch: bool = True,
    command_runner: CommandRunner | None = None,
    process_rows: list[str] | None = None,
    current_pid: int | None = None,
) -> dict[str, Any]:
    runner = command_runner or _run_command
    checks: dict[str, dict[str, Any]] = {}

    checks["listener_singleton"] = _listener_singleton_check(process_rows=process_rows, current_pid=current_pid)
    checks["channels_status"] = _channels_status_check(runner, timeout)
    checks["health_summary"] = _health_summary_check(runner, timeout)
    checks["feishu_logs"] = _feishu_logs_check(runner, timeout, log_lines, require_dispatch=require_dispatch)
    checks["health_consistency"] = _health_consistency_check(checks["channels_status"], checks["health_summary"])

    status_counts = _status_counts(checks)
    return {
        "ok": status_counts["fail"] == 0,
        "phase": "OpenClaw Feishu websocket running evidence",
        "scope": "staging_websocket_evidence_only",
        "boundary": BOUNDARY,
        "checks": checks,
        "status_counts": status_counts,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        str(report["phase"]),
        f"ok: {str(report['ok']).lower()}",
        f"scope: {report['scope']}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    for name, check in checks.items():
        if not isinstance(check, dict):
            continue
        lines.append(f"- {name}: {check.get('status')}{_summary(name, check)}")
        if check.get("next_step"):
            lines.append(f"  next_step: {check['next_step']}")
    lines.append("")
    lines.append(f"status_counts: {json.dumps(report.get('status_counts', {}), ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines)


def redact_text(text: str) -> str:
    return ID_PATTERN.sub("<redacted_id>", text)


def _listener_singleton_check(
    *, process_rows: list[str] | None = None, current_pid: int | None = None
) -> dict[str, Any]:
    try:
        active = assert_single_feishu_listener("openclaw-websocket", process_rows=process_rows, current_pid=current_pid)
    except FeishuListenerConflict as exc:
        return {
            "status": "fail",
            "planned_listener": "openclaw-websocket",
            "conflict": redact_text(str(exc)),
            "next_step": "停止 repo 内 copilot/legacy lark-cli listener 或 direct lark-cli event +subscribe 后重试。",
        }

    return {
        "status": "pass",
        "planned_listener": "openclaw-websocket",
        "active_listener_kinds": [process.kind for process in active],
        "openclaw_gateway_unknown_seen": any(process.kind == "openclaw-gateway-unknown" for process in active),
        "next_step": "",
    }


def _channels_status_check(runner: CommandRunner, timeout: int) -> dict[str, Any]:
    result = runner(["openclaw", "channels", "status", "--probe", "--json"], timeout)
    if result.returncode != 0:
        return _command_fail("openclaw channels status --probe --json", result)
    data = _parse_json(result.stdout)
    if not isinstance(data, dict):
        return _json_fail("openclaw channels status --probe --json", result.stdout)

    channel = _dig(data, "channels", "feishu") or {}
    account = _first_account(data)
    probe = channel.get("probe") if isinstance(channel.get("probe"), dict) else {}
    account_probe = account.get("probe") if isinstance(account.get("probe"), dict) else {}
    probe_ok = bool(probe.get("ok") or account_probe.get("ok"))
    channel_running = bool(channel.get("running"))
    account_running = bool(account.get("running"))
    status = "pass" if channel_running and account_running and probe_ok else "fail"
    return {
        "status": status,
        "command": "openclaw channels status --probe --json",
        "channel_running": channel_running,
        "account_running": account_running,
        "configured": bool(channel.get("configured") or account.get("configured")),
        "probe_ok": probe_ok,
        "account_enabled": bool(account.get("enabled", True)),
        "last_start_at": channel.get("lastStartAt") or account.get("lastStartAt"),
        "last_stop_at": channel.get("lastStopAt") or account.get("lastStopAt"),
        "last_error": redact_text(str(channel.get("lastError") or account.get("lastError") or "")),
        "next_step": ""
        if status == "pass"
        else "先让 OpenClaw Feishu channel running=true，并确认 credential probe ok。",
    }


def _health_summary_check(runner: CommandRunner, timeout: int) -> dict[str, Any]:
    result = runner(["openclaw", "health", "--json", "--timeout", "5000"], timeout)
    if result.returncode != 0:
        return _command_fail("openclaw health --json --timeout 5000", result)
    data = _parse_json(result.stdout)
    if not isinstance(data, dict):
        return _json_fail("openclaw health --json --timeout 5000", result.stdout)

    channel = _dig(data, "channels", "feishu") or {}
    account = _dig(channel, "accounts", "default") or {}
    probe = channel.get("probe") if isinstance(channel.get("probe"), dict) else {}
    account_probe = account.get("probe") if isinstance(account.get("probe"), dict) else {}
    return {
        "status": "pass" if bool(data.get("ok")) else "fail",
        "command": "openclaw health --json --timeout 5000",
        "health_ok": bool(data.get("ok")),
        "channel_running": bool(channel.get("running")),
        "account_running": bool(account.get("running")),
        "probe_ok": bool(probe.get("ok") or account_probe.get("ok")),
        "next_step": "" if bool(data.get("ok")) else "先修复 openclaw health 的 fail 项。",
    }


def _health_consistency_check(channels: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
    channels_running = bool(channels.get("channel_running") and channels.get("account_running"))
    health_running = bool(health.get("channel_running") and health.get("account_running"))
    if channels_running == health_running:
        return {
            "status": "pass",
            "channels_status_running": channels_running,
            "health_running": health_running,
            "next_step": "",
        }
    return {
        "status": "warning",
        "channels_status_running": channels_running,
        "health_running": health_running,
        "next_step": (
            "记录 OpenClaw 2026.4.24 中 health 总览与 channels.status 的 running 字段不一致；"
            "websocket running 证据以 channels.status 和 gateway log 为准。"
        ),
    }


def _feishu_logs_check(
    runner: CommandRunner, timeout: int, log_lines: int, *, require_dispatch: bool
) -> dict[str, Any]:
    result = runner(
        ["openclaw", "channels", "logs", "--channel", "feishu", "--json", "--lines", str(log_lines)], timeout
    )
    if result.returncode != 0:
        return _command_fail(f"openclaw channels logs --channel feishu --json --lines {log_lines}", result)
    data = _parse_json(result.stdout)
    if not isinstance(data, dict):
        return _json_fail("openclaw channels logs --channel feishu --json", result.stdout)

    lines = data.get("lines") if isinstance(data.get("lines"), list) else []
    evidence = {name: _latest_log_time(lines, pattern) for name, pattern in LOG_PATTERNS.items()}
    required = ["websocket_start", "websocket_client_started"]
    if require_dispatch:
        required.extend(["inbound_message_seen", "dispatching_to_agent", "dispatch_complete"])
    missing = [name for name in required if not evidence.get(name)]
    status = "pass" if not missing else "fail"
    return {
        "status": status,
        "command": f"openclaw channels logs --channel feishu --json --lines {log_lines}",
        "log_file": str(data.get("file") or ""),
        "log_lines_checked": len(lines),
        "required_events": required,
        "missing_required_events": missing,
        "evidence_times": evidence,
        "network_disconnect_seen": bool(evidence.get("network_disconnect_seen")),
        "next_step": "" if status == "pass" else "发送一条真实飞书消息给 bot，等待 dispatch complete 后重跑本脚本。",
    }


def _latest_log_time(lines: list[Any], pattern: str) -> str | None:
    latest: str | None = None
    for line in lines:
        if not isinstance(line, dict):
            continue
        message = str(line.get("message") or "")
        if pattern in message:
            latest = str(line.get("time") or "")
    return latest


def _first_account(data: dict[str, Any]) -> dict[str, Any]:
    accounts = _dig(data, "channelAccounts", "feishu")
    if isinstance(accounts, list) and accounts:
        first = accounts[0]
        return first if isinstance(first, dict) else {}
    return {}


def _dig(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _parse_json(stdout: str) -> Any:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _command_fail(command: str, result: CommandResult) -> dict[str, Any]:
    return {
        "status": "fail",
        "command": command,
        "returncode": result.returncode,
        "stderr": redact_text(result.stderr.strip()),
        "next_step": "读取命令错误并修复 OpenClaw / channel 配置后重试。",
    }


def _json_fail(command: str, stdout: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "command": command,
        "stdout_preview": redact_text(stdout[:500]),
        "next_step": "命令没有返回有效 JSON；先修复 CLI 输出或去掉非 JSON 前缀。",
    }


def _status_counts(checks: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in STATUS_ORDER}
    for check in checks.values():
        status = str(check.get("status") or "fail")
        counts[status if status in counts else "fail"] += 1
    return counts


def _summary(name: str, check: dict[str, Any]) -> str:
    if name == "listener_singleton":
        return f" active={check.get('active_listener_kinds')}"
    if name == "channels_status":
        return (
            f" channel_running={check.get('channel_running')}"
            f" account_running={check.get('account_running')}"
            f" probe_ok={check.get('probe_ok')}"
        )
    if name == "health_summary":
        return (
            f" health_ok={check.get('health_ok')}"
            f" health_running={check.get('channel_running')}/{check.get('account_running')}"
        )
    if name == "health_consistency":
        return (
            f" channels_status_running={check.get('channels_status_running')}"
            f" health_running={check.get('health_running')}"
        )
    if name == "feishu_logs":
        return (
            f" missing={check.get('missing_required_events')}"
            f" network_disconnect_seen={check.get('network_disconnect_seen')}"
        )
    return ""


def _run_command(command: Sequence[str], timeout: int) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(124, stdout, stderr or f"timed out after {timeout}s")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
