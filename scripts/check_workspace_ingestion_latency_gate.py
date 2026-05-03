#!/usr/bin/env python3
"""Local latency gate for workspace/document ingestion routing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.benchmark import run_document_ingestion_benchmark  # noqa: E402

DEFAULT_CASES = PROJECT_ROOT / "benchmarks/day5_ingestion_cases.json"
BOUNDARY = (
    "local document/workspace ingestion latency baseline; no Feishu API calls, "
    "no production SLO proof, no full workspace ingestion claim"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local workspace/document ingestion latency and quality against conservative thresholds."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--avg-latency-ms-max", type=float, default=750.0)
    parser.add_argument("--max-latency-ms-max", type=float, default=1500.0)
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=1,
        help="Run unmeasured warmup iterations before checking the local hot path.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    for _ in range(max(0, args.warmup_runs)):
        run_document_ingestion_benchmark(args.cases)
    benchmark = run_document_ingestion_benchmark(args.cases)
    report = build_latency_gate_report(
        benchmark,
        cases_path=args.cases,
        avg_latency_ms_max=args.avg_latency_ms_max,
        max_latency_ms_max=args.max_latency_ms_max,
        warmup_runs=max(0, args.warmup_runs),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def build_latency_gate_report(
    benchmark: dict[str, Any],
    *,
    cases_path: str | Path,
    avg_latency_ms_max: float,
    max_latency_ms_max: float,
    warmup_runs: int = 0,
) -> dict[str, Any]:
    summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}
    results = [item for item in benchmark.get("results", []) if isinstance(item, dict)]
    latencies = [float(item.get("ingestion_latency_ms") or 0.0) for item in results]
    max_latency = max(latencies) if latencies else 0.0
    checks = {
        "case_pass_rate": _min_check(summary.get("case_pass_rate"), 1.0),
        "quote_coverage": _min_check(summary.get("avg_quote_coverage"), 1.0),
        "noise_rejection": _min_check(summary.get("avg_noise_rejection_rate"), 1.0),
        "document_evidence_coverage": _min_check(summary.get("document_evidence_coverage"), 1.0),
        "avg_ingestion_latency_ms": _max_check(summary.get("avg_ingestion_latency_ms"), avg_latency_ms_max),
        "max_ingestion_latency_ms": _max_check(max_latency, max_latency_ms_max),
    }
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "boundary": BOUNDARY,
        "cases": str(cases_path),
        "thresholds": {
            "avg_latency_ms_max": avg_latency_ms_max,
            "max_latency_ms_max": max_latency_ms_max,
        },
        "warmup_runs": warmup_runs,
        "summary": {
            "case_count": summary.get("case_count"),
            "case_pass_rate": summary.get("case_pass_rate"),
            "avg_quote_coverage": summary.get("avg_quote_coverage"),
            "avg_noise_rejection_rate": summary.get("avg_noise_rejection_rate"),
            "document_evidence_coverage": summary.get("document_evidence_coverage"),
            "avg_ingestion_latency_ms": summary.get("avg_ingestion_latency_ms"),
            "max_ingestion_latency_ms": round(max_latency, 3),
        },
        "checks": checks,
        "failures": failures,
        "case_latencies": [
            {
                "case_id": item.get("case_id"),
                "ingestion_latency_ms": item.get("ingestion_latency_ms"),
                "candidate_count": item.get("candidate_count"),
                "passed": item.get("passed"),
            }
            for item in results
        ],
        "next_step": ""
        if not failures
        else "Fix quality failures or investigate local ingestion latency before expanding workspace ingestion.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Latency Gate",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(
            f"  {name}: {check['status']} "
            f"(actual={check['actual']}, threshold={check['operator']} {check['threshold']})"
        )
    if report["failures"]:
        lines.append("")
        lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


def _min_check(value: Any, threshold: float) -> dict[str, Any]:
    actual = _number(value)
    return {
        "status": "pass" if actual >= threshold else "fail",
        "actual": actual,
        "threshold": threshold,
        "operator": ">=",
    }


def _max_check(value: Any, threshold: float) -> dict[str, Any]:
    actual = _number(value)
    return {
        "status": "pass" if actual <= threshold else "fail",
        "actual": actual,
        "threshold": threshold,
        "operator": "<=",
    }


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
