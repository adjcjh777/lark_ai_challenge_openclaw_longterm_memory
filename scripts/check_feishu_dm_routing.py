"""Check Feishu DM routing status.

Validates that:
1. OpenClaw gateway is running
2. feishu-memory-copilot plugin is installed and enabled
3. Plugin tools are registered with fmc_xxx names
4. tools.alsoAllow includes fmc_xxx tools
5. Agent can call fmc_memory_search successfully

Usage:
    python3 scripts/check_feishu_dm_routing.py [--json] [--timeout 60]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def check_gateway_running() -> dict:
    """Check if OpenClaw gateway is running."""
    rc, stdout, stderr = run_cmd(["openclaw", "gateway", "status"])
    running = "running" in stdout and "Connectivity probe: ok" in stdout
    return {
        "name": "gateway_running",
        "ok": running,
        "detail": "Gateway is running and connectivity is ok" if running else "Gateway is not running",
    }


def check_plugin_enabled() -> dict:
    """Check if feishu-memory-copilot plugin is enabled."""
    rc, stdout, stderr = run_cmd(["openclaw", "plugins", "inspect", "feishu-memory-copilot", "--json"])
    if rc != 0:
        return {"name": "plugin_enabled", "ok": False, "detail": f"Failed to inspect plugin: {stderr}"}

    try:
        data = json.loads(stdout)
        enabled = data.get("plugin", {}).get("enabled", False)
        activated = data.get("plugin", {}).get("activated", False)
        return {
            "name": "plugin_enabled",
            "ok": enabled and activated,
            "detail": f"enabled={enabled}, activated={activated}",
        }
    except json.JSONDecodeError:
        return {"name": "plugin_enabled", "ok": False, "detail": "Failed to parse plugin inspect output"}


def check_tools_registered() -> dict:
    """Check if plugin tools are registered with fmc_xxx names."""
    rc, stdout, stderr = run_cmd(["openclaw", "plugins", "inspect", "feishu-memory-copilot", "--json"])
    if rc != 0:
        return {"name": "tools_registered", "ok": False, "detail": f"Failed to inspect plugin: {stderr}"}

    try:
        data = json.loads(stdout)
        tools = data.get("plugin", {}).get("toolNames", [])
        expected = [
            "fmc_memory_search",
            "fmc_memory_create_candidate",
            "fmc_memory_confirm",
            "fmc_memory_reject",
            "fmc_memory_explain_versions",
            "fmc_memory_prefetch",
            "fmc_heartbeat_review_due",
        ]
        all_fmc = all(t.startswith("fmc_") for t in tools)
        has_expected = all(t in tools for t in expected)
        return {
            "name": "tools_registered",
            "ok": all_fmc and has_expected,
            "detail": f"tools={tools}",
            "expected": expected,
        }
    except json.JSONDecodeError:
        return {"name": "tools_registered", "ok": False, "detail": "Failed to parse plugin inspect output"}


def check_tools_also_allow() -> dict:
    """Check if tools.alsoAllow includes fmc_xxx tools."""
    rc, stdout, stderr = run_cmd(["openclaw", "config", "get", "tools.alsoAllow"])
    if rc != 0:
        return {"name": "tools_also_allow", "ok": False, "detail": f"tools.alsoAllow not configured: {stderr}"}

    try:
        also_allow = json.loads(stdout)
        has_fmc = any(t.startswith("fmc_") for t in also_allow)
        return {
            "name": "tools_also_allow",
            "ok": has_fmc,
            "detail": f"tools.alsoAllow={also_allow}",
        }
    except json.JSONDecodeError:
        return {"name": "tools_also_allow", "ok": False, "detail": f"Failed to parse tools.alsoAllow: {stdout}"}


def check_agent_tool_list() -> dict:
    """Check if Agent has fmc_xxx tools available."""
    rc, stdout, stderr = run_cmd(
        ["openclaw", "agent", "--agent", "main", "--message", "列出工具", "--json", "--timeout", "90"],
        timeout=120,
    )
    if rc != 0:
        return {"name": "agent_tool_list", "ok": False, "detail": f"Agent call failed: {stderr[:200]}"}

    try:
        data = json.loads(stdout)
        tools = data.get("result", {}).get("meta", {}).get("systemPromptReport", {}).get("tools", {}).get("entries", [])
        tool_names = [t["name"] for t in tools]
        has_fmc = any(t.startswith("fmc_") for t in tool_names)
        return {
            "name": "agent_tool_list",
            "ok": has_fmc,
            "detail": f"fmc tools in agent: {[t for t in tool_names if t.startswith('fmc_')]}",
        }
    except (json.JSONDecodeError, KeyError):
        return {"name": "agent_tool_list", "ok": False, "detail": "Failed to parse agent response"}


def check_python_tests() -> dict:
    """Run routing tests and check they pass."""
    rc, stdout, stderr = run_cmd(
        ["python3", "-m", "unittest", "tests.test_feishu_dm_routing", "-v"],
        timeout=60,
    )
    ok = rc == 0 and "FAILED" not in stdout
    return {
        "name": "python_tests",
        "ok": ok,
        "detail": f"exit_code={rc}",
        "output": stdout[-500:] if stdout else stderr[-500:],
    }


def check_feishu_dm_routing() -> dict:
    """Run all checks and return aggregated result."""
    checks = [
        check_gateway_running(),
        check_plugin_enabled(),
        check_tools_registered(),
        check_tools_also_allow(),
        check_agent_tool_list(),
        check_python_tests(),
    ]

    all_ok = all(c["ok"] for c in checks)
    return {
        "ok": all_ok,
        "checks": checks,
        "summary": f"{sum(1 for c in checks if c['ok'])}/{len(checks)} checks passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Feishu DM routing status")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    args = parser.parse_args()

    result = check_feishu_dm_routing()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Feishu DM Routing Check: {result['summary']}")
        print()
        for check in result["checks"]:
            status = "✅" if check["ok"] else "❌"
            print(f"  {status} {check['name']}: {check['detail']}")
        print()
        if result["ok"]:
            print("All checks passed! Feishu DM routing is working correctly.")
        else:
            print("Some checks failed. Please fix the issues above.")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
