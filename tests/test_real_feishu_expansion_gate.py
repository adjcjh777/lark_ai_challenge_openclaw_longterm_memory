from __future__ import annotations

import unittest

from scripts.check_real_feishu_expansion_gate import evaluate_gate


class RealFeishuExpansionGateTest(unittest.TestCase):
    def test_gate_blocks_without_allowlist_reviewers_listener_and_resource(self) -> None:
        result = evaluate_gate(env={}, planned_listener="none")

        self.assertFalse(result["ok"])
        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            {
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS",
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS",
                "planned_listener",
                "controlled_resource",
            },
            set(result["blocked_checks"]),
        )
        self.assertEqual("environment values and resource ids are not printed", result["redaction_policy"])

    def test_gate_passes_with_controlled_task_resource(self) -> None:
        result = evaluate_gate(
            env={
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": "oc_controlled_group",
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "ou_reviewer",
            },
            planned_listener="copilot-lark-cli",
            task_id="task_controlled",
        )

        self.assertTrue(result["ok"])
        self.assertEqual("pass", result["status"])
        self.assertEqual([], result["blocked_checks"])

    def test_gate_requires_complete_bitable_resource_tuple(self) -> None:
        partial = evaluate_gate(
            env={
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": "oc_controlled_group",
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "ou_reviewer",
            },
            planned_listener="openclaw-websocket",
            bitable_app_token="app_controlled",
            bitable_table_id="tbl_controlled",
        )
        complete = evaluate_gate(
            env={
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": "oc_controlled_group",
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "ou_reviewer",
            },
            planned_listener="openclaw-websocket",
            bitable_app_token="app_controlled",
            bitable_table_id="tbl_controlled",
            bitable_record_id="rec_controlled",
        )

        self.assertFalse(partial["ok"])
        self.assertIn("controlled_resource", partial["blocked_checks"])
        self.assertTrue(complete["ok"])


if __name__ == "__main__":
    unittest.main()
