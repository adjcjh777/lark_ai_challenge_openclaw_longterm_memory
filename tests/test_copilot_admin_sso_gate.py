from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_engine.db import init_db
from scripts.check_copilot_admin_sso_gate import BOUNDARY, DEFAULT_SCOPE, run_sso_gate_check


class CopilotAdminSsoGateTest(unittest.TestCase):
    def test_default_sso_gate_verifier_uses_seeded_loopback_server(self) -> None:
        result = run_sso_gate_check()

        self.assertTrue(result["ok"], result)
        self.assertEqual(BOUNDARY, result["boundary"])
        self.assertEqual("loopback_only", result["server"]["bind_scope"])
        self.assertEqual(DEFAULT_SCOPE, result["preflight"]["scope"])
        self.assertGreaterEqual(result["preflight"]["wiki_card_count"], 1)
        self.assertEqual([], result["failed_checks"])
        self.assertEqual(
            {
                "wiki_card_preflight",
                "no_header_denied",
                "viewer_summary_allowed",
                "viewer_export_forbidden",
                "admin_export_allowed",
                "metrics_requires_authenticated_identity",
                "viewer_metrics_allowed",
                "health_reports_sso_policy",
            },
            set(result["checks"]),
        )
        self.assertTrue(all(check["status"] == "pass" for check in result["checks"].values()))

    def test_existing_empty_db_fails_without_seeded_wiki_card(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_admin_sso_empty_", suffix=".sqlite") as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                init_db(conn)
            finally:
                conn.close()

            result = run_sso_gate_check(db_path=Path(tmp.name), seed_demo_data=False)

        self.assertFalse(result["ok"], result)
        self.assertEqual(0, result["preflight"]["wiki_card_count"])
        self.assertIn("wiki_card_preflight", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
