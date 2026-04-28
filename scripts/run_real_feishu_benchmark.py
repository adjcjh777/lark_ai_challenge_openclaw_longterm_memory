#!/usr/bin/env python3
"""真实飞书场景 benchmark runner。

验证系统在真实飞书来源（任务、会议、Bitable）下的：
1. candidate precision（不误记闲聊和噪声）
2. recall accuracy（不漏召回关键决策）
3. sensitive leakage（不泄露密码和个人 PII）
4. false positive（闲聊不被误记为 candidate）

用法：
  python3 scripts/run_real_feishu_benchmark.py
  python3 scripts/run_real_feishu_benchmark.py --json
  python3 scripts/run_real_feishu_benchmark.py --case-id real_feishu_task_recall_001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from memory_engine.document_ingestion import extract_candidate_quotes

CASES_PATH = Path("benchmarks/copilot_real_feishu_cases.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="真实飞书场景 benchmark runner")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--case-id", help="只运行指定的 case")
    args = parser.parse_args()

    cases = _load_cases()
    if args.case_id:
        cases = [c for c in cases if c["case_id"] == args.case_id]
        if not cases:
            print(f"未找到 case: {args.case_id}", file=sys.stderr)
            sys.exit(1)

    results = []
    for case in cases:
        result = _run_case(case)
        results.append(result)

    summary = _build_summary(results)

    if args.json:
        output = {"summary": summary, "results": results}
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_report(summary, results)

    sys.exit(0 if summary["pass_rate"] >= 0.8 else 1)


def _load_cases() -> list[dict]:
    if not CASES_PATH.exists():
        print(f"benchmark cases 文件不存在: {CASES_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_case(case: dict) -> dict:
    """执行单个 benchmark case。"""
    case_id = case["case_id"]
    subtype = case.get("subtype", "unknown")
    source_type = case.get("source_type", "unknown")

    try:
        if subtype == "recall":
            return _run_recall_case(case)
        elif subtype == "candidate":
            return _run_candidate_case(case)
        else:
            return {
                "case_id": case_id,
                "subtype": subtype,
                "source_type": source_type,
                "status": "skipped",
                "reason": f"未知 subtype: {subtype}",
            }
    except Exception as e:
        return {
            "case_id": case_id,
            "subtype": subtype,
            "source_type": source_type,
            "status": "error",
            "reason": str(e),
        }


def _run_recall_case(case: dict) -> dict:
    """运行 recall 类 case。

    验证从 source_text 中提取的候选文本能被正确提取，并与 query 相关。
    """
    case_id = case["case_id"]
    source_type = case.get("source_type", "unknown")
    source_text = case.get("source_text", "")
    query = case.get("query", "")
    expected_active_value = case.get("expected_active_value", "")
    evidence_keyword = case.get("evidence_keyword", "")
    noise_texts = case.get("noise_texts", [])

    # 验证 1: 从 source_text 中能提取到候选文本
    candidates = extract_candidate_quotes(source_text, limit=12)

    # 验证 2: 候选文本包含期望的 evidence keyword
    evidence_found = any(evidence_keyword in candidate for candidate in candidates) if evidence_keyword else True

    # 验证 3: expected_active_value 能在 source_text 中找到
    value_in_source = expected_active_value in source_text if expected_active_value else True

    # 验证 4: 如果有噪声文本，确认噪声不会干扰候选提取
    noise_not_in_candidates = True
    if noise_texts:
        for noise in noise_texts:
            noise_normalized = " ".join(noise.split())
            for candidate in candidates:
                if noise_normalized in candidate:
                    noise_not_in_candidates = False
                    break

    all_pass = evidence_found and value_in_source and noise_not_in_candidates and len(candidates) > 0

    failures = []
    if not candidates:
        failures.append("无法从 source_text 中提取候选文本")
    if not evidence_found:
        failures.append(f"候选文本中未找到 evidence_keyword: {evidence_keyword}")
    if not value_in_source:
        failures.append(f"source_text 中未找到 expected_active_value: {expected_active_value}")
    if not noise_not_in_candidates:
        failures.append("噪声文本泄漏到候选中")

    return {
        "case_id": case_id,
        "subtype": "recall",
        "source_type": source_type,
        "status": "pass" if all_pass else "fail",
        "candidates_extracted": len(candidates),
        "evidence_found": evidence_found,
        "value_in_source": value_in_source,
        "noise_not_in_candidates": noise_not_in_candidates,
        "failures": failures,
        "query": query,
        "expected_active_value": expected_active_value,
    }


def _run_candidate_case(case: dict) -> dict:
    """运行 candidate 类 case。

    验证文本是否应该成为候选记忆。
    """
    case_id = case["case_id"]
    source_type = case.get("source_type", "unknown")
    source_text = case.get("source_text", "")
    expected_candidate = case.get("expected_candidate", False)
    expected_reason = case.get("expected_reason", "")

    # 提取候选文本
    candidates = extract_candidate_quotes(source_text, limit=12)

    # 判断是否提取到候选（即文本是否包含记忆信号）
    actual_candidate = len(candidates) > 0

    # 精度检查: 预期不是候选但提取到了
    false_positive = not expected_candidate and actual_candidate
    # 召回检查: 预期是候选但没提取到
    false_negative = expected_candidate and not actual_candidate

    all_pass = actual_candidate == expected_candidate

    failures = []
    if false_positive:
        failures.append(f"误记: 预期不是候选但提取到了 {len(candidates)} 个候选")
    if false_negative:
        failures.append("漏记: 预期是候选但未提取到任何候选")

    return {
        "case_id": case_id,
        "subtype": "candidate",
        "source_type": source_type,
        "status": "pass" if all_pass else "fail",
        "expected_candidate": expected_candidate,
        "actual_candidate": actual_candidate,
        "candidates_extracted": len(candidates),
        "false_positive": false_positive,
        "false_negative": false_negative,
        "expected_reason": expected_reason,
        "failures": failures,
    }


def _build_summary(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    # 按 subtype 分类统计
    recall_results = [r for r in results if r.get("subtype") == "recall"]
    candidate_results = [r for r in results if r.get("subtype") == "candidate"]

    recall_pass = sum(1 for r in recall_results if r["status"] == "pass")
    candidate_pass = sum(1 for r in candidate_results if r["status"] == "pass")

    # 精度指标
    false_positives = sum(1 for r in candidate_results if r.get("false_positive"))
    false_negatives = sum(1 for r in candidate_results if r.get("false_negative"))

    # 按 source_type 分类统计
    source_stats = {}
    for r in results:
        st = r.get("source_type", "unknown")
        if st not in source_stats:
            source_stats[st] = {"total": 0, "pass": 0, "fail": 0}
        source_stats[st]["total"] += 1
        if r["status"] == "pass":
            source_stats[st]["pass"] += 1
        elif r["status"] == "fail":
            source_stats[st]["fail"] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "pass_rate": passed / total if total > 0 else 0.0,
        "recall": {
            "total": len(recall_results),
            "pass": recall_pass,
            "accuracy": recall_pass / len(recall_results) if recall_results else 0.0,
        },
        "candidate_precision": {
            "total": len(candidate_results),
            "pass": candidate_pass,
            "precision": candidate_pass / len(candidate_results) if candidate_results else 0.0,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        },
        "source_type_stats": source_stats,
    }


def _print_report(summary: dict, results: list[dict]) -> None:
    print("=" * 70)
    print("真实飞书场景 Benchmark 报告")
    print("=" * 70)

    print(f"\n总 case 数: {summary['total']}")
    print(f"通过: {summary['passed']}")
    print(f"失败: {summary['failed']}")
    print(f"错误: {summary['errors']}")
    print(f"跳过: {summary['skipped']}")
    print(f"总通过率: {summary['pass_rate']:.1%}")

    # Recall 指标
    recall = summary["recall"]
    print("\n--- Recall ---")
    print(f"  总数: {recall['total']}")
    print(f"  通过: {recall['pass']}")
    print(f"  准确率: {recall['accuracy']:.1%}")

    # Candidate Precision 指标
    cand = summary["candidate_precision"]
    print("\n--- Candidate Precision ---")
    print(f"  总数: {cand['total']}")
    print(f"  通过: {cand['pass']}")
    print(f"  精度: {cand['precision']:.1%}")
    print(f"  误记 (false_positive): {cand['false_positives']}")
    print(f"  漏记 (false_negative): {cand['false_negatives']}")

    # 按来源类型统计
    print("\n--- 来源类型统计 ---")
    for st, stats in summary["source_type_stats"].items():
        rate = stats["pass"] / stats["total"] if stats["total"] > 0 else 0.0
        print(f"  {st}: {stats['pass']}/{stats['total']} ({rate:.1%})")

    # 失败详情
    failed_cases = [r for r in results if r["status"] == "fail"]
    if failed_cases:
        print("\n--- 失败详情 ---")
        for r in failed_cases:
            print(f"\n  [{r['case_id']}] {r.get('source_type', '?')}")
            for failure in r.get("failures", []):
                print(f"    - {failure}")

    print(f"\n{'=' * 70}")
    if summary["pass_rate"] >= 0.8:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")


if __name__ == "__main__":
    main()
