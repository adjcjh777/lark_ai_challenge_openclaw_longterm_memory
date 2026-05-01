from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.check_copilot_admin_idp_probe import run_idp_probe


class CopilotAdminIdpProbeTest(unittest.TestCase):
    def test_idp_probe_emits_manifest_patch_for_guarded_admin_url(self) -> None:
        result = run_idp_probe(
            base_url="https://memory.company.internal/admin/",
            provider="feishu_sso",
            login_tested_at="2026-05-01T12:00:00+08:00",
            admin_login_passed=True,
            viewer_export_denied=True,
            allowed_domains=["company.internal"],
            evidence_refs=["ops/idp-login-20260501", "ops/viewer-export-denial-20260501"],
            http_fetcher=lambda url, timeout: {
                "status": 302,
                "headers": {"Location": "https://sso.company.internal/login"},
                "body": "",
            },
            now=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"])
        patch = result["production_manifest_patch"]["enterprise_idp_sso"]
        self.assertEqual("feishu_sso", patch["provider"])
        self.assertTrue(patch["admin_login_passed"])
        self.assertTrue(patch["viewer_export_denied"])
        self.assertIn("idp_entrypoint_probe:memory.company.internal:", patch["evidence_refs"][-1])

    def test_idp_probe_rejects_placeholder_url_without_fetching(self) -> None:
        called = {"fetcher": False}

        def fetcher(url: str, timeout: float):
            called["fetcher"] = True
            return {"status": 401, "headers": {}, "body": ""}

        result = run_idp_probe(
            base_url="https://localhost:8765",
            provider="feishu_sso",
            login_tested_at="2026-05-01T12:00:00+08:00",
            admin_login_passed=True,
            viewer_export_denied=True,
            allowed_domains=["company.internal"],
            evidence_refs=["ops/idp-login-20260501"],
            http_fetcher=fetcher,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual(["admin_url"], result["failed_checks"])
        self.assertFalse(called["fetcher"])
        self.assertIn("host_is_not_placeholder", result["checks"]["admin_url"]["missing_or_placeholder"])

    def test_idp_probe_rejects_public_api_and_missing_external_evidence(self) -> None:
        result = run_idp_probe(
            base_url="https://memory.company.internal",
            provider="",
            login_tested_at="not-a-date",
            admin_login_passed=False,
            viewer_export_denied=False,
            allowed_domains=["example.com"],
            evidence_refs=["Bearer secret"],
            http_fetcher=lambda url, timeout: {"status": 200, "headers": {}, "body": "{\"ok\":true}"},
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("idp_evidence", result["failed_checks"])
        self.assertIn("unauthenticated_guard", result["failed_checks"])
        self.assertIn("not_publicly_readable", result["checks"]["unauthenticated_guard"]["missing_or_placeholder"])
        self.assertIn("provider_present", result["checks"]["idp_evidence"]["missing_or_placeholder"])
        self.assertIn("login_tested_at_is_iso", result["checks"]["idp_evidence"]["missing_or_placeholder"])
        self.assertIn("evidence_refs_present", result["checks"]["idp_evidence"]["missing_or_placeholder"])


if __name__ == "__main__":
    unittest.main()
