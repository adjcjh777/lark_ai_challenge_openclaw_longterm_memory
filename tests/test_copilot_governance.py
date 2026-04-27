from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.schemas import ConfirmRequest, CreateCandidateRequest, RejectRequest
from memory_engine.copilot.service import CopilotService
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository


SCOPE = "project:feishu_ai_challenge"


def candidate_request(text: str, *, auto_confirm: bool = False) -> CreateCandidateRequest:
    payload = {
        "text": text,
        "scope": SCOPE,
        "source": {
            "source_type": "unit_test",
            "source_id": text[:24],
            "actor_id": "ou_test",
            "created_at": "2026-04-30T10:00:00+08:00",
            "quote": text,
        },
        "auto_confirm": auto_confirm,
    }
    return CreateCandidateRequest.from_payload(payload)


class CopilotGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)
        self.service = CopilotService(repository=self.repo)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_create_candidate_stays_out_of_default_search_until_confirmed(self) -> None:
        created = self.service.create_candidate(candidate_request("决定：生产部署必须加 --canary --region cn-shanghai。"))

        self.assertTrue(created["ok"])
        self.assertEqual("created", created["action"])
        self.assertEqual("candidate", created["candidate"]["status"])
        self.assertEqual("review_candidate", created["recommended_action"])

        inactive = self.repo.recall(SCOPE, "生产部署参数")
        self.assertIsNone(inactive)

        confirmed = self.service.confirm(
            ConfirmRequest(candidate_id=created["candidate_id"], scope=SCOPE, actor_id="ou_test", reason="人工确认")
        )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("confirmed", confirmed["action"])
        recalled = self.repo.recall(SCOPE, "生产部署参数")
        self.assertIsNotNone(recalled)
        assert recalled is not None
        self.assertEqual("active", recalled["status"])
        self.assertIn("--canary", recalled["answer"])
        self.assertIn("生产部署必须加", recalled["source"]["quote"])

    def test_reject_keeps_candidate_out_of_recall(self) -> None:
        created = self.service.create_candidate(candidate_request("规则：OpenClaw 固定 2026.4.24，不要随意升级。"))

        rejected = self.service.reject(
            RejectRequest(candidate_id=created["candidate_id"], scope=SCOPE, actor_id="ou_test", reason="测试拒绝")
        )

        self.assertTrue(rejected["ok"])
        self.assertEqual("rejected", rejected["action"])
        self.assertIsNone(self.repo.recall(SCOPE, "OpenClaw 版本"))

    def test_low_signal_text_is_ignored(self) -> None:
        result = self.service.create_candidate(candidate_request("大家下午三点喝咖啡。"))

        self.assertTrue(result["ok"])
        self.assertEqual("ignored", result["action"])
        self.assertIsNone(result["candidate"])
        self.assertIn("low_memory_signal", result["risk_flags"])

    def test_sensitive_auto_confirm_is_blocked_but_manual_review_candidate_is_allowed(self) -> None:
        text = "规则：临时测试 app_secret=abc123456789 只可放本地调试。"

        blocked = self.service.create_candidate(candidate_request(text, auto_confirm=True))
        self.assertFalse(blocked["ok"])
        self.assertEqual("sensitive_content_blocked", blocked["error"]["code"])

        candidate = self.service.create_candidate(candidate_request(text))
        self.assertTrue(candidate["ok"])
        self.assertEqual("candidate", candidate["candidate"]["status"])
        self.assertIn("sensitive_content", candidate["risk_flags"])
        self.assertEqual("manual_review_sensitive", candidate["recommended_action"])

    def test_confirm_requires_evidence_quote(self) -> None:
        created = self.service.create_candidate(candidate_request("决定：Benchmark 报告必须保留 evidence coverage。"))
        self.conn.execute("DELETE FROM memory_evidence WHERE memory_id = ?", (created["memory_id"],))
        self.conn.commit()

        confirmed = self.service.confirm(
            ConfirmRequest(candidate_id=created["candidate_id"], scope=SCOPE, actor_id="ou_test", reason="缺证据")
        )

        self.assertFalse(confirmed["ok"])
        self.assertEqual("candidate_not_confirmable", confirmed["error"]["code"])
        self.assertEqual("evidence_missing", confirmed["error"]["details"]["reason"])

    def test_conflict_candidate_does_not_overwrite_active_until_confirmed(self) -> None:
        self.repo.remember(SCOPE, "生产部署必须加 --canary --region cn-shanghai。", source_type="unit_test")

        created = self.service.create_candidate(candidate_request("不对，生产部署 region 改成 ap-shanghai。"))

        self.assertTrue(created["ok"])
        self.assertEqual("candidate_conflict", created["action"])
        self.assertTrue(created["conflict"]["has_conflict"])
        before = self.repo.recall(SCOPE, "生产部署 region")
        self.assertIsNotNone(before)
        assert before is not None
        self.assertIn("cn-shanghai", before["answer"])

        confirmed = self.service.confirm(
            ConfirmRequest(candidate_id=created["candidate_id"], scope=SCOPE, actor_id="ou_test", reason="确认覆盖")
        )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("confirmed", confirmed["action"])
        self.assertIn("cn-shanghai", confirmed["superseded"]["value"])
        after = self.repo.recall(SCOPE, "生产部署 region")
        self.assertIsNotNone(after)
        assert after is not None
        self.assertIn("ap-shanghai", after["answer"])


if __name__ == "__main__":
    unittest.main()
