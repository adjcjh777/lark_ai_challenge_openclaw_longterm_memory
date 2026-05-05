from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from memory_engine.benchmark import _text_has_forbidden_leak, run_benchmark
from scripts.check_realistic_recall_challenge_gate import build_challenge_gate_report

LAYER_CASES = Path("benchmarks/copilot_layer_cases.json")
RECALL_CASES = Path("benchmarks/copilot_recall_cases.json")
CANDIDATE_CASES = Path("benchmarks/copilot_candidate_cases.json")
CONFLICT_CASES = Path("benchmarks/copilot_conflict_cases.json")
REAL_FEISHU_CASES = Path("benchmarks/copilot_real_feishu_cases.json")
REALISTIC_RECALL_CHALLENGE = Path("benchmarks/copilot_realistic_recall_challenge.json")


class CopilotBenchmarkTest(unittest.TestCase):
    def test_layer_benchmark_reports_expected_layer_accuracy(self) -> None:
        result = run_benchmark(LAYER_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_layer", result["benchmark_type"])
        self.assertEqual(40, summary["case_count"])
        self.assertEqual(40, summary["layer_case_count"])
        self.assertGreaterEqual(summary["case_pass_rate"], 0.8)
        self.assertEqual(1.0, summary["layer_accuracy"])
        self.assertIn("l1_hot_recall_p95_ms", summary)
        self.assertIn("failure_type_counts", summary)
        for item in result["results"]:
            self.assertEqual(item["expected_layer"], item["actual_layer"], msg=item["case_id"])
            self.assertTrue(item["layer_passed"], msg=item["case_id"])
            self.assertIn("trace", item)
            self.assertIn("failure_type", item)
            self.assertIn("recommended_fix", item)

    def test_layer_fixture_is_balanced_and_debuggable(self) -> None:
        cases = json.loads(LAYER_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]
        layers = Counter(case["expected_layer"] for case in cases)

        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual({"L1": 12, "L2": 16, "L3": 12}, dict(layers))
        for case in cases:
            self.assertTrue(case["query"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_active_value"].strip(), msg=case["case_id"])
            self.assertTrue(case["evidence_keyword"].strip(), msg=case["case_id"])
            self.assertTrue(case["layer_reason"].strip(), msg=case["case_id"])
            self.assertTrue(case["failure_debug_hint"].strip(), msg=case["case_id"])

    def test_recall_fixture_has_enterprise_memory_intent(self) -> None:
        cases = json.loads(RECALL_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]

        self.assertGreaterEqual(len(cases), 8)
        self.assertEqual(len(case_ids), len(set(case_ids)))
        for case in cases:
            self.assertTrue(case["query"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_active_value"].strip(), msg=case["case_id"])
            self.assertTrue(case["evidence_keyword"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_memory_intent"].strip(), msg=case["case_id"])
            self.assertTrue(case["failure_debug_hint"].strip(), msg=case["case_id"])
            self.assertIn(
                case["failure_category"],
                {
                    "keyword_miss",
                    "vector_miss",
                    "wrong_subject_normalization",
                    "evidence_missing",
                    "stale_conflict",
                    "topic_bleed",
                    "noise_overwhelm",
                    "result_drift",
                },
                msg=case["case_id"],
            )

    def test_recall_benchmark_reports_recall_at_3_and_evidence_coverage(self) -> None:
        result = run_benchmark(RECALL_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_recall", result["benchmark_type"])
        self.assertGreaterEqual(summary["case_count"], 8)
        self.assertGreaterEqual(summary["recall_at_3"], 0.6)
        self.assertGreaterEqual(summary["evidence_coverage"], 0.8)
        self.assertIn("p95_latency_ms", summary)
        for item in result["results"]:
            self.assertIn("top_candidates", item)
            self.assertIn("trace", item)
            self.assertIn("expected_output", item)
            self.assertIn("actual_output_summary", item)
            self.assertIn("score_breakdown_summary", item["actual_output_summary"])
            self.assertIn("failure_type", item)

    def test_forbidden_leak_detector_allows_explicit_rejection_context_only(self) -> None:
        self.assertFalse(
            _text_has_forbidden_leak("发布 pipeline 统一用 GitHub Actions，禁止 Jenkins 触发。", "Jenkins")
        )
        self.assertFalse(_text_has_forbidden_leak("项目管理面板用飞书多维表格，不引入 Jira 或 Linear。", "Jira"))
        self.assertFalse(_text_has_forbidden_leak("源码仓库迁到 GitHub，GitLab 只留镜像。", "GitLab"))
        self.assertFalse(
            _text_has_forbidden_leak("生产环境部署必须走审批流，任何人不能直接 push 到 main。", "直接 push")
        )
        self.assertTrue(_text_has_forbidden_leak("规则：发布 pipeline 使用 Jenkins。", "Jenkins"))
        self.assertFalse(_text_has_forbidden_leak("覆盖率标准改成 90%，之前 80% 太低了。", "80%"))
        self.assertFalse(_text_has_forbidden_leak("PostgreSQL 运维文档没跟上，暂时切回 MySQL。", "PostgreSQL"))
        self.assertFalse(_text_has_forbidden_leak("80% 导致很多无意义 mock，调到 70%。", "80%"))

    def test_candidate_fixture_has_balanced_plain_language_reasons(self) -> None:
        cases = json.loads(CANDIDATE_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]
        expected = Counter(case["expected_candidate"] for case in cases)

        self.assertEqual(57, len(cases))
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual({True: 30, False: 27}, dict(expected))
        for case in cases:
            self.assertEqual("copilot_candidate", case["type"], msg=case["case_id"])
            self.assertTrue(case["text"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_reason"].strip(), msg=case["case_id"])

    def test_candidate_benchmark_reports_precision_and_failures(self) -> None:
        result = run_benchmark(CANDIDATE_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_candidate", result["benchmark_type"])
        self.assertEqual(57, summary["case_count"])
        self.assertGreaterEqual(summary["candidate_precision"], 0.6)
        self.assertIn("failure_type_counts", summary)

    def test_conflict_fixture_has_review_actions_and_forbidden_old_values(self) -> None:
        cases = json.loads(CONFLICT_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]

        self.assertGreaterEqual(len(cases), 10)
        self.assertEqual(len(case_ids), len(set(case_ids)))
        for case in cases:
            self.assertEqual("copilot_conflict", case["type"], msg=case["case_id"])
            self.assertIn(case["expected_action"], {"confirm", "reject"}, msg=case["case_id"])
            self.assertTrue(case["expected_active_value"].strip(), msg=case["case_id"])
            self.assertTrue(case["forbidden_value"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_reason"].strip(), msg=case["case_id"])
            self.assertTrue(case["failure_debug_hint"].strip(), msg=case["case_id"])

    def test_conflict_benchmark_reports_accuracy_and_zero_leakage(self) -> None:
        result = run_benchmark(CONFLICT_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_conflict", result["benchmark_type"])
        self.assertGreaterEqual(summary["case_count"], 10)
        self.assertGreaterEqual(summary["conflict_accuracy"], 0.3)
        self.assertIn("stale_leakage_rate", summary)
        self.assertIn("superseded_leakage_rate", summary)
        self.assertGreaterEqual(summary["evidence_coverage"], 0.8)
        self.assertIn("score_breakdown_summary", result["results"][0]["actual_output_summary"])

    def test_real_feishu_expression_fixture_schema_and_coverage(self) -> None:
        cases = json.loads(REAL_FEISHU_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]
        categories = Counter(case["expression_category"] for case in cases)

        self.assertEqual(40, len(cases))
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual(
            {
                "ambiguous": 8,
                "chitchat_false_positive": 8,
                "colloquial": 8,
                "multi_turn_correction": 8,
                "permission": 8,
            },
            dict(sorted(categories.items())),
        )
        for case in cases:
            self.assertEqual("copilot_real_feishu", case["type"], msg=case["case_id"])
            self.assertTrue(case["input"].strip(), msg=case["case_id"])
            self.assertIsInstance(case["context"], dict, msg=case["case_id"])
            self.assertTrue(case["expected_intent"].strip(), msg=case["case_id"])
            self.assertIsInstance(case["expected_should_remember"], bool, msg=case["case_id"])
            self.assertIn(case["expected_permission"]["decision"], {"allow", "deny"}, msg=case["case_id"])
            self.assertIn("observed_baseline", case, msg=case["case_id"])
            self.assertTrue(case["failure_debug_hint"].strip(), msg=case["case_id"])
            serialized = json.dumps(case, ensure_ascii=False).lower()
            for forbidden in ("chat_id", "open_id", "app_secret", "tenant_access_token", "root@123456"):
                self.assertNotIn(forbidden, serialized, msg=case["case_id"])

    def test_real_feishu_expression_benchmark_reports_ux_metrics_and_failures(self) -> None:
        result = run_benchmark(REAL_FEISHU_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_real_feishu", result["benchmark_type"])
        self.assertEqual(40, summary["case_count"])
        self.assertEqual(5, summary["category_count"])
        self.assertIn("recall_at_3", summary)
        self.assertIn("false_memory_rate", summary)
        self.assertIn("false_reminder_rate", summary)
        self.assertIn("user_confirmation_burden", summary)
        self.assertIn("explanation_coverage", summary)
        self.assertIn("old_value_leakage_rate", summary)
        self.assertEqual(0.0, summary["old_value_leakage_rate"])
        self.assertEqual(0.0, summary["false_memory_rate"])
        self.assertEqual(1.0, summary["explanation_coverage"])
        self.assertEqual(1.0, summary["case_pass_rate"])
        self.assertNotIn("user_expression_context_miss", summary["failure_type_counts"])
        self.assertNotIn("user_expression_explanation_missing", summary["failure_type_counts"])
        self.assertNotIn("false_positive_candidate", summary["failure_type_counts"])
        self.assertNotIn("user_expression_old_value_leaked", summary["failure_type_counts"])
        for item in result["results"]:
            self.assertIn("expected_output", item)
            self.assertIn("actual_output_summary", item)
            self.assertIn("failure_debug_hint", item)

    def test_realistic_recall_fixture_is_large_and_challenge_shaped(self) -> None:
        spec = json.loads(REALISTIC_RECALL_CHALLENGE.read_text(encoding="utf-8"))
        queries = spec["queries"]
        categories = Counter(query["category"] for query in queries)

        self.assertEqual("copilot_realistic_recall_challenge", spec["benchmark_type"])
        self.assertGreaterEqual(len(spec["corpus"]["events"]), 80)
        self.assertGreaterEqual(len(queries), 125)
        self.assertGreaterEqual(len(categories), 8)
        self.assertGreaterEqual(sum(1 for item in queries if item.get("expected_no_answer")), 14)
        self.assertGreaterEqual(sum(1 for item in queries if item.get("expected_permission_decision") == "deny"), 14)
        self.assertGreaterEqual(sum(1 for item in queries if item.get("forbidden_values")), 80)
        self.assertEqual(len({item["id"] for item in queries}), len(queries))
        for item in queries:
            self.assertTrue(item["query"].strip(), msg=item["id"])
            self.assertTrue(item["failure_debug_hint"].strip(), msg=item["id"])

    def test_realistic_recall_runner_uses_shared_corpus_and_reports_strict_metrics(self) -> None:
        spec = {
            "benchmark_type": "copilot_realistic_recall_challenge",
            "name": "unit_shared_corpus_challenge",
            "corpus": {
                "events": [
                    {
                        "id": "evt_prod_region_final",
                        "content": "生产部署 region 最终改成 ap-shanghai，灰度 5% 观察 10 分钟。",
                        "source_type": "feishu_message",
                    },
                    {
                        "id": "evt_test_region_distractor",
                        "content": "测试环境部署 region 仍然使用 cn-shanghai，不能套用到生产。",
                        "source_type": "lark_doc",
                    },
                ]
            },
            "queries": [
                {
                    "id": "q_prod_region",
                    "category": "confusable_distractor",
                    "query": "生产发版现在用哪个 region",
                    "expected_active_value": "ap-shanghai",
                    "forbidden_values": ["cn-shanghai"],
                    "evidence_keywords": ["最终改成 ap-shanghai"],
                    "expected_source_types": ["feishu_message"],
                    "failure_debug_hint": "生产 region 不能被测试环境 region 干扰。",
                },
                {
                    "id": "q_unanswerable",
                    "category": "no_answer",
                    "query": "财务报销入口在哪里",
                    "expected_no_answer": True,
                    "failure_debug_hint": "共享语料没有财务报销信息时应该拒答或低置信度。",
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as tmp:
            json.dump(spec, tmp, ensure_ascii=False)
            tmp.flush()
            result = run_benchmark(Path(tmp.name))
        summary = result["summary"]

        self.assertEqual("copilot_realistic_recall_challenge", result["benchmark_type"])
        self.assertEqual(2, result["layers"]["query_count"])
        self.assertEqual(2, result["layers"]["corpus_event_count"])
        self.assertIn("recall_at_1", summary)
        self.assertIn("recall_at_3", summary)
        self.assertIn("mrr", summary)
        self.assertIn("distractor_leakage_rate", summary)
        self.assertIn("stale_leakage_rate", summary)
        self.assertIn("evidence_source_accuracy", summary)
        self.assertIn("abstention_accuracy", summary)
        for item in result["results"]:
            self.assertIn("top_candidates", item)
            self.assertIn("actual_output_summary", item)
            self.assertIn("failure_type", item)

    def test_realistic_recall_gate_is_a_validity_gate_not_production_claim(self) -> None:
        benchmark = {
            "source": "benchmarks/copilot_realistic_recall_challenge.json",
            "layers": {"corpus_event_count": 80, "query_count": 125},
            "summary": {
                "case_pass_rate": 0.58,
                "recall_at_3": 0.75,
                "evidence_coverage": 0.75,
                "abstention_accuracy": 0.34,
                "permission_negative_accuracy": 1.0,
                "distractor_leakage_rate": 0.2,
                "stale_leakage_rate": 0.5,
            },
            "results": [{"case_id": "q1", "passed": False, "failure_type": "vector_miss"}],
        }
        report = build_challenge_gate_report(benchmark)

        self.assertTrue(report["ok"])
        self.assertIn("not production", report["boundary"])
        self.assertIn("failed_cases", report)


if __name__ == "__main__":
    unittest.main()
