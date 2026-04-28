from __future__ import annotations

import unittest

from memory_engine.copilot.healthcheck import run_copilot_healthcheck


class CopilotHealthcheckTest(unittest.TestCase):
    def test_healthcheck_reports_versions_and_non_live_provider_statuses(self) -> None:
        report = run_copilot_healthcheck(openclaw_version_reader=lambda: ("2026.4.24", "2026.4.24"))

        self.assertTrue(report["ok"])
        self.assertEqual("Phase 6 Deployability + Healthcheck", report["phase"])
        self.assertIn(report["checks"]["openclaw_version"]["status"], {"pass"})
        self.assertEqual("2026.4.24", report["checks"]["openclaw_version"]["locked_version"])
        self.assertEqual("2026.4.24", report["checks"]["openclaw_version"]["local_version"])
        self.assertEqual("2026-05-07", report["checks"]["openclaw_schema"]["schema_version"])
        self.assertEqual("2026.4.24", report["checks"]["openclaw_schema"]["openclaw_version"])
        self.assertIn("memory.search", report["checks"]["openclaw_schema"]["tools"])
        self.assertIn(report["checks"]["cognee_adapter"]["status"], {"pass", "fallback_used", "not_configured"})
        self.assertTrue(report["checks"]["cognee_adapter"]["fallback_available"])
        self.assertIn(report["checks"]["embedding_provider"]["status"], {"pass", "warning", "not_configured", "fallback_used"})
        self.assertEqual("configuration_only", report["checks"]["embedding_provider"]["check_mode"])
        self.assertIn("status_counts", report)

    def test_healthcheck_storage_schema_is_checkable_without_claiming_migration(self) -> None:
        report = run_copilot_healthcheck(openclaw_version_reader=lambda: ("2026.4.24", "2026.4.24"))
        storage = report["checks"]["storage_schema"]

        self.assertIn(storage["status"], {"pass", "warning"})
        self.assertEqual("legacy_scope_v1", storage["schema_version"])
        self.assertTrue(storage["schema_checkable"])
        self.assertFalse(storage["tenant_visibility_columns"])
        self.assertFalse(storage["audit_table_available"])
        self.assertIn("not a full audit migration", storage["boundary"])

    def test_healthcheck_smoke_covers_search_permission_deny_and_candidate_review(self) -> None:
        report = run_copilot_healthcheck(openclaw_version_reader=lambda: ("2026.4.24", "2026.4.24"))
        smoke = report["checks"]["smoke_tests"]

        self.assertEqual("pass", smoke["status"])
        self.assertEqual("pass", smoke["search"]["status"])
        self.assertEqual("pass", smoke["permission_deny"]["status"])
        self.assertEqual("permission_denied", smoke["permission_deny"]["error_code"])
        self.assertEqual("missing_permission_context", smoke["permission_deny"]["missing_reason_code"])
        self.assertEqual("malformed_permission_context", smoke["permission_deny"]["malformed_reason_code"])
        self.assertEqual("req_health_bad", smoke["permission_deny"]["request_id"])
        self.assertEqual("trace_health_bad", smoke["permission_deny"]["trace_id"])
        self.assertEqual("pass", smoke["candidate_review"]["status"])
        self.assertEqual("handle_tool_request", smoke["candidate_review"]["entrypoint"])
        self.assertEqual("candidate", smoke["candidate_review"]["created_status"])
        self.assertEqual("active", smoke["candidate_review"]["confirmed_status"])

    def test_healthcheck_marks_openclaw_mismatch_as_fail(self) -> None:
        report = run_copilot_healthcheck(openclaw_version_reader=lambda: ("2026.4.24", "2026.4.25"))

        self.assertFalse(report["ok"])
        self.assertEqual("fail", report["checks"]["openclaw_version"]["status"])
        self.assertEqual(1, report["status_counts"]["fail"])


if __name__ == "__main__":
    unittest.main()
