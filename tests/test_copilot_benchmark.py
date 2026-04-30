from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from memory_engine.benchmark import run_benchmark

LAYER_CASES = Path("benchmarks/copilot_layer_cases.json")
RECALL_CASES = Path("benchmarks/copilot_recall_cases.json")
CANDIDATE_CASES = Path("benchmarks/copilot_candidate_cases.json")
CONFLICT_CASES = Path("benchmarks/copilot_conflict_cases.json")
REAL_FEISHU_CASES = Path("benchmarks/copilot_real_feishu_cases.json")


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
                {"keyword_miss", "vector_miss", "wrong_subject_normalization", "evidence_missing", "stale_conflict", "topic_bleed", "noise_overwhelm", "result_drift"},
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
            self.assertIn("failure_type", item)

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

    def test_real_feishu_expression_fixture_schema_and_coverage(self) -> None:
        cases = json.loads(REAL_FEISHU_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]
        categories = Counter(case["expression_category"] for case in cases)

        self.assertEqual(25, len(cases))
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual(
            {
                "ambiguous": 5,
                "chitchat_false_positive": 5,
                "colloquial": 5,
                "multi_turn_correction": 5,
                "permission": 5,
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
        self.assertEqual(25, summary["case_count"])
        self.assertEqual(5, summary["category_count"])
        self.assertIn("recall_at_3", summary)
        self.assertIn("false_memory_rate", summary)
        self.assertIn("false_reminder_rate", summary)
        self.assertIn("user_confirmation_burden", summary)
        self.assertIn("explanation_coverage", summary)
        self.assertIn("old_value_leakage_rate", summary)
        self.assertGreater(summary["failure_type_counts"].get("user_expression_explanation_missing", 0), 0)
        self.assertGreater(summary["failure_type_counts"].get("false_positive_candidate", 0), 0)
        self.assertGreater(summary["failure_type_counts"].get("user_expression_old_value_leaked", 0), 0)
        for item in result["results"]:
            self.assertIn("expected_output", item)
            self.assertIn("actual_output_summary", item)
            self.assertIn("failure_debug_hint", item)


if __name__ == "__main__":
    unittest.main()
