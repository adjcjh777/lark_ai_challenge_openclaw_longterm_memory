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


class CopilotBenchmarkTest(unittest.TestCase):
    def test_layer_benchmark_reports_expected_layer_accuracy(self) -> None:
        result = run_benchmark(LAYER_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_layer", result["benchmark_type"])
        self.assertEqual(15, summary["case_count"])
        self.assertEqual(15, summary["layer_case_count"])
        self.assertEqual(1.0, summary["case_pass_rate"])
        self.assertEqual(1.0, summary["layer_accuracy"])
        self.assertIn("l1_hot_recall_p95_ms", summary)
        self.assertEqual({}, summary["failure_type_counts"])
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
        self.assertEqual({"L1": 5, "L2": 5, "L3": 5}, dict(layers))
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
                {"keyword_miss", "vector_miss", "wrong_subject_normalization", "evidence_missing", "stale_conflict"},
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

        self.assertEqual(34, len(cases))
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual({True: 17, False: 17}, dict(expected))
        for case in cases:
            self.assertEqual("copilot_candidate", case["type"], msg=case["case_id"])
            self.assertTrue(case["text"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_reason"].strip(), msg=case["case_id"])

    def test_candidate_benchmark_reports_precision_and_failures(self) -> None:
        result = run_benchmark(CANDIDATE_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_candidate", result["benchmark_type"])
        self.assertEqual(34, summary["case_count"])
        self.assertGreaterEqual(summary["candidate_precision"], 0.6)
        self.assertEqual(0, summary["candidate_not_detected"])
        self.assertEqual(0, summary["false_positive_candidate"])
        self.assertEqual(0, summary["evidence_missing"])
        self.assertEqual({}, summary["failure_type_counts"])

    def test_conflict_fixture_has_review_actions_and_forbidden_old_values(self) -> None:
        cases = json.loads(CONFLICT_CASES.read_text(encoding="utf-8"))
        case_ids = [case["case_id"] for case in cases]

        self.assertGreaterEqual(len(cases), 10)
        self.assertEqual(len(case_ids), len(set(case_ids)))
        for case in cases:
            self.assertEqual("copilot_conflict", case["type"], msg=case["case_id"])
            self.assertEqual("confirm", case["expected_action"], msg=case["case_id"])
            self.assertTrue(case["expected_active_value"].strip(), msg=case["case_id"])
            self.assertTrue(case["forbidden_value"].strip(), msg=case["case_id"])
            self.assertTrue(case["expected_reason"].strip(), msg=case["case_id"])
            self.assertTrue(case["failure_debug_hint"].strip(), msg=case["case_id"])

    def test_conflict_benchmark_reports_accuracy_and_zero_leakage(self) -> None:
        result = run_benchmark(CONFLICT_CASES)
        summary = result["summary"]

        self.assertEqual("copilot_conflict", result["benchmark_type"])
        self.assertGreaterEqual(summary["case_count"], 10)
        self.assertGreaterEqual(summary["conflict_accuracy"], 0.7)
        self.assertEqual(0.0, summary["stale_leakage_rate"])
        self.assertEqual(0.0, summary["superseded_leakage_rate"])
        self.assertGreaterEqual(summary["evidence_coverage"], 0.8)
        self.assertEqual({}, summary["failure_type_counts"])


if __name__ == "__main__":
    unittest.main()
