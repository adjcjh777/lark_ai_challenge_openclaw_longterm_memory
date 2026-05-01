from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_copilot_admin_production_evidence import (
    DEFAULT_MANIFEST_PATH,
    run_production_evidence_check,
)


class CopilotAdminProductionEvidenceTest(unittest.TestCase):
    def test_example_manifest_is_valid_but_not_production_ready(self) -> None:
        result = run_production_evidence_check(DEFAULT_MANIFEST_PATH)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready"], result)
        self.assertTrue(result["example_manifest"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertIn("production_db", result["warning_checks"])
        self.assertIn("enterprise_idp_sso", result["warning_checks"])
        self.assertIn("production_domain_tls", result["warning_checks"])
        self.assertIn("production_monitoring", result["warning_checks"])
        self.assertIn("productized_live_long_run", result["warning_checks"])

    def test_complete_manifest_is_production_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "production-evidence.json"
            manifest_path.write_text(json.dumps(_complete_manifest()), encoding="utf-8")

            result = run_production_evidence_check(manifest_path)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["production_ready"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertEqual([], result["warning_checks"])
        self.assertEqual([], result["production_blockers"])

    def test_real_manifest_with_placeholders_fails(self) -> None:
        manifest = _complete_manifest()
        manifest["production_db"]["engine"] = "__FILL_POSTGRESQL__"
        manifest["production_domain_tls"]["url"] = "https://example.com"
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "bad-production-evidence.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_production_evidence_check(manifest_path)

        self.assertFalse(result["ok"], result)
        self.assertFalse(result["production_ready"], result)
        self.assertIn("production_db", result["failed_checks"])
        self.assertIn("production_domain_tls", result["failed_checks"])

    def test_manifest_with_secret_like_value_fails(self) -> None:
        manifest = _complete_manifest()
        manifest["production_monitoring"]["evidence_refs"] = ["Bearer secret-token"]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "secret-production-evidence.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_production_evidence_check(manifest_path)

        self.assertFalse(result["ok"], result)
        self.assertIn("secret_redaction", result["failed_checks"])


def _complete_manifest() -> dict[str, object]:
    return {
        "schema_version": "copilot_admin_production_evidence/v1",
        "example": False,
        "generated_at": "2026-05-01T10:00:00+08:00",
        "environment": "production",
        "owner": "chengjunhao",
        "production_db": {
            "engine": "postgresql",
            "migration_applied_at": "2026-05-01T10:05:00+08:00",
            "pitr_enabled": True,
            "backup_restore_drill_at": "2026-05-01T11:00:00+08:00",
            "evidence_refs": ["ops/db-migration-run-20260501"],
        },
        "enterprise_idp_sso": {
            "provider": "feishu_sso",
            "production_login_tested_at": "2026-05-01T11:30:00+08:00",
            "admin_login_passed": True,
            "viewer_export_denied": True,
            "allowed_domains": ["company.internal"],
            "evidence_refs": ["ops/sso-smoke-20260501"],
        },
        "production_domain_tls": {
            "url": "https://memory.company.internal",
            "tls_validated_at": "2026-05-01T12:00:00+08:00",
            "certificate_subject": "CN=memory.company.internal",
            "certificate_expires_at": "2099-01-01T00:00:00+00:00",
            "hsts_enabled": True,
            "evidence_refs": ["ops/tls-check-20260501"],
        },
        "production_monitoring": {
            "prometheus_scrape_proven": True,
            "grafana_dashboard_url": "https://grafana.company.internal/d/copilot-admin",
            "alertmanager_route": "team-memory-copilot",
            "alert_delivery_tested_at": "2026-05-01T13:00:00+08:00",
            "evidence_refs": ["ops/alert-delivery-20260501"],
        },
        "productized_live_long_run": {
            "service_unit": "copilot-admin.service",
            "started_at": "2026-05-01T14:00:00+08:00",
            "evidence_window_hours": 24,
            "healthcheck_sample_count": 3,
            "oncall_owner": "chengjunhao",
            "rollback_drill_at": "2026-05-01T15:00:00+08:00",
            "evidence_refs": ["ops/long-run-window-20260501"],
        },
    }


if __name__ == "__main__":
    unittest.main()
