from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.prepare_feishu_live_evidence_run import prepare_live_evidence_run


def _event_diagnostics(*, ok: bool = True, warnings: list[dict[str, str]] | None = None) -> dict[str, object]:
    warning_items = warnings or []
    return {
        "ok": ok,
        "failed_checks": [] if ok else ["message_event_registered"],
        "warnings": warning_items,
        "checks": {
            "event_status_readable": {"status": "pass"},
            "message_event_registered": {"status": "pass" if ok else "fail"},
        },
    }


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
                event_subscription_diagnostics=_event_diagnostics(),
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual("pass", result["checks"]["single_listener"]["status"])
        self.assertEqual("pass", result["checks"]["event_subscription"]["status"])
        self.assertEqual(["openclaw-gateway-unknown"], [item["kind"] for item in result["checks"]["single_listener"]["active"]])
        self.assertEqual([], result["blocking_failures"])

    def test_preflight_blocks_repo_lark_listener_when_openclaw_is_running(self) -> None:
        result = prepare_live_evidence_run(
            planned_listener="copilot-lark-cli",
            output_dir=Path("/tmp/feishu-live-preflight"),
            process_rows=["401 1 openclaw-gateway"],
            event_subscription_diagnostics=_event_diagnostics(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual("fail", result["checks"]["single_listener"]["status"])
        self.assertEqual(["single_listener"], result["blocking_failures"])

    def test_preflight_blocks_when_event_subscription_diagnostics_fail(self) -> None:
        result = prepare_live_evidence_run(
            planned_listener="openclaw-websocket",
            output_dir=Path("/tmp/feishu-live-preflight"),
            process_rows=[],
            event_subscription_diagnostics=_event_diagnostics(ok=False),
        )

        self.assertFalse(result["ok"])
        self.assertEqual("fail", result["checks"]["event_subscription"]["status"])
        self.assertEqual(["event_subscription"], result["blocking_failures"])

    def test_preflight_emits_packet_and_completion_commands_without_sending_messages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=Path(temp_dir),
                process_rows=[],
                event_subscription_diagnostics=_event_diagnostics(
                    warnings=[
                        {
                            "id": "message_schema_scope_does_not_list_group_msg_readonly",
                            "detail": "scope should be verified in Feishu console",
                        }
                    ]
                ),
            )

        instructions = "\n".join(step["instruction"] for step in result["manual_steps"])
        self.assertTrue(result["ok"], result)
        self.assertEqual("warning", result["checks"]["event_subscription"]["status"])
        self.assertIn("event_subscription", result["warnings"])
        self.assertIn("check_feishu_event_subscription_diagnostics.py", instructions)
        self.assertIn("collect_feishu_live_evidence_packet.py", instructions)
        self.assertIn("check_openclaw_feishu_productization_completion.py", instructions)
        self.assertIn("Save the listener/OpenClaw log", instructions)
        self.assertNotIn("lark-cli im +messages-send", instructions)
        self.assertNotIn("lark-cli event consume", instructions)
        self.assertIn("controlled_chat_id", result["warnings"])


if __name__ == "__main__":
    unittest.main()
