from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from scripts.collect_copilot_admin_long_run_evidence import HttpResult, collect_long_run_evidence


class CopilotAdminLongRunEvidenceTest(unittest.TestCase):
    def test_collects_manifest_patch_for_complete_long_run_window(self) -> None:
        result = collect_long_run_evidence(
            base_url="https://memory.company.internal",
            token="redacted-token",
            sample_count=3,
            sample_interval_seconds=0,
            min_window_hours=24,
            min_sample_count=3,
            service_unit="copilot-admin.service",
            oncall_owner="chengjunhao",
            rollback_drill_at="2026-05-02T09:00:00+08:00",
            evidence_ref="ops/long-run-window-20260501",
            fetcher=_passing_fetcher,
            now_fn=_clock(
                "2026-05-01T00:00:00+00:00",
                "2026-05-01T12:00:00+00:00",
                "2026-05-02T00:00:00+00:00",
                "2026-05-02T00:00:01+00:00",
            ),
            sleep_fn=lambda _seconds: None,
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"], result)
        self.assertEqual(24.0, result["evidence_window_hours"])
        self.assertEqual(3, result["successful_sample_count"])
        patch = result["production_manifest_patch"]["productized_live_long_run"]
        self.assertEqual("copilot-admin.service", patch["service_unit"])
        self.assertEqual(24.0, patch["evidence_window_hours"])
        self.assertEqual(3, patch["healthcheck_sample_count"])
        self.assertEqual(["ops/long-run-window-20260501"], patch["evidence_refs"])

    def test_short_run_without_ops_fields_fails_collector_gate(self) -> None:
        result = collect_long_run_evidence(
            base_url="http://127.0.0.1:8765?token=should-not-appear",
            token=None,
            sample_count=1,
            sample_interval_seconds=0,
            min_window_hours=24,
            min_sample_count=3,
            service_unit="copilot-admin.service",
            fetcher=_passing_fetcher,
            now_fn=_clock("2026-05-01T00:00:00+00:00", "2026-05-01T00:00:01+00:00"),
            sleep_fn=lambda _seconds: None,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual("http://127.0.0.1:8765", result["base_url"])
        self.assertIn("successful_samples", result["failed_checks"])
        self.assertIn("evidence_window", result["failed_checks"])
        self.assertIn("manifest_patch_fields", result["failed_checks"])


def _passing_fetcher(url: str, token: str | None, timeout_seconds: float) -> HttpResult:
    if url.endswith("/healthz"):
        return HttpResult(status=200, body=json.dumps({"ok": True, "service": "copilot_admin"}))
    if url.endswith("/api/health"):
        return HttpResult(
            status=200,
            body=json.dumps(
                {
                    "ok": True,
                    "data": {
                        "database": "readable",
                        "read_only_knowledge_surfaces": True,
                        "wiki_card_count": 3,
                        "graph_quality_status": "pass",
                    },
                }
            ),
        )
    if url.endswith("/api/launch-readiness"):
        return HttpResult(
            status=200,
            body=json.dumps({"ok": True, "data": {"staging_status": "pass", "production_status": "blocked"}}),
        )
    if url.endswith("/api/graph-quality"):
        return HttpResult(status=200, body=json.dumps({"ok": True, "data": {"status": "pass"}}))
    if url.endswith("/metrics"):
        return HttpResult(status=200, body="copilot_admin_memory_total 1\n")
    return HttpResult(status=404, body=json.dumps({"ok": False}))


def _clock(*iso_values: str):
    values = [datetime.fromisoformat(value).astimezone(timezone.utc) for value in iso_values]
    index = {"value": 0}

    def now() -> datetime:
        value = values[min(index["value"], len(values) - 1)]
        index["value"] += 1
        return value

    return now


if __name__ == "__main__":
    unittest.main()
