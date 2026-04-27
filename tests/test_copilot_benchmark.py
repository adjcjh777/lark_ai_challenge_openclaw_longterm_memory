from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from memory_engine.benchmark import run_benchmark


LAYER_CASES = Path("benchmarks/copilot_layer_cases.json")
RECALL_CASES = Path("benchmarks/copilot_recall_cases.json")


class CopilotBenchmarkTest(unittest.TestCase):
    def test_layer_benchmark_reports_expected_layer_accuracy(self) -> None:
        result = run_benchmark(LAYER_CASES)
        summary = result["summary"]

        self.assertEqual(15, summary["case_count"])
        self.assertEqual(15, summary["layer_case_count"])
        self.assertEqual(1.0, summary["case_pass_rate"])
        self.assertEqual(1.0, summary["layer_accuracy"])
        for item in result["results"]:
            self.assertEqual(item["expected_layer"], item["actual_layer"], msg=item["case_id"])
            self.assertTrue(item["layer_passed"], msg=item["case_id"])
            self.assertIn("trace", item)

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


if __name__ == "__main__":
    unittest.main()
