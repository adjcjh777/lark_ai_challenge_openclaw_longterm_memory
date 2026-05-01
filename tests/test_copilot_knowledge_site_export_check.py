from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from scripts.check_copilot_knowledge_site_export import (
    DEFAULT_SCOPE,
    run_knowledge_site_export_check,
)


class CopilotKnowledgeSiteExportCheckTest(unittest.TestCase):
    def test_default_check_exports_seeded_static_site(self) -> None:
        result = run_knowledge_site_export_check()

        self.assertTrue(result["ok"], result)
        self.assertEqual(DEFAULT_SCOPE, result["scope"])
        self.assertTrue(result["output_is_temporary"])
        self.assertEqual([], result["failed_checks"])
        self.assertTrue(all(check["status"] == "pass" for check in result["checks"].values()))
        self.assertTrue(result["manifest_summary"]["read_only"])
        self.assertGreaterEqual(result["manifest_summary"]["wiki_card_count"], 1)
        self.assertIn("no production deployment", result["manifest_summary"]["boundary"])

    def test_existing_empty_db_fails_wiki_and_manifest_checks(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_site_empty_", suffix=".sqlite") as db_tmp:
            conn = connect(db_tmp.name)
            try:
                init_db(conn)
            finally:
                conn.close()

            result = run_knowledge_site_export_check(db_path=Path(db_tmp.name), seed_demo_data=False)

        self.assertFalse(result["ok"], result)
        self.assertIn("manifest", result["failed_checks"])
        self.assertIn("wiki", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
