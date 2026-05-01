from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_feishu_live_evidence_run import prepare_live_evidence_run


def _event_diagnostics(
    *,
    ok: bool = True,
    warnings: list[dict[str, str]] | None = None,
    failed_checks: list[str] | None = None,
) -> dict[str, object]:
    warning_items = warnings or []
    failed = failed_checks if failed_checks is not None else ([] if ok else ["message_event_registered"])
    return {
        "ok": ok,
        "failed_checks": failed,
        "warnings": warning_items,
        "remediation": {
            "steps": [
                "Enable im:message.group_msg:readonly in Feishu console.",
                "Rerun diagnostics before sending another non-@ group test message.",
            ]
        },
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
        self.assertTrue(result["ready_to_capture_live_logs"])
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
        self.assertFalse(result["ready_to_capture_live_logs"])
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
        self.assertFalse(result["ready_to_capture_live_logs"])
        self.assertEqual("fail", result["checks"]["event_subscription"]["status"])
        self.assertEqual(["event_subscription"], result["blocking_failures"])
        self.assertIn("Enable im:message.group_msg:readonly", "\n".join(result["blocking_resolution_steps"]))

    def test_preflight_emits_packet_and_completion_commands_without_sending_messages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=Path(temp_dir),
                process_rows=[],
                event_subscription_diagnostics=_event_diagnostics(
                    ok=False,
                    failed_checks=["message_schema_group_message_scope"],
                    warnings=[
                        {
                            "id": "message_schema_scope_does_not_list_group_msg_readonly",
                            "detail": "scope should be verified in Feishu console",
                        }
                    ]
                ),
            )

        instructions = "\n".join(step["instruction"] for step in result["manual_steps"])
        self.assertFalse(result["ok"], result)
        self.assertFalse(result["ready_to_capture_live_logs"])
        self.assertEqual("fail", result["checks"]["event_subscription"]["status"])
        self.assertIn("event_subscription", result["blocking_failures"])
        self.assertIn("check_feishu_event_subscription_diagnostics.py", instructions)
        self.assertIn("--require-group-message-scope", instructions)
        self.assertIn("> ", instructions)
        self.assertIn("00-feishu-event-diagnostics.json", instructions)
        self.assertIn("collect_feishu_live_evidence_packet.py", instructions)
        self.assertIn("check_openclaw_feishu_productization_completion.py", instructions)
        self.assertIn("--feishu-event-diagnostics", instructions)
        packet_step = next(step for step in result["manual_steps"] if step["title"] == "Build sanitized Feishu live packet")
        self.assertIn("--feishu-event-diagnostics", packet_step["instruction"])
        live_steps = [
            step for step in result["manual_steps"] if step["phase"] in {"live_capture", "post_capture"}
        ]
        self.assertTrue(live_steps)
        self.assertTrue(all(step["requires_ready_to_capture_live_logs"] for step in live_steps))
        preflight_step = next(step for step in result["manual_steps"] if step["phase"] == "preflight")
        self.assertFalse(preflight_step["requires_ready_to_capture_live_logs"])
        self.assertIn("Save the listener/OpenClaw log", instructions)
        self.assertNotIn("lark-cli im +messages-send", instructions)
        self.assertNotIn("lark-cli event consume", instructions)
        self.assertIn("controlled_chat_id", result["warnings"])

    def test_preflight_can_include_cognee_sampler_status_in_completion_audit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            root = Path(temp_dir)
            sample_log = root / "embedding-samples.ndjson"
            pid_file = root / "sampler.pid"
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=root,
                process_rows=[],
                embedding_sample_log=sample_log,
                embedding_sampler_pid_file=pid_file,
                event_subscription_diagnostics=_event_diagnostics(),
            )

        instructions = "\n".join(step["instruction"] for step in result["manual_steps"])
        self.assertIn("check_cognee_embedding_sampler_status.py", instructions)
        self.assertIn(f"--embedding-sample-log {sample_log}", instructions)
        self.assertIn(f"--pid-file {pid_file}", instructions)
        self.assertIn("00-cognee-sampler-status.json", instructions)
        self.assertIn("--cognee-sampler-status", instructions)

    def test_create_dirs_writes_event_diagnostics_for_completion_audit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            root = Path(temp_dir)
            diagnostics = _event_diagnostics(
                ok=False,
                failed_checks=["message_schema_group_message_scope"],
            )
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=root,
                process_rows=[],
                create_dirs=True,
                event_subscription_diagnostics=diagnostics,
            )

            diagnostic_path = Path(result["diagnostic_paths"]["feishu_event_diagnostics"])
            written = json.loads(diagnostic_path.read_text(encoding="utf-8"))

        self.assertEqual(diagnostics, written)
        self.assertEqual(
            "pass",
            result["diagnostic_write_results"]["feishu_event_diagnostics"]["status"],
        )

    def test_create_dirs_writes_injected_cognee_sampler_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_preflight_") as temp_dir:
            root = Path(temp_dir)
            sample_log = root / "embedding-samples.ndjson"
            pid_file = root / "sampler.pid"
            sampler_status = {
                "ok": True,
                "completion_ready": False,
                "warning_checks": ["embedding_window"],
                "failed_checks": [],
            }
            result = prepare_live_evidence_run(
                planned_listener="openclaw-websocket",
                output_dir=root,
                process_rows=[],
                embedding_sample_log=sample_log,
                embedding_sampler_pid_file=pid_file,
                create_dirs=True,
                event_subscription_diagnostics=_event_diagnostics(),
                cognee_sampler_status=sampler_status,
            )

            diagnostic_path = Path(result["diagnostic_paths"]["cognee_sampler_status"])
            written = json.loads(diagnostic_path.read_text(encoding="utf-8"))

        self.assertEqual(sampler_status, written)
        self.assertEqual(
            "pass",
            result["diagnostic_write_results"]["cognee_sampler_status"]["status"],
        )


if __name__ == "__main__":
    unittest.main()
