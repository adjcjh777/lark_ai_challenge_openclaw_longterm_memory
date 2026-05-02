from __future__ import annotations

import json
import unittest

from scripts.check_feishu_review_delivery_gate import check_review_delivery_gate, check_review_delivery_log_events


def _candidate_result() -> dict:
    return {
        "event": "copilot_live_event_result",
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
        },
    }


def _review_dm_result(target: str = "ou_review_owner") -> dict:
    return {
        "result": {
            "ok": True,
            "message_id": "om_review_inbox",
            "tool": "memory.review_inbox",
            "publish": {
                "mode": "interactive",
                "delivery_mode": "dm",
                "targets": [target],
                "card": {"open_ids": [target], "elements": []},
            },
        }
    }


def _card_update_result() -> dict:
    return {
        "result": {
            "ok": True,
            "message_id": "card_action_confirm",
            "tool": "memory.confirm",
            "publish": {
                "mode": "update_card",
                "card_update_token": "card_token_review",
                "card": {"elements": []},
            },
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


class FeishuReviewDeliveryGateTest(unittest.TestCase):
    def test_review_delivery_gate_passes_local_private_card_and_update_flow(self) -> None:
        report = check_review_delivery_gate()

        self.assertTrue(report["ok"], report)
        self.assertEqual("feishu_review_delivery_gate", report["gate"])
        self.assertIn("not prove production", report["boundary"])
        self.assertEqual(
            [
                "candidate_created",
                "review_inbox_private_dm_targeted",
                "card_action_updates_original_card",
                "missing_card_token_does_not_mutate",
            ],
            [check["name"] for check in report["checks"]],
        )
        self.assertTrue(all(check["status"] == "pass" for check in report["checks"]))

    def test_log_gate_passes_with_review_dm_click_and_missing_token_evidence(self) -> None:
        text = "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in [_candidate_result(), _review_dm_result(), _card_update_result(), _missing_token_result()]
        )

        report = check_review_delivery_log_events(text)

        self.assertTrue(report["ok"], report)
        self.assertEqual("review_delivery_e2e_evidence_seen", report["reason"])
        self.assertEqual(1, report["summary"]["candidate_review_cards"])
        self.assertEqual(1, report["summary"]["private_review_dm_results"])
        self.assertEqual(1, report["summary"]["card_action_update_results"])
        self.assertEqual(1, report["summary"]["missing_token_fail_closed_results"])

    def test_log_gate_filters_expected_reviewer_dm_target(self) -> None:
        text = "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in [
                _candidate_result(),
                _review_dm_result(target="ou_other_reviewer"),
                _card_update_result(),
                _missing_token_result(),
            ]
        )

        report = check_review_delivery_log_events(text, expected_reviewer_open_id="ou_review_owner")

        self.assertFalse(report["ok"])
        self.assertEqual("private_review_dm_target_mismatch", report["reason"])
        self.assertEqual(0, report["summary"]["private_review_dm_results"])
        self.assertEqual(1, report["summary"]["private_review_target_mismatch"])

    def test_log_gate_fails_when_only_candidate_card_is_seen(self) -> None:
        report = check_review_delivery_log_events(json.dumps(_candidate_result(), ensure_ascii=False))

        self.assertFalse(report["ok"])
        self.assertEqual("candidate_card_only_no_private_review_dm", report["reason"])
        self.assertEqual(
            [
                "private_review_dm_seen",
                "card_action_updates_original_card_seen",
                "missing_card_token_fail_closed_seen",
            ],
            report["failures"],
        )

    def test_log_gate_reads_copilot_raw_line_wrappers(self) -> None:
        wrapped = {
            "ts": "2026-05-01T10:00:00+08:00",
            "event": "copilot_live_event_result",
            "raw_line": json.dumps(_candidate_result(), ensure_ascii=False),
        }

        report = check_review_delivery_log_events(json.dumps(wrapped, ensure_ascii=False))

        self.assertFalse(report["ok"])
        self.assertEqual(1, report["summary"]["candidate_review_cards"])

    def test_log_gate_reads_numbered_openclaw_file_log_fields(self) -> None:
        text = "\n".join(
            json.dumps(
                {
                    "0": "2026-05-02T12:00:00+08:00 info",
                    "1": f"feishu[default]: review result {json.dumps(item, ensure_ascii=False)}",
                    "_meta": {"date": "2026-05-02T04:00:00Z"},
                },
                ensure_ascii=False,
            )
            for item in [_candidate_result(), _review_dm_result(), _card_update_result(), _missing_token_result()]
        )

        report = check_review_delivery_log_events(text)

        self.assertTrue(report["ok"], report)
        self.assertEqual("review_delivery_e2e_evidence_seen", report["reason"])
        self.assertEqual(1, report["summary"]["private_review_dm_results"])
        self.assertEqual(1, report["summary"]["card_action_update_results"])


if __name__ == "__main__":
    unittest.main()
