from __future__ import annotations

import json
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
        self.assertIn("im:message.group_msg:readonly", item["next_step"])
        passive_item = next(entry for entry in report["items"] if entry["name"] == "non_at_group_message_live_delivery")
        diagnostic_evidence = passive_item["evidence"]["event_subscription_diagnostics"]
        self.assertEqual(["im:message.p2p_msg:readonly"], diagnostic_evidence["scopes"])

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
                [_routing_result(tool) for tool in ("fmc_memory_search", "fmc_memory_create_candidate", "fmc_memory_prefetch")],
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
