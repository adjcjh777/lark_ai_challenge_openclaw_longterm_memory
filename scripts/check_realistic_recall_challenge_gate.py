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

DEFAULT_CASES = ROOT / "benchmarks/copilot_realistic_recall_challenge.json"
DEFAULT_THRESHOLDS = {
    "corpus_event_count_min": 80,
    "query_count_min": 125,
    "case_pass_rate_min": 0.50,
    "recall_at_3_min": 0.60,
    "evidence_coverage_min": 0.70,
    "abstention_accuracy_min": 0.30,
    "permission_negative_accuracy_min": 1.0,
    "distractor_leakage_rate_max": 0.25,
    "stale_leakage_rate_max": 0.50,
}
BOUNDARY = (
    "realistic shared-corpus benchmark validity gate; not production live proof, "
    "not production SLO, and not production real-user stability evidence"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the realistic shared-corpus recall challenge and check minimum validity thresholds."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    benchmark = run_benchmark(args.cases)
    report = build_challenge_gate_report(benchmark, source_path=args.cases)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def build_challenge_gate_report(
    benchmark: dict[str, Any],
    *,
    thresholds: dict[str, float] | None = None,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}
    layers = benchmark.get("layers") if isinstance(benchmark.get("layers"), dict) else {}
    checks = {
        "corpus_event_count": _min_check(layers, "corpus_event_count", thresholds["corpus_event_count_min"]),
        "query_count": _min_check(layers, "query_count", thresholds["query_count_min"]),
        "case_pass_rate": _min_check(summary, "case_pass_rate", thresholds["case_pass_rate_min"]),
        "recall_at_3": _min_check(summary, "recall_at_3", thresholds["recall_at_3_min"]),
        "evidence_coverage": _min_check(summary, "evidence_coverage", thresholds["evidence_coverage_min"]),
        "abstention_accuracy": _min_check(
            summary, "abstention_accuracy", thresholds["abstention_accuracy_min"]
        ),
        "permission_negative_accuracy": _min_check(
            summary, "permission_negative_accuracy", thresholds["permission_negative_accuracy_min"]
        ),
        "distractor_leakage_rate": _max_check(
            summary, "distractor_leakage_rate", thresholds["distractor_leakage_rate_max"]
        ),
        "stale_leakage_rate": _max_check(summary, "stale_leakage_rate", thresholds["stale_leakage_rate_max"]),
    }
    failed_checks = [name for name, check in checks.items() if check["status"] != "pass"]
    failed_cases = [
        {
            "case_id": result.get("case_id"),
            "category": result.get("category"),
            "failure_type": result.get("failure_type"),
            "recommended_fix": result.get("recommended_fix"),
            "failure_debug_hint": result.get("failure_debug_hint"),
        }
        for result in benchmark.get("results", [])
        if isinstance(result, dict) and not result.get("passed")
    ]
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
                "answerable_query_count",
                "no_answer_query_count",
                "permission_negative_count",
                "recall_at_1",
                "recall_at_3",
                "mrr",
                "evidence_coverage",
                "evidence_source_accuracy",
                "abstention_accuracy",
                "permission_negative_accuracy",
                "distractor_leakage_rate",
                "stale_leakage_rate",
            )
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "failure_type_counts": summary.get("failure_type_counts") or {},
        "failed_cases": failed_cases,
        "next_step": (
            "Benchmark validity passed; use failed_cases as product hardening backlog, not as production proof."
            if not failed_checks
            else "Fix the benchmark fixture shape or retrieval quality before claiming the realistic challenge gate."
        ),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Realistic Recall Challenge Gate",
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
    lines.append("")
    lines.append("failure_type_counts:")
    for failure_type, count in sorted(report["failure_type_counts"].items()):
        lines.append(f"  {failure_type}: {count}")
    lines.append("")
    lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


def _min_check(values: dict[str, Any], key: str, threshold: float) -> dict[str, Any]:
    actual = _number(values.get(key))
    return {
        "status": "pass" if actual >= threshold else "fail",
        "actual": actual,
        "threshold": threshold,
        "operator": ">=",
    }


def _max_check(values: dict[str, Any], key: str, threshold: float) -> dict[str, Any]:
    actual = _number(values.get(key))
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
