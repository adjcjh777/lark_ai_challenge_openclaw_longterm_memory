#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.benchmark import run_benchmark  # noqa: E402

DEFAULT_CASES = ROOT / "benchmarks/copilot_real_feishu_cases.json"
DEFAULT_THRESHOLDS = {
    "recall_at_3_min": 0.80,
    "false_memory_rate_max": 0.05,
    "false_reminder_rate_max": 0.05,
    "explanation_coverage_min": 0.80,
    "old_value_leakage_rate_max": 0.0,
}
BOUNDARY = (
    "pre-live local quality gate over sanitized real-expression fixtures; "
    "not real Feishu live evidence and not productized live proof"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check the sanitized real Feishu expression benchmark against UX-06 pre-live quality thresholds."
        )
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--recall-at-3-min", type=float, default=DEFAULT_THRESHOLDS["recall_at_3_min"])
    parser.add_argument(
        "--false-memory-rate-max", type=float, default=DEFAULT_THRESHOLDS["false_memory_rate_max"]
    )
    parser.add_argument(
        "--false-reminder-rate-max", type=float, default=DEFAULT_THRESHOLDS["false_reminder_rate_max"]
    )
    parser.add_argument(
        "--explanation-coverage-min", type=float, default=DEFAULT_THRESHOLDS["explanation_coverage_min"]
    )
    parser.add_argument(
        "--old-value-leakage-rate-max", type=float, default=DEFAULT_THRESHOLDS["old_value_leakage_rate_max"]
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    thresholds = {
        "recall_at_3_min": args.recall_at_3_min,
        "false_memory_rate_max": args.false_memory_rate_max,
        "false_reminder_rate_max": args.false_reminder_rate_max,
        "explanation_coverage_min": args.explanation_coverage_min,
        "old_value_leakage_rate_max": args.old_value_leakage_rate_max,
    }
    benchmark = run_benchmark(args.cases)
    report = build_quality_gate_report(benchmark, thresholds=thresholds, source_path=args.cases)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def build_quality_gate_report(
    benchmark: dict[str, Any],
    *,
    thresholds: dict[str, float] | None = None,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}
    checks = {
        "recall_at_3": _min_check(summary, "recall_at_3", thresholds["recall_at_3_min"]),
        "false_memory_rate": _max_check(summary, "false_memory_rate", thresholds["false_memory_rate_max"]),
        "false_reminder_rate": _max_check(summary, "false_reminder_rate", thresholds["false_reminder_rate_max"]),
        "explanation_coverage": _min_check(
            summary, "explanation_coverage", thresholds["explanation_coverage_min"]
        ),
        "old_value_leakage_rate": _max_check(
            summary, "old_value_leakage_rate", thresholds["old_value_leakage_rate_max"]
        ),
    }
    failed_checks = [name for name, check in checks.items() if check["status"] != "pass"]
    failed_cases = [
        {
            "case_id": result.get("case_id"),
            "failure_type": result.get("failure_type"),
            "recommended_fix": result.get("recommended_fix"),
            "failure_debug_hint": result.get("failure_debug_hint"),
        }
        for result in benchmark.get("results", [])
        if isinstance(result, dict) and not result.get("passed")
    ]
    failure_type_counts = summary.get("failure_type_counts")
    if not isinstance(failure_type_counts, dict):
        failure_type_counts = {}
    return {
        "ok": not failed_checks,
        "status": "pass" if not failed_checks else "fail",
        "boundary": BOUNDARY,
        "source": str(source_path or benchmark.get("source") or ""),
        "thresholds": thresholds,
        "summary": {
            key: summary.get(key)
            for key in (
                "case_count",
                "case_pass_rate",
                "recall_at_3",
                "false_memory_rate",
                "false_reminder_rate",
                "user_confirmation_burden",
                "explanation_coverage",
                "old_value_leakage_rate",
            )
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "failure_type_counts": failure_type_counts,
        "failed_cases": failed_cases,
        "next_step": ""
        if not failed_checks
        else "Fix the failing sanitized real-expression cases or keep UX-06 marked as not quality-gate complete.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Real Feishu Expression Quality Gate",
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
    if report["failed_checks"]:
        lines.append("")
        lines.append("failed cases:")
        for case in report["failed_cases"]:
            lines.append(f"  {case['case_id']}: {case['failure_type']}")
        lines.append("")
        lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


def _min_check(summary: dict[str, Any], key: str, threshold: float) -> dict[str, Any]:
    actual = _number(summary.get(key))
    return {
        "status": "pass" if actual >= threshold else "fail",
        "actual": actual,
        "threshold": threshold,
        "operator": ">=",
    }


def _max_check(summary: dict[str, Any], key: str, threshold: float) -> dict[str, Any]:
    actual = _number(summary.get(key))
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
