from __future__ import annotations

import unittest

from scripts.check_real_feishu_expression_quality_gate import build_quality_gate_report


class RealFeishuExpressionQualityGateTest(unittest.TestCase):
    def test_gate_passes_when_all_thresholds_are_met(self) -> None:
        report = build_quality_gate_report(
            {
                "summary": {
                    "case_count": 25,
                    "case_pass_rate": 1.0,
                    "recall_at_3": 0.9,
                    "false_memory_rate": 0.0,
                    "false_reminder_rate": 0.0,
                    "user_confirmation_burden": 2.0,
                    "explanation_coverage": 0.9,
                    "old_value_leakage_rate": 0.0,
                    "failure_type_counts": {},
                },
                "results": [],
            },
            source_path="benchmarks/copilot_real_feishu_cases.json",
        )

        self.assertTrue(report["ok"])
        self.assertEqual("pass", report["status"])
        self.assertEqual([], report["failed_checks"])

    def test_gate_fails_on_old_value_leakage_and_reports_failed_cases(self) -> None:
        report = build_quality_gate_report(
            {
                "summary": {
                    "case_count": 25,
                    "case_pass_rate": 0.76,
                    "recall_at_3": 0.875,
                    "false_memory_rate": 0.04,
                    "false_reminder_rate": 0.0,
                    "user_confirmation_burden": 2.4,
                    "explanation_coverage": 0.85,
                    "old_value_leakage_rate": 0.1429,
                    "failure_type_counts": {"user_expression_old_value_leaked": 1},
                },
                "results": [
                    {
                        "case_id": "real_expr_multi_turn_correction_004",
                        "passed": False,
                        "failure_type": "user_expression_old_value_leaked",
                        "recommended_fix": "旧值只能出现在版本解释中。",
                        "failure_debug_hint": "旧 Jenkins 仍可能泄漏。",
                    }
                ],
            },
            source_path="benchmarks/copilot_real_feishu_cases.json",
        )

        self.assertFalse(report["ok"])
        self.assertEqual("fail", report["status"])
        self.assertIn("old_value_leakage_rate", report["failed_checks"])
        self.assertEqual(0.1429, report["checks"]["old_value_leakage_rate"]["actual"])
        self.assertEqual("real_expr_multi_turn_correction_004", report["failed_cases"][0]["case_id"])
        self.assertIn("pre-live local quality gate", report["boundary"])


if __name__ == "__main__":
    unittest.main()
