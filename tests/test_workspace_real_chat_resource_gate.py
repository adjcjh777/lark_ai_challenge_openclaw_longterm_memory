from __future__ import annotations

import unittest

from scripts.check_workspace_real_chat_resource_gate import build_real_chat_workspace_report


class WorkspaceRealChatResourceGateTest(unittest.TestCase):
    def test_report_passes_when_chat_and_workspace_sources_share_pipeline(self) -> None:
        report = build_real_chat_workspace_report(
            chat_result={
                "ok": True,
                "source": {"source_type": "feishu_message"},
                "candidate_count": 1,
                "duplicate_count": 0,
            },
            resource_results=[
                {
                    "source": {"source_type": "document_feishu"},
                    "candidate_count": 2,
                    "duplicate_count": 0,
                },
                {
                    "source": {"source_type": "lark_bitable"},
                    "candidate_count": 1,
                    "duplicate_count": 0,
                },
            ],
            failed_count=0,
            min_chat_candidates=1,
            min_resource_sources=1,
            min_resource_candidates=1,
            chat_source="event_log",
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(
            {"feishu_message": 1, "document_feishu": 1, "lark_bitable": 1},
            report["source_type_counts"],
        )

    def test_report_fails_without_chat_candidate_or_workspace_source(self) -> None:
        report = build_real_chat_workspace_report(
            chat_result={"ok": True, "source": {"source_type": "feishu_message"}, "candidate_count": 0},
            resource_results=[],
            failed_count=0,
            min_chat_candidates=1,
            min_resource_sources=1,
            min_resource_candidates=1,
            chat_source="event_log",
        )

        self.assertFalse(report["ok"])
        self.assertIn("min_chat_candidates", report["failures"])
        self.assertIn("min_resource_sources", report["failures"])
        self.assertIn("same_temp_db_has_chat_and_workspace_sources", report["failures"])


if __name__ == "__main__":
    unittest.main()
