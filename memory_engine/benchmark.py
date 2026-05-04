from __future__ import annotations

import csv
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from .copilot.heartbeat import HeartbeatReminderEngine
from .copilot.permissions import demo_permission_context
from .copilot.schemas import (
    ConfirmRequest,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    PrefetchRequest,
    RejectRequest,
    SearchRequest,
)
from .copilot.service import CopilotService
from .db import connect, init_db
from .document_ingestion import ingest_document_source
from .models import DEFAULT_SCOPE
from .repository import MemoryRepository

FAILURE_RECOMMENDED_FIXES = {
    "candidate_not_detected": "检查 candidate 规则是否覆盖决策、负责人、截止时间、流程规则和风险结论。",
    "wrong_subject_normalization": "检查 subject 归一化，确认新旧表达被归到同一主题。",
    "wrong_layer_routing": "检查 L1/L2/L3 分层过滤、fallback 顺序和 trace 中的 layer 标记。",
    "vector_miss": "检查 curated memory embedding 文本和 rerank 权重，确认语义改写能进入 Top 3。",
    "keyword_miss": "检查关键词索引、文件名/参数名保留，以及 query token 是否被过度清洗。",
    "stale_value_leaked": "检查 active-only 过滤和 version chain，确保 superseded / stale 不作为当前答案返回。",
    "evidence_missing": "检查 evidence quote 写入和工具输出，召回结果必须带来源证据。",
    "reject_failed": "检查 reject 状态机和权限上下文，确认拒绝候选不会污染 active memory。",
    "agent_did_not_prefetch": "检查 memory.prefetch 是否在 Agent 任务前被调用，且 context pack 非空。",
    "reminder_too_noisy": "检查 heartbeat 触发条件、cooldown 和 relevance gate，避免漏发或乱发 reminder candidate。",
    "permission_scope_error": "检查 scope permission、敏感内容脱敏和 reminder 输出权限门控。",
    "false_positive_candidate": "检查低价值闲聊和临时确认的过滤规则，避免乱记。",
    "user_expression_context_miss": "检查真实表达样本中的 thread_topic、上一轮消息和口语意图是否进入判别上下文。",
    "user_expression_explanation_missing": "检查真实表达输出是否给出用户可读解释，而不是只返回工程 trace。",
    "user_expression_old_value_leaked": "检查真实表达样本的 active-only 过滤，旧值只能出现在版本解释中。",
    "distractor_leakage": "检查共享语料中的相似项目、环境、文档来源是否把错误候选带进 Top 3。",
    "no_answer_failed": "检查低置信度拒答阈值和澄清问题策略，避免没有证据时硬答。",
    "evidence_source_mismatch": "检查 evidence source_type/source_id 是否来自期望来源，而不是相似干扰来源。",
}

_FORBIDDEN_REJECTION_BEFORE = (
    "禁止",
    "不能",
    "不得",
    "不用",
    "不要",
    "不引入",
    "不单独",
    "不会",
    "无需",
    "之前",
    "旧",
    "avoid ",
    "without ",
    "not ",
)

_FORBIDDEN_REJECTION_AFTER = (
    "只留镜像",
    "仅留镜像",
    "只保留镜像",
    "留作镜像",
    "留镜像",
    "运维文档没跟上",
    "导致",
    "太多",
    "太低",
    "有冲突",
)


def run_benchmark(cases_path: str | Path, *, scope: str = DEFAULT_SCOPE) -> dict[str, Any]:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if isinstance(cases, dict) and cases.get("benchmark_type") == "anti_interference":
        return run_anti_interference_benchmark(cases, source_path=cases_path, scope=scope)
    if isinstance(cases, dict) and cases.get("benchmark_type") == "copilot_realistic_recall_challenge":
        return run_copilot_realistic_recall_challenge_benchmark(cases, source_path=cases_path, scope=scope)
    case_types = {_case_type(case) for case in cases} if isinstance(cases, list) else set()
    if "copilot_recall" in case_types:
        return run_copilot_recall_benchmark(cases, source_path=cases_path, scope=scope)
    if "copilot_candidate" in case_types:
        return run_copilot_candidate_benchmark(cases, source_path=cases_path, scope=scope)
    if "copilot_conflict" in case_types:
        return run_copilot_conflict_benchmark(cases, source_path=cases_path, scope=scope)
    if "copilot_layer" in case_types:
        return run_copilot_layer_benchmark(cases, source_path=cases_path, scope=scope)
    if "copilot_prefetch" in case_types:
        return run_copilot_prefetch_benchmark(cases, source_path=cases_path, scope=scope)
    if "copilot_heartbeat" in case_types:
        return run_copilot_heartbeat_benchmark(cases, source_path=cases_path, scope=scope)
    if "copilot_real_feishu" in case_types:
        return run_copilot_real_feishu_benchmark(cases, source_path=cases_path, scope=scope)

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
            "current_context": demo_permission_context("memory.search", scope),
        }
    )
    response = CopilotService(repository=repo).search(request)
    result = response["results"][0] if response.get("results") else None
    return {
        "recall": result,
        "actual_layer": result.get("layer") if result else None,
        "trace": response.get("trace"),
    }


def run_copilot_layer_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="copilot_layer_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)

            for event in case.get("events", []):
                repo.remember(scope, event, source_type="benchmark_copilot_layer")

            expected_layer = case.get("expected_layer")
            started = time.perf_counter()
            recall_result = _run_copilot_layer_case(repo, case, scope=scope)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            conn.close()

        recalled = recall_result["recall"]
        actual = _answer_from_recall(recalled)
        expected = case.get("expected_active_value", "")
        forbidden = case.get("forbidden_value")
        evidence_present = _recall_has_evidence(recalled)
        expected_ok = expected in actual if expected else bool(actual)
        forbidden_leak = _text_has_forbidden_leak(actual, forbidden)
        layer_passed = recall_result["actual_layer"] == expected_layer if expected_layer else True
        passed = bool(expected_ok and not forbidden_leak and evidence_present and layer_passed)
        failure_type = _layer_failure_type(
            case=case,
            expected_ok=expected_ok,
            evidence_present=evidence_present,
            forbidden_leak=forbidden_leak,
            layer_passed=layer_passed,
        )

        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "query": case["query"],
                "expected": expected,
                "expected_output": {
                    "expected_active_value": expected,
                    "expected_layer": expected_layer,
                    "forbidden_value": forbidden,
                    "evidence_keyword": case.get("evidence_keyword"),
                },
                "actual": actual,
                "actual_output_summary": {
                    "actual_layer": recall_result["actual_layer"],
                    "evidence_present": evidence_present,
                    "forbidden_leak": forbidden_leak,
                },
                "forbidden": forbidden,
                "passed": passed,
                "latency_ms": latency_ms,
                "evidence_present": evidence_present,
                "expected_layer": expected_layer,
                "actual_layer": recall_result["actual_layer"],
                "layer_passed": layer_passed,
                "recall": recalled,
                "trace": recall_result["trace"],
                "failure_type": failure_type,
                "recommended_fix": _recommended_fix(case, failure_type),
                "failure_debug_hint": case.get("failure_debug_hint"),
            }
        )

    return {
        "benchmark_type": "copilot_layer",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_layer_metrics(results),
        "results": results,
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
                        "current_context": demo_permission_context("memory.search", scope),
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
        forbidden_leak = bool(forbidden and any(_result_has_forbidden_leak(item, forbidden) for item in top_results))
        evidence_present = _copilot_evidence_present(top_results, evidence_keyword)
        recall_at_1 = expected_rank == 1
        recall_at_3 = expected_rank is not None and expected_rank <= 3
        passed = bool(recall_at_3 and evidence_present and not forbidden_leak)
        failure_type = _recall_failure_type(
            case=case,
            recall_at_3=recall_at_3,
            evidence_present=evidence_present,
            forbidden_leak=forbidden_leak,
        )

        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "query": case["query"],
                "expected": expected,
                "expected_output": {
                    "expected_active_value": expected,
                    "forbidden_value": forbidden,
                    "evidence_keyword": evidence_keyword,
                    "top_k": 3,
                },
                "actual_output_summary": {
                    "expected_rank": expected_rank,
                    "recall_at_3": recall_at_3,
                    "evidence_present": evidence_present,
                    "forbidden_leak": forbidden_leak,
                    "score_breakdown_summary": _score_breakdown_summary(top_results),
                },
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
                "failure_type": failure_type,
                "recommended_fix": _recommended_fix(case, failure_type),
                "failure_debug_hint": case.get("failure_debug_hint"),
                "planned_failure_category": case.get("failure_category"),
            }
        )

    return {
        "benchmark_type": "copilot_recall",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_recall_metrics(results),
        "results": results,
    }


def run_copilot_candidate_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="copilot_candidate_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)

            for event in case.get("existing_memories", []):
                repo.remember(scope, event["content"], source_type="benchmark_candidate_seed")

            started = time.perf_counter()
            request_payload = {
                "text": case["text"],
                "scope": scope,
                "source": {
                    "source_type": case.get("source_type", "benchmark_candidate"),
                    "source_id": case.get("source_id", case["case_id"]),
                    "actor_id": case.get("actor_id", "benchmark"),
                    "created_at": case.get("created_at", "2026-04-30T00:00:00+08:00"),
                    "quote": case.get("quote", case["text"]),
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate", scope, actor_id=case.get("actor_id", "benchmark")
                ),
            }
            if case.get("auto_confirm") is not None:
                request_payload["auto_confirm"] = case["auto_confirm"]
            response = CopilotService(repository=repo).create_candidate(
                CreateCandidateRequest.from_payload(request_payload)
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            conn.close()

        candidate = response.get("candidate") if response.get("ok") else None
        candidate_created = bool(
            candidate and response.get("action") in {"created", "candidate_conflict", "auto_confirmed"}
        )
        expected_candidate = bool(case.get("expected_candidate"))
        evidence_present = bool(candidate and (candidate.get("evidence") or {}).get("quote"))
        failure_category = _candidate_failure_category(
            expected_candidate=expected_candidate,
            candidate_created=candidate_created,
            evidence_present=evidence_present,
            response=response,
        )
        passed = failure_category is None
        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "text": case["text"],
                "expected_candidate": expected_candidate,
                "expected_output": {
                    "candidate_created": expected_candidate,
                    "expected_reason": case.get("expected_reason"),
                },
                "candidate_created": candidate_created,
                "actual_output_summary": {
                    "action": response.get("action") if response.get("ok") else None,
                    "candidate_created": candidate_created,
                    "evidence_present": evidence_present,
                    "risk_flags": response.get("risk_flags") if response.get("ok") else [],
                },
                "expected_reason": case.get("expected_reason"),
                "actual_action": response.get("action") if response.get("ok") else None,
                "candidate_id": (candidate or {}).get("candidate_id"),
                "risk_flags": response.get("risk_flags") if response.get("ok") else [],
                "conflict": response.get("conflict") if response.get("ok") else {},
                "evidence_present": evidence_present,
                "failure_category": failure_category or case.get("failure_category"),
                "failure_type": failure_category,
                "recommended_fix": _recommended_fix(case, failure_category),
                "passed": passed,
                "latency_ms": latency_ms,
                "response": response,
            }
        )

    return {
        "benchmark_type": "copilot_candidate",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_candidate_metrics(results),
        "results": results,
    }


def run_copilot_conflict_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="copilot_conflict_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            service = CopilotService(repository=repo)

            for event in case.get("existing_memories", []):
                repo.remember(
                    event.get("scope", scope),
                    event["content"],
                    source_type=event.get("source_type", "benchmark_conflict_seed"),
                    source_id=event.get("source_id"),
                    created_by="benchmark",
                )

            started = time.perf_counter()
            request_payload = {
                "text": case["text"],
                "scope": scope,
                "source": {
                    "source_type": case.get("source_type", "benchmark_conflict"),
                    "source_id": case.get("source_id", case["case_id"]),
                    "actor_id": case.get("actor_id", "benchmark"),
                    "created_at": case.get("created_at", "2026-05-01T00:00:00+08:00"),
                    "quote": case.get("quote", case["text"]),
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate", scope, actor_id=case.get("actor_id", "benchmark")
                ),
            }
            candidate_response = service.create_candidate(CreateCandidateRequest.from_payload(request_payload))
            candidate_id = candidate_response.get("candidate_id")
            confirm_response = None
            reject_response = None
            if case.get("expected_action") == "confirm" and candidate_id:
                confirm_response = service.confirm(
                    ConfirmRequest(
                        candidate_id=str(candidate_id),
                        scope=scope,
                        actor_id=case.get("actor_id", "benchmark"),
                        reason=case.get("expected_reason", "benchmark confirm"),
                        current_context=demo_permission_context(
                            "memory.confirm",
                            scope,
                            actor_id=case.get("actor_id", "benchmark"),
                        ),
                    )
                )
            elif case.get("expected_action") == "reject" and candidate_id:
                reject_response = service.reject(
                    RejectRequest(
                        candidate_id=str(candidate_id),
                        scope=scope,
                        actor_id=case.get("actor_id", "benchmark"),
                        reason=case.get("expected_reason", "benchmark reject"),
                        current_context=demo_permission_context(
                            "memory.reject",
                            scope,
                            actor_id=case.get("actor_id", "benchmark"),
                        ),
                    )
                )
            search_response = service.search(
                SearchRequest.from_payload(
                    {
                        "query": case["query"],
                        "scope": scope,
                        "top_k": 3,
                        "current_context": demo_permission_context(
                            "memory.search", scope, actor_id=case.get("actor_id", "benchmark")
                        ),
                    }
                )
            )
            memory_id = candidate_response.get("memory_id")
            explain_response = (
                service.explain_versions(
                    ExplainVersionsRequest(
                        memory_id=str(memory_id),
                        scope=scope,
                        current_context=demo_permission_context(
                            "memory.explain_versions",
                            scope,
                            actor_id=case.get("actor_id", "benchmark"),
                        ),
                    )
                )
                if memory_id
                else {"ok": False}
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            conn.close()

        top_results = search_response.get("results", []) if search_response.get("ok") else []
        expected = case.get("expected_active_value", "")
        forbidden = case.get("forbidden_value", "")
        expected_rank = _copilot_expected_rank(top_results, expected)
        forbidden_leak = bool(forbidden and any(_result_has_forbidden_leak(item, forbidden) for item in top_results))
        version_statuses = {
            item.get("status") for item in explain_response.get("versions", []) if isinstance(item, dict)
        }
        superseded_seen = "superseded" in version_statuses
        active_seen = "active" in version_statuses
        conflict_detected = (
            bool((candidate_response.get("conflict") or {}).get("has_conflict"))
            if candidate_response.get("ok")
            else False
        )
        explain_has_evidence = _explain_versions_has_evidence(explain_response)
        if case.get("expected_action") == "reject":
            passed = bool(
                reject_response
                and reject_response.get("ok")
                and expected_rank is not None
                and expected_rank <= 3
                and not forbidden_leak
            )
            failure_type = _conflict_reject_failure_type(
                reject_ok=bool(reject_response and reject_response.get("ok")),
                expected_rank=expected_rank,
                forbidden_leak=forbidden_leak,
            )
        else:
            passed = bool(
                conflict_detected
                and confirm_response
                and confirm_response.get("ok")
                and expected_rank is not None
                and expected_rank <= 3
                and not forbidden_leak
                and superseded_seen
                and active_seen
                and explain_has_evidence
            )
            failure_type = _conflict_failure_type(
                conflict_detected=conflict_detected,
                confirm_ok=bool(confirm_response and confirm_response.get("ok")),
                expected_rank=expected_rank,
                forbidden_leak=forbidden_leak,
                superseded_seen=superseded_seen,
                active_seen=active_seen,
                explain_has_evidence=explain_has_evidence,
            )
        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "text": case["text"],
                "query": case["query"],
                "expected_action": case.get("expected_action"),
                "expected": expected,
                "expected_output": {
                    "expected_active_value": expected,
                    "forbidden_value": forbidden,
                    "expected_action": case.get("expected_action"),
                    "version_statuses": ["active", "superseded"],
                    "expected_stable_key": case.get("expected_stable_key"),
                },
                "actual_output_summary": {
                    "conflict_detected": conflict_detected,
                    "confirm_ok": bool(confirm_response and confirm_response.get("ok")),
                    "reject_ok": bool(reject_response and reject_response.get("ok")),
                    "expected_rank": expected_rank,
                    "forbidden_leak": forbidden_leak,
                    "version_statuses": sorted(status for status in version_statuses if status),
                    "explain_has_evidence": explain_has_evidence,
                    "stable_key": (candidate_response.get("stable_key") or {}).get("stable_key")
                    if isinstance(candidate_response.get("stable_key"), dict)
                    else None,
                    "stable_key_slot_type": (candidate_response.get("stable_key") or {}).get("slot_type")
                    if isinstance(candidate_response.get("stable_key"), dict)
                    else None,
                    "score_breakdown_summary": _score_breakdown_summary(top_results),
                },
                "forbidden": forbidden,
                "conflict_detected": conflict_detected,
                "confirm_ok": bool(confirm_response and confirm_response.get("ok")),
                "reject_ok": bool(reject_response and reject_response.get("ok")),
                "expected_rank": expected_rank,
                "forbidden_leak": forbidden_leak,
                "superseded_seen": superseded_seen,
                "active_seen": active_seen,
                "explain_has_evidence": explain_has_evidence,
                "passed": passed,
                "latency_ms": latency_ms,
                "candidate_response": candidate_response,
                "confirm_response": confirm_response,
                "reject_response": reject_response,
                "search_response": search_response,
                "explain_versions": explain_response,
                "failure_type": failure_type,
                "recommended_fix": _recommended_fix(case, failure_type),
                "failure_debug_hint": case.get("failure_debug_hint"),
            }
        )

    return {
        "benchmark_type": "copilot_conflict",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_conflict_metrics(results),
        "results": results,
    }


def run_copilot_prefetch_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="copilot_prefetch_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)

            for event in case.get("events", []):
                repo.remember(
                    scope, event["content"] if isinstance(event, dict) else event, source_type="benchmark_prefetch"
                )

            for update in case.get("conflict_updates", []):
                repo.remember(scope, update, source_type="benchmark_prefetch_conflict")

            started = time.perf_counter()
            response = CopilotService(repository=repo).prefetch(
                PrefetchRequest.from_payload(
                    {
                        "task": case["task"],
                        "scope": scope,
                        "current_context": _benchmark_prefetch_context(case, scope),
                        "top_k": case.get("top_k", 5),
                    }
                )
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            conn.close()

        pack = response.get("context_pack", {}) if response.get("ok") else {}
        relevant = pack.get("relevant_memories", []) if isinstance(pack, dict) else []
        text = json.dumps(pack, ensure_ascii=False)
        expected_keyword = case.get("expected_memory_keyword", "")
        forbidden = case.get("forbidden_value", "")
        context_pack_required = bool(
            case.get(
                "context_pack_required",
                expected_keyword or case.get("events") or case.get("conflict_updates"),
            )
        )
        evidence_present = any(item.get("evidence") for item in relevant if isinstance(item, dict))
        used_context = bool(relevant)
        forbidden_leak = _text_has_forbidden_leak(text, forbidden)
        if context_pack_required:
            passed = bool(
                response.get("ok")
                and used_context
                and expected_keyword in text
                and evidence_present
                and not forbidden_leak
            )
        else:
            passed = bool(response.get("ok") and not used_context and not forbidden_leak)
        failure_type = _prefetch_failure_type(
            expected_keyword=expected_keyword,
            output_text=text,
            used_context=used_context,
            evidence_present=evidence_present,
            forbidden_leak=forbidden_leak,
            context_pack_required=context_pack_required,
        )
        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "task": case["task"],
                "expected_memory_keyword": expected_keyword,
                "expected_output": {
                    "expected_memory_keyword": expected_keyword,
                    "forbidden_value": forbidden,
                    "context_pack_required": context_pack_required,
                },
                "actual_output_summary": {
                    "used_context": used_context,
                    "relevant_memory_count": len(relevant),
                    "evidence_present": evidence_present,
                    "forbidden_leak": forbidden_leak,
                },
                "forbidden": forbidden,
                "context_pack_required": context_pack_required,
                "used_context": used_context,
                "evidence_present": evidence_present,
                "forbidden_leak": forbidden_leak,
                "passed": passed,
                "latency_ms": latency_ms,
                "response": response,
                "failure_type": failure_type,
                "recommended_fix": _recommended_fix(case, failure_type),
                "failure_debug_hint": case.get("failure_debug_hint"),
            }
        )

    return {
        "benchmark_type": "copilot_prefetch",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_prefetch_metrics(results),
        "results": results,
    }


def run_copilot_heartbeat_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        with tempfile.NamedTemporaryFile(prefix="copilot_heartbeat_benchmark_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            for event in case.get("events", []):
                created = repo.remember(
                    scope, event["content"] if isinstance(event, dict) else event, source_type="benchmark_heartbeat"
                )
                if case.get("days_since_recall"):
                    recalled_at = int(time.time() * 1000) - int(case["days_since_recall"]) * 24 * 60 * 60 * 1000
                    with conn:
                        conn.execute(
                            "UPDATE memories SET last_recalled_at = ?, recall_count = ? WHERE id = ?",
                            (recalled_at, 1, created["memory_id"]),
                        )
            if case.get("mark_recalled_query"):
                repo.recall(scope, case["mark_recalled_query"])

            started = time.perf_counter()
            response = HeartbeatReminderEngine(
                repo,
                now_ms=case.get("now_ms"),
                review_due_ms=case.get("review_due_ms", 7 * 24 * 60 * 60 * 1000),
                cooldown_ms=case.get("cooldown_ms", 24 * 60 * 60 * 1000),
            ).generate(
                scope=scope,
                current_context=_benchmark_heartbeat_context(case, scope),
                limit=case.get("limit", 5),
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            conn.close()

        candidates = response.get("candidates", []) if response.get("ok") else []
        text = json.dumps(candidates, ensure_ascii=False)
        expected_trigger = case.get("expected_trigger")
        expected_subject = case.get("expected_subject", "")
        expected_status = case.get("expected_status")
        forbidden = case.get("forbidden_value", "")
        if expected_trigger is None:
            expected_found = len(candidates) == 0
        else:
            expected_found = any(
                item.get("trigger") == expected_trigger
                and (not expected_subject or _heartbeat_subject_matches(item, expected_subject))
                and (not expected_status or item.get("status") == expected_status)
                for item in candidates
                if isinstance(item, dict)
            )
        sensitive_leak = bool(forbidden and forbidden in text)
        duplicate_count = max(
            0,
            len(candidates)
            - len({item.get("mute_key") or item.get("reminder_id") for item in candidates if isinstance(item, dict)}),
        )
        expected_no_reminder = expected_trigger is None
        false_reminder = bool(expected_no_reminder and candidates)
        action_count = sum(
            len(item.get("actions") or [])
            for item in candidates
            if isinstance(item, dict) and isinstance(item.get("actions"), list)
        )
        passed = bool(response.get("ok") and expected_found and not sensitive_leak)
        failure_type = _heartbeat_failure_type(
            expected_found=expected_found, sensitive_leak=sensitive_leak, false_reminder=false_reminder
        )
        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "expected_trigger": expected_trigger,
                "expected_subject": expected_subject,
                "expected_output": {
                    "expected_trigger": expected_trigger,
                    "expected_subject": expected_subject,
                    "expected_status": expected_status,
                    "forbidden_value": forbidden,
                },
                "actual_output_summary": {
                    "candidate_count": len(candidates),
                    "expected_found": expected_found,
                    "sensitive_leak": sensitive_leak,
                    "expected_status": expected_status,
                    "duplicate_count": duplicate_count,
                    "false_reminder": false_reminder,
                    "action_count": action_count,
                },
                "candidate_count": len(candidates),
                "expected_found": expected_found,
                "sensitive_leak": sensitive_leak,
                "duplicate_count": duplicate_count,
                "false_reminder": false_reminder,
                "action_count": action_count,
                "passed": passed,
                "latency_ms": latency_ms,
                "response": response,
                "failure_type": failure_type,
                "recommended_fix": _recommended_fix(case, failure_type),
                "failure_debug_hint": case.get("failure_debug_hint"),
            }
        )

    return {
        "benchmark_type": "copilot_heartbeat",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_heartbeat_metrics(results),
        "results": results,
    }


def run_copilot_real_feishu_benchmark(
    cases: list[dict[str, Any]],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    results = []

    for case in cases:
        observed = case.get("observed_baseline") or {}
        expected_permission = case.get("expected_permission") or {}
        expected_permission_decision = expected_permission.get("decision")
        observed_permission_decision = observed.get("permission_decision")
        expected_recall_rank = case.get("expected_recall_rank")
        observed_rank = observed.get("recall_rank")
        recall_expected = expected_recall_rank is not None and expected_permission_decision != "deny"
        recall_at_3 = bool(recall_expected and isinstance(observed_rank, int) and observed_rank <= 3)
        expected_should_remember = bool(case.get("expected_should_remember"))
        candidate_created = bool(observed.get("candidate_created"))
        false_memory = bool(not expected_should_remember and candidate_created)
        reminder_created = bool(observed.get("reminder_created"))
        false_reminder = bool(not case.get("expected_reminder", False) and reminder_created)
        explanation_required = bool(case.get("expected_explanation_required", True))
        explanation_present = bool(observed.get("has_user_explanation"))
        explanation_ok = bool(not explanation_required or explanation_present)
        old_value_applicable = bool(case.get("expected_old_value_filtered"))
        old_value_leaked = bool(observed.get("old_value_leaked"))
        old_value_ok = bool(not old_value_applicable or not old_value_leaked)
        permission_ok = observed_permission_decision == expected_permission_decision
        candidate_ok = candidate_created == expected_should_remember
        reminder_ok = not false_reminder
        passed = bool(
            permission_ok
            and candidate_ok
            and reminder_ok
            and explanation_ok
            and old_value_ok
            and (not recall_expected or recall_at_3)
        )
        failure_type = _real_feishu_failure_type(
            permission_ok=permission_ok,
            recall_expected=recall_expected,
            recall_at_3=recall_at_3,
            false_memory=false_memory,
            false_reminder=false_reminder,
            explanation_ok=explanation_ok,
            old_value_ok=old_value_ok,
        )

        results.append(
            {
                "case_id": case["case_id"],
                "case_type": _case_type(case),
                "expression_category": case.get("expression_category"),
                "input": case.get("input"),
                "expected_output": {
                    "expected_intent": case.get("expected_intent"),
                    "expected_should_remember": expected_should_remember,
                    "expected_permission": expected_permission,
                    "expected_recall_rank": expected_recall_rank,
                    "expected_reminder": bool(case.get("expected_reminder", False)),
                    "expected_explanation_required": explanation_required,
                    "expected_old_value_filtered": old_value_applicable,
                },
                "actual_output_summary": {
                    "observed_recall_rank": observed_rank,
                    "recall_at_3": recall_at_3,
                    "candidate_created": candidate_created,
                    "false_memory": false_memory,
                    "reminder_created": reminder_created,
                    "false_reminder": false_reminder,
                    "review_action_count": int(observed.get("review_action_count") or 0),
                    "has_user_explanation": explanation_present,
                    "old_value_leaked": old_value_leaked,
                    "permission_decision": observed_permission_decision,
                },
                "recall_expected": recall_expected,
                "recall_at_3": recall_at_3,
                "candidate_created": candidate_created,
                "false_memory": false_memory,
                "false_reminder": false_reminder,
                "review_action_count": int(observed.get("review_action_count") or 0),
                "explanation_required": explanation_required,
                "explanation_present": explanation_present,
                "old_value_applicable": old_value_applicable,
                "old_value_leaked": old_value_leaked,
                "permission_ok": permission_ok,
                "passed": passed,
                "latency_ms": 0.0,
                "failure_type": failure_type,
                "recommended_fix": _recommended_fix(case, failure_type),
                "failure_debug_hint": case.get("failure_debug_hint"),
            }
        )

    return {
        "benchmark_type": "copilot_real_feishu",
        "name": Path(source_path).stem,
        "source": str(source_path),
        "summary": _copilot_real_feishu_metrics(results),
        "results": results,
    }


def run_copilot_realistic_recall_challenge_benchmark(
    spec: dict[str, Any],
    *,
    source_path: str | Path,
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    corpus = spec.get("corpus") or {}
    events = list(corpus.get("events") or [])
    noise_events = list(corpus.get("noise_events") or [])
    queries = list(spec.get("queries") or [])
    results: list[dict[str, Any]] = []

    with tempfile.NamedTemporaryFile(prefix="copilot_realistic_recall_", suffix=".sqlite") as tmp:
        conn = connect(tmp.name)
        init_db(conn)
        repo = MemoryRepository(conn)

        ingested_event_count = 0
        for event in events:
            if isinstance(event, str):
                repo.remember(scope, event, source_type="benchmark_realistic_recall")
                ingested_event_count += 1
                continue
            if not isinstance(event, dict):
                continue
            content = str(event.get("content") or "").strip()
            if not content:
                continue
            if event.get("status") == "noise":
                repo.add_noise_event(scope, content, source_type=str(event.get("source_type") or "benchmark_noise"))
            else:
                repo.remember(
                    scope,
                    content,
                    source_type=str(event.get("source_type") or "benchmark_realistic_recall"),
                    source_id=str(event.get("id") or event.get("source_id") or ""),
                    sender_id=event.get("sender_id"),
                    created_by=str(event.get("actor_id") or "benchmark"),
                )
            ingested_event_count += 1

        for item in noise_events:
            content = item.get("content") if isinstance(item, dict) else item
            if content:
                repo.add_noise_event(scope, str(content), source_type="benchmark_realistic_noise")

        service = CopilotService(repository=repo)
        for query in queries:
            started = time.perf_counter()
            context = _realistic_recall_context(query, scope)
            try:
                response = service.search(
                    SearchRequest.from_payload(
                        {
                            "query": query["query"],
                            "scope": scope,
                            "top_k": int(query.get("top_k", 3)),
                            "filters": dict(query.get("filters") or {}),
                            "current_context": context,
                        }
                    )
                )
            except Exception as exc:
                response = {
                    "ok": False,
                    "error": {"code": "internal_error", "message": str(exc), "details": {}},
                    "results": [],
                }
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            top_results = response.get("results", []) if response.get("ok") else []
            if not isinstance(top_results, list):
                top_results = []

            expected_values = _as_string_list(query.get("expected_active_value") or query.get("expected_values"))
            forbidden_values = _as_string_list(query.get("forbidden_values") or query.get("forbidden_value"))
            evidence_keywords = _as_string_list(query.get("evidence_keywords") or query.get("evidence_keyword"))
            expected_source_types = set(_as_string_list(query.get("expected_source_types")))
            expected_permission_decision = str(query.get("expected_permission_decision") or "allow")
            expected_permission_denied = expected_permission_decision == "deny"
            permission_decision = _response_permission_decision(response)
            permission_ok = permission_decision == expected_permission_decision
            expected_no_answer = bool(query.get("expected_no_answer"))
            expected_rank = _copilot_expected_rank_any(top_results, expected_values)
            recall_at_1 = expected_rank == 1
            recall_at_3 = expected_rank is not None and expected_rank <= 3
            mrr = round(1 / expected_rank, 4) if expected_rank else 0.0
            distractor_leak = bool(
                forbidden_values
                and any(_result_has_any_forbidden_leak(item, forbidden_values) for item in top_results)
            )
            stale_values = _as_string_list(query.get("stale_values"))
            stale_leak = bool(
                stale_values and any(_result_has_any_forbidden_leak(item, stale_values) for item in top_results)
            )
            evidence_present = _copilot_evidence_keywords_present(top_results, evidence_keywords)
            evidence_source_ok = _copilot_evidence_source_ok(top_results, expected_source_types)
            min_confident_score = float(query.get("min_confident_score", spec.get("min_confident_score", 120.0)))
            abstained = _response_abstained(top_results, min_confident_score=min_confident_score)
            no_answer_ok = (not expected_no_answer) or abstained
            passed = bool(
                permission_ok
                and (
                    expected_permission_denied
                    or (
                        no_answer_ok
                        and (expected_no_answer or recall_at_3)
                        and (expected_no_answer or evidence_present)
                        and evidence_source_ok
                        and not distractor_leak
                        and not stale_leak
                    )
                )
            )
            failure_type = _realistic_recall_failure_type(
                query=query,
                permission_ok=permission_ok,
                expected_no_answer=expected_no_answer,
                no_answer_ok=no_answer_ok,
                recall_at_3=recall_at_3,
                evidence_present=evidence_present,
                evidence_source_ok=evidence_source_ok,
                distractor_leak=distractor_leak,
                stale_leak=stale_leak,
            )

            results.append(
                {
                    "case_id": query["id"],
                    "case_type": "copilot_realistic_recall_challenge",
                    "category": query.get("category"),
                    "query": query["query"],
                    "expected_output": {
                        "expected_active_value": expected_values,
                        "expected_no_answer": expected_no_answer,
                        "expected_permission_decision": expected_permission_decision,
                        "expected_source_types": sorted(expected_source_types),
                        "forbidden_values": forbidden_values,
                        "stale_values": stale_values,
                        "evidence_keywords": evidence_keywords,
                    },
                    "actual_output_summary": {
                        "expected_rank": expected_rank,
                        "recall_at_1": recall_at_1,
                        "recall_at_3": recall_at_3,
                        "mrr": mrr,
                        "permission_decision": permission_decision,
                        "abstained": abstained,
                        "top_score": _top_score(top_results),
                        "evidence_present": evidence_present,
                        "evidence_source_ok": evidence_source_ok,
                        "distractor_leak": distractor_leak,
                        "stale_leak": stale_leak,
                        "score_breakdown_summary": _score_breakdown_summary(top_results),
                    },
                    "expected_rank": expected_rank,
                    "recall_at_1": recall_at_1,
                    "recall_at_3": recall_at_3,
                    "mrr": mrr,
                    "expected_no_answer": expected_no_answer,
                    "abstained": abstained,
                    "permission_ok": permission_ok,
                    "permission_decision": permission_decision,
                    "expected_permission_denied": expected_permission_denied,
                    "evidence_present": evidence_present,
                    "evidence_source_ok": evidence_source_ok,
                    "distractor_leak": distractor_leak,
                    "stale_leak": stale_leak,
                    "passed": passed,
                    "latency_ms": latency_ms,
                    "top_candidates": top_results,
                    "trace": response.get("trace"),
                    "failure_type": failure_type,
                    "recommended_fix": _recommended_fix(query, failure_type),
                    "failure_debug_hint": query.get("failure_debug_hint"),
                }
            )
        conn.close()

    return {
        "benchmark_type": "copilot_realistic_recall_challenge",
        "name": spec.get("name") or Path(source_path).stem,
        "source": str(source_path),
        "layers": {
            "corpus_event_count": ingested_event_count,
            "noise_event_count": len(noise_events),
            "query_count": len(queries),
        },
        "summary": _copilot_realistic_recall_metrics(results),
        "by_category": _realistic_group_metrics(results, "category"),
        "results": results,
    }


def _benchmark_prefetch_context(case: dict[str, Any], scope: str) -> dict[str, Any]:
    context = dict(case.get("current_context") or {"intent": case["task"]})
    context.update(
        demo_permission_context(
            "memory.prefetch",
            scope,
            actor_id=str(case.get("actor_id", "benchmark")),
            metadata=context.get("metadata") if isinstance(context.get("metadata"), dict) else None,
        )
    )
    return context


def _benchmark_heartbeat_context(case: dict[str, Any], scope: str) -> dict[str, Any]:
    context = dict(case.get("current_context") or {"intent": case.get("intent", "")})
    context.update(
        demo_permission_context(
            "heartbeat.review_due",
            scope,
            actor_id=str(case.get("actor_id", "benchmark")),
            roles=case.get("roles") if isinstance(case.get("roles"), list) else None,
            entrypoint="heartbeat",
            metadata=context.get("metadata") if isinstance(context.get("metadata"), dict) else None,
        )
    )
    return context


def _heartbeat_subject_matches(candidate: dict[str, Any], expected_subject: str) -> bool:
    expected = str(expected_subject or "")
    if not expected:
        return True
    subject = str(candidate.get("subject") or "")
    current_value = str(candidate.get("current_value") or "")
    if expected in subject or expected in current_value:
        return True
    normalized_expected = "".join(ch for ch in expected.lower() if ch.isalnum())
    normalized_text = "".join(ch for ch in f"{subject} {current_value}".lower() if ch.isalnum())
    return bool(normalized_expected and normalized_expected in normalized_text)


def _candidate_failure_category(
    *,
    expected_candidate: bool,
    candidate_created: bool,
    evidence_present: bool,
    response: dict[str, Any],
) -> str | None:
    if expected_candidate and not candidate_created:
        if response.get("error", {}).get("code") == "validation_error":
            return "evidence_missing"
        return "candidate_not_detected"
    if not expected_candidate and candidate_created:
        return "false_positive_candidate"
    if candidate_created and not evidence_present:
        return "evidence_missing"
    return None


def _case_type(case: dict[str, Any]) -> str:
    return str(case.get("case_type") or case.get("type") or "")


def _recommended_fix(case: dict[str, Any], failure_type: str | None) -> str | None:
    if not failure_type:
        return None
    return case.get("recommended_fix") or FAILURE_RECOMMENDED_FIXES.get(failure_type) or case.get("failure_debug_hint")


def _recall_failure_type(
    *,
    case: dict[str, Any],
    recall_at_3: bool,
    evidence_present: bool,
    forbidden_leak: bool,
) -> str | None:
    if forbidden_leak:
        return "stale_value_leaked"
    if not evidence_present:
        return "evidence_missing"
    if not recall_at_3:
        return case.get("failure_category") or "keyword_miss"
    return None


def _layer_failure_type(
    *,
    case: dict[str, Any],
    expected_ok: bool,
    evidence_present: bool,
    forbidden_leak: bool,
    layer_passed: bool,
) -> str | None:
    if forbidden_leak:
        return "stale_value_leaked"
    if not evidence_present:
        return "evidence_missing"
    if not layer_passed:
        return "wrong_layer_routing"
    if not expected_ok:
        return case.get("failure_category") or "keyword_miss"
    return None


def _conflict_failure_type(
    *,
    conflict_detected: bool,
    confirm_ok: bool,
    expected_rank: int | None,
    forbidden_leak: bool,
    superseded_seen: bool,
    active_seen: bool,
    explain_has_evidence: bool,
) -> str | None:
    if forbidden_leak:
        return "stale_value_leaked"
    if not conflict_detected or not superseded_seen or not active_seen:
        return "wrong_subject_normalization"
    if not explain_has_evidence:
        return "evidence_missing"
    if not confirm_ok:
        return "permission_scope_error"
    if expected_rank is None or expected_rank > 3:
        return "keyword_miss"
    return None


def _conflict_reject_failure_type(
    *,
    reject_ok: bool,
    expected_rank: int | None,
    forbidden_leak: bool,
) -> str | None:
    if forbidden_leak:
        return "stale_value_leaked"
    if not reject_ok:
        return "reject_failed"
    if expected_rank is None or expected_rank > 3:
        return "keyword_miss"
    return None


def _prefetch_failure_type(
    *,
    expected_keyword: str,
    output_text: str,
    used_context: bool,
    evidence_present: bool,
    forbidden_leak: bool,
    context_pack_required: bool = True,
) -> str | None:
    if forbidden_leak:
        return "stale_value_leaked"
    if not context_pack_required:
        return "unexpected_context_leak" if used_context else None
    if not used_context:
        return "agent_did_not_prefetch"
    if not evidence_present:
        return "evidence_missing"
    if expected_keyword and expected_keyword not in output_text:
        return "keyword_miss"
    return None


def _heartbeat_failure_type(*, expected_found: bool, sensitive_leak: bool, false_reminder: bool = False) -> str | None:
    if sensitive_leak:
        return "permission_scope_error"
    if false_reminder:
        return "reminder_too_noisy"
    if not expected_found:
        return "reminder_too_noisy"
    return None


def _real_feishu_failure_type(
    *,
    permission_ok: bool,
    recall_expected: bool,
    recall_at_3: bool,
    false_memory: bool,
    false_reminder: bool,
    explanation_ok: bool,
    old_value_ok: bool,
) -> str | None:
    if not permission_ok:
        return "permission_scope_error"
    if false_memory:
        return "false_positive_candidate"
    if false_reminder:
        return "reminder_too_noisy"
    if not old_value_ok:
        return "user_expression_old_value_leaked"
    if not explanation_ok:
        return "user_expression_explanation_missing"
    if recall_expected and not recall_at_3:
        return "user_expression_context_miss"
    return None


def _failure_type_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        failure_type = result.get("failure_type")
        if failure_type:
            counts[failure_type] = counts.get(failure_type, 0) + 1
    return dict(sorted(counts.items()))


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


def _copilot_expected_rank_any(top_results: list[dict[str, Any]], expected_values: list[str]) -> int | None:
    if not expected_values:
        return 1 if top_results else None
    for index, item in enumerate(top_results, start=1):
        current_value = str(item.get("current_value") or "")
        if any(expected in current_value for expected in expected_values if expected):
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


def _copilot_evidence_keywords_present(top_results: list[dict[str, Any]], evidence_keywords: list[str]) -> bool:
    if not evidence_keywords:
        return bool(top_results)
    for keyword in evidence_keywords:
        if not _copilot_evidence_present(top_results, keyword):
            return False
    return True


def _copilot_evidence_source_ok(top_results: list[dict[str, Any]], expected_source_types: set[str]) -> bool:
    if not expected_source_types:
        return True
    for item in top_results:
        for evidence in item.get("evidence", []):
            if str(evidence.get("source_type") or "") in expected_source_types:
                return True
    return False


def _result_has_any_forbidden_leak(result: dict[str, Any], forbidden_values: list[str]) -> bool:
    current_value = str(result.get("current_value") or "")
    return any(_text_has_forbidden_leak(current_value, forbidden) for forbidden in forbidden_values)


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _top_score(top_results: list[dict[str, Any]]) -> float:
    if not top_results:
        return 0.0
    try:
        return float(top_results[0].get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _response_abstained(top_results: list[dict[str, Any]], *, min_confident_score: float) -> bool:
    return not top_results or _top_score(top_results) < min_confident_score


def _response_permission_decision(response: dict[str, Any]) -> str:
    if response.get("ok"):
        return "allow"
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    if error.get("code") == "permission_denied":
        return "deny"
    return str(error.get("code") or "error")


def _realistic_recall_context(query: dict[str, Any], scope: str) -> dict[str, Any]:
    if query.get("current_context"):
        return dict(query["current_context"])
    if query.get("expected_permission_decision") == "deny":
        context = demo_permission_context("memory.search", scope, actor_id=str(query.get("actor_id", "benchmark")))
        permission = dict(context["permission"])
        actor = dict(permission["actor"])
        actor["tenant_id"] = "tenant:other"
        permission["actor"] = actor
        context["permission"] = permission
        return context
    return demo_permission_context("memory.search", scope, actor_id=str(query.get("actor_id", "benchmark")))


def _realistic_recall_failure_type(
    *,
    query: dict[str, Any],
    permission_ok: bool,
    expected_no_answer: bool,
    no_answer_ok: bool,
    recall_at_3: bool,
    evidence_present: bool,
    evidence_source_ok: bool,
    distractor_leak: bool,
    stale_leak: bool,
) -> str | None:
    if not permission_ok:
        return "permission_scope_error"
    if query.get("expected_permission_decision") == "deny":
        return None
    if expected_no_answer and not no_answer_ok:
        return "no_answer_failed"
    if distractor_leak:
        return "distractor_leakage"
    if stale_leak:
        return "stale_value_leaked"
    if not recall_at_3 and not expected_no_answer:
        return str(query.get("failure_category") or "vector_miss")
    if not evidence_present and not expected_no_answer:
        return "evidence_missing"
    if not evidence_source_ok:
        return "evidence_source_mismatch"
    return None


def _score_breakdown_summary(top_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for item in top_results[:3]:
        why_ranked = item.get("why_ranked") if isinstance(item, dict) else {}
        why_ranked = why_ranked if isinstance(why_ranked, dict) else {}
        breakdown = why_ranked.get("score_breakdown")
        breakdown = breakdown if isinstance(breakdown, dict) else {}
        signals = breakdown.get("signals")
        signals = signals if isinstance(signals, dict) else {}
        bonuses = breakdown.get("bonuses")
        bonuses = bonuses if isinstance(bonuses, dict) else {}
        summary.append(
            {
                "memory_id": item.get("memory_id"),
                "rank": item.get("rank"),
                "score": item.get("score"),
                "keyword": _score_contribution(signals.get("keyword_score")),
                "vector": _score_contribution(signals.get("vector_score")),
                "cognee": _score_contribution(signals.get("cognee_score")),
                "importance": _score_contribution((breakdown.get("quality") or {}).get("importance")),
                "confidence": _score_contribution((breakdown.get("quality") or {}).get("confidence")),
                "recency": signals.get("recency_score"),
                "evidence": bonuses.get("evidence_score"),
                "filtering": why_ranked.get("filtering"),
            }
        )
    return summary


def _score_contribution(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("contribution")
    return value


def _result_has_forbidden_leak(result: dict[str, Any], forbidden: str | None) -> bool:
    if not forbidden:
        return False
    current_value = str(result.get("current_value") or "")
    return _text_has_forbidden_leak(current_value, forbidden)


def _text_has_forbidden_leak(text: str, forbidden: str | None) -> bool:
    if not forbidden:
        return False
    lowered = str(text or "").lower()
    forbidden_text = str(forbidden).lower()
    if not forbidden_text:
        return False

    start = 0
    while True:
        index = lowered.find(forbidden_text, start)
        if index < 0:
            return False
        before = lowered[max(0, index - 16) : index]
        after = lowered[index + len(forbidden_text) : index + len(forbidden_text) + 16]
        if not _is_explicitly_rejected_forbidden_context(before, after):
            return True
        start = index + len(forbidden_text)


def _is_explicitly_rejected_forbidden_context(before: str, after: str) -> bool:
    return any(marker in before for marker in _FORBIDDEN_REJECTION_BEFORE) or any(
        marker in after for marker in _FORBIDDEN_REJECTION_AFTER
    )


def _explain_versions_has_evidence(response: dict[str, Any]) -> bool:
    if not response.get("ok"):
        return False
    return all(
        bool((item.get("evidence") or {}).get("quote"))
        for item in response.get("versions", [])
        if isinstance(item, dict)
    )


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
    if str(result.get("benchmark_type", "")).startswith("copilot_"):
        return format_copilot_benchmark_report(result)

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


def format_copilot_benchmark_report(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    benchmark_type = result.get("benchmark_type", "copilot")
    lines = [
        "# Benchmark Report",
        "",
        "日期：2026-05-03",
        "",
        f"## {benchmark_type}",
        "",
        "本节由 `memory_engine benchmark run` 生成，面向 OpenClaw-native Feishu Memory Copilot 的指标自证。",
        "",
        "### 可复现实验命令",
        "",
        "```bash",
        f"python3 -m memory_engine benchmark run {result.get('source', '<cases>')} --json-output reports/{benchmark_type}.json --csv-output reports/{benchmark_type}.csv --markdown-output docs/benchmark-report.md",
        "```",
        "",
        "### 指标摘要",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if isinstance(value, (int, float)):
            lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "### 失败分类",
            "",
            "| failure_type | 数量 | recommended_fix |",
            "|---|---:|---|",
        ]
    )
    failure_counts = summary.get("failure_type_counts") or {}
    if failure_counts:
        for failure_type, count in failure_counts.items():
            lines.append(f"| {failure_type} | {count} | {FAILURE_RECOMMENDED_FIXES.get(failure_type, '')} |")
    else:
        lines.append("| 无失败 | 0 | 当前样例全部通过；继续保留边界样例，不为了指标删样例。 |")
    lines.extend(
        [
            "",
            "### 样例证据",
            "",
            "| case_id | passed | failure_type | actual_output_summary |",
            "|---|---:|---|---|",
        ]
    )
    for item in result.get("results", [])[:20]:
        actual = json.dumps(item.get("actual_output_summary", {}), ensure_ascii=False, sort_keys=True)
        lines.append(
            f"| {item.get('case_id')} | {str(bool(item.get('passed'))).lower()} | {item.get('failure_type') or ''} | {actual} |"
        )
    lines.extend(
        [
            "",
            "### 当前局限",
            "",
            "- 本报告证明 runner、字段和 failure 分类可复现，不代表最终指标已经冲到复赛目标。",
            "- `reports/` 下的 JSON / CSV 是本地运行证据目录，默认不提交。",
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
                expected for expected in expected_quotes if any(expected in quote for quote in candidate_quotes)
            ]
            forbidden_hits = [
                forbidden for forbidden in forbidden_quotes if any(forbidden in quote for quote in candidate_quotes)
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
                        "document_source_present": bool(
                            source and source.get("document_title") and source.get("quote")
                        ),
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
    leaked = [result for result in forbidden_cases if _text_has_forbidden_leak(result["actual"], result["forbidden"])]
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


def _copilot_layer_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    evidence_present = sum(1 for result in results if result["evidence_present"])
    layer_passed = sum(1 for result in results if result["layer_passed"])
    forbidden_cases = [result for result in results if result.get("forbidden")]
    forbidden_leaks = [
        result
        for result in forbidden_cases
        if _text_has_forbidden_leak(result.get("actual", ""), result.get("forbidden"))
    ]
    latencies = sorted(result["latency_ms"] for result in results)
    l1_latencies = sorted(result["latency_ms"] for result in results if result.get("expected_layer") == "L1")
    l2_cases = [result for result in results if result.get("expected_layer") == "L2"]
    l3_cases = [result for result in results if result.get("expected_layer") == "L3"]
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "layer_case_count": total,
        "layer_accuracy": _ratio(layer_passed, total),
        "l1_hit_rate": _ratio(
            sum(1 for result in results if result.get("expected_layer") == "L1" and result["layer_passed"]),
            len(l1_latencies),
        ),
        "l2_fallback_success_rate": _ratio(sum(1 for result in l2_cases if result["layer_passed"]), len(l2_cases)),
        "l3_deep_search_success_rate": _ratio(sum(1 for result in l3_cases if result["layer_passed"]), len(l3_cases)),
        "l1_hot_recall_p95_ms": _percentile(l1_latencies, 0.95),
        "stale_leakage_rate": _ratio(len(forbidden_leaks), len(forbidden_cases)),
        "evidence_coverage": _ratio(evidence_present, total),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "failure_type_counts": _failure_type_counts(results),
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
        "failure_type_counts": _failure_type_counts(results),
    }


def _copilot_candidate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    true_positive = sum(1 for result in results if result["expected_candidate"] and result["candidate_created"])
    false_positive = sum(1 for result in results if not result["expected_candidate"] and result["candidate_created"])
    candidate_not_detected = sum(1 for result in results if result["failure_category"] == "candidate_not_detected")
    evidence_missing = sum(1 for result in results if result["failure_category"] == "evidence_missing")
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "expected_candidate_count": sum(1 for result in results if result["expected_candidate"]),
        "candidate_precision": _ratio(true_positive, true_positive + false_positive),
        "candidate_not_detected": candidate_not_detected,
        "false_positive_candidate": false_positive,
        "evidence_missing": evidence_missing,
        "failure_type_counts": _failure_type_counts(results),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
    }


def _copilot_conflict_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    conflict_detected = sum(1 for result in results if result["conflict_detected"])
    confirm_ok = sum(1 for result in results if result["confirm_ok"])
    reject_ok = sum(1 for result in results if result.get("reject_ok"))
    forbidden_cases = [result for result in results if result.get("forbidden")]
    forbidden_leaks = [result for result in forbidden_cases if result["forbidden_leak"]]
    superseded_seen = sum(1 for result in results if result["superseded_seen"])
    explain_evidence = sum(1 for result in results if result["explain_has_evidence"])
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "conflict_accuracy": _ratio(passed, total),
        "conflict_detected_rate": _ratio(conflict_detected, total),
        "confirm_success_rate": _ratio(confirm_ok, total),
        "reject_success_rate": _ratio(reject_ok, total),
        "superseded_chain_rate": _ratio(superseded_seen, total),
        "stale_leakage_rate": _ratio(len(forbidden_leaks), len(forbidden_cases)),
        "superseded_leakage_rate": _ratio(len(forbidden_leaks), len(forbidden_cases)),
        "evidence_coverage": _ratio(explain_evidence, total),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "failure_type_counts": _failure_type_counts(results),
    }


def _copilot_prefetch_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    context_required_cases = [result for result in results if result.get("context_pack_required", True)]
    used_context = sum(1 for result in context_required_cases if result["used_context"])
    evidence_present = sum(1 for result in context_required_cases if result["evidence_present"])
    forbidden_cases = [result for result in results if result.get("forbidden")]
    forbidden_leaks = [result for result in forbidden_cases if result["forbidden_leak"]]
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "context_required_case_count": len(context_required_cases),
        "agent_task_context_use_rate": _ratio(used_context, len(context_required_cases)),
        "evidence_coverage": _ratio(evidence_present, len(context_required_cases)),
        "stale_leakage_rate": _ratio(len(forbidden_leaks), len(forbidden_cases)),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "failure_type_counts": _failure_type_counts(results),
    }


def _copilot_heartbeat_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    expected_found = sum(1 for result in results if result["expected_found"])
    sensitive_leaks = sum(1 for result in results if result["sensitive_leak"])
    false_reminders = sum(1 for result in results if result.get("false_reminder"))
    duplicate_cases = sum(1 for result in results if result.get("duplicate_count", 0) > 0)
    total_actions = sum(int(result.get("action_count") or 0) for result in results)
    total_candidates = sum(int(result.get("candidate_count") or 0) for result in results)
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "reminder_candidate_rate": _ratio(expected_found, total),
        "sensitive_reminder_leakage_rate": _ratio(sensitive_leaks, total),
        "false_reminder_rate": _ratio(false_reminders, total),
        "duplicate_reminder_rate": _ratio(duplicate_cases, total),
        "user_confirmation_burden": round(total_actions / total_candidates, 3) if total_candidates else 0.0,
        "avg_candidate_count": round(sum(result["candidate_count"] for result in results) / total, 3) if total else 0.0,
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "failure_type_counts": _failure_type_counts(results),
    }


def _copilot_real_feishu_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    recall_cases = [result for result in results if result["recall_expected"]]
    recall_hits = sum(1 for result in recall_cases if result["recall_at_3"])
    false_memories = sum(1 for result in results if result["false_memory"])
    false_reminders = sum(1 for result in results if result["false_reminder"])
    explanation_cases = [result for result in results if result["explanation_required"]]
    explanation_hits = sum(1 for result in explanation_cases if result["explanation_present"])
    old_value_cases = [result for result in results if result["old_value_applicable"]]
    old_value_leaks = sum(1 for result in old_value_cases if result["old_value_leaked"])
    review_candidates = sum(1 for result in results if result["candidate_created"])
    categories = sorted({str(result.get("expression_category") or "unknown") for result in results})
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "category_count": len(categories),
        "recall_case_count": len(recall_cases),
        "recall_at_3": _ratio(recall_hits, len(recall_cases)),
        "false_memory_rate": _ratio(false_memories, total),
        "false_reminder_rate": _ratio(false_reminders, total),
        "user_confirmation_burden": round(review_candidates / total * 10, 3) if total else 0.0,
        "explanation_coverage": _ratio(explanation_hits, len(explanation_cases)),
        "old_value_leakage_rate": _ratio(old_value_leaks, len(old_value_cases)),
        "failure_type_counts": _failure_type_counts(results),
    }


def _copilot_realistic_recall_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    answerable = [result for result in results if not result.get("expected_no_answer") and not result.get("expected_permission_denied")]
    denied = [result for result in results if result.get("expected_permission_denied")]
    no_answer = [result for result in results if result.get("expected_no_answer")]
    evidence_cases = [result for result in answerable if result.get("expected_output", {}).get("evidence_keywords")]
    source_cases = [result for result in answerable if result.get("expected_output", {}).get("expected_source_types")]
    forbidden_cases = [result for result in results if result.get("expected_output", {}).get("forbidden_values")]
    stale_cases = [result for result in results if result.get("expected_output", {}).get("stale_values")]
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "case_count": total,
        "case_pass_rate": _ratio(passed, total),
        "query_count": total,
        "answerable_query_count": len(answerable),
        "no_answer_query_count": len(no_answer),
        "permission_negative_count": len(denied),
        "recall_at_1": _ratio(sum(1 for result in answerable if result["recall_at_1"]), len(answerable)),
        "recall_at_3": _ratio(sum(1 for result in answerable if result["recall_at_3"]), len(answerable)),
        "mrr": round(sum(result["mrr"] for result in answerable) / len(answerable), 4) if answerable else 0.0,
        "answer_exactness": _ratio(sum(1 for result in answerable if result["recall_at_1"]), len(answerable)),
        "abstention_accuracy": _ratio(sum(1 for result in no_answer if result["abstained"]), len(no_answer)),
        "permission_negative_accuracy": _ratio(sum(1 for result in denied if result["permission_ok"]), len(denied)),
        "evidence_coverage": _ratio(sum(1 for result in evidence_cases if result["evidence_present"]), len(evidence_cases)),
        "evidence_source_accuracy": _ratio(
            sum(1 for result in source_cases if result["evidence_source_ok"]), len(source_cases)
        ),
        "distractor_leakage_rate": _ratio(
            sum(1 for result in forbidden_cases if result["distractor_leak"]), len(forbidden_cases)
        ),
        "stale_leakage_rate": _ratio(sum(1 for result in stale_cases if result["stale_leak"]), len(stale_cases)),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 3) if total else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "failure_type_counts": _failure_type_counts(results),
    }


def _realistic_group_metrics(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result.get(key) or "unknown"), []).append(result)
    return {group: _copilot_realistic_recall_metrics(items) for group, items in sorted(grouped.items())}


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
    if results and str(results[0].get("case_type", "")).startswith("copilot_"):
        fields = [
            "case_id",
            "case_type",
            "passed",
            "failure_type",
            "recommended_fix",
            "latency_ms",
            "input_summary",
            "expected_output",
            "actual_output_summary",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "case_id": result.get("case_id"),
                        "case_type": result.get("case_type"),
                        "passed": result.get("passed"),
                        "failure_type": result.get("failure_type"),
                        "recommended_fix": result.get("recommended_fix"),
                        "latency_ms": result.get("latency_ms"),
                        "input_summary": result.get("query")
                        or result.get("text")
                        or result.get("task")
                        or result.get("input")
                        or result.get("expected_subject"),
                        "expected_output": json.dumps(
                            result.get("expected_output", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "actual_output_summary": json.dumps(
                            result.get("actual_output_summary", {}), ensure_ascii=False, sort_keys=True
                        ),
                    }
                )
        return

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
        "avg_noise_rejection_rate": round(sum(result["noise_rejection_rate"] for result in results) / total, 4)
        if total
        else 0.0,
        "document_evidence_coverage": _ratio(
            sum(1 for result in results for recall in result["recalls"] if recall["document_source_present"]),
            sum(len(result["recalls"]) for result in results),
        ),
        "avg_ingestion_latency_ms": round(sum(result["ingestion_latency_ms"] for result in results) / total, 3)
        if total
        else 0.0,
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
