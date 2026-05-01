from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.schemas import (
    ConfirmRequest,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    RejectRequest,
    SearchRequest,
    UndoReviewRequest,
)
from memory_engine.copilot.service import CopilotService
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def current_context(action: str) -> dict[str, object]:
    return {
        "scope": SCOPE,
        "permission": {
            "request_id": f"req_{action.replace('.', '_')}",
            "trace_id": f"trace_{action.replace('.', '_')}",
            "actor": {
                "user_id": "ou_test",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": ["member", "reviewer"],
            },
            "source_context": {"entrypoint": "unit_test", "workspace_id": SCOPE},
            "requested_action": action,
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }


def review_request(candidate_id: str, action: str) -> RejectRequest:
    return RejectRequest(
        candidate_id=candidate_id,
        scope=SCOPE,
        actor_id="ou_test",
        reason=action,
        current_context=current_context(action),
    )


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
        "current_context": current_context("memory.create_candidate"),
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
        self.service = CopilotService(repository=self.repo, auto_init_cognee=False)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_create_candidate_stays_out_of_default_search_until_confirmed(self) -> None:
        created = self.service.create_candidate(
            candidate_request("决定：生产部署必须加 --canary --region cn-shanghai。")
        )

        self.assertTrue(created["ok"])
        self.assertEqual("created", created["action"])
        self.assertEqual("candidate", created["candidate"]["status"])
        self.assertEqual("review_candidate", created["recommended_action"])

        inactive = self.repo.recall(SCOPE, "生产部署参数")
        self.assertIsNone(inactive)

        confirmed = self.service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="人工确认",
                current_context=current_context("memory.confirm"),
            )
        )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("confirmed", confirmed["action"])
        recalled = self.repo.recall(SCOPE, "生产部署参数")
        self.assertIsNotNone(recalled)
        assert recalled is not None
        self.assertEqual("active", recalled["status"])
        self.assertIn("--canary", recalled["answer"])
        self.assertIn("生产部署必须加", recalled["source"]["quote"])
        self.assertEqual("skipped", confirmed["cognee_sync"]["status"])
        self.assertEqual("repository_ledger", confirmed["cognee_sync"]["fallback"])

    def test_confirmed_memory_syncs_curated_payload_to_configured_cognee(self) -> None:
        class FakeCogneeAdapter:
            is_configured = True

            def __init__(self) -> None:
                self.synced: list[tuple[str, dict[str, object]]] = []

            def sync_curated_memory(self, scope: str, memory: dict[str, object]) -> dict[str, object]:
                self.synced.append((scope, memory))
                return {
                    "ok": True,
                    "dataset_name": "feishu_memory_copilot_project_feishu_ai_challenge",
                    "memory_id": memory["memory_id"],
                    "version": memory["version"],
                }

        adapter = FakeCogneeAdapter()
        service = CopilotService(repository=self.repo, cognee_adapter=adapter)  # type: ignore[arg-type]
        created = service.create_candidate(candidate_request("决定：生产部署必须加 --canary --region cn-shanghai。"))

        confirmed = service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="人工确认",
                current_context=current_context("memory.confirm"),
            )
        )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("pass", confirmed["cognee_sync"]["status"])
        self.assertEqual("feishu_memory_copilot_project_feishu_ai_challenge", confirmed["cognee_sync"]["dataset_name"])
        self.assertEqual(1, len(adapter.synced))
        _, synced_memory = adapter.synced[0]
        self.assertEqual("active", synced_memory["status"])
        self.assertEqual("unit_test", synced_memory["evidence"]["source_type"])

    def test_cognee_sync_failure_keeps_confirmed_memory_in_repository_fallback(self) -> None:
        class FailingCogneeAdapter:
            is_configured = True

            def sync_curated_memory(self, scope: str, memory: dict[str, object]) -> dict[str, object]:
                raise RuntimeError("cognee down")

        service = CopilotService(repository=self.repo, cognee_adapter=FailingCogneeAdapter())  # type: ignore[arg-type]
        created = service.create_candidate(candidate_request("决定：Benchmark 报告必须保留 evidence coverage。"))

        confirmed = service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="人工确认",
                current_context=current_context("memory.confirm"),
            )
        )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("fallback_used", confirmed["cognee_sync"]["status"])
        self.assertEqual("repository_ledger", confirmed["cognee_sync"]["fallback"])
        self.assertIsNotNone(self.repo.recall(SCOPE, "Benchmark 报告 evidence"))

    def test_reject_keeps_candidate_out_of_recall(self) -> None:
        created = self.service.create_candidate(candidate_request("规则：OpenClaw 固定 2026.4.24，不要随意升级。"))

        rejected = self.service.reject(
            RejectRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="测试拒绝",
                current_context=current_context("memory.reject"),
            )
        )

        self.assertTrue(rejected["ok"])
        self.assertEqual("rejected", rejected["action"])
        self.assertEqual("skipped", rejected["cognee_sync"]["status"])
        self.assertIsNone(self.repo.recall(SCOPE, "OpenClaw 版本"))

    def test_needs_evidence_and_expired_are_service_owned_audited_review_states(self) -> None:
        needs_evidence = self.service.create_candidate(candidate_request("决定：上线风险口径需要补来源证据。"))
        marked = self.service.needs_evidence(review_request(needs_evidence["candidate_id"], "memory.needs_evidence"))

        expired_candidate = self.service.create_candidate(candidate_request("规则：临时灰度窗口只在今天有效。"))
        expired = self.service.expire_candidate(review_request(expired_candidate["candidate_id"], "memory.expire"))

        self.assertTrue(marked["ok"])
        self.assertEqual("needs_evidence", marked["status"])
        self.assertEqual("needs_evidence", marked["review_status"])
        self.assertEqual("ou_test", marked["last_handler"])
        self.assertTrue(expired["ok"])
        self.assertEqual("expired", expired["status"])
        self.assertEqual("expired", expired["review_status"])
        self.assertIsNone(self.repo.recall(SCOPE, "上线风险口径"))
        self.assertIsNone(self.repo.recall(SCOPE, "临时灰度窗口"))

        audit_events = self.conn.execute(
            """
            SELECT event_type, action, candidate_id, actor_id, permission_decision
            FROM memory_audit_events
            WHERE action IN ('memory.needs_evidence', 'memory.expire')
            ORDER BY created_at, action
            """
        ).fetchall()
        self.assertEqual(2, len(audit_events))
        self.assertEqual({"candidate_needs_evidence", "candidate_expired"}, {row["event_type"] for row in audit_events})
        self.assertEqual({"allow"}, {row["permission_decision"] for row in audit_events})
        self.assertEqual({"ou_test"}, {row["actor_id"] for row in audit_events})

    def test_reject_with_configured_cognee_withdraws_candidate_from_dataset(self) -> None:
        class FakeCogneeAdapter:
            is_configured = True

            def __init__(self) -> None:
                self.withdrawn: list[tuple[str, str, dict[str, object]]] = []

            def sync_memory_withdrawal(self, scope: str, memory_id: str, **metadata: object) -> dict[str, object]:
                self.withdrawn.append((scope, memory_id, metadata))
                return {
                    "ok": True,
                    "dataset_name": "feishu_memory_copilot_project_feishu_ai_challenge",
                    "memory_id": memory_id,
                }

        adapter = FakeCogneeAdapter()
        service = CopilotService(repository=self.repo, cognee_adapter=adapter)  # type: ignore[arg-type]
        created = service.create_candidate(candidate_request("规则：OpenClaw 固定 2026.4.24，不要随意升级。"))

        rejected = service.reject(
            RejectRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="测试拒绝",
                current_context=current_context("memory.reject"),
            )
        )

        self.assertTrue(rejected["ok"])
        self.assertEqual("pass", rejected["cognee_sync"]["status"])
        self.assertEqual(
            [
                (
                    SCOPE,
                    created["memory_id"],
                    {"candidate_id": created["candidate_id"], "action": "rejected", "provenance": "copilot_ledger"},
                )
            ],
            adapter.withdrawn,
        )

    def test_low_signal_text_is_ignored(self) -> None:
        result = self.service.create_candidate(candidate_request("大家下午三点喝咖啡。"))

        self.assertTrue(result["ok"])
        self.assertEqual("ignored", result["action"])
        self.assertIsNone(result["candidate"])
        self.assertIn("low_memory_signal", result["risk_flags"])

    def test_low_importance_candidate_auto_confirms_without_review_card(self) -> None:
        result = self.service.create_candidate(candidate_request("偏好：周报默认用简洁版格式。"))

        self.assertTrue(result["ok"])
        self.assertEqual("auto_confirmed", result["action"])
        self.assertEqual("active", result["status"])
        self.assertEqual("auto_confirm", result["review_policy"]["decision"])
        self.assertEqual("low", result["review_policy"]["importance_level"])
        self.assertEqual("none", result["review_policy"]["delivery_channel"])
        recalled = self.repo.recall(SCOPE, "周报")
        self.assertIsNotNone(recalled)
        assert recalled is not None
        self.assertIn("简洁版", recalled["answer"])

    def test_important_conflict_stays_candidate_and_routes_private_review_targets(self) -> None:
        self.repo.remember(SCOPE, "生产部署 region 固定 cn-shanghai。", source_type="unit_test")

        result = self.service.create_candidate(candidate_request("不对，生产部署 region 改成 ap-shanghai。"))

        self.assertTrue(result["ok"])
        self.assertEqual("candidate_conflict", result["action"])
        self.assertEqual("candidate", result["status"])
        self.assertEqual("human_review", result["review_policy"]["decision"])
        self.assertEqual("high", result["review_policy"]["importance_level"])
        self.assertEqual("routed_private_review", result["review_policy"]["delivery_channel"])
        self.assertIn("ou_test", result["review_policy"]["review_targets"])
        before = self.repo.recall(SCOPE, "生产部署 region")
        self.assertIsNotNone(before)
        assert before is not None
        self.assertIn("cn-shanghai", before["answer"])

    def test_stable_key_detects_conflict_when_subject_text_drifted(self) -> None:
        seed = self.service.create_candidate(candidate_request("决定：生产部署 region 固定 cn-shanghai。"))
        confirmed = self.service.confirm(
            ConfirmRequest(
                candidate_id=seed["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="人工确认",
                current_context=current_context("memory.confirm"),
            )
        )
        self.assertTrue(confirmed["ok"])

        result = self.service.create_candidate(candidate_request("不对，线上部署机房以后统一改成 ap-shanghai。"))

        self.assertTrue(result["ok"])
        self.assertEqual("candidate_conflict", result["action"])
        self.assertTrue(result["conflict"]["has_conflict"])
        self.assertEqual("same stable memory key already has an active value", result["conflict"]["reason"])
        self.assertEqual("deploy_region", result["candidate"]["stable_key"]["slot_type"])

    def test_stable_key_does_not_merge_owner_with_weekly_report_recipient(self) -> None:
        owner = self.service.create_candidate(candidate_request("OpenClaw 产品化负责人是程俊豪。"))
        confirmed = self.service.confirm(
            ConfirmRequest(
                candidate_id=owner["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="人工确认",
                current_context=current_context("memory.confirm"),
            )
        )
        self.assertTrue(confirmed["ok"])

        recipient = self.service.create_candidate(candidate_request("OpenClaw 周报接收人改成 Alice。"))

        self.assertTrue(recipient["ok"])
        self.assertNotEqual("candidate_conflict", recipient["action"])
        self.assertEqual("weekly_report_recipient", recipient["candidate"]["stable_key"]["slot_type"])

    def test_undo_confirm_returns_new_memory_to_candidate(self) -> None:
        created = self.service.create_candidate(candidate_request("决定：演示脚本必须先展示权限拒绝。"))
        confirmed = self.service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="人工确认",
                current_context=current_context("memory.confirm"),
            )
        )

        undone = self.service.undo_review(
            UndoReviewRequest(
                candidate_id=confirmed["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="误点撤销",
                current_context=current_context("memory.undo_review"),
            )
        )

        self.assertTrue(undone["ok"])
        self.assertEqual("review_undone", undone["action"])
        self.assertEqual("candidate", undone["status"])
        self.assertEqual("pending", undone["review_status"])
        self.assertIsNone(self.repo.recall(SCOPE, "演示脚本权限拒绝"))

    def test_undo_confirmed_conflict_restores_previous_active_version(self) -> None:
        self.repo.remember(SCOPE, "生产部署 region 固定 cn-shanghai。", source_type="unit_test")
        created = self.service.create_candidate(candidate_request("不对，生产部署 region 改成 ap-shanghai。"))
        confirmed = self.service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="确认覆盖",
                current_context=current_context("memory.confirm"),
            )
        )
        self.assertIn("ap-shanghai", self.repo.recall(SCOPE, "生产部署 region")["answer"])

        undone = self.service.undo_review(
            UndoReviewRequest(
                candidate_id=confirmed["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="误点撤销",
                current_context=current_context("memory.undo_review"),
            )
        )

        self.assertTrue(undone["ok"])
        self.assertEqual("review_undone", undone["action"])
        after = self.repo.recall(SCOPE, "生产部署 region")
        self.assertIsNotNone(after)
        assert after is not None
        self.assertIn("cn-shanghai", after["answer"])

    def test_owner_deadline_style_sentence_becomes_candidate_without_decision_prefix(self) -> None:
        result = self.service.create_candidate(
            candidate_request("上线窗口固定为每周四下午，回滚负责人是程俊豪，截止周五中午。")
        )

        self.assertTrue(result["ok"])
        self.assertEqual("created", result["action"])
        self.assertEqual("candidate", result["candidate"]["status"])
        self.assertIn("负责人", result["candidate"]["current_value"])

    def test_question_with_workflow_keywords_is_not_treated_as_candidate(self) -> None:
        result = self.service.create_candidate(candidate_request("生产部署 region 是什么？"))

        self.assertTrue(result["ok"])
        self.assertEqual("ignored", result["action"])
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
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="缺证据",
                current_context=current_context("memory.confirm"),
            )
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
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="确认覆盖",
                current_context=current_context("memory.confirm"),
            )
        )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("confirmed", confirmed["action"])
        self.assertIn("cn-shanghai", confirmed["superseded"]["value"])
        after = self.repo.recall(SCOPE, "生产部署 region")
        self.assertIsNotNone(after)
        assert after is not None
        self.assertIn("ap-shanghai", after["answer"])

    def test_explain_versions_shows_superseded_value_and_evidence(self) -> None:
        self.repo.remember(SCOPE, "生产部署必须加 --canary --region cn-shanghai。", source_type="unit_test")
        created = self.service.create_candidate(candidate_request("不对，生产部署 region 以后统一改成 ap-shanghai。"))
        self.service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="确认覆盖",
                current_context=current_context("memory.confirm"),
            )
        )

        explained = self.service.explain_versions(
            ExplainVersionsRequest(
                memory_id=created["memory_id"],
                scope=SCOPE,
                current_context=current_context("memory.explain_versions"),
            )
        )

        self.assertTrue(explained["ok"])
        self.assertEqual("memory.explain_versions", explained["tool"])
        self.assertEqual("ap-shanghai", explained["active_version"]["value"].split()[-1].rstrip("。"))
        self.assertEqual(["active", "superseded"], sorted({item["status"] for item in explained["versions"]}))
        self.assertTrue(all(item["evidence"]["quote"] for item in explained["versions"]))
        superseded = [item for item in explained["versions"] if item["status"] == "superseded"][0]
        self.assertIn("cn-shanghai", superseded["value"])
        self.assertIn("默认 search 不再", superseded["inactive_reason"])

    def test_default_search_does_not_leak_superseded_or_stale_values(self) -> None:
        self.repo.remember(SCOPE, "生产部署必须加 --canary --region cn-shanghai。", source_type="unit_test")
        created = self.service.create_candidate(candidate_request("不对，生产部署 region 以后统一改成 ap-shanghai。"))
        self.service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=SCOPE,
                actor_id="ou_test",
                reason="确认覆盖",
                current_context=current_context("memory.confirm"),
            )
        )
        self.conn.execute("UPDATE memories SET status = 'stale' WHERE id LIKE 'mem_nonexistent'")
        self.conn.commit()

        search = self.service.search(
            SearchRequest.from_payload(
                {
                    "query": "生产部署 region",
                    "scope": SCOPE,
                    "top_k": 3,
                    "current_context": current_context("memory.search"),
                }
            )
        )

        self.assertTrue(search["ok"])
        self.assertTrue(search["results"])
        self.assertTrue(all(item["status"] == "active" for item in search["results"]))
        self.assertTrue(all("cn-shanghai" not in item["current_value"] for item in search["results"]))


if __name__ == "__main__":
    unittest.main()
