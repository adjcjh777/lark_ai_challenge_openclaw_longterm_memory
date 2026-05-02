#!/usr/bin/env python3
"""Preflight the OpenClaw-native Memory Copilot demo availability path.

This is a local/staging preflight for the "bot must not silently no-reply"
demo risk. It does not replace a post-fix live Feishu message evidence log.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = (
    "local_demo_preflight_only; verifies OpenClaw, Feishu channel, singleton listener, "
    "plugin hook, and card-delivery helper readiness; does not prove live Feishu card delivery "
    "without a fresh message log containing feishu-memory-copilot card delivery ok=true"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--planned-listener",
        default="openclaw-websocket",
        help="Expected Feishu listener owner for singleton check.",
    )
    args = parser.parse_args()
    report = run_preflight(planned_listener=args.planned_listener)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_preflight(*, planned_listener: str = "openclaw-websocket") -> dict[str, Any]:
    checks = [
        check_gateway_status(),
        check_feishu_channel_status(),
        check_listener_singleton(planned_listener),
        check_memory_copilot_plugin(),
        check_card_delivery_helper_syntax(),
    ]
    return {
        "ok": all(check["ok"] for check in checks),
        "boundary": BOUNDARY,
        "checks": checks,
        "next_live_gate": (
            "Send /settings in the controlled Feishu test group and confirm gateway.log contains "
            "feishu-memory-copilot card delivery with ok=true, or a visible card_delivery_failed/router_failed fallback."
        ),
    }


def check_gateway_status() -> dict[str, Any]:
    result = run_command(["openclaw", "gateway", "status"], timeout=20)
    ok = result["returncode"] == 0 and "Connectivity probe: ok" in result["stdout"]
    return {
        "name": "openclaw_gateway_status",
        "ok": ok,
        "detail": "Connectivity probe ok" if ok else command_failure_detail(result),
    }


def check_feishu_channel_status() -> dict[str, Any]:
    result = run_command(["openclaw", "channels", "status", "--probe"], timeout=20)
    stdout = result["stdout"]
    ok = result["returncode"] == 0 and "Feishu default: enabled, configured, running, works" in stdout
    return {
        "name": "feishu_channel_status",
        "ok": ok,
        "detail": "Feishu default enabled/configured/running/works" if ok else command_failure_detail(result),
    }


def check_listener_singleton(planned_listener: str) -> dict[str, Any]:
    result = run_command(
        [
            sys.executable,
            "scripts/check_feishu_listener_singleton.py",
            "--planned-listener",
            planned_listener,
        ],
        timeout=20,
    )
    ok = result["returncode"] == 0 and "Feishu listener singleton check OK" in result["stdout"]
    return {
        "name": "feishu_listener_singleton",
        "ok": ok,
        "detail": f"planned_listener={planned_listener}" if ok else command_failure_detail(result),
    }


def check_memory_copilot_plugin() -> dict[str, Any]:
    result = run_command(["openclaw", "plugins", "inspect", "feishu-memory-copilot", "--json"], timeout=30)
    if result["returncode"] != 0:
        return {"name": "memory_copilot_plugin", "ok": False, "detail": command_failure_detail(result)}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        return {"name": "memory_copilot_plugin", "ok": False, "detail": f"invalid plugin inspect JSON: {exc}"}
    plugin = payload.get("plugin") if isinstance(payload, dict) else {}
    typed_hooks = payload.get("typedHooks") if isinstance(payload, dict) else []
    hook_names = {
        str(hook.get("name"))
        for hook in typed_hooks
        if isinstance(hook, dict) and hook.get("name")
    }
    tool_names = plugin.get("toolNames") if isinstance(plugin, dict) else []
    source = str(plugin.get("source") or "") if isinstance(plugin, dict) else ""
    required_tools = {
        "fmc_memory_search",
        "fmc_memory_create_candidate",
        "fmc_memory_confirm",
        "fmc_memory_reject",
        "fmc_memory_explain_versions",
        "fmc_memory_prefetch",
        "fmc_heartbeat_review_due",
    }
    ok = (
        isinstance(plugin, dict)
        and plugin.get("status") == "loaded"
        and plugin.get("enabled") is True
        and "before_dispatch" in hook_names
        and required_tools.issubset(set(tool_names or []))
        and source.endswith("agent_adapters/openclaw/plugin/index.js")
    )
    return {
        "name": "memory_copilot_plugin",
        "ok": ok,
        "detail": {
            "status": plugin.get("status") if isinstance(plugin, dict) else None,
            "enabled": plugin.get("enabled") if isinstance(plugin, dict) else None,
            "typed_hooks": sorted(hook_names),
            "tool_count": len(tool_names or []),
            "source": source,
        },
    }


def check_card_delivery_helper_syntax() -> dict[str, Any]:
    files = [
        "agent_adapters/openclaw/plugin/index.js",
        "agent_adapters/openclaw/plugin/feishu_card_delivery.js",
    ]
    details = []
    for path in files:
        result = run_command(["node", "--check", path], timeout=20)
        details.append({"path": path, "ok": result["returncode"] == 0, "detail": command_failure_detail(result)})
    return {
        "name": "card_delivery_helper_syntax",
        "ok": all(detail["ok"] for detail in details),
        "detail": details,
    }


def run_command(command: list[str], *, timeout: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    except Exception as exc:  # pragma: no cover - exercised by caller failure paths in production
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}
    return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def command_failure_detail(result: dict[str, Any]) -> str:
    stderr = str(result.get("stderr") or "").strip()
    stdout = str(result.get("stdout") or "").strip()
    return stderr or stdout or f"returncode={result.get('returncode')}"


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"OpenClaw Memory Copilot demo preflight: {'PASS' if report['ok'] else 'FAIL'}",
        f"Boundary: {report['boundary']}",
    ]
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {'PASS' if check['ok'] else 'FAIL'}")
    lines.append(f"Next live gate: {report['next_live_gate']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
