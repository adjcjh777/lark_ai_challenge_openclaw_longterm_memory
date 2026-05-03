from __future__ import annotations

import unittest

from scripts.check_workspace_real_fetch_latency_gate import build_real_fetch_latency_report


class WorkspaceRealFetchLatencyGateTest(unittest.TestCase):
    def test_report_passes_for_successful_real_fetch_summary(self) -> None:
        report = build_real_fetch_latency_report(
            ingest_output={
                "ok": True,
                "mode": "controlled_workspace_ingestion_pilot",
                "boundary": "candidate_pipeline_only_with_registry_no_production_daemon_no_raw_event_embedding",
                "fetched_count": 1,
                "source_count": 3,
                "candidate_count": 2,
                "failed_count": 0,
                "result_count": 3,
                "results": [
                    {
                        "resource": {"route_type": "sheet"},
                        "source": {"source_type": "lark_sheet"},
                    },
                    {
                        "resource": {"route_type": "sheet"},
                        "source": {"source_type": "lark_sheet"},
                    },
                ],
            },
            returncode=0,
            elapsed_ms=12000.0,
            resource_count=1,
            elapsed_ms_max=45000.0,
            per_resource_ms_max=45000.0,
            min_source_count=1,
            min_candidate_count=1,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(12000.0, report["summary"]["elapsed_ms"])
        self.assertEqual({"sheet": 2}, report["route_counts"])
        self.assertEqual({"lark_sheet": 2}, report["source_type_counts"])

    def test_report_fails_for_fetch_error_or_latency_regression(self) -> None:
        report = build_real_fetch_latency_report(
            ingest_output={
                "ok": True,
                "source_count": 0,
                "candidate_count": 0,
                "failed_count": 1,
                "results": [],
            },
            returncode=0,
            elapsed_ms=60000.0,
            resource_count=1,
            elapsed_ms_max=45000.0,
            per_resource_ms_max=45000.0,
            min_source_count=1,
            min_candidate_count=1,
        )

        self.assertFalse(report["ok"])
        self.assertIn("no_failed_fetch", report["failures"])
        self.assertIn("min_source_count", report["failures"])
        self.assertIn("min_candidate_count", report["failures"])
        self.assertIn("elapsed_ms", report["failures"])
        self.assertIn("per_resource_ms", report["failures"])


if __name__ == "__main__":
    unittest.main()
