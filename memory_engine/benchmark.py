from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .models import DEFAULT_SCOPE
from .repository import MemoryRepository


def run_benchmark(cases_path: str | Path, *, scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="memory_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)

            for event in case.get("events", []):
                repo.remember(scope, event, source_type="benchmark")

            for index in range(int(case.get("noise_count", 0))):
                repo.add_noise_event(scope, f"无关闲聊样例 {index}: 今天同步一下普通进展。")

            started = time.perf_counter()
            recalled = repo.recall(scope, case["query"])
            latency_ms = round((time.perf_counter() - started) * 1000, 3)

            actual = recalled["answer"] if recalled else ""
            expected = case.get("expected_active_value", "")
            forbidden = case.get("forbidden_value")
            evidence_present = bool(recalled and recalled.get("source") and recalled["source"].get("quote"))
            expected_ok = expected in actual if expected else bool(actual)
            forbidden_ok = forbidden not in actual if forbidden else True
            passed = bool(expected_ok and forbidden_ok and evidence_present)

            results.append(
                {
                    "case_id": case["case_id"],
                    "case_type": case["type"],
                    "query": case["query"],
                    "expected": expected,
                    "actual": actual,
                    "forbidden": forbidden,
                    "passed": passed,
                    "latency_ms": latency_ms,
                    "evidence_present": evidence_present,
                    "recall": recalled,
                }
            )
            conn.close()

    return {
        "summary": _metrics(results),
        "results": results,
    }


def _metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    conflict_cases = [result for result in results if result["case_type"] == "conflict_update"]
    forbidden_cases = [result for result in results if result.get("forbidden")]
    leaked = [
        result
        for result in forbidden_cases
        if result["forbidden"] and result["forbidden"] in result["actual"]
    ]
    evidence_cases = [result for result in results if result["evidence_present"]]

    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "conflict_accuracy": _ratio(sum(1 for result in conflict_cases if result["passed"]), len(conflict_cases)),
        "stale_leakage_rate": _ratio(len(leaked), len(forbidden_cases)),
        "evidence_coverage": _ratio(len(evidence_cases), total),
        "avg_latency_ms": round(
            sum(result["latency_ms"] for result in results) / total,
            3,
        )
        if total
        else 0.0,
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)

