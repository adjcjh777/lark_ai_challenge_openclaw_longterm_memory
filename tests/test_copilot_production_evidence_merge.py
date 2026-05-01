from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_copilot_admin_production_evidence import DEFAULT_MANIFEST_PATH
from scripts.merge_copilot_production_evidence import merge_production_evidence_patches


class CopilotProductionEvidenceMergeTest(unittest.TestCase):
    def test_merges_complete_patch_set_into_production_ready_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            patch_paths = _write_complete_patch_set(tmp_path)
            output_path = tmp_path / "production-evidence.json"

            result = merge_production_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=patch_paths,
                output_path=output_path,
            )

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["production_ready_claim"], result)
            self.assertEqual(
                [
                    "enterprise_idp_sso",
                    "production_db",
                    "production_domain_tls",
                    "production_monitoring",
                    "productized_live_long_run",
                ],
                result["merged_sections"],
            )
            self.assertTrue(result["validation"]["production_ready"], result)
            merged = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertFalse(merged["example"])
            self.assertEqual("postgresql", merged["production_db"]["engine"])

    def test_partial_merge_is_valid_operation_but_not_production_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_patch = tmp_path / "db-patch.json"
            db_patch.write_text(json.dumps({"production_manifest_patch": _db_patch()}), encoding="utf-8")

            result = merge_production_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=[db_patch],
            )

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["validation"]["production_ready"], result)
            self.assertIn("enterprise_idp_sso", result["validation"]["failed_checks"])
            self.assertIn("production_domain_tls", result["validation"]["failed_checks"])
            self.assertIn("productized_live_long_run", result["validation"]["failed_checks"])

    def test_rejects_unknown_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch_path = Path(tmp) / "bad-patch.json"
            patch_path.write_text(
                json.dumps({"production_manifest_patch": {"unexpected_section": {"ok": True}}}),
                encoding="utf-8",
            )

            result = merge_production_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=[patch_path],
            )

            self.assertFalse(result["ok"], result)
            self.assertEqual("unknown_manifest_sections", result["errors"][0]["error"])

    def test_rejects_placeholder_or_secret_like_patch_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch_path = Path(tmp) / "secret-patch.json"
            patch_path.write_text(
                json.dumps(
                    {
                        "production_manifest_patch": {
                            "production_monitoring": {
                                "prometheus_scrape_proven": True,
                                "grafana_dashboard_url": "https://grafana.company.internal/d/admin?access_token=secret",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = merge_production_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=[patch_path],
            )

            self.assertFalse(result["ok"], result)
            self.assertEqual("patch_contains_placeholder_or_secret_like_value", result["errors"][0]["error"])


def _write_complete_patch_set(base: Path) -> list[Path]:
    patches = {
        "db.json": _db_patch(),
        "external.json": _external_patch(),
        "long-run.json": _long_run_patch(),
    }
    paths: list[Path] = []
    for filename, patch in patches.items():
        path = base / filename
        path.write_text(json.dumps({"production_manifest_patch": patch}), encoding="utf-8")
        paths.append(path)
    return paths


def _db_patch() -> dict[str, object]:
    return {
        "production_db": {
            "engine": "postgresql",
            "migration_applied_at": "2026-05-01T10:05:00+08:00",
            "pitr_enabled": True,
            "backup_restore_drill_at": "2026-05-01T11:00:00+08:00",
            "evidence_refs": ["ops/db-migration-run-20260501"],
        }
    }


def _external_patch() -> dict[str, object]:
    return {
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
    }


def _long_run_patch() -> dict[str, object]:
    return {
        "productized_live_long_run": {
            "service_unit": "copilot-admin.service",
            "started_at": "2026-05-01T14:00:00+08:00",
            "evidence_window_hours": 24,
            "healthcheck_sample_count": 3,
            "oncall_owner": "chengjunhao",
            "rollback_drill_at": "2026-05-01T15:00:00+08:00",
            "evidence_refs": ["ops/long-run-window-20260501"],
        }
    }


if __name__ == "__main__":
    unittest.main()
