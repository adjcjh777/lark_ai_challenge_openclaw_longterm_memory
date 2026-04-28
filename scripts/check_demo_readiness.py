#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.healthcheck import run_copilot_healthcheck
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from scripts.demo_seed import build_replay, seed_demo_memories


STATUS_ORDER = ("pass", "fail", "warning", "skipped", "not_configured", "fallback_used")
BOUNDARY = "demo/pre-production readiness only; no production deployment, no real Feishu push, no productized live claim."


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local demo/pre-production readiness checks without production deployment or real Feishu push."
    )
    parser.add_argument("--json", action="store_true", help="Print the readiness report as JSON.")
    parser.add_argument(
        "--demo-json-output",
        default="reports/demo_replay.json",
        help="Path where the full demo replay JSON should be written.",
    )
    args = parser.parse_args()

    report = run_demo_readiness(demo_json_output=Path(args.demo_json_output))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_readiness_text(report))
        print("")
        print("JSON: python3 scripts/check_demo_readiness.py --json")
    return 0 if report["ok"] else 1


def run_demo_readiness(*, demo_json_output: Path | None = None) -> dict[str, Any]:
    healthcheck = run_copilot_healthcheck()
    replay = _run_demo_replay()
    if demo_json_output is not None:
        demo_json_output.parent.mkdir(parents=True, exist_ok=True)
        demo_json_output.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")

    checks = {
        "openclaw_version": _openclaw_check(healthcheck),
        "phase6_healthcheck": _phase6_healthcheck(healthcheck),
        "demo_replay": evaluate_demo_replay(replay, demo_json_output=demo_json_output),
        "provider_config": _provider_config_check(healthcheck),
    }
    status_counts = _status_counts(checks)
    return {
        "ok": status_counts["fail"] == 0,
        "phase": "Demo-ready + Pre-production Readiness",
        "scope": "local_demo_readiness_only",
        "boundary": BOUNDARY,
        "checks": checks,
        "status_counts": status_counts,
    }


def evaluate_demo_replay(replay: dict[str, Any], *, demo_json_output: Path | None = None) -> dict[str, Any]:
    steps = replay.get("steps") if isinstance(replay.get("steps"), list) else []
    failed_steps = [
        str(step.get("name") or f"step_{index}")
        for index, step in enumerate(steps, start=1)
        if not _step_ok(step)
    ]
    contract_ok = bool((replay.get("openclaw_example_contract") or {}).get("ok"))
    status = "pass" if not failed_steps and contract_ok and bool(replay.get("ok")) else "fail"
    return {
        "status": status,
        "step_count": len(steps),
        "failed_steps": failed_steps,
        "openclaw_example_contract_ok": contract_ok,
        "json_output": str(demo_json_output) if demo_json_output else None,
        "next_step": "" if status == "pass" else "修复 failed_steps；demo readiness 只要任一 step ok=false 就必须失败。",
    }


def format_readiness_text(report: dict[str, Any]) -> str:
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
    lines.append("")
    lines.append(f"status_counts: {json.dumps(report.get('status_counts', {}), ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines)


def _run_demo_replay() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="feishu_memory_demo_readiness_") as temp_dir:
        db_path = Path(temp_dir) / "demo.sqlite"
        conn = connect(db_path)
        try:
            init_db(conn)
            repo = MemoryRepository(conn)
            seed_demo_memories(conn, "project:feishu_ai_challenge")
            return build_replay(repo, "project:feishu_ai_challenge", str(db_path), persistent=False)
        finally:
            conn.close()


def _openclaw_check(healthcheck: dict[str, Any]) -> dict[str, Any]:
    check = dict((healthcheck.get("checks") or {}).get("openclaw_version") or {})
    return {
        "status": check.get("status") or "fail",
        "locked_version": check.get("locked_version"),
        "local_version": check.get("local_version"),
        "command": "python3 scripts/check_openclaw_version.py",
        "next_step": check.get("next_step") or "",
    }


def _phase6_healthcheck(healthcheck: dict[str, Any]) -> dict[str, Any]:
    status = "pass" if healthcheck.get("ok") else "fail"
    return {
        "status": status,
        "command": "python3 scripts/check_copilot_health.py",
        "healthcheck_ok": bool(healthcheck.get("ok")),
        "status_counts": dict(healthcheck.get("status_counts") or {}),
        "next_step": "" if status == "pass" else "先修复 Phase 6 healthcheck 中的 fail 项。",
    }


def _provider_config_check(healthcheck: dict[str, Any]) -> dict[str, Any]:
    provider = dict((healthcheck.get("checks") or {}).get("embedding_provider") or {})
    status = str(provider.get("status") or "not_configured")
    return {
        "status": status if status in STATUS_ORDER else "warning",
        "check_mode": provider.get("check_mode") or "configuration_only",
        "provider": provider.get("provider"),
        "model": provider.get("model"),
        "fallback_available": bool(provider.get("fallback_available")),
        "fallback": provider.get("fallback"),
        "next_step": provider.get("next_step") or "",
    }


def _step_ok(step: Any) -> bool:
    if not isinstance(step, dict):
        return False
    output = step.get("output")
    return isinstance(output, dict) and output.get("ok") is True


def _status_counts(checks: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in STATUS_ORDER}
    for check in checks.values():
        status = str(check.get("status") or "fail")
        counts[status if status in counts else "fail"] += 1
    return counts


def _summary(name: str, check: dict[str, Any]) -> str:
    if name == "openclaw_version":
        return f" locked={check.get('locked_version')} local={check.get('local_version')}"
    if name == "phase6_healthcheck":
        return f" healthcheck_ok={check.get('healthcheck_ok')} counts={check.get('status_counts')}"
    if name == "demo_replay":
        return f" steps={check.get('step_count')} failed_steps={check.get('failed_steps')} json={check.get('json_output')}"
    if name == "provider_config":
        return f" mode={check.get('check_mode')} provider={check.get('provider')} model={check.get('model')}"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
