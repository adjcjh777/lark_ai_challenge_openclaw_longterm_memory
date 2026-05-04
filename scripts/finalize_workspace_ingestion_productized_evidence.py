#!/usr/bin/env python3
"""Finalize productized workspace ingestion evidence.

This is a read-only closeout checker. It reruns the strict productized
readiness gate and the objective completion audit against the same manifest,
then writes a small status file that is safe to use from launchd/cron or a
handoff run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_workspace_ingestion_objective_completion import (  # noqa: E402
    run_workspace_ingestion_objective_completion_audit,
)
from scripts.check_workspace_productized_ingestion_readiness import (  # noqa: E402
    run_productized_ingestion_check,
)

DEFAULT_EVIDENCE_DIR = ROOT / "logs" / "workspace-ingestion-productized-probe" / "20260504T042943Z"
DEFAULT_MANIFEST_PATH = DEFAULT_EVIDENCE_DIR / "productized-evidence.active.json"
DEFAULT_LONG_RUN_EVIDENCE_PATH = DEFAULT_EVIDENCE_DIR / "long-run-evidence.active.json"
DEFAULT_OBJECTIVE_OUTPUT_PATH = DEFAULT_EVIDENCE_DIR / "workspace-objective-completion.active.json"
DEFAULT_OUTPUT_PATH = DEFAULT_EVIDENCE_DIR / "workspace-productized-finalization.active.json"
BOUNDARY = (
    "workspace_productized_finalizer_read_only; reruns strict evidence gates and writes a closeout status, "
    "but does not run ingestion, send Feishu messages, start listeners, or mark the user goal complete by itself"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize productized Feishu workspace ingestion evidence from existing artifacts."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--long-run-evidence", type=Path, default=DEFAULT_LONG_RUN_EVIDENCE_PATH)
    parser.add_argument("--objective-output", type=Path, default=DEFAULT_OBJECTIVE_OUTPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--launchd-label",
        default="",
        help="Optional macOS launchd label to record as operational context. It is not a readiness substitute.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = finalize_workspace_ingestion_productized_evidence(
        manifest_path=args.manifest.expanduser(),
        long_run_evidence_path=args.long_run_evidence.expanduser(),
        objective_output_path=args.objective_output.expanduser(),
        output_path=args.output.expanduser(),
        launchd_label=args.launchd_label,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["goal_complete"] else 1


def finalize_workspace_ingestion_productized_evidence(
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    long_run_evidence_path: Path = DEFAULT_LONG_RUN_EVIDENCE_PATH,
    objective_output_path: Path = DEFAULT_OBJECTIVE_OUTPUT_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    launchd_label: str = "",
) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser()
    long_run_evidence_path = long_run_evidence_path.expanduser()
    objective_output_path = objective_output_path.expanduser()
    output_path = output_path.expanduser()

    readiness = run_productized_ingestion_check(manifest_path)
    objective = run_workspace_ingestion_objective_completion_audit(manifest_path)
    objective_output_path.parent.mkdir(parents=True, exist_ok=True)
    objective_output_path.write_text(json.dumps(objective, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    long_run_summary = _summarize_long_run_evidence(long_run_evidence_path)
    launchd_status = _inspect_launchd(launchd_label) if launchd_label else {"checked": False}
    goal_complete = bool(readiness.get("goal_complete")) and bool(objective.get("goal_complete"))
    result = {
        "ok": goal_complete,
        "goal_complete": goal_complete,
        "status": "complete" if goal_complete else "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "boundary": BOUNDARY,
        "production_ready_claim_allowed": goal_complete,
        "manifest_path": str(manifest_path.resolve()),
        "objective_output_path": str(objective_output_path.resolve()),
        "long_run_evidence_path": str(long_run_evidence_path.resolve()) if long_run_evidence_path.exists() else "",
        "productized_readiness": readiness,
        "objective_completion": objective,
        "long_run_summary": long_run_summary,
        "launchd_status": launchd_status,
        "blockers": _blockers(readiness, objective),
        "warnings": _warnings(long_run_summary, launchd_status),
        "next_step": _next_step(goal_complete, readiness, objective, long_run_summary),
        "output_path": str(output_path.resolve()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Productized Evidence Finalizer",
        f"status: {result['status']}",
        f"goal_complete: {str(result['goal_complete']).lower()}",
        f"manifest_path: {result['manifest_path']}",
        f"output_path: {result.get('output_path', '')}",
    ]
    long_run = result.get("long_run_summary") if isinstance(result.get("long_run_summary"), dict) else {}
    if long_run:
        lines.append(
            "long_run: "
            f"ok={str(long_run.get('ok')).lower()} "
            f"window_hours={long_run.get('window_hours')} "
            f"successful_runs={long_run.get('successful_run_count')} "
            f"unresolved_failed_runs={long_run.get('unresolved_failed_run_count')}"
        )
    if result.get("blockers"):
        lines.append("blockers:")
        for blocker in result["blockers"]:
            lines.append(f"  - {blocker['source']}: {blocker['reason']}")
    if result.get("warnings"):
        lines.append("warnings:")
        for warning in result["warnings"]:
            lines.append(f"  - {warning}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _summarize_long_run_evidence(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "reason": "long_run_evidence_missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"present": True, "ok": False, "reason": "long_run_evidence_invalid_json", "error": str(exc)}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "present": True,
        "ok": bool(payload.get("ok")),
        "failed_checks": payload.get("failed_checks", []),
        "window_hours": payload.get("window_hours"),
        "successful_run_count": payload.get("successful_run_count"),
        "unresolved_failed_run_count": payload.get("unresolved_failed_run_count"),
        "started_at": payload.get("started_at"),
        "ended_at": payload.get("ended_at"),
    }


def _inspect_launchd(label: str) -> dict[str, Any]:
    if sys.platform != "darwin":
        return {"checked": True, "ok": False, "reason": "launchd_only_available_on_macos", "label": label}
    target = f"gui/{os.getuid()}/{label}"
    try:
        completed = subprocess.run(
            ["launchctl", "print", target],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"checked": True, "ok": False, "reason": "launchctl_failed", "label": label, "error": str(exc)}
    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "checked": True,
        "ok": completed.returncode == 0,
        "label": label,
        "returncode": completed.returncode,
        "state": _find_launchd_value(output, "state"),
        "last_exit_code": _find_launchd_value(output, "last exit code"),
        "run_interval": _find_launchd_value(output, "run interval"),
    }


def _find_launchd_value(output: str, key: str) -> str:
    prefix = f"{key} = "
    for line in output.splitlines():
        text = line.strip()
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return ""


def _blockers(readiness: dict[str, Any], objective: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not readiness.get("goal_complete"):
        for blocker in readiness.get("blockers", []):
            blockers.append({"source": "productized_readiness", **blocker})
    if not objective.get("goal_complete"):
        for blocker in objective.get("blockers", []):
            blockers.append(
                {
                    "source": "objective_completion",
                    "requirement": blocker.get("requirement", ""),
                    "reason": blocker.get("reason", ""),
                    "path": blocker.get("path", ""),
                    "details": blocker.get("details", {}),
                }
            )
    return blockers


def _warnings(long_run_summary: dict[str, Any], launchd_status: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not long_run_summary.get("present"):
        warnings.append("long-run evidence file is missing")
    if launchd_status.get("checked") and not launchd_status.get("ok"):
        warnings.append(f"launchd status check did not pass for {launchd_status.get('label', '')}")
    return warnings


def _next_step(
    goal_complete: bool,
    readiness: dict[str, Any],
    objective: dict[str, Any],
    long_run_summary: dict[str, Any],
) -> str:
    if goal_complete:
        return "Inspect this finalizer output, then update README, handoff, Feishu board, and close the active goal."
    if long_run_summary.get("present") and not long_run_summary.get("ok"):
        return "Keep the scheduled long-run ticks collecting until the sanitized evidence window reaches 24h+ with zero unresolved failures."
    if readiness.get("next_step"):
        return str(readiness["next_step"])
    if objective.get("next_step"):
        return str(objective["next_step"])
    return "Inspect blockers and rerun after adding the missing productized evidence."


if __name__ == "__main__":
    raise SystemExit(main())
