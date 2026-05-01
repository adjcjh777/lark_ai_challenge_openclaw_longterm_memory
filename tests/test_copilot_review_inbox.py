from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.permissions import demo_permission_context
from memory_engine.copilot.review_inbox import list_review_inbox
from memory_engine.copilot.schemas import ConfirmRequest, CreateCandidateRequest, ReviewInboxRequest
from memory_engine.copilot.service import CopilotService
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def current_context(
    action: str,
    *,
    actor_id: str,
    reviewers: list[str] | None = None,
    chat_id: str | None = None,
    tenant_id: str = "tenant:demo",
    organization_id: str = "org:demo",
) -> dict[str, object]:
    context = demo_permission_context(
        action,
        SCOPE,
        actor_id=actor_id,
        roles=["member", "reviewer"],
        entrypoint="unit_test",
    )
    permission = context["permission"]
    assert isinstance(permission, dict)
    context["tenant_id"] = tenant_id
    context["organization_id"] = organization_id
    actor = permission["actor"]
    assert isinstance(actor, dict)
    actor["tenant_id"] = tenant_id
    actor["organization_id"] = organization_id
    if reviewers:
        permission["reviewers"] = list(reviewers)
    if chat_id:
        context["chat_id"] = chat_id
        source_context = permission.get("source_context")
        assert isinstance(source_context, dict)
        source_context["chat_id"] = chat_id
    return context


def candidate_request(
    text: str,
    *,
    actor_id: str,
    source_type: str = "feishu_message",
    reviewers: list[str] | None = None,
    chat_id: str | None = None,
    tenant_id: str = "tenant:demo",
    organization_id: str = "org:demo",
) -> CreateCandidateRequest:
    payload = {
        "text": text,
        "scope": SCOPE,
        "source": {
            "source_type": source_type,
            "source_id": f"src-{actor_id}-{abs(hash(text))}",
            "actor_id": actor_id,
            "created_at": "2026-04-30T10:00:00+08:00",
            "quote": text,
        },
        "current_context": current_context(
            "memory.create_candidate",
            actor_id=actor_id,
            reviewers=reviewers,
            chat_id=chat_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
        ),
        "auto_confirm": False,
    }
    return CreateCandidateRequest.from_payload(payload)


class CopilotReviewInboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)
        self.service = CopilotService(repository=self.repo, auto_init_cognee=False)
        self.seed_review_candidates()

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def seed_review_candidates(self) -> None:
        self.normal_candidate = self.service.create_candidate(
            candidate_request(
                "负责人：评委体验包由 Alice 负责，周五前更新。",
                actor_id="ou_owner_normal",
                reviewers=["ou_reviewer_a"],
            )
        )
        self.assertTrue(self.normal_candidate["ok"])
        self.assertEqual("candidate", self.normal_candidate["status"])

        active_seed = self.service.create_candidate(
            candidate_request("决定：上线窗口固定在周三 10:00。", actor_id="ou_owner_conflict")
        )
        self.assertTrue(active_seed["ok"])
        confirmed = self.service.confirm(
            ConfirmRequest(
                candidate_id=str(active_seed["candidate_id"]),
                scope=SCOPE,
                actor_id="ou_owner_conflict",
                reason="seed active memory",
                current_context=current_context("memory.confirm", actor_id="ou_owner_conflict"),
            )
        )
        self.assertTrue(confirmed["ok"])
        self.conflict_candidate = self.service.create_candidate(
            candidate_request(
                "决定：上线窗口改到周五 18:00。",
                actor_id="ou_owner_conflict",
                reviewers=["ou_reviewer_conflict"],
            )
        )
        self.assertTrue(self.conflict_candidate["ok"])
        self.assertEqual("candidate_conflict", self.conflict_candidate["action"])

        self.sensitive_candidate = self.service.create_candidate(
            candidate_request(
                "风险：演示环境 password=supersecret123 必须立刻轮换。",
                actor_id="ou_owner_sensitive",
                reviewers=["ou_security"],
            )
        )
        self.assertTrue(self.sensitive_candidate["ok"])
        self.assertEqual("candidate", self.sensitive_candidate["status"])

    def test_all_view_lists_safe_display_fields_without_raw_payloads(self) -> None:
        inbox = list_review_inbox(self.repo, scope=SCOPE, actor_roles=["reviewer"], view="all", limit=10)

        self.assertTrue(inbox["ok"])
        self.assertEqual(SCOPE, inbox["scope"])
        self.assertEqual("all", inbox["view"])
        self.assertEqual(3, len(inbox["items"]))
        self.assertEqual({"all": 3, "mine": 0, "conflicts": 1, "high_risk": 2}, inbox["counts"])

        required_fields = {
            "candidate_id",
            "memory_id",
            "subject",
            "type",
            "new_value",
            "old_value",
            "status",
            "conflict_status",
            "risk_level",
            "owner_id",
            "source_type",
            "evidence_quote",
            "visibility_policy",
            "review_targets",
        }
        for item in inbox["items"]:
            self.assertTrue(required_fields.issubset(item.keys()))
            self.assertNotIn("raw_json", item)
            self.assertNotIn("token", item)
            self.assertEqual("candidate", item["status"])

    def test_mine_view_matches_owner_or_review_targets(self) -> None:
        owner_view = list_review_inbox(self.repo, scope=SCOPE, actor_id="ou_owner_normal", view="mine")
        reviewer_view = list_review_inbox(self.repo, scope=SCOPE, actor_id="ou_reviewer_conflict", view="mine")

        self.assertEqual(1, len(owner_view["items"]))
        self.assertEqual(str(self.normal_candidate["candidate_id"]), owner_view["items"][0]["candidate_id"])
        self.assertEqual(1, reviewer_view["counts"]["mine"])
        self.assertEqual(str(self.conflict_candidate["candidate_id"]), reviewer_view["items"][0]["candidate_id"])
        self.assertIn("ou_reviewer_conflict", reviewer_view["items"][0]["review_targets"])

    def test_graph_chat_membership_extends_review_targets(self) -> None:
        chat_id = "oc_review_graph"
        ts = 1777600000000
        self.conn.execute(
            """
            INSERT INTO knowledge_graph_nodes (
              id, tenant_id, organization_id, node_type, node_key, label,
              visibility_policy, status, metadata_json, first_seen_at, last_seen_at
            )
            VALUES
              ('node_chat_review_graph', 'tenant:demo', 'org:demo', 'feishu_chat', ?, 'review graph chat', 'team', 'active', '{}', ?, ?),
              ('node_user_review_graph', 'tenant:demo', 'org:demo', 'feishu_user', 'ou_graph_reviewer', 'graph reviewer', 'team', 'active', '{}', ?, ?)
            """,
            (chat_id, ts, ts, ts, ts),
        )
        self.conn.execute(
            """
            INSERT INTO knowledge_graph_edges (
              id, tenant_id, organization_id, source_node_id, target_node_id,
              edge_type, metadata_json, first_seen_at, last_seen_at
            )
            VALUES (
              'edge_user_chat_review_graph', 'tenant:demo', 'org:demo',
              'node_user_review_graph', 'node_chat_review_graph',
              'member_of_feishu_chat', '{}', ?, ?
            )
            """,
            (ts, ts),
        )
        created = self.service.create_candidate(
            candidate_request(
                "决定：图谱审核候选需要按群成员路由。",
                actor_id="ou_graph_owner",
                chat_id=chat_id,
            )
        )
        self.assertTrue(created["ok"])

        inbox = list_review_inbox(
            self.repo,
            scope=SCOPE,
            actor_id="ou_graph_reviewer",
            actor_roles=["member"],
            view="mine",
        )

        self.assertEqual(1, len(inbox["items"]))
        item = inbox["items"][0]
        self.assertEqual(str(created["candidate_id"]), item["candidate_id"])
        self.assertIn("ou_graph_reviewer", item["review_targets"])
        self.assertEqual(["ou_graph_reviewer"], item["graph_review_targets"])
        self.assertEqual(chat_id, item["graph_context"]["source_chat_id"])

    def test_conflicts_view_returns_version_candidates_with_old_and_new_values(self) -> None:
        inbox = list_review_inbox(
            self.repo,
            scope=SCOPE,
            actor_id="ou_reviewer_conflict",
            view="conflicts",
        )

        self.assertEqual(1, len(inbox["items"]))
        conflict = inbox["items"][0]
        self.assertEqual(str(self.conflict_candidate["candidate_id"]), conflict["candidate_id"])
        self.assertEqual(str(self.conflict_candidate["memory_id"]), conflict["memory_id"])
        self.assertEqual("conflict", conflict["conflict_status"])
        self.assertIn("周五 18:00", conflict["new_value"])
        self.assertIn("周三 10:00", conflict["old_value"])

    def test_high_risk_view_includes_sensitive_and_conflict_candidates(self) -> None:
        inbox = list_review_inbox(self.repo, scope=SCOPE, actor_roles=["reviewer"], view="high_risk")
        candidate_ids = {item["candidate_id"] for item in inbox["items"]}

        self.assertEqual(2, len(inbox["items"]))
        self.assertIn(str(self.conflict_candidate["candidate_id"]), candidate_ids)
        self.assertIn(str(self.sensitive_candidate["candidate_id"]), candidate_ids)
        risk_levels = {item["candidate_id"]: item["risk_level"] for item in inbox["items"]}
        self.assertEqual("medium", risk_levels[str(self.conflict_candidate["candidate_id"])])
        self.assertEqual("high", risk_levels[str(self.sensitive_candidate["candidate_id"])])

    def test_non_reviewer_conflicts_and_high_risk_views_only_show_related_items(self) -> None:
        unrelated_conflicts = list_review_inbox(
            self.repo,
            scope=SCOPE,
            actor_id="ou_unrelated",
            actor_roles=["member"],
            view="conflicts",
        )
        related_high_risk = list_review_inbox(
            self.repo,
            scope=SCOPE,
            actor_id="ou_security",
            actor_roles=["member"],
            view="high_risk",
        )

        self.assertEqual([], unrelated_conflicts["items"])
        self.assertEqual({"all": 0, "mine": 0, "conflicts": 0, "high_risk": 0}, unrelated_conflicts["counts"])
        self.assertEqual(1, len(related_high_risk["items"]))
        self.assertEqual(str(self.sensitive_candidate["candidate_id"]), related_high_risk["items"][0]["candidate_id"])
        self.assertEqual({"all": 1, "mine": 1, "conflicts": 0, "high_risk": 1}, related_high_risk["counts"])

    def test_reviewer_view_filters_same_scope_candidates_by_tenant_and_organization(self) -> None:
        other = self.service.create_candidate(
            candidate_request(
                "决定：其他租户的发布节奏不应进入本租户审核收件箱。",
                actor_id="ou_other_tenant",
                reviewers=["ou_reviewer_a"],
                tenant_id="tenant:other",
                organization_id="org:other",
            )
        )

        inbox = list_review_inbox(
            self.repo,
            scope=SCOPE,
            tenant_id="tenant:demo",
            organization_id="org:demo",
            actor_id="ou_reviewer_a",
            actor_roles=["reviewer"],
            view="all",
            limit=10,
        )

        self.assertTrue(other["ok"])
        self.assertNotIn(str(other["candidate_id"]), {item["candidate_id"] for item in inbox["items"]})
        self.assertEqual(3, inbox["counts"]["all"])

    def test_service_review_inbox_uses_permission_tenant_and_records_audit(self) -> None:
        other = self.service.create_candidate(
            candidate_request(
                "风险：外部租户候选不能通过 service 收件箱串读。",
                actor_id="ou_other_service_tenant",
                reviewers=["ou_reviewer_a"],
                tenant_id="tenant:other",
                organization_id="org:other",
            )
        )

        inbox = self.service.review_inbox(
            ReviewInboxRequest(
                scope=SCOPE,
                view="all",
                limit=10,
                current_context=current_context("memory.review_inbox", actor_id="ou_reviewer_a"),
            )
        )

        self.assertTrue(other["ok"])
        self.assertTrue(inbox["ok"])
        self.assertNotIn(str(other["candidate_id"]), {item["candidate_id"] for item in inbox["items"]})
        self.assertEqual(3, inbox["counts"]["all"])
        audit = self.conn.execute(
            """
            SELECT event_type, tool_name, permission_decision
            FROM memory_audit_events
            WHERE tool_name = 'memory.review_inbox'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        self.assertIsNotNone(audit)
        assert audit is not None
        self.assertEqual("review_inbox_viewed", audit["event_type"])
        self.assertEqual("allow", audit["permission_decision"])


if __name__ == "__main__":
    unittest.main()
