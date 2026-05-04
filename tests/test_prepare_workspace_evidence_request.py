from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_workspace_evidence_request import prepare_workspace_evidence_request


class PrepareWorkspaceEvidenceRequestTest(unittest.TestCase):
    def test_packet_contains_redacted_commands_and_boundaries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_evidence_request_") as temp_dir:
            packet = prepare_workspace_evidence_request(
                output_dir=Path(temp_dir),
                create_dirs=False,
            )

        self.assertTrue(packet["ok"])
        self.assertEqual("ready_to_request_samples", packet["status"])
        self.assertIn("no Feishu API calls", packet["boundary"])
        self.assertIn("project_or_enterprise_normal_sheet", [item["id"] for item in packet["required_inputs"]])
        self.assertIn("check_workspace_project_sheet_evidence_gate.py", packet["commands"]["project_normal_sheet_explicit"])
        self.assertIn("--folder-walk-tokens '<folder_token>'", packet["commands"]["project_normal_sheet_folder_or_wiki"])
        self.assertIn("check_workspace_real_same_conclusion_sample_finder.py", packet["commands"]["same_fact_sample_finder"])
        self.assertIn("check_workspace_ingestion_goal_readiness.py", packet["commands"]["final_readiness"])
        self.assertIn("Workspace ingestion readiness gate", packet["sample_durable_fact"])
        self.assertIn("决定：", packet["sample_durable_fact"])
        for command in packet["commands"].values():
            self.assertNotIn("\n+  ", command)
        self.assertNotIn("appSecret", json.dumps(packet))
        self.assertNotIn("accessToken", json.dumps(packet))

    def test_create_dirs_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_evidence_request_") as temp_dir:
            root = Path(temp_dir)
            packet = prepare_workspace_evidence_request(
                output_dir=root,
                create_dirs=True,
                sheet_token_placeholder="<sheet_token_for_owner>",
            )

            packet_json = Path(packet["paths"]["packet_json"])
            markdown = Path(packet["paths"]["operator_markdown"])

            self.assertTrue(packet_json.exists())
            self.assertTrue(markdown.exists())
            loaded = json.loads(packet_json.read_text(encoding="utf-8"))
            markdown_text = markdown.read_text(encoding="utf-8")
            self.assertEqual(packet["run_id"], loaded["run_id"])
            self.assertIn("<sheet_token_for_owner>", markdown_text)
            self.assertIn(packet["sample_durable_fact"], markdown_text)


if __name__ == "__main__":
    unittest.main()
