from __future__ import annotations

import unittest

from scripts.check_feishu_review_delivery_gate import check_review_delivery_gate


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


if __name__ == "__main__":
    unittest.main()
