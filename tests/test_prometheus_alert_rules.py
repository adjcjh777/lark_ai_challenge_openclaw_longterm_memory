from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_prometheus_alert_rules import DEFAULT_RULES_PATH, check_alert_rules


class PrometheusAlertRulesTest(unittest.TestCase):
    def test_default_alert_rules_cover_admin_metrics_and_no_overclaim_boundary(self) -> None:
        report = check_alert_rules(DEFAULT_RULES_PATH)

        self.assertTrue(report["ok"], report)
        self.assertEqual(8, report["alert_count"])
        self.assertIn("CopilotLaunchStagingNotReady", report["alerts"])
        self.assertIn("CopilotProductionMonitoringBlocker", report["alerts"])
        self.assertIn("production Prometheus/Grafana deployment remains unverified", report["boundary"])

    def test_missing_required_metric_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="copilot_alert_rules_") as tmp:
            path = Path(tmp) / "alerts.yml"
            text = DEFAULT_RULES_PATH.read_text(encoding="utf-8")
            path.write_text(
                text.replace("copilot_admin_wiki_card_count", "copilot_admin_wrong_metric"), encoding="utf-8"
            )

            report = check_alert_rules(path)

            self.assertFalse(report["ok"])
            self.assertEqual("fail", report["checks"]["required_metrics"]["status"])
            self.assertIn("CopilotWikiCardsMissing", report["checks"]["required_metrics"]["missing"])


if __name__ == "__main__":
    unittest.main()
