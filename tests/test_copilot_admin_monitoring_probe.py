from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.check_copilot_admin_monitoring_probe import run_monitoring_probe


VALID_METRICS = """
# HELP copilot_admin_memory_total Total memories.
copilot_admin_memory_total 3
copilot_admin_wiki_card_count 1
copilot_admin_graph_workspace_node_count 4
copilot_admin_launch_production_blocked 1
"""


class CopilotAdminMonitoringProbeTest(unittest.TestCase):
    def test_monitoring_probe_emits_manifest_patch_for_valid_metrics(self) -> None:
        result = run_monitoring_probe(
            base_url="https://memory.company.internal/admin/",
            token="viewer-token-redacted",
            grafana_dashboard_url="https://grafana.company.internal/d/copilot-admin",
            alertmanager_route="team-memory-copilot",
            alert_delivery_tested_at="2026-05-01T12:00:00+00:00",
            monitoring_evidence_refs=["ops/alert-delivery-20260501"],
            metrics_fetcher=lambda url, token, timeout: {
                "status": 200,
                "content_type": "text/plain; version=0.0.4",
                "body": VALID_METRICS,
            },
            now=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"])
        patch = result["production_manifest_patch"]["production_monitoring"]
        self.assertTrue(patch["prometheus_scrape_proven"])
        self.assertEqual("https://grafana.company.internal/d/copilot-admin", patch["grafana_dashboard_url"])
        self.assertEqual("team-memory-copilot", patch["alertmanager_route"])
        self.assertIn("metrics_probe:memory.company.internal:", patch["evidence_refs"][1])

    def test_monitoring_probe_rejects_placeholder_base_url_without_fetching(self) -> None:
        called = {"metrics": False}

        def fetcher(url: str, token: str | None, timeout: float):
            called["metrics"] = True
            return {"status": 200, "content_type": "text/plain", "body": VALID_METRICS}

        result = run_monitoring_probe(
            base_url="https://localhost:8765",
            token=None,
            grafana_dashboard_url="https://grafana.company.internal/d/copilot-admin",
            alertmanager_route="team-memory-copilot",
            alert_delivery_tested_at="2026-05-01T12:00:00+00:00",
            monitoring_evidence_refs=["ops/alert-delivery-20260501"],
            metrics_fetcher=fetcher,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual(["admin_url"], result["failed_checks"])
        self.assertFalse(called["metrics"])
        self.assertIn("host_is_not_placeholder", result["checks"]["admin_url"]["missing_or_placeholder"])

    def test_monitoring_probe_rejects_missing_metric_and_bad_alert_ref(self) -> None:
        result = run_monitoring_probe(
            base_url="https://memory.company.internal",
            token=None,
            grafana_dashboard_url="https://example.com/d/copilot-admin",
            alertmanager_route="team-memory-copilot",
            alert_delivery_tested_at="not-a-date",
            monitoring_evidence_refs=["Bearer secret"],
            metrics_fetcher=lambda url, token, timeout: {
                "status": 200,
                "content_type": "text/plain",
                "body": "copilot_admin_memory_total 3\n",
            },
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("metrics", result["failed_checks"])
        self.assertIn("grafana_url", result["failed_checks"])
        self.assertIn("alerting", result["failed_checks"])
        self.assertIn("required_metrics_present", result["checks"]["metrics"]["missing_or_placeholder"])
        self.assertIn("alert_delivery_tested_at_is_iso", result["checks"]["alerting"]["missing_or_placeholder"])
        self.assertIn("evidence_refs_present", result["checks"]["alerting"]["missing_or_placeholder"])


if __name__ == "__main__":
    unittest.main()
