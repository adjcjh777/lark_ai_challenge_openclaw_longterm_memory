from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_openclaw_feishu_productization_completion import build_completion_audit
from scripts.collect_feishu_live_evidence_packet import collect_feishu_live_evidence_packet
from tests.test_openclaw_feishu_productization_completion import (
    _candidate_result,
    _card_update_result,
    _missing_token_result,
    _passive_message,
    _permission_denied_result,
    _review_dm_result,
    _routing_result,
    _write_json,
    _write_jsonl,
)


class FeishuLiveEvidencePacketTest(unittest.TestCase):
    def test_collects_sanitized_packet_for_all_feishu_live_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_packet_") as temp_dir:
            root = Path(temp_dir)
            passive_log, routing_log, permission_log, review_log = _write_passing_logs(root)

            packet = collect_feishu_live_evidence_packet(
                passive_event_log=passive_log,
                routing_event_log=routing_log,
                permission_event_log=permission_log,
                review_event_log=review_log,
                feishu_event_diagnostics=_write_json(
                    root / "feishu-event-diagnostics.json",
                    _missing_group_scope_diagnostics(),
                ),
            )

        self.assertTrue(packet["ok"], packet)
        self.assertEqual([], packet["failed_reports"])
        self.assertEqual("passive_group_message_seen", packet["reports"]["passive_group_message"]["reason"])
        self.assertEqual("first_class_live_routing_evidence_seen", packet["reports"]["first_class_routing"]["reason"])
        self.assertFalse(packet["diagnostics"]["event_subscription"]["message_event_schema"]["has_group_message_scope"])
        serialized = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("决定：非 @ 群消息进入 passive screening。", serialized)

    def test_completion_audit_accepts_packet_reports_for_feishu_items(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_packet_") as temp_dir:
            root = Path(temp_dir)
            passive_log, routing_log, permission_log, review_log = _write_passing_logs(root)
            packet = collect_feishu_live_evidence_packet(
                passive_event_log=passive_log,
                routing_event_log=routing_log,
                permission_event_log=permission_log,
                review_event_log=review_log,
            )
            packet_path = _write_json(root / "feishu-live-packet.json", packet)
            cognee_evidence = _write_json(
                root / "cognee-long-run.json",
                {
                    "cognee_sync": {"status": "pass"},
                    "persistence": {"store_reopened": True, "reopened_search_ok": True},
                    "embedding_service": {"window_hours": 24.5, "healthcheck_sample_count": 4},
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                feishu_live_evidence_packet=packet_path,
                cognee_long_run_evidence=cognee_evidence,
            )

        self.assertTrue(report["goal_complete"], report["blockers"])

    def test_packet_fails_when_one_source_log_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_packet_") as temp_dir:
            root = Path(temp_dir)
            passive_log, routing_log, permission_log, review_log = _write_passing_logs(root)

            packet = collect_feishu_live_evidence_packet(
                passive_event_log=passive_log,
                routing_event_log=routing_log,
                permission_event_log=permission_log,
                review_event_log=review_log.with_name("missing-review.ndjson"),
            )

        self.assertFalse(packet["ok"])
        self.assertEqual(["review_delivery"], packet["failed_reports"])
        self.assertEqual("evidence_log_missing", packet["reports"]["review_delivery"]["reason"])

    def test_packet_applies_chat_and_non_reviewer_filters(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_packet_") as temp_dir:
            root = Path(temp_dir)
            passive_log, routing_log, permission_log, review_log = _write_passing_logs(root)

            packet = collect_feishu_live_evidence_packet(
                passive_event_log=passive_log,
                routing_event_log=routing_log,
                permission_event_log=permission_log,
                review_event_log=review_log,
                expected_chat_id="oc_wrong_controlled_group",
                expected_non_reviewer_open_id="ou_wrong_user",
            )

        self.assertFalse(packet["ok"])
        self.assertEqual(["passive_group_message", "permission_negative"], packet["failed_reports"])
        self.assertEqual("expected_chat_not_seen", packet["reports"]["passive_group_message"]["reason"])
        self.assertEqual("expected_chat_not_seen", packet["reports"]["permission_negative"]["reason"])
        self.assertEqual(1, packet["reports"]["passive_group_message"]["summary"]["chat_mismatch"])
        self.assertEqual(1, packet["reports"]["permission_negative"]["summary"]["chat_mismatch"])

    def test_completion_audit_can_use_event_diagnostics_from_packet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu_live_packet_") as temp_dir:
            root = Path(temp_dir)
            packet_path = _write_json(
                root / "feishu-live-packet.json",
                {
                    "ok": False,
                    "reports": {},
                    "diagnostics": {"event_subscription": _missing_group_scope_diagnostics()},
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                feishu_live_evidence_packet=packet_path,
                cognee_long_run_evidence=None,
            )

        passive_item = next(entry for entry in report["items"] if entry["name"] == "non_at_group_message_live_delivery")
        self.assertEqual("message_schema_group_message_scope_missing", passive_item["reason"])
        self.assertTrue(
            passive_item["evidence"]["event_subscription_diagnostics"]["remediation"][
                "requires_external_console_change"
            ]
        )


def _write_passing_logs(root: Path) -> tuple[Path, Path, Path, Path]:
    passive_log = _write_jsonl(root / "passive.ndjson", [_passive_message()])
    permission_log = _write_jsonl(root / "permission.ndjson", [_permission_denied_result()])
    review_log = _write_jsonl(
        root / "review.ndjson",
        [_candidate_result(), _review_dm_result(), _card_update_result(), _missing_token_result()],
    )
    routing_log = _write_jsonl(
        root / "routing.ndjson",
        [_routing_result(tool) for tool in ("fmc_memory_search", "fmc_memory_create_candidate", "fmc_memory_prefetch")],
    )
    return passive_log, routing_log, permission_log, review_log


def _missing_group_scope_diagnostics() -> dict[str, object]:
    return {
        "ok": False,
        "failed_checks": ["message_schema_group_message_scope"],
        "message_event_schema": {
            "scopes": ["im:message.p2p_msg:readonly"],
            "has_group_message_scope": False,
        },
        "remediation": {
            "requires_external_console_change": True,
            "required_scopes_any_of": ["im:message.group_msg:readonly"],
        },
    }


if __name__ == "__main__":
    unittest.main()
