from __future__ import annotations

import unittest

from scripts.collect_copilot_external_production_evidence import collect_external_production_evidence


class CopilotExternalProductionEvidenceTest(unittest.TestCase):
    def test_collects_complete_external_manifest_patch(self) -> None:
        result = collect_external_production_evidence(
            idp_provider="feishu_sso",
            idp_login_tested_at="2026-05-01T10:00:00+08:00",
            idp_admin_login_passed=True,
            idp_viewer_export_denied=True,
            idp_allowed_domains=["company.internal"],
            idp_evidence_refs=["ops/idp-smoke-20260501"],
            tls_url="https://memory.company.internal",
            tls_validated_at="2026-05-01T11:00:00+08:00",
            tls_certificate_subject="CN=memory.company.internal",
            tls_certificate_expires_at="2099-01-01T00:00:00+00:00",
            tls_hsts_enabled=True,
            tls_evidence_refs=["ops/tls-check-20260501"],
            prometheus_scrape_proven=True,
            grafana_dashboard_url="https://grafana.company.internal/d/copilot-admin",
            alertmanager_route="team-memory-copilot",
            alert_delivery_tested_at="2026-05-01T12:00:00+08:00",
            monitoring_evidence_refs=["ops/alert-delivery-20260501"],
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"], result)
        patch = result["production_manifest_patch"]
        self.assertEqual("feishu_sso", patch["enterprise_idp_sso"]["provider"])
        self.assertEqual("https://memory.company.internal", patch["production_domain_tls"]["url"])
        self.assertTrue(patch["production_monitoring"]["prometheus_scrape_proven"])
        self.assertEqual([], result["failed_checks"])

    def test_rejects_placeholder_tls_and_idp_domain(self) -> None:
        result = _complete_result(
            idp_allowed_domains=["example.com"],
            tls_url="https://localhost",
            tls_certificate_expires_at="2020-01-01T00:00:00+00:00",
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("enterprise_idp_sso", result["failed_checks"])
        self.assertIn("production_domain_tls", result["failed_checks"])

    def test_rejects_missing_alert_delivery_and_secret_ref(self) -> None:
        result = _complete_result(
            prometheus_scrape_proven=False,
            monitoring_evidence_refs=["Bearer secret-token"],
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("production_monitoring", result["failed_checks"])
        self.assertIn("prometheus_scrape_proven", result["checks"]["production_monitoring"]["missing_or_placeholder"])
        self.assertIn("evidence_refs_present", result["checks"]["production_monitoring"]["missing_or_placeholder"])

    def test_rejects_secret_like_grafana_url(self) -> None:
        result = _complete_result(
            grafana_dashboard_url="https://grafana.company.internal/d/copilot-admin?access_token=secret",
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("production_monitoring", result["failed_checks"])
        self.assertIn(
            "grafana_dashboard_url_present", result["checks"]["production_monitoring"]["missing_or_placeholder"]
        )


def _complete_result(**overrides):
    params = {
        "idp_provider": "feishu_sso",
        "idp_login_tested_at": "2026-05-01T10:00:00+08:00",
        "idp_admin_login_passed": True,
        "idp_viewer_export_denied": True,
        "idp_allowed_domains": ["company.internal"],
        "idp_evidence_refs": ["ops/idp-smoke-20260501"],
        "tls_url": "https://memory.company.internal",
        "tls_validated_at": "2026-05-01T11:00:00+08:00",
        "tls_certificate_subject": "CN=memory.company.internal",
        "tls_certificate_expires_at": "2099-01-01T00:00:00+00:00",
        "tls_hsts_enabled": True,
        "tls_evidence_refs": ["ops/tls-check-20260501"],
        "prometheus_scrape_proven": True,
        "grafana_dashboard_url": "https://grafana.company.internal/d/copilot-admin",
        "alertmanager_route": "team-memory-copilot",
        "alert_delivery_tested_at": "2026-05-01T12:00:00+08:00",
        "monitoring_evidence_refs": ["ops/alert-delivery-20260501"],
    }
    params.update(overrides)
    return collect_external_production_evidence(**params)


if __name__ == "__main__":
    unittest.main()
