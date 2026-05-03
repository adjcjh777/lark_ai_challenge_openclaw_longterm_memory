from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_openclaw_feishu_productization_completion import build_completion_audit


class OpenClawFeishuProductizationCompletionTest(unittest.TestCase):
    def test_audit_defaults_to_incomplete_when_live_evidence_is_missing(self) -> None:
        report = build_completion_audit(
            passive_event_log=None,
            permission_event_log=None,
            review_event_log=None,
            routing_event_log=None,
            cognee_long_run_evidence=None,
        )

        self.assertFalse(report["goal_complete"])
        blockers = {item["name"]: item["reason"] for item in report["blockers"]}
        self.assertEqual("evidence_log_not_configured", blockers["non_at_group_message_live_delivery"])
        self.assertEqual("evidence_log_not_configured", blockers["first_class_memory_tool_live_routing"])
        self.assertEqual("evidence_log_not_configured", blockers["live_negative_permission_second_user"])
        self.assertEqual("evidence_log_not_configured", blockers["review_dm_card_e2e"])
        self.assertEqual("long_term_cognee_embedding_evidence_missing", blockers["cognee_embedding_long_term_service"])
        self.assertIn("prepare_feishu_live_evidence_run.py", report["next_step"])
        self.assertIn("prepare_feishu_live_evidence_run.py", report["next_evidence_run"]["preflight_command"])
        self.assertIn("--skip-event-diagnostics", report["next_evidence_run"]["offline_checklist_command"])
        self.assertIn("collect_feishu_live_evidence_packet.py", report["next_evidence_run"]["packet_collector_command"])
        self.assertIn("--feishu-event-diagnostics", report["next_evidence_run"]["packet_collector_command"])
        self.assertIn("--output <feishu-live-evidence-packet.json>", report["next_evidence_run"]["packet_collector_command"])
        self.assertIn("--expected-chat-id", report["next_evidence_run"]["packet_collector_command"])
        self.assertIn("check_openclaw_feishu_productization_completion.py", report["next_evidence_run"]["completion_audit_command"])
        self.assertIn("--output <completion-audit.json>", report["next_evidence_run"]["completion_audit_command"])

    def test_cli_output_writes_json_even_when_incomplete(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            output = root / "completion-audit.json"
            missing_log = root / "missing.ndjson"

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/check_openclaw_feishu_productization_completion.py",
                    "--passive-event-log",
                    str(missing_log),
                    "--permission-event-log",
                    str(missing_log),
                    "--review-event-log",
                    str(missing_log),
                    "--routing-event-log",
                    str(missing_log),
                    "--output",
                    str(output),
                    "--json",
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(1, completed.returncode)
        self.assertFalse(payload["goal_complete"])
        self.assertIn("next_evidence_run", payload)
        self.assertIn("prepare_feishu_live_evidence_run.py", payload["next_step"])
        self.assertIn("completion_audit_command", payload["next_evidence_run"])

    def test_audit_uses_event_diagnostics_for_passive_group_scope_blocker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            diagnostics = _write_json(
                root / "feishu-event-diagnostics.json",
                {
                    "ok": False,
                    "failed_checks": ["message_schema_group_message_scope"],
                    "message_event_schema": {
                        "scopes": ["im:message.p2p_msg:readonly"],
                        "has_group_message_scope": False,
                    },
                    "target_group_probe": {
                        "ok": False,
                        "error_code": 230027,
                        "target_chat_id": "oc_t...chat",
                    },
                    "remediation": {
                        "requires_external_console_change": True,
                        "required_scopes_any_of": ["im:message.group_msg", "im:message.group_msg:readonly"],
                    },
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                feishu_event_diagnostics=diagnostics,
                cognee_long_run_evidence=None,
            )

        blockers = {item["name"]: item for item in report["blockers"]}
        item = blockers["non_at_group_message_live_delivery"]
        self.assertEqual("message_schema_group_message_scope_missing", item["reason"])
        self.assertIn("im:message.group_msg", item["next_step"])
        passive_item = next(entry for entry in report["items"] if entry["name"] == "non_at_group_message_live_delivery")
        diagnostic_evidence = passive_item["evidence"]["event_subscription_diagnostics"]
        self.assertEqual(["im:message.p2p_msg:readonly"], diagnostic_evidence["scopes"])
        self.assertEqual(230027, diagnostic_evidence["target_group_probe"]["error_code"])
        self.assertTrue(diagnostic_evidence["remediation"]["requires_external_console_change"])

    def test_audit_fails_single_listener_when_event_diagnostics_show_conflict(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            diagnostics = _write_json(
                root / "feishu-event-diagnostics.json",
                {
                    "ok": False,
                    "planned_listener": "openclaw-websocket",
                    "failed_checks": ["listener_mode_consistent"],
                    "checks": {"listener_mode_consistent": {"status": "fail"}},
                    "event_status": {
                        "active_bus_count": 1,
                        "active_bus_app_ids": ["cli_...1234"],
                    },
                    "message_event_schema": {"has_group_message_scope": True},
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                feishu_event_diagnostics=diagnostics,
                cognee_long_run_evidence=None,
            )

        blockers = {item["name"]: item for item in report["blockers"]}
        self.assertEqual("listener_conflict_detected", blockers["single_feishu_listener_entry"]["reason"])
        single_listener_item = next(
            entry for entry in report["items"] if entry["name"] == "single_feishu_listener_entry"
        )
        diagnostic_evidence = single_listener_item["evidence"]["event_subscription_diagnostics"]
        self.assertEqual(1, diagnostic_evidence["active_bus_count"])
        self.assertTrue(diagnostic_evidence["listener_conflict_detected"])

    def test_audit_fails_single_listener_when_openclaw_group_policy_dispatches_generic_agent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            diagnostics = _write_json(
                root / "feishu-event-diagnostics.json",
                {
                    "ok": False,
                    "planned_listener": "openclaw-websocket",
                    "failed_checks": ["openclaw_feishu_group_policy_safe"],
                    "checks": {
                        "listener_mode_consistent": {"status": "pass"},
                        "openclaw_feishu_group_policy_safe": {"status": "fail"},
                    },
                    "event_status": {"active_bus_count": 0, "active_bus_app_ids": []},
                    "openclaw_feishu_policy": {
                        "status": "fail",
                        "groupPolicy": "open",
                        "requireMention": None,
                    },
                    "message_event_schema": {"has_group_message_scope": True},
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                feishu_event_diagnostics=diagnostics,
                cognee_long_run_evidence=None,
            )

        blockers = {item["name"]: item for item in report["blockers"]}
        self.assertEqual(
            "openclaw_group_policy_dispatches_generic_agent",
            blockers["single_feishu_listener_entry"]["reason"],
        )
        single_listener_item = next(
            entry for entry in report["items"] if entry["name"] == "single_feishu_listener_entry"
        )
        diagnostic_evidence = single_listener_item["evidence"]["event_subscription_diagnostics"]
        self.assertTrue(diagnostic_evidence["openclaw_group_policy_unsafe"])
        self.assertEqual("open", diagnostic_evidence["openclaw_group_policy"])

    def test_audit_uses_sampler_status_for_cognee_progress_blocker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            sampler_status = _write_json(
                root / "cognee-sampler-status.json",
                {
                    "ok": True,
                    "completion_ready": False,
                    "sample_count": 1,
                    "successful_sample_count": 1,
                    "embedding_window_hours": 0.0,
                    "estimated_ready_at": "2026-05-02T16:50:51+00:00",
                    "next_expected_sample_at": "2026-05-02T04:50:51+00:00",
                    "final_scheduled_sample_at": "2026-05-02T16:50:51+00:00",
                    "failed_checks": [],
                    "warning_checks": ["embedding_successful_samples", "embedding_window"],
                    "next_step": "Leave the sampler running until it collects more successful samples.",
                    "collector_command_template": "python3 scripts/collect_cognee_embedding_long_run_evidence.py --embedding-sample-log samples.ndjson",
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                cognee_sampler_status=sampler_status,
            )

        blockers = {item["name"]: item for item in report["blockers"]}
        item = blockers["cognee_embedding_long_term_service"]
        self.assertEqual("cognee_sampler_running_but_window_incomplete", item["reason"])
        self.assertIn("Leave the sampler running", item["next_step"])
        cognee_item = next(entry for entry in report["items"] if entry["name"] == "cognee_embedding_long_term_service")
        sampler_evidence = cognee_item["evidence"]["sampler_status"]
        self.assertEqual(1, sampler_evidence["successful_sample_count"])
        self.assertEqual("2026-05-02T16:50:51+00:00", sampler_evidence["estimated_ready_at"])
        self.assertEqual("2026-05-02T04:50:51+00:00", sampler_evidence["next_expected_sample_at"])
        self.assertEqual("2026-05-02T16:50:51+00:00", sampler_evidence["final_scheduled_sample_at"])
        self.assertIn("collect_cognee_embedding_long_run_evidence.py", sampler_evidence["collector_command_template"])

    def test_audit_uses_sampler_collector_command_when_sampler_ready(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            sampler_status = _write_json(
                root / "cognee-sampler-status.json",
                {
                    "ok": True,
                    "completion_ready": True,
                    "sample_count": 3,
                    "successful_sample_count": 3,
                    "embedding_window_hours": 24.5,
                    "failed_checks": [],
                    "warning_checks": [],
                    "collector_command_template": "python3 scripts/collect_cognee_embedding_long_run_evidence.py --embedding-sample-log samples.ndjson",
                },
            )

            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                cognee_sampler_status=sampler_status,
            )

        blockers = {item["name"]: item for item in report["blockers"]}
        item = blockers["cognee_embedding_long_term_service"]
        self.assertEqual("cognee_sampler_ready_but_long_run_evidence_missing", item["reason"])
        self.assertIn("collect_cognee_embedding_long_run_evidence.py", item["next_step"])

    def test_audit_fails_closed_for_unreadable_sampler_status_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            report = build_completion_audit(
                passive_event_log=None,
                permission_event_log=None,
                review_event_log=None,
                routing_event_log=None,
                cognee_sampler_status=root,
            )

        blockers = {item["name"]: item for item in report["blockers"]}
        self.assertEqual("cognee_sampler_status_failed", blockers["cognee_embedding_long_term_service"]["reason"])

    def test_audit_can_pass_when_all_live_and_long_run_evidence_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_completion_audit_") as temp_dir:
            root = Path(temp_dir)
            passive_log = _write_jsonl(root / "passive.ndjson", [_passive_message()])
            permission_log = _write_jsonl(root / "permission.ndjson", [_permission_denied_result()])
            review_log = _write_jsonl(
                root / "review.ndjson",
                [_candidate_result(), _review_dm_result(), _card_update_result(), _missing_token_result()],
            )
            routing_log = _write_jsonl(
                root / "routing.ndjson",
                [
                    _routing_result(tool)
                    for tool in ("fmc_memory_search", "fmc_memory_create_candidate", "fmc_memory_prefetch")
                ],
            )
            cognee_evidence = _write_json(
                root / "cognee-long-run.json",
                {
                    "cognee_sync": {"status": "pass"},
                    "persistence": {"store_reopened": True, "reopened_search_ok": True},
                    "embedding_service": {"window_hours": 24.5, "healthcheck_sample_count": 4},
                },
            )

            report = build_completion_audit(
                passive_event_log=passive_log,
                permission_event_log=permission_log,
                review_event_log=review_log,
                routing_event_log=routing_log,
                cognee_long_run_evidence=cognee_evidence,
            )

        self.assertTrue(report["goal_complete"], report["blockers"])
        self.assertEqual([], report["blockers"])
        self.assertTrue(all(item["status"] == "pass" for item in report["items"]))


def _write_jsonl(path: Path, payloads: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(payload, ensure_ascii=False) for payload in payloads), encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _passive_message() -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_passive_sender"}, "sender_type": "user"},
            "message": {
                "message_id": "om_passive_message",
                "chat_id": "oc_passive_gate",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "决定：非 @ 群消息进入 passive screening。"}, ensure_ascii=False),
                "mentions": [],
                "create_time": "1777647600000",
            },
        },
    }


def _permission_denied_result() -> dict:
    return {
        "type": "copilot_live_event_result",
        "result": {
            "ok": False,
            "message_id": "om_denied_enable_memory",
            "tool": "copilot.group_enable_memory",
            "routing_reason": "explicit_group_memory_enable",
            "tool_result": {
                "ok": False,
                "tool": "copilot.group_enable_memory",
                "status": "permission_denied",
                "error": {"code": "permission_denied", "reason_code": "reviewer_or_admin_required"},
                "actor_id": "ou_non_reviewer",
                "group_policy": {"chat_id": "oc_permission_negative_gate", "status": "pending_onboarding"},
            },
            "publish": {"ok": True, "mode": "interactive", "chat_id": "oc_permission_negative_gate"},
        },
    }


def _candidate_result() -> dict:
    return {
        "result": {
            "ok": True,
            "message_id": "om_review_candidate",
            "tool": "memory.create_candidate",
            "publish": {
                "mode": "reply_card",
                "card": {
                    "elements": [
                        {
                            "tag": "action",
                            "actions": [
                                {
                                    "tag": "button",
                                    "text": {"tag": "plain_text", "content": "确认保存"},
                                    "value": {"memory_engine_action": "confirm", "candidate_id": "ver_review"},
                                }
                            ],
                        }
                    ]
                },
            },
        }
    }


def _review_dm_result() -> dict:
    return {
        "result": {
            "ok": True,
            "message_id": "om_review_inbox",
            "tool": "memory.review_inbox",
            "publish": {
                "mode": "interactive",
                "delivery_mode": "dm",
                "targets": ["ou_review_owner"],
                "card": {"open_ids": ["ou_review_owner"], "elements": []},
            },
        }
    }


def _card_update_result() -> dict:
    return {
        "result": {
            "ok": True,
            "message_id": "card_action_confirm",
            "tool": "memory.confirm",
            "publish": {"mode": "update_card", "card_update_token": "card_token_review", "card": {"elements": []}},
        }
    }


def _missing_token_result() -> dict:
    return {
        "result": {
            "ignored": True,
            "reason": "card action update token missing",
            "message_id": "card_action_missing",
            "tool": "memory.confirm",
            "publish": {"mode": "card_action_update_token_missing"},
        }
    }


def _routing_result(tool: str) -> dict:
    return {
        "event": "copilot_live_event_result",
        "result": {
            "ok": True,
            "message_id": f"om_{tool}",
            "tool": tool.replace("fmc_memory_", "memory.").replace("fmc_heartbeat_", "heartbeat."),
            "bridge": {
                "entrypoint": "openclaw_tool",
                "tool": tool,
                "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
                "request_id": f"req_{tool}",
                "trace_id": f"trace_{tool}",
            },
            "publish": {"mode": "reply_text"},
        },
    }


if __name__ == "__main__":
    unittest.main()
