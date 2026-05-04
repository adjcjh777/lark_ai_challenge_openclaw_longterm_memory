#!/usr/bin/env python3
"""Sample bounded workspace ingestion schedule reports over time."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_workspace_ingestion_long_run_evidence import (
    collect_workspace_ingestion_long_run_evidence,
)
from scripts.run_workspace_ingestion_schedule import DEFAULT_CONFIG_PATH, run_schedule, sanitize_report

DEFAULT_OUTPUT_DIR = ROOT / "logs" / "workspace-ingestion-schedule-samples"
BOUNDARY = (
    "workspace_ingestion_schedule_sampler_only; collects sanitized one-shot schedule reports over time, "
    "but does not prove productized full-workspace readiness until collector and production gate pass"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect sanitized workspace ingestion schedule samples.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--execute", action="store_true", help="Run schedule jobs. Default is plan-only.")
    parser.add_argument("--sample-count", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = sample_workspace_ingestion_schedule(
        config_path=Path(args.config).expanduser(),
        output_dir=Path(args.output_dir).expanduser(),
        execute=args.execute,
        sample_count=args.sample_count,
        interval_seconds=args.interval_seconds,
        evidence_refs=args.evidence_ref,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def sample_workspace_ingestion_schedule(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    execute: bool = False,
    sample_count: int = 1,
    interval_seconds: float = 0.0,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if sample_count <= 0:
        return _blocked("sample_count_must_be_positive", output_dir)
    if interval_seconds < 0:
        return _blocked("interval_seconds_must_be_non_negative", output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    index_path = output_dir / "samples.ndjson"
    for index in range(sample_count):
        report = sanitize_report(run_schedule(config_path, execute=execute))
        report_path = output_dir / f"schedule-report-{_stamp()}-{index + 1:03d}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        reports.append(report)
        sample = {
            "index": index + 1,
            "ok": bool(report.get("ok")),
            "mode": report.get("mode"),
            "status": report.get("status"),
            "generated_at": report.get("generated_at"),
            "report_path": str(report_path),
            "failed_jobs": report.get("failed_jobs", []),
        }
        samples.append(sample)
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
        if index < sample_count - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)

    refs = list(evidence_refs or []) or [str(output_dir)]
    collector = collect_workspace_ingestion_long_run_evidence(reports=reports, evidence_refs=refs)
    summary = {
        "ok": all(sample["ok"] for sample in samples),
        "boundary": BOUNDARY,
        "production_ready_claim": False,
        "mode": "execute" if execute else "plan",
        "output_dir": str(output_dir),
        "index_path": str(index_path),
        "sample_count": sample_count,
        "interval_seconds": interval_seconds,
        "samples": samples,
        "collector": collector,
        "next_step": (
            ""
            if collector.get("ok")
            else "Keep sampling sanitized schedule reports across a 24h+ window, then rerun the collector and production gate."
        ),
    }
    status_path = output_dir / "sampler-status.json"
    summary["status_path"] = str(status_path)
    status_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Schedule Sampler",
        f"ok: {str(result['ok']).lower()}",
        f"mode: {result.get('mode')}",
        f"boundary: {result['boundary']}",
        f"output_dir: {result.get('output_dir')}",
        f"sample_count: {result.get('sample_count')}",
    ]
    collector = result.get("collector") if isinstance(result.get("collector"), dict) else {}
    if collector:
        lines.append(f"collector_ok: {str(collector.get('ok')).lower()}")
        lines.append(f"collector_window_hours: {collector.get('window_hours')}")
        lines.append(f"collector_successful_runs: {collector.get('successful_run_count')}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _blocked(reason: str, output_dir: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "boundary": BOUNDARY,
        "production_ready_claim": False,
        "output_dir": str(output_dir),
        "reason": reason,
        "samples": [],
        "collector": {},
        "next_step": "Fix sampler arguments and rerun.",
    }


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
