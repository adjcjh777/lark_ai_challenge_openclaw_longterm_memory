#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_OLLAMA_MODELS = ("qwen3-embedding:0.6b-fp16", "bge-m3:567m")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase D live Cognee/Ollama embedding gate and clean up project Ollama models."
    )
    parser.add_argument("--json", action="store_true", help="Print the full gate report as JSON.")
    parser.add_argument("--provider-timeout", type=float, default=60.0)
    parser.add_argument(
        "--skip-spike-dry-run", action="store_true", help="Skip scripts/spike_cognee_local.py --dry-run."
    )
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Report running project models without stopping them."
    )
    args = parser.parse_args()

    report = run_live_embedding_gate(
        provider_timeout=args.provider_timeout,
        run_spike_dry_run=not args.skip_spike_dry_run,
        cleanup=not args.no_cleanup,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_gate_text(report))
        print("")
        print("JSON: python3 scripts/check_live_embedding_gate.py --json")
    return 0 if report["ok"] else 1


def run_live_embedding_gate(
    *,
    provider_timeout: float = 60.0,
    run_spike_dry_run: bool = True,
    cleanup: bool = True,
) -> dict[str, Any]:
    before = _ollama_ps()
    provider = _run_command(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_embedding_provider.py"),
            "--timeout",
            str(provider_timeout),
        ]
    )
    spike = (
        _run_command([sys.executable, str(ROOT / "scripts" / "spike_cognee_local.py"), "--dry-run"])
        if run_spike_dry_run
        else {"ok": True, "skipped": True, "command": "python3 scripts/spike_cognee_local.py --dry-run"}
    )

    after_live = _ollama_ps()
    running_before_cleanup = running_project_models(after_live.get("stdout", ""))
    stop_results = [_stop_ollama_model(model) for model in running_before_cleanup] if cleanup else []
    after_cleanup = _wait_for_ollama_cleanup() if stop_results else _ollama_ps()
    running_after_cleanup = running_project_models(after_cleanup.get("stdout", ""))

    provider_payload = provider.get("json") if isinstance(provider.get("json"), dict) else {}
    status = "pass" if provider["ok"] and spike["ok"] and not running_after_cleanup else "fail"
    if not provider["ok"]:
        status = "blocked"

    return {
        "ok": status == "pass",
        "phase": "Phase D Live Cognee / Ollama Embedding Gate",
        "scope": "live_embedding_gate_only",
        "boundary": "Runs a real embedding provider check, keeps Cognee as a narrow adapter, and cleans project Ollama models; this is not productized live.",
        "status": status,
        "provider": {
            "status": "pass" if provider["ok"] else "blocked",
            "command": provider["command"],
            "exit_code": provider["exit_code"],
            "model": provider_payload.get("model"),
            "ollama_model": provider_payload.get("ollama_model"),
            "endpoint": provider_payload.get("endpoint"),
            "expected_dimensions": provider_payload.get("expected_dimensions"),
            "actual_dimensions": provider_payload.get("actual_dimensions"),
            "error": _command_error(provider),
        },
        "cognee_spike_dry_run": {
            "status": "pass" if spike["ok"] else "blocked",
            "command": spike["command"],
            "exit_code": spike.get("exit_code"),
            "skipped": bool(spike.get("skipped")),
            "error": _command_error(spike),
        },
        "ollama_cleanup": {
            "status": "pass" if not running_after_cleanup else "warning",
            "project_models": list(PROJECT_OLLAMA_MODELS),
            "running_before_gate": running_project_models(before.get("stdout", "")),
            "running_before_cleanup": running_before_cleanup,
            "cleanup_enabled": cleanup,
            "stop_results": stop_results,
            "running_after_cleanup": running_after_cleanup,
            "ps_command": "ollama ps",
        },
        "next_step": "" if status == "pass" else _next_step(status, provider, running_after_cleanup),
    }


def format_gate_text(report: dict[str, Any]) -> str:
    provider = report["provider"]
    cleanup = report["ollama_cleanup"]
    spike = report["cognee_spike_dry_run"]
    lines = [
        str(report["phase"]),
        f"ok: {str(report['ok']).lower()}",
        f"status: {report['status']}",
        f"scope: {report['scope']}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
        (
            "- provider: "
            f"{provider['status']} model={provider.get('model')} endpoint={provider.get('endpoint')} "
            f"dimensions={provider.get('actual_dimensions')}/{provider.get('expected_dimensions')}"
        ),
        f"- cognee_spike_dry_run: {spike['status']} skipped={spike.get('skipped')}",
        (
            "- ollama_cleanup: "
            f"{cleanup['status']} before_cleanup={cleanup['running_before_cleanup']} "
            f"after_cleanup={cleanup['running_after_cleanup']}"
        ),
    ]
    if report.get("next_step"):
        lines.extend(["", f"next_step: {report['next_step']}"])
    return "\n".join(lines)


def running_project_models(ollama_ps_output: str) -> list[str]:
    running: list[str] = []
    for raw_line in ollama_ps_output.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        model = line.split()[0]
        if model in PROJECT_OLLAMA_MODELS and model not in running:
            running.append(model)
    return running


def _run_command(command: list[str]) -> dict[str, Any]:
    display = _display_command(command)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload: dict[str, Any] | None = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = None
    return {
        "ok": completed.returncode == 0,
        "command": display,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "json": payload,
    }


def _ollama_ps() -> dict[str, Any]:
    try:
        return _run_command(["ollama", "ps"])
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "command": "ollama ps",
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "json": None,
        }


def _stop_ollama_model(model: str) -> dict[str, Any]:
    try:
        result = _run_command(["ollama", "stop", model])
    except FileNotFoundError as exc:
        return {"ok": False, "command": f"ollama stop {model}", "exit_code": 127, "stderr": str(exc)}
    return {
        "ok": result["ok"],
        "command": result["command"],
        "exit_code": result["exit_code"],
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


def _wait_for_ollama_cleanup(*, attempts: int = 5, interval_seconds: float = 1.0) -> dict[str, Any]:
    last = _ollama_ps()
    for attempt in range(1, attempts + 1):
        if not running_project_models(last.get("stdout", "")):
            last["cleanup_confirm_attempt"] = attempt
            return last
        if attempt < attempts:
            time.sleep(interval_seconds)
            last = _ollama_ps()
    last["cleanup_confirm_attempt"] = attempts
    return last


def _command_error(result: dict[str, Any]) -> str | None:
    if result.get("ok"):
        return None
    payload = result.get("json")
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload.get("error"))
    return str(result.get("stderr") or result.get("stdout") or "").strip() or None


def _display_command(command: list[str]) -> str:
    if command and command[0] == sys.executable:
        return "python3 " + " ".join(
            str(Path(part).relative_to(ROOT)) if str(part).startswith(str(ROOT)) else part for part in command[1:]
        )
    return " ".join(command)


def _next_step(status: str, provider: dict[str, Any], running_after_cleanup: list[str]) -> str:
    if running_after_cleanup:
        return f"手动执行 ollama stop {' '.join(running_after_cleanup)}，再运行 ollama ps 确认无本项目模型驻留。"
    if status == "blocked":
        return _command_error(provider) or "检查 Ollama、litellm、embedding-provider.lock 和本地模型是否可用。"
    return "检查 provider dry-run 输出和 Cognee adapter 配置。"


if __name__ == "__main__":
    raise SystemExit(main())
