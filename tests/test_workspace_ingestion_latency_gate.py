from __future__ import annotations

import unittest

from scripts.check_workspace_ingestion_latency_gate import build_latency_gate_report


class WorkspaceIngestionLatencyGateTest(unittest.TestCase):
    def test_latency_gate_passes_when_quality_and_latency_are_within_thresholds(self) -> None:
        report = build_latency_gate_report(
            _benchmark(avg_latency=12.0, latencies=[10.0, 14.0]),
            cases_path="benchmarks/day5_ingestion_cases.json",
            avg_latency_ms_max=750.0,
            max_latency_ms_max=1500.0,
            warmup_runs=1,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(1, report["warmup_runs"])
        self.assertEqual(14.0, report["summary"]["max_ingestion_latency_ms"])
        self.assertEqual([], report["failures"])

    def test_latency_gate_fails_on_quality_or_latency_regression(self) -> None:
        benchmark = _benchmark(avg_latency=900.0, latencies=[900.0, 1600.0])
        benchmark["summary"]["case_pass_rate"] = 0.5

        report = build_latency_gate_report(
            benchmark,
            cases_path="benchmarks/day5_ingestion_cases.json",
            avg_latency_ms_max=750.0,
            max_latency_ms_max=1500.0,
            warmup_runs=1,
        )

        self.assertFalse(report["ok"])
        self.assertIn("case_pass_rate", report["failures"])
        self.assertIn("avg_ingestion_latency_ms", report["failures"])
        self.assertIn("max_ingestion_latency_ms", report["failures"])


def _benchmark(*, avg_latency: float, latencies: list[float]) -> dict[str, object]:
    return {
        "summary": {
            "case_count": len(latencies),
            "case_pass_rate": 1.0,
            "avg_quote_coverage": 1.0,
            "avg_noise_rejection_rate": 1.0,
            "document_evidence_coverage": 1.0,
            "avg_ingestion_latency_ms": avg_latency,
        },
        "results": [
            {
                "case_id": f"case_{index}",
                "ingestion_latency_ms": latency,
                "candidate_count": 5,
                "passed": True,
            }
            for index, latency in enumerate(latencies, start=1)
        ],
    }


if __name__ == "__main__":
    unittest.main()
