"""Check Feishu DM routing status.

Validates that:
1. OpenClaw gateway is running
2. feishu-memory-copilot plugin is installed and enabled
3. Plugin tools are registered with fmc_xxx names
4. tools.alsoAllow includes fmc_xxx tools
5. Agent can call fmc_memory_search successfully

Boundary: this is a local/staging readiness check. It does not prove stable
long-running real Feishu DM/group routing.

Usage:
    python3 scripts/check_feishu_dm_routing.py [--json] [--timeout 60]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = "Local/staging Feishu DM routing readiness only; does not prove stable long-running real Feishu routing."
LIVE_EVIDENCE_BOUNDARY = (
    "Captured Feishu/OpenClaw first-class routing evidence only; requires fmc_* bridge results, "
    "but still does not prove stable long-running real Feishu routing."
)
DEFAULT_REQUIRED_LIVE_TOOLS = (
    "fmc_memory_search",
    "fmc_memory_create_candidate",
    "fmc_memory_prefetch",
)


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


def check_before_dispatch_hook_registered() -> dict:
    """Check if the plugin owns a before_dispatch hook for Feishu group router handoff."""
    rc, stdout, stderr = run_cmd(["openclaw", "plugins", "inspect", "feishu-memory-copilot", "--json"])
    if rc != 0:
        return {"name": "before_dispatch_hook_registered", "ok": False, "detail": f"Failed to inspect plugin: {stderr}"}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "name": "before_dispatch_hook_registered",
            "ok": False,
            "detail": "Failed to parse plugin inspect output",
        }
    hooks = data.get("typedHooks") if isinstance(data.get("typedHooks"), list) else []
    hook_names = [str(item.get("name") or "") for item in hooks if isinstance(item, dict)]
    return {
        "name": "before_dispatch_hook_registered",
        "ok": "before_dispatch" in hook_names,
        "detail": f"typedHooks={hook_names}",
    }


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
        check_before_dispatch_hook_registered(),
        check_tools_also_allow(),
        check_agent_tool_list(),
        check_python_tests(),
    ]

    all_ok = all(c["ok"] for c in checks)
    return {
        "ok": all_ok,
        "boundary": BOUNDARY,
        "production_ready_claim": False,
        "stable_live_routing_claim": False,
        "checks": checks,
        "summary": f"{sum(1 for c in checks if c['ok'])}/{len(checks)} checks passed",
    }


def check_live_routing_events(
    text: str,
    *,
    required_tools: Iterable[str] = DEFAULT_REQUIRED_LIVE_TOOLS,
    min_first_class_results: int = 1,
) -> dict[str, Any]:
    payloads = list(_payloads_from_text(text))
    required = tuple(tool.strip() for tool in required_tools if tool.strip())
    summary = {
        "total_payloads": len(payloads),
        "first_class_fmc_results": 0,
        "successful_first_class_results": 0,
        "failed_first_class_results": 0,
        "allowed_first_class_results": 0,
        "denied_first_class_results": 0,
        "internal_memory_results": 0,
        "unsupported_payloads": 0,
    }
    first_class_tools: dict[str, int] = {}
    internal_tools: dict[str, int] = {}
    examples: list[dict[str, Any]] = []

    for payload in payloads:
        result = _result_payload(payload)
        if result is None:
            summary["unsupported_payloads"] += 1
            continue
        bridge = _bridge_payload(result)
        bridge_tool = str(bridge.get("tool") or "").strip()
        result_tool = str(result.get("tool") or "").strip()
        tool = bridge_tool or result_tool
        if bridge_tool.startswith("fmc_"):
            summary["first_class_fmc_results"] += 1
            first_class_tools[bridge_tool] = first_class_tools.get(bridge_tool, 0) + 1
            decision = _permission_decision(bridge)
            if _result_successful(result):
                summary["successful_first_class_results"] += 1
            else:
                summary["failed_first_class_results"] += 1
            if decision == "deny":
                summary["denied_first_class_results"] += 1
            elif decision == "allow":
                summary["allowed_first_class_results"] += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "tool": bridge_tool,
                        "result_tool": result_tool,
                        "message_id": _redacted_id(str(result.get("message_id") or "")),
                        "permission_decision": decision,
                        "request_id_present": bool(bridge.get("request_id")),
                        "trace_id_present": bool(bridge.get("trace_id")),
                        "publish_mode": _publish_mode(result),
                    }
                )
        elif result_tool.startswith("memory.") or tool.startswith("memory."):
            summary["internal_memory_results"] += 1
            internal_tools[tool] = internal_tools.get(tool, 0) + 1
        else:
            summary["unsupported_payloads"] += 1

    missing_required = [tool for tool in required if first_class_tools.get(tool, 0) <= 0]
    ok = summary["successful_first_class_results"] >= min_first_class_results and not missing_required
    reason = "first_class_live_routing_evidence_seen" if ok else _live_failure_reason(summary, missing_required)
    return {
        "ok": ok,
        "gate": "feishu_first_class_routing_evidence",
        "boundary": LIVE_EVIDENCE_BOUNDARY,
        "required": {
            "required_tools": list(required),
            "min_first_class_results": min_first_class_results,
        },
        "summary": summary,
        "first_class_tools": first_class_tools,
        "internal_tools": internal_tools,
        "missing_required_tools": missing_required,
        "examples": examples,
        "reason": reason,
        "next_step": "" if ok else _live_next_step(reason, missing_required),
        "stable_live_routing_claim": False,
    }


def format_human_result(result: dict) -> str:
    lines = [
        f"Feishu DM Routing Readiness Check: {result['summary']}",
        f"Boundary: {result.get('boundary') or BOUNDARY}",
        "",
    ]
    for check in result["checks"]:
        status = "PASS" if check["ok"] else "FAIL"
        lines.append(f"  {status} {check['name']}: {check['detail']}")
    lines.append("")
    if result["ok"]:
        lines.append(
            "Local/staging readiness checks passed. Do not claim stable live Feishu routing without captured live result evidence."
        )
    else:
        lines.append(
            "Some readiness checks failed. Fix the issues above before collecting live Feishu routing evidence."
        )
    return "\n".join(lines)


def format_live_evidence_result(result: dict[str, Any]) -> str:
    lines = [
        f"Feishu First-class Routing Evidence: ok={str(result['ok']).lower()}",
        f"reason: {result['reason']}",
        f"Boundary: {result.get('boundary') or LIVE_EVIDENCE_BOUNDARY}",
        f"summary: {json.dumps(result['summary'], ensure_ascii=False, sort_keys=True)}",
        f"first_class_tools: {json.dumps(result['first_class_tools'], ensure_ascii=False, sort_keys=True)}",
    ]
    if result.get("missing_required_tools"):
        lines.append(f"missing_required_tools: {', '.join(result['missing_required_tools'])}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


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
    if "result" in line or "tool" in line or "tool_result" in line:
        return line
    raw_line = line.get("raw_line")
    if isinstance(raw_line, str):
        parsed = _parse_json(raw_line)
        if isinstance(parsed, dict):
            return parsed
    for key in ("payload", "data", "raw", "message", "1"):
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
    return line


def _result_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
    if result and ("tool" in result or "tool_result" in result or "bridge" in result):
        return result
    if "tool" in payload or "tool_result" in payload or "bridge" in payload:
        return payload
    for key in ("payload", "data", "message", "raw", "1"):
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
    return None


def _bridge_payload(result: dict[str, Any]) -> dict[str, Any]:
    bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else None
    if bridge is not None:
        return bridge
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    bridge = tool_result.get("bridge") if isinstance(tool_result.get("bridge"), dict) else {}
    return bridge


def _permission_decision(bridge: dict[str, Any]) -> str:
    decision = bridge.get("permission_decision")
    if isinstance(decision, dict):
        return str(decision.get("decision") or "").strip()
    return ""


def _result_successful(result: dict[str, Any]) -> bool:
    if result.get("ok") is False:
        return False
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    if tool_result.get("ok") is False:
        return False
    return True


def _publish_mode(result: dict[str, Any]) -> str:
    publish = result.get("publish") if isinstance(result.get("publish"), dict) else {}
    return str(publish.get("mode") or "").strip()


def _live_failure_reason(summary: dict[str, int], missing_required: list[str]) -> str:
    if summary["first_class_fmc_results"] == 0 and summary["internal_memory_results"]:
        return "only_internal_memory_results_seen"
    if summary["first_class_fmc_results"] == 0:
        return "first_class_fmc_result_missing"
    if summary["allowed_first_class_results"] == 0 and summary["denied_first_class_results"]:
        return "only_denied_first_class_results_seen"
    if summary["successful_first_class_results"] == 0:
        return "first_class_live_routing_without_successful_result"
    if missing_required:
        return "missing_required_first_class_tools"
    return "first_class_live_routing_evidence_incomplete"


def _live_next_step(reason: str, missing_required: list[str]) -> str:
    if reason == "only_internal_memory_results_seen":
        return "当前日志只证明 Python 内部 memory.* 结果；需要 OpenClaw first-class fmc_* bridge result。"
    if reason == "only_denied_first_class_results_seen":
        return "当前只看到 first-class deny-path；需要至少一条 allow-path，并补齐关键工具动作。"
    if reason == "first_class_live_routing_without_successful_result":
        return "当前看到 first-class bridge，但没有成功 tool result；需要真实 Feishu/OpenClaw allow-path 成功结果。"
    if reason == "missing_required_first_class_tools":
        return f"继续在真实 Feishu/OpenClaw 路径触发并导出这些工具结果：{', '.join(missing_required)}。"
    return "导出真实 Feishu/OpenClaw gateway result log，并确认包含 fmc_* bridge tool、request_id、trace_id 和 permission_decision。"


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_embedded_json(text: str) -> Any:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return _parse_json(text[start : end + 1])


def _redacted_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Feishu DM routing status")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    parser.add_argument(
        "--event-log",
        type=Path,
        default=None,
        help="Audit captured NDJSON/JSON/OpenClaw log evidence for first-class fmc_* routing.",
    )
    parser.add_argument(
        "--required-tools",
        default=",".join(DEFAULT_REQUIRED_LIVE_TOOLS),
        help="Comma-separated fmc_* tools required in --event-log mode.",
    )
    parser.add_argument("--min-first-class-results", type=int, default=1)
    args = parser.parse_args()

    if args.event_log:
        result = check_live_routing_events(
            args.event_log.read_text(encoding="utf-8"),
            required_tools=args.required_tools.split(","),
            min_first_class_results=args.min_first_class_results,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(format_live_evidence_result(result))
        return 0 if result["ok"] else 1

    result = check_feishu_dm_routing()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_human_result(result))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
