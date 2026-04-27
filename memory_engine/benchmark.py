from __future__ import annotations

import csv
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from .copilot.schemas import SearchRequest
from .copilot.service import CopilotService
from .db import connect, init_db
from .document_ingestion import ingest_document_source
from .models import DEFAULT_SCOPE
from .repository import MemoryRepository


def run_benchmark(cases_path: str | Path, *, scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if isinstance(cases, dict) and cases.get("benchmark_type") == "anti_interference":
        return run_anti_interference_benchmark(cases, source_path=cases_path, scope=scope)
    if isinstance(cases, list) and any(case.get("type") == "copilot_recall" for case in cases):
        return run_copilot_recall_benchmark(cases, source_path=cases_path, scope=scope)

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

            expected_layer = case.get("expected_layer")
            started = time.perf_counter()
            if case.get("type") == "copilot_layer" and expected_layer:
                recall_result = _run_copilot_layer_case(repo, case, scope=scope)
                recalled = recall_result["recall"]
                trace = recall_result["trace"]
                actual_layer = recall_result["actual_layer"]
            else:
                recalled = repo.recall(scope, case["query"])
                trace = None
                actual_layer = case.get("layer_hint")
            latency_ms = round((time.perf_counter() - started) * 1000, 3)

            actual = _answer_from_recall(recalled)
            expected = case.get("expected_active_value", "")
            forbidden = case.get("forbidden_value")
            evidence_present = _recall_has_evidence(recalled)
            expected_ok = expected in actual if expected else bool(actual)
            forbidden_ok = forbidden not in actual if forbidden else True
            layer_passed = actual_layer == expected_layer if expected_layer else True
            passed = bool(expected_ok and forbidden_ok and evidence_present and layer_passed)

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
                    "expected_layer": expected_layer,
                    "actual_layer": actual_layer,
                    "layer_passed": layer_passed,
                    "recall": recalled,
                    "trace": trace,
                }
            )
            conn.close()

    return {
        "summary": _metrics(results),
        "results": results,
    }


def _run_copilot_layer_case(repo: MemoryRepository, case: dict[str, Any], *, scope: str) -> dict[str, Any]:
    request = SearchRequest.from_payload(
        {
            "query": case["query"],
            "scope": scope,
            "top_k": 3,
            "filters": {"layer": case["expected_layer"]},
        }
    )
    response = CopilotService(repository=repo).search(request)
    result = response["results"][0] if response.get("results") else None
    return {
        "recall": result,
        "actual_layer": result.get("layer") if result else None,
        "trace": response.get("trace"),
    }


def run_copilot_recall_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="copilot_recall_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)

            for event in case.get("events", []):
                repo.remember(scope, event, source_type="benchmark_copilot_recall")

            for index in range(int(case.get("noise_count", 0))):
                repo.add_noise_event(scope, f"无关飞书群聊噪声 {index}: 今天同步一下普通进展。")

            started = time.perf_counter()
            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": case["query"],
                        "scope": scope,
                        "top_k": 3,
                    }
                )
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            conn.close()

        top_results = response.get("results", []) if response.get("ok") else []
        expected = case.get("expected_active_value", "")
        forbidden = case.get("forbidden_value")
        evidence_keyword = case.get("evidence_keyword", "")
        expected_rank = _copilot_expected_rank(top_results, expected)
        forbidden_leak = bool(forbidden and any(forbidden in item.get("current_value", "") for item in top_results))
        evidence_present = _copilot_evidence_present(top_results, evidence_keyword)
        recall_at_1 = expected_rank == 1
        recall_at_3 = expected_rank is not None and expected_rank <= 3
        passed = bool(recall_at_3 and evidence_present and not forbidden_leak)

        results.append(
            {
                "case_id": case["case_id"],
                "case_type": case["type"],
                "query": case["query"],
                "expected": expected,
                "forbidden": forbidden,
                "expected_rank": expected_rank,
                "recall_at_1": recall_at_1,
                "recall_at_3": recall_at_3,
                "evidence_present": evidence_present,
                "forbidden_leak": forbidden_leak,
                "passed": passed,
                "latency_ms": latency_ms,
                "top_candidates": top_results,
                "trace": response.get("trace"),
                "failure_debug_hint": case.get("failure_debug_hint"),
                "failure_category": case.get("failure_category"),
            }
        )

    return {
        "benchmark_type": "copilot_recall",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_recall_metrics(results),
        "results": results,
    }


def _answer_from_recall(recalled: dict[str, Any] | None) -> str:
    if not recalled:
        return ""
    return str(recalled.get("answer") or recalled.get("current_value") or "")


def _recall_has_evidence(recalled: dict[str, Any] | None) -> bool:
    if not recalled:
        return False
    if recalled.get("source") and recalled["source"].get("quote"):
        return True
    evidence = recalled.get("evidence")
    return bool(evidence and evidence[0].get("quote"))


def _copilot_expected_rank(top_results: list[dict[str, Any]], expected: str) -> int | None:
    if not expected:
        return 1 if top_results else None
    for index, item in enumerate(top_results, start=1):
        if expected in str(item.get("current_value") or ""):
            return index
    return None


def _copilot_evidence_present(top_results: list[dict[str, Any]], evidence_keyword: str) -> bool:
    if not evidence_keyword:
        return bool(top_results)
    for item in top_results:
        for evidence in item.get("evidence", []):
            if evidence_keyword in str(evidence.get("quote") or ""):
                return True
    return False


def run_anti_interference_benchmark(
    spec: dict[str, Any],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(prefix="anti_interference_benchmark_", suffix=".sqlite") as tmp:
        conn = connect(tmp.name)
        init_db(conn)
        repo = MemoryRepository(conn)

        memory_index: dict[str, dict[str, Any]] = {}
        for item in spec.get("curated_memories", []):
            result = repo.remember(
                scope,
                item["content"],
                source_type="benchmark_curated",
                source_id=item.get("source_id") or item["id"],
                created_by="benchmark",
            )
            memory = result["memory"]
            memory_index[item["id"]] = {
                "fixture_id": item["id"],
                "memory_id": result["memory_id"],
                "content": item["content"],
                "type": memory["type"],
                "subject": memory["subject"],
                "expected_value": item.get("expected_value") or item["content"],
            }

        noise_events = _expand_noise_events(spec)
        for content in noise_events:
            repo.add_noise_event(scope, content, source_type="benchmark_noise")

        _maybe_build_raw_events_fts(conn)

        recall_logs = []
        for query in spec.get("queries", []):
            started = time.perf_counter()
            candidates = repo.recall_candidates(scope, query["query"], limit=3)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)

            expected = memory_index[query["expected_memory_ref"]]
            rank = _candidate_rank(candidates, expected, query.get("expected_active_value"))
            passed = rank == 1
            recall_logs.append(
                {
                    "query_id": query["id"],
                    "query": query["query"],
                    "expected_memory_ref": query["expected_memory_ref"],
                    "expected_memory_id": expected["memory_id"],
                    "expected_active_value": query.get("expected_active_value") or expected["expected_value"],
                    "expected_type": expected["type"],
                    "expected_subject": expected["subject"],
                    "rank": rank,
                    "passed": passed,
                    "recall_at_1": rank == 1,
                    "recall_at_3": rank is not None and rank <= 3,
                    "mrr": round(1 / rank, 4) if rank else 0.0,
                    "latency_ms": latency_ms,
                    "top_candidates": candidates,
                    "diagnostic_raw_hits": _raw_event_hits(conn, query["query"]) if not passed else [],
                }
            )

        conn.close()

    summary = _anti_interference_metrics(
        recall_logs,
        curated_memory_count=len(memory_index),
        raw_event_count=len(memory_index) + len(noise_events),
    )
    return {
        "benchmark_type": "anti_interference",
        "name": spec.get("name") or Path(source_path).stem,
        "source": str(source_path),
        "layers": {
            "raw_events": len(memory_index) + len(noise_events),
            "curated_memories": len(memory_index),
            "recall_logs": len(recall_logs),
        },
        "summary": summary,
        "by_type": _group_metrics(recall_logs, "expected_type"),
        "by_subject": _group_metrics(recall_logs, "expected_subject"),
        "results": recall_logs,
    }


def write_benchmark_outputs(
    result: dict[str, Any],
    *,
    json_output: str | Path | None = None,
    csv_output: str | Path | None = None,
    markdown_output: str | Path | None = None,
) -> None:
    if json_output:
        _write_text(json_output, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if csv_output:
        _write_csv(csv_output, result.get("results", []))
    if markdown_output:
        _write_text(markdown_output, format_benchmark_report(result))


def format_benchmark_report(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    layers = result.get("layers", {})
    by_type = result.get("by_type", {})
    by_subject = result.get("by_subject", {})

    lines = [
        "# Benchmark Report",
        "",
        "日期：2026-04-25",
        "",
        "## D7 抗干扰召回评测",
        "",
        "本轮评测验证 Memory Engine 在大量无关群聊干扰下，是否仍能从 active memory 层召回关键企业记忆。D7 把数据分为三层：",
        "",
        "- raw events：完整消息归档，包含关键记忆写入和干扰对话，用于审计和失败定位。",
        "- curated memories：经过结构化抽取、去重和状态机管理的 active memory，是默认召回层。",
        "- recall logs：每次查询的候选、排名、延迟和失败诊断，用于复现实验结果。",
        "",
        "这种分层参考 Hermes persistent memory 的思路：长期记忆不是把所有聊天塞进 prompt，而是把高价值事实压缩成有界、可解释、可版本化的 active memory；raw archive 只在需要追溯上下文或定位失败时按需搜索。",
        "",
        "### 可复现实验命令",
        "",
        "```bash",
        "python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md --csv-output reports/day7_anti_interference.csv",
        "```",
        "",
        "### 数据规模",
        "",
        "| 层 | 数量 | 说明 |",
        "|---|---:|---|",
        f"| raw events | {layers.get('raw_events', 0)} | 关键记忆 + 干扰对话归档 |",
        f"| curated memories | {layers.get('curated_memories', 0)} | 已结构化并处于 active 状态的关键记忆 |",
        f"| recall logs | {layers.get('recall_logs', 0)} | 查询评测记录 |",
        "",
        "### 总体指标",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| Recall@1 | {summary.get('recall_at_1', 0.0):.4f} |",
        f"| Recall@3 | {summary.get('recall_at_3', 0.0):.4f} |",
        f"| MRR | {summary.get('mrr', 0.0):.4f} |",
        f"| 平均延迟 ms | {summary.get('avg_latency_ms', 0.0):.3f} |",
        f"| P95 延迟 ms | {summary.get('p95_latency_ms', 0.0):.3f} |",
        "",
        "### 按 Type 分项",
        "",
        "| Type | 查询数 | Recall@1 | Recall@3 | MRR | 平均延迟 ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(_metric_rows(by_type))
    lines.extend(
        [
            "",
            "### 按 Subject 分项",
            "",
            "| Subject | 查询数 | Recall@1 | Recall@3 | MRR | 平均延迟 ms |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(_metric_rows(by_subject))
    lines.extend(
        [
            "",
            "### 当前结论",
            "",
            "- D7 数据集覆盖 50 条关键记忆、1000 条干扰对话和 50 条查询，满足 P0 并完成 P1 干扰规模加码。",
            "- 评测输出同时支持机器可读 JSON、CSV 和评委可读 Markdown 摘要；CSV 默认写入 `reports/`，不作为提交物。",
            "- FTS5 仅用于失败样例定位，不替代 active memory 状态机和结构化召回路径。",
            "",
            "### 局限",
            "",
            "- 当前 D7 主要验证抗干扰召回；矛盾更新专项和效能对比将在 D8/D9 补齐。",
            "- 召回仍是规则打分，不使用 embedding；这有利于解释性，但对复杂语义改写的覆盖有限。",
        ]
    )
    return "\n".join(lines) + "\n"


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
    layer_cases = [result for result in results if result.get("expected_layer")]
    layer_passed = [result for result in layer_cases if result.get("layer_passed")]

    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "conflict_accuracy": _ratio(sum(1 for result in conflict_cases if result["passed"]), len(conflict_cases)),
        "stale_leakage_rate": _ratio(len(leaked), len(forbidden_cases)),
        "evidence_coverage": _ratio(len(evidence_cases), total),
        "layer_case_count": len(layer_cases),
        "layer_accuracy": _ratio(len(layer_passed), len(layer_cases)) if layer_cases else 0.0,
        "avg_latency_ms": round(
            sum(result["latency_ms"] for result in results) / total,
            3,
        )
        if total
        else 0.0,
    }


def _copilot_recall_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    recall_at_1 = sum(1 for result in results if result["recall_at_1"])
    recall_at_3 = sum(1 for result in results if result["recall_at_3"])
    evidence_present = sum(1 for result in results if result["evidence_present"])
    forbidden_cases = [result for result in results if result.get("forbidden")]
    forbidden_leaks = [result for result in forbidden_cases if result["forbidden_leak"]]
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "query_count": total,
        "recall_at_1": _ratio(recall_at_1, total),
        "recall_at_3": _ratio(recall_at_3, total),
        "evidence_coverage": _ratio(evidence_present, total),
        "stale_leakage_rate": _ratio(len(forbidden_leaks), len(forbidden_cases)),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
    }


def _anti_interference_metrics(
    results: list[dict[str, Any]],
    *,
    curated_memory_count: int,
    raw_event_count: int,
) -> dict[str, Any]:
    total = len(results)
    latencies = sorted(result["latency_ms"] for result in results)
    recall_at_1 = sum(1 for result in results if result["recall_at_1"])
    recall_at_3 = sum(1 for result in results if result["recall_at_3"])
    return {
        "case_count": total,
        "case_pass_rate": _ratio(recall_at_1, total),
        "query_count": total,
        "curated_memory_count": curated_memory_count,
        "raw_event_count": raw_event_count,
        "noise_event_count": max(raw_event_count - curated_memory_count, 0),
        "recall_at_1": _ratio(recall_at_1, total),
        "recall_at_3": _ratio(recall_at_3, total),
        "mrr": round(sum(result["mrr"] for result in results) / total, 4) if total else 0.0,
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
    }


def _group_metrics(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        groups.setdefault(result.get(key) or "unknown", []).append(result)
    return {
        group: _anti_interference_metrics(
            items,
            curated_memory_count=len({item["expected_memory_id"] for item in items}),
            raw_event_count=len(items),
        )
        for group, items in sorted(groups.items())
    }


def _expand_noise_events(spec: dict[str, Any]) -> list[str]:
    explicit = list(spec.get("noise_events", []))
    noise = spec.get("noise", {})
    count = int(noise.get("count", 0))
    templates = noise.get("templates") or ["大家今天同步一下普通进展，暂无需要沉淀的长期记忆。"]
    generated = [
        template.format(index=index, shard=index % 17, topic=index % 9)
        for index in range(1, max(count - len(explicit), 0) + 1)
        for template in [templates[(index - 1) % len(templates)]]
    ]
    return explicit + generated


def _candidate_rank(
    candidates: list[dict[str, Any]],
    expected: dict[str, Any],
    expected_value: str | None,
) -> int | None:
    for index, candidate in enumerate(candidates, start=1):
        answer = candidate.get("answer") or ""
        if candidate.get("memory_id") == expected["memory_id"]:
            return index
        if expected_value and expected_value in answer:
            return index
    return None


def _maybe_build_raw_events_fts(conn) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.raw_events_fts USING fts5(content, event_id UNINDEXED)")
        conn.execute(
            """
            INSERT INTO temp.raw_events_fts(content, event_id)
            SELECT content, id FROM raw_events
            """
        )
    except Exception:
        return


def _raw_event_hits(conn, query: str) -> list[dict[str, Any]]:
    tokens = [char for char in query if char.strip()][:8]
    fts_query = " OR ".join(tokens)
    if not fts_query:
        return []
    try:
        rows = conn.execute(
            """
            SELECT event_id, snippet(raw_events_fts, 0, '[', ']', '...', 12) AS snippet
            FROM temp.raw_events_fts
            WHERE raw_events_fts MATCH ?
            LIMIT 3
            """,
            (fts_query,),
        ).fetchall()
    except Exception:
        rows = conn.execute(
            """
            SELECT id AS event_id, content AS snippet
            FROM raw_events
            WHERE content LIKE ?
            LIMIT 3
            """,
            (f"%{query[:4]}%",),
        ).fetchall()
    return [dict(row) for row in rows]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = min(int(round((len(values) - 1) * percentile)), len(values) - 1)
    return round(values[index], 3)


def _metric_rows(groups: dict[str, Any]) -> list[str]:
    if not groups:
        return ["| 无 | 0 | 0.0000 | 0.0000 | 0.0000 | 0.000 |"]
    return [
        "| {name} | {count} | {r1:.4f} | {r3:.4f} | {mrr:.4f} | {latency:.3f} |".format(
            name=name,
            count=metrics.get("query_count", 0),
            r1=metrics.get("recall_at_1", 0.0),
            r3=metrics.get("recall_at_3", 0.0),
            mrr=metrics.get("mrr", 0.0),
            latency=metrics.get("avg_latency_ms", 0.0),
        )
        for name, metrics in groups.items()
    ]


def _write_csv(path: str | Path, results: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "query_id",
        "expected_type",
        "expected_subject",
        "rank",
        "recall_at_1",
        "recall_at_3",
        "mrr",
        "latency_ms",
        "query",
        "expected_active_value",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow({field: result.get(field) for field in fields})


def _write_text(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
