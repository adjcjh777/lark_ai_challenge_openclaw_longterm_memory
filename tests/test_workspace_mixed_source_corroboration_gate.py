from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from scripts.check_workspace_mixed_source_corroboration_gate import build_report


class WorkspaceMixedSourceCorroborationGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.conn = connect(Path(self.temp_dir.name) / "memory.sqlite")
        self.addCleanup(self.conn.close)
        init_db(self.conn)

    def test_gate_proves_chat_document_corroboration_and_bitable_conflict(self) -> None:
        report = build_report(self.conn)

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual([], report["failures"])
        self.assertEqual(
            ["document_feishu", "feishu_message"],
            report["evidence"]["active_evidence_source_types"],
        )
        self.assertEqual(["lark_bitable"], report["evidence"]["conflict_evidence_source_types"])
        self.assertEqual({"active": 1, "candidate": 1}, report["evidence"]["version_status_counts"])
        self.assertEqual("duplicate", report["actions"]["document_duplicate"]["action"])
        self.assertEqual("candidate_conflict", report["actions"]["bitable_conflict"]["action"])


if __name__ == "__main__":
    unittest.main()
