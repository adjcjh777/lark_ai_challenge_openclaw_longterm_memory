from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.prepare_feishu_live_evidence_run import prepare_live_evidence_run


class PrepareFeishuLiveEvidenceRunTest(unittest.TestCase):
    def test_preflight_allows_generic_openclaw_when_openclaw_is_planned_owner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=Path(temp_dir),
                controlled_chat_id="oc_controlled",
                non_reviewer_open_id="ou_non_reviewer",
                reviewer_open_id="ou_reviewer",
                process_rows=["401 1 openclaw-gateway"],
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual("pass", result["checks"]["single_listener"]["status"])
        self.assertEqual(["openclaw-gateway-unknown"], [item["kind"] for item in result["checks"]["single_listener"]["active"]])
        self.assertEqual([], result["blocking_failures"])

    def test_preflight_blocks_repo_lark_listener_when_openclaw_is_running(self) -> None:
        result = prepare_live_evidence_run(
            planned_listener="copilot-lark-cli",
            output_dir=Path("/tmp/feishu-live-preflight"),
            process_rows=["401 1 openclaw-gateway"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual("fail", result["checks"]["single_listener"]["status"])
        self.assertEqual(["single_listener"], result["blocking_failures"])

    def test_preflight_emits_packet_and_completion_commands_without_sending_messages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=Path(temp_dir),
                process_rows=[],
            )

        instructions = "\n".join(step["instruction"] for step in result["manual_steps"])
        self.assertIn("collect_feishu_live_evidence_packet.py", instructions)
        self.assertIn("check_openclaw_feishu_productization_completion.py", instructions)
        self.assertIn("Save the listener/OpenClaw log", instructions)
        self.assertNotIn("lark-cli im +messages-send", instructions)
        self.assertIn("controlled_chat_id", result["warnings"])


if __name__ == "__main__":
    unittest.main()
