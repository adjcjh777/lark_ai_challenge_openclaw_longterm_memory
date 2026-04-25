from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .document_ingestion import ingest_document_source
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


def run_document_ingestion_benchmark(cases_path: str | Path, *, scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="doc_ingestion_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)

            started = time.perf_counter()
            ingestion = ingest_document_source(
                repo,
                case["document"],
                scope=scope,
                limit=int(case.get("limit", 24)),
            )
            ingestion_latency_ms = round((time.perf_counter() - started) * 1000, 3)

            candidate_quotes = [
                item.get("quote") or (item.get("memory") or {}).get("current_value") or ""
                for item in ingestion.get("candidates", [])
            ]
            expected_quotes = case.get("expected_quotes", [])
            forbidden_quotes = case.get("forbidden_quotes", [])
            quote_hits = [
                expected
                for expected in expected_quotes
                if any(expected in quote for quote in candidate_quotes)
            ]
            forbidden_hits = [
                forbidden
                for forbidden in forbidden_quotes
                if any(forbidden in quote for quote in candidate_quotes)
            ]
            candidate_count = int(ingestion.get("candidate_count", 0))
            candidate_min_ok = candidate_count >= int(case.get("expected_candidate_min", 1))
            quote_coverage = _ratio(len(quote_hits), len(expected_quotes))
            noise_rejection_rate = _ratio(len(forbidden_quotes) - len(forbidden_hits), len(forbidden_quotes))

            recall_results = []
            for recall_case in case.get("recalls", []):
                memory_id = _candidate_id_for_quote(ingestion, recall_case["confirm_quote"])
                confirmed = repo.confirm_candidate(memory_id) if memory_id else None
                recalled = repo.recall(scope, recall_case["query"])
                source = recalled.get("source") if recalled else {}
                actual = recalled.get("answer") if recalled else ""
                recall_results.append(
                    {
                        "query": recall_case["query"],
                        "expected": recall_case["expected"],
                        "actual": actual,
                        "confirmed_memory_id": memory_id,
                        "confirm_action": confirmed,
                        "document_source_present": bool(source and source.get("document_title") and source.get("quote")),
                        "passed": bool(
                            confirmed
                            and recalled
                            and recall_case["expected"] in actual
                            and source
                            and source.get("document_title")
                            and source.get("quote")
                        ),
                        "recall": recalled,
                    }
                )

            passed = bool(
                candidate_min_ok
                and quote_coverage == 1.0
                and not forbidden_hits
                and all(item["passed"] for item in recall_results)
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "document": case["document"],
                    "document_title": ingestion.get("document", {}).get("title"),
                    "candidate_count": candidate_count,
                    "expected_candidate_min": case.get("expected_candidate_min", 1),
                    "candidate_min_ok": candidate_min_ok,
                    "quote_coverage": quote_coverage,
                    "noise_rejection_rate": noise_rejection_rate,
                    "forbidden_hits": forbidden_hits,
                    "ingestion_latency_ms": ingestion_latency_ms,
                    "passed": passed,
                    "recalls": recall_results,
                }
            )
            conn.close()

    return {
        "summary": _document_ingestion_metrics(results),
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


def _document_ingestion_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "avg_candidate_count": round(sum(result["candidate_count"] for result in results) / total, 3) if total else 0.0,
        "avg_quote_coverage": round(sum(result["quote_coverage"] for result in results) / total, 4) if total else 0.0,
        "avg_noise_rejection_rate": round(sum(result["noise_rejection_rate"] for result in results) / total, 4) if total else 0.0,
        "document_evidence_coverage": _ratio(
            sum(1 for result in results for recall in result["recalls"] if recall["document_source_present"]),
            sum(len(result["recalls"]) for result in results),
        ),
        "avg_ingestion_latency_ms": round(sum(result["ingestion_latency_ms"] for result in results) / total, 3) if total else 0.0,
    }


def _candidate_id_for_quote(ingestion: dict[str, Any], expected_quote: str) -> str | None:
    for item in ingestion.get("candidates", []):
        quote = item.get("quote") or (item.get("memory") or {}).get("current_value") or ""
        if expected_quote in quote:
            return item.get("memory_id")
    return None


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)
