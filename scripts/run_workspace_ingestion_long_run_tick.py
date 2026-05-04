#!/usr/bin/env python3
"""Run one workspace ingestion long-run sampling tick.

This wrapper is meant for launchd/cron. Each invocation runs one bounded
workspace schedule, writes a sanitized report, then recomputes the long-run
evidence window from every report in the output directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_workspace_ingestion_long_run_evidence import (  # noqa: E402
    collect_workspace_ingestion_long_run_evidence,
)
from scripts.merge_workspace_productized_ingestion_evidence import (  # noqa: E402
    merge_workspace_productized_ingestion_evidence_patches,
)
from scripts.run_workspace_ingestion_schedule import DEFAULT_CONFIG_PATH, run_schedule, sanitize_report  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "logs" / "workspace-ingestion-productized-probe" / "long-run-active"
BOUNDARY = (
    "workspace_ingestion_long_run_tick_only; runs one bounded schedule tick and normalizes sanitized "
    "reports, but does not claim productized readiness unless the downstream gate passes"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one workspace ingestion long-run sampling tick.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--merge-patch", action="append", default=[])
    parser.add_argument("--long-run-output", default="")
    parser.add_argument("--merged-output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_workspace_ingestion_long_run_tick(
        config_path=Path(args.config).expanduser(),
        output_dir=Path(args.output_dir).expanduser(),
        evidence_refs=args.evidence_ref,
        merge_patch_paths=[Path(path).expanduser() for path in args.merge_patch],
        long_run_output=Path(args.long_run_output).expanduser() if args.long_run_output else None,
        merged_output=Path(args.merged_output).expanduser() if args.merged_output else None,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def run_workspace_ingestion_long_run_tick(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    evidence_refs: list[str] | None = None,
    merge_patch_paths: list[Path] | None = None,
    long_run_output: Path | None = None,
    merged_output: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = sanitize_report(run_schedule(config_path, execute=True))
    report_path = _unique_report_path(output_dir)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    sample = {
        "generated_at": report.get("generated_at"),
        "ok": bool(report.get("ok")),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "report_path": str(report_path),
        "failed_jobs": report.get("failed_jobs", []),
    }
    index_path = output_dir / "samples.ndjson"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")

    reports = _load_reports(output_dir)
    refs = list(evidence_refs or []) or [str(output_dir)]
    collector = collect_workspace_ingestion_long_run_evidence(reports=reports, evidence_refs=refs)
    long_run_path = long_run_output or output_dir / "long-run-evidence.partial.json"
    long_run_path.parent.mkdir(parents=True, exist_ok=True)
    long_run_path.write_text(json.dumps(collector, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    merge_result: dict[str, Any] | None = None
    patches = list(merge_patch_paths or [])
    if patches:
        patches.append(long_run_path)
        merge_result = merge_workspace_productized_ingestion_evidence_patches(
            patch_paths=patches,
            output_path=merged_output or output_dir / "productized-evidence.long-run.partial.json",
        )

    ok = bool(report.get("ok"))
    result = {
        "ok": ok,
        "boundary": BOUNDARY,
        "production_ready_claim": False,
        "config_path": str(config_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "report_path": str(report_path.resolve()),
        "index_path": str(index_path.resolve()),
        "long_run_output": str(long_run_path.resolve()),
        "schedule_report_count": len(reports),
        "collector_ok": bool(collector.get("ok")),
        "collector_failed_checks": collector.get("failed_checks", []),
        "collector_window_hours": collector.get("window_hours"),
        "collector_successful_runs": collector.get("successful_run_count"),
        "merge_result": merge_result,
        "next_step": _next_step(report, collector, merge_result),
    }
    status_path = output_dir / "long-run-tick-status.json"
    result["status_path"] = str(status_path.resolve())
    status_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Long-run Tick",
        f"ok: {str(result['ok']).lower()}",
        f"collector_ok: {str(result.get('collector_ok')).lower()}",
        f"collector_window_hours: {result.get('collector_window_hours')}",
        f"collector_successful_runs: {result.get('collector_successful_runs')}",
        f"report_path: {result.get('report_path')}",
    ]
    merge = result.get("merge_result") if isinstance(result.get("merge_result"), dict) else {}
    if merge:
        validation = merge.get("validation") if isinstance(merge.get("validation"), dict) else {}
        lines.append(f"merged_goal_complete: {str(validation.get('goal_complete')).lower()}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _load_reports(output_dir: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("schedule-report-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            reports.append(payload)
    return reports


def _unique_report_path(output_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = output_dir / f"schedule-report-{stamp}.json"
    index = 2
    while candidate.exists():
        candidate = output_dir / f"schedule-report-{stamp}-{index:02d}.json"
        index += 1
    return candidate


def _next_step(report: dict[str, Any], collector: dict[str, Any], merge_result: dict[str, Any] | None) -> str:
    if not report.get("ok"):
        return "Inspect the failed sanitized schedule report before continuing the long-run window."
    if not collector.get("ok"):
        return "Keep launchd/cron ticks running until the sanitized reports cover a 24h+ window."
    if merge_result:
        validation = merge_result.get("validation") if isinstance(merge_result.get("validation"), dict) else {}
        if validation.get("goal_complete"):
            return "Productized workspace evidence gate is complete; update docs and board with this manifest."
        return "Long-run patch is ready, but merged productized gate still has blockers; inspect merge_result.validation."
    return "Long-run patch is ready; merge it with source, governance, operations, and rate-limit evidence."


if __name__ == "__main__":
    raise SystemExit(main())
