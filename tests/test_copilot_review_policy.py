from __future__ import annotations

import unittest

from memory_engine.copilot.review_policy import evaluate_review_policy


class CopilotReviewPolicyTest(unittest.TestCase):
    def test_low_importance_auto_confirm_for_safe_non_feishu_source(self) -> None:
        policy = evaluate_review_policy(
            candidate={"text": "这周站会提到可以把按钮文案微调一下。", "importance_level": "low"},
            risk_flags=[],
            conflict={"has_conflict": False},
            source={"source_type": "unit_test", "actor_id": "ou_member"},
            current_context={"scope": "project:feishu_ai_challenge"},
        )

        self.assertEqual("auto_confirm", policy["decision"])
        self.assertEqual("low", policy["importance_level"])
        self.assertEqual("none", policy["delivery_channel"])
        self.assertEqual([], policy["review_targets"])
        self.assertIn("low_importance", policy["reasons"])

    def test_conflict_requires_human_review(self) -> None:
        policy = evaluate_review_policy(
            candidate={"text": "不对，上线窗口改到周五。"},
            risk_flags=[],
            conflict={"has_conflict": True, "memory_id": "mem_123"},
            source={"source_type": "unit_test", "actor_id": "ou_editor"},
            current_context={"scope": "project:feishu_ai_challenge"},
        )

        self.assertEqual("human_review", policy["decision"])
        self.assertEqual("high", policy["importance_level"])
        self.assertEqual("routed_private_review", policy["delivery_channel"])
        self.assertIn("conflict_update", policy["reasons"])

    def test_important_actor_from_real_feishu_routes_private_review(self) -> None:
        policy = evaluate_review_policy(
            candidate={"text": "负责人：Alice 负责生产上线，截止周五。"},
            risk_flags=[],
            conflict={"has_conflict": False},
            source={"source_type": "feishu_message", "actor_id": "ou_owner"},
            actor={"open_id": "ou_owner", "roles": ["owner"]},
            current_context={
                "scope": "project:feishu_ai_challenge",
                "permission": {
                    "reviewers": ["ou_reviewer_a"],
                    "reviewer_open_ids": ["ou_reviewer_b"],
                    "reviewer_user_ids": ["user_reviewer_c"],
                },
            },
        )

        self.assertEqual("human_review", policy["decision"])
        self.assertEqual("routed_private_review", policy["delivery_channel"])
        self.assertEqual("project", policy["visibility_label"])
        self.assertIn("important_actor", policy["reasons"])
        self.assertIn("real_feishu_source_private_review", policy["reasons"])
        self.assertEqual(
            ["ou_owner", "ou_reviewer_a", "ou_reviewer_b", "user_reviewer_c"],
            policy["review_targets"],
        )

    def test_sensitive_flags_block_auto_confirm(self) -> None:
        policy = evaluate_review_policy(
            candidate={"text": "客户合同金额和个人手机号要记录下来。", "importance_level": "low"},
            risk_flags=["personal_data", "contract_sensitive"],
            conflict={"has_conflict": False},
            source={"source_type": "unit_test", "actor_id": "ou_member"},
            current_context={"scope": "project:feishu_ai_challenge"},
        )

        self.assertEqual("human_review", policy["decision"])
        self.assertEqual("high", policy["importance_level"])
        self.assertIn("sensitive_risk", policy["reasons"])
        self.assertNotEqual("auto_confirm", policy["decision"])

    def test_visibility_label_team_private_project(self) -> None:
        cases = [
            ({"permission": {"requested_visibility": "team"}}, "team"),
            ({"permission": {"requested_visibility": "private"}}, "private"),
            ({"scope": "project:feishu_ai_challenge"}, "project"),
        ]

        for current_context, expected in cases:
            with self.subTest(expected=expected):
                policy = evaluate_review_policy(
                    candidate={"text": "普通低风险记录", "importance_level": "low"},
                    risk_flags=[],
                    conflict={"has_conflict": False},
                    source={"source_type": "unit_test", "actor_id": "ou_member"},
                    current_context=current_context,
                )
                self.assertEqual(expected, policy["visibility_label"])


if __name__ == "__main__":
    unittest.main()
