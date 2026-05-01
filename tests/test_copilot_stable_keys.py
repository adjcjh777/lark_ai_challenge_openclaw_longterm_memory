from __future__ import annotations

import unittest

from memory_engine.copilot.stable_keys import resolve_stable_memory_key

SCOPE = "project:feishu_ai_challenge"


class CopilotStableKeyTest(unittest.TestCase):
    def test_region_aliases_resolve_to_same_key(self) -> None:
        old = resolve_stable_memory_key("决定：生产部署 region 固定 cn-shanghai。", scope=SCOPE, subject="生产部署")
        new = resolve_stable_memory_key("线上部署机房以后统一改成 ap-shanghai。", scope=SCOPE, subject="生产部署")

        self.assertEqual(old.stable_key, new.stable_key)
        self.assertEqual("deploy_region", old.slot_type)
        self.assertGreaterEqual(old.confidence, 0.9)

    def test_owner_and_weekly_report_recipient_do_not_merge(self) -> None:
        owner = resolve_stable_memory_key("OpenClaw 产品化负责人是程俊豪。", scope=SCOPE, subject="负责人")
        recipient = resolve_stable_memory_key("OpenClaw 周报接收人改成 Alice。", scope=SCOPE, subject="周报收件人")

        self.assertNotEqual(owner.stable_key, recipient.stable_key)
        self.assertEqual("owner", owner.slot_type)
        self.assertEqual("weekly_report_recipient", recipient.slot_type)


if __name__ == "__main__":
    unittest.main()
