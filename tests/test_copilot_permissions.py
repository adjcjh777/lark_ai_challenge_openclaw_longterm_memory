from __future__ import annotations

import tempfile
import unittest

from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def permission_context(
    *,
    action: str,
    user_id: str = "u_reviewer",
    tenant_id: str = "tenant:demo",
    organization_id: str = "org:demo",
    roles: list[str] | None = None,
    visibility: str = "team",
    workspace_id: str = SCOPE,
    context_tenant_id: str | None = None,
    context_organization_id: str | None = None,
    context_chat_id: str | None = None,
    source_chat_id: str | None = None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "scope": SCOPE,
        "permission": {
            "request_id": f"req_{action.replace('.', '_')}",
            "trace_id": f"trace_{action.replace('.', '_')}",
            "actor": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "roles": roles if roles is not None else ["member", "reviewer"],
            },
            "source_context": {
                "entrypoint": "openclaw",
                "workspace_id": workspace_id,
            },
            "requested_action": action,
            "requested_visibility": visibility,
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }
    if context_tenant_id:
        context["tenant_id"] = context_tenant_id
    if context_organization_id:
        context["organization_id"] = context_organization_id
    if context_chat_id:
        context["chat_id"] = context_chat_id
    if source_chat_id:
        context["permission"]["source_context"]["chat_id"] = source_chat_id  # type: ignore[index]
    return context


class CopilotPermissionTest(unittest.TestCase):
    def test_search_missing_permission_context_auto_generates_default(self) -> None:
        response = handle_tool_request("memory.search", {"query": "部署", "scope": SCOPE})

        self.assertTrue(response["ok"], response)
        self.assertIn("results", response)

    def test_search_malformed_permission_context_fails_closed(self) -> None:
        response = handle_tool_request(
            "memory.search",
            {
                "query": "部署",
                "scope": SCOPE,
                "current_context": {
                    "scope": SCOPE,
                    "permission": {
                        "request_id": "req_bad",
                        "trace_id": "trace_bad",
                        "actor": {
                            "user_id": "u_bad",
                            "tenant_id": "tenant:demo",
                            "organization_id": "org:demo",
                            "roles": "reviewer",
                        },
                        "source_context": {"entrypoint": "openclaw", "workspace_id": SCOPE},
                        "requested_action": "memory.search",
                        "requested_visibility": "team",
                        "timestamp": "2026-05-07T00:00:00+08:00",
                    },
                },
            },
        )

        self.assert_permission_denied(response, "malformed_permission_context")
        self.assertEqual("req_bad", response["error"]["details"]["request_id"])
        self.assertEqual("trace_bad", response["error"]["details"]["trace_id"])

    def test_search_tenant_mismatch_does_not_return_memory_or_evidence(self) -> None:
        with seeded_service() as service:
            response = handle_tool_request(
                "memory.search",
                {
                    "query": "生产部署参数",
                    "scope": SCOPE,
                    "current_context": permission_context(action="memory.search", tenant_id="tenant:other"),
                },
                service=service,
            )

        self.assert_permission_denied(response, "tenant_mismatch")
        self.assertNotIn("results", response)
        self.assertNotIn("--canary", str(response))

    def test_search_organization_mismatch_does_not_return_memory_or_evidence(self) -> None:
        with seeded_service() as service:
            response = handle_tool_request(
                "memory.search",
                {
                    "query": "生产部署参数",
                    "scope": SCOPE,
                    "current_context": permission_context(action="memory.search", organization_id="org:other"),
                },
                service=service,
            )

        self.assert_permission_denied(response, "organization_mismatch")
        self.assertNotIn("results", response)

    def test_real_feishu_tenant_and_org_are_allowed_when_context_matches(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_perm_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            service = CopilotService(repository=MemoryRepository(conn))
            response = handle_tool_request(
                "memory.create_candidate",
                {
                    "text": "决定：真实飞书试点群只进入 candidate。",
                    "scope": SCOPE,
                    "source": {
                        "source_type": "feishu_message",
                        "source_id": "om_real_tenant",
                        "actor_id": "ou_real_user",
                        "created_at": "2026-04-28T10:00:00+08:00",
                        "quote": "决定：真实飞书试点群只进入 candidate。",
                        "source_chat_id": "oc_real_chat",
                    },
                    "current_context": permission_context(
                        action="memory.create_candidate",
                        user_id="u_real_user",
                        tenant_id="tenant:feishu-prod",
                        organization_id="org:feishu-ai",
                        context_tenant_id="tenant:feishu-prod",
                        context_organization_id="org:feishu-ai",
                        context_chat_id="oc_real_chat",
                        source_chat_id="oc_real_chat",
                    ),
                },
                service=service,
            )
            memory_row = conn.execute("SELECT tenant_id, organization_id FROM memories").fetchone()
            raw_row = conn.execute("SELECT tenant_id, organization_id FROM raw_events").fetchone()
            conn.close()

        self.assertTrue(response["ok"], response)
        self.assertEqual("candidate", response["status"])
        self.assertEqual("tenant:feishu-prod", memory_row["tenant_id"])
        self.assertEqual("org:feishu-ai", memory_row["organization_id"])
        self.assertEqual("tenant:feishu-prod", raw_row["tenant_id"])
        self.assertEqual("org:feishu-ai", raw_row["organization_id"])

    def test_source_context_chat_mismatch_denies_without_evidence(self) -> None:
        with seeded_service() as service:
            response = handle_tool_request(
                "memory.search",
                {
                    "query": "生产部署参数",
                    "scope": SCOPE,
                    "current_context": permission_context(
                        action="memory.search",
                        context_chat_id="oc_expected_chat",
                        source_chat_id="oc_other_chat",
                    ),
                },
                service=service,
            )

        self.assert_permission_denied(response, "source_context_mismatch")
        self.assertNotIn("results", response)
        self.assertNotIn("--canary", str(response))

    def test_private_visibility_denies_non_owner_member(self) -> None:
        response = handle_tool_request(
            "memory.search",
            {
                "query": "私人规则",
                "scope": SCOPE,
                "current_context": permission_context(
                    action="memory.search",
                    user_id="u_member",
                    roles=["member"],
                    visibility="private",
                ),
            },
        )

        self.assert_permission_denied(response, "visibility_private_non_owner")

    def test_member_cannot_confirm_candidate_and_candidate_stays_candidate(self) -> None:
        with candidate_service() as fixture:
            denied = handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": fixture.candidate_id,
                    "scope": SCOPE,
                    "actor_id": "u_member",
                    "current_context": permission_context(
                        action="memory.confirm",
                        user_id="u_member",
                        roles=["member"],
                    ),
                },
                service=fixture.service,
            )
            status = fixture.memory_status()
            audit_events = fixture.audit_events("memory.confirm")

        self.assert_permission_denied(denied, "review_role_required")
        self.assertEqual("candidate", status)
        self.assertEqual("deny", audit_events[-1]["permission_decision"])
        self.assertEqual("review_role_required", audit_events[-1]["reason_code"])
        self.assertEqual("u_member", audit_events[-1]["actor_id"])

    def test_member_auto_confirm_cannot_bypass_review_role(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_perm_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            service = CopilotService(repository=MemoryRepository(conn))
            denied = handle_tool_request(
                "memory.create_candidate",
                {
                    "text": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    "scope": SCOPE,
                    "source": {
                        "source_type": "unit_test",
                        "source_id": "msg_auto_confirm",
                        "actor_id": "u_member",
                        "created_at": "2026-05-07T10:00:00+08:00",
                        "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    },
                    "auto_confirm": True,
                    "current_context": permission_context(
                        action="memory.create_candidate",
                        user_id="u_member",
                        roles=["member"],
                    ),
                },
                service=service,
            )
            active_count = conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()[
                "count"
            ]
            candidate_count = conn.execute(
                "SELECT COUNT(*) AS count FROM memories WHERE status = 'candidate'"
            ).fetchone()["count"]
            conn.close()

        self.assert_permission_denied(denied, "review_role_required")
        self.assertEqual(0, active_count)
        self.assertEqual(0, candidate_count)

    def test_member_cannot_reject_candidate_and_candidate_stays_candidate(self) -> None:
        with candidate_service() as fixture:
            denied = handle_tool_request(
                "memory.reject",
                {
                    "candidate_id": fixture.candidate_id,
                    "scope": SCOPE,
                    "actor_id": "u_member",
                    "current_context": permission_context(
                        action="memory.reject",
                        user_id="u_member",
                        roles=["member"],
                    ),
                },
                service=fixture.service,
            )
            status = fixture.memory_status()
            audit_events = fixture.audit_events("memory.reject")

        self.assert_permission_denied(denied, "review_role_required")
        self.assertEqual("candidate", status)
        self.assertEqual("deny", audit_events[-1]["permission_decision"])
        self.assertEqual("review_role_required", audit_events[-1]["reason_code"])

    def test_confirm_and_reject_write_allow_audit_records(self) -> None:
        with candidate_service() as fixture:
            confirmed = handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": fixture.candidate_id,
                    "scope": SCOPE,
                    "actor_id": "u_reviewer",
                    "current_context": permission_context(action="memory.confirm"),
                },
                service=fixture.service,
            )
            second = fixture.create_candidate("msg_2", "决定：QA 冻结前必须跑 audit smoke。")
            rejected = handle_tool_request(
                "memory.reject",
                {
                    "candidate_id": second,
                    "scope": SCOPE,
                    "actor_id": "u_reviewer",
                    "current_context": permission_context(action="memory.reject"),
                },
                service=fixture.service,
            )
            confirm_events = fixture.audit_events("memory.confirm")
            reject_events = fixture.audit_events("memory.reject")

        self.assertTrue(confirmed["ok"])
        self.assertTrue(rejected["ok"])
        self.assertEqual("allow", confirm_events[-1]["permission_decision"])
        self.assertEqual("candidate_confirmed", confirm_events[-1]["event_type"])
        self.assertEqual("allow", reject_events[-1]["permission_decision"])
        self.assertEqual("candidate_rejected", reject_events[-1]["event_type"])

    def test_explain_versions_missing_permission_context_auto_generates_default(self) -> None:
        response = handle_tool_request(
            "memory.explain_versions",
            {
                "memory_id": "mem_1",
                "scope": SCOPE,
            },
        )

        # Permission check passes with auto-generated context (no permission_denied)
        self.assertNotEqual("permission_denied", response.get("error", {}).get("code"))
        # Either succeeds or returns memory_not_found (mem_1 doesn't exist)
        self.assertTrue(
            response["ok"] or response.get("error", {}).get("code") == "memory_not_found",
            response,
        )

    def test_prefetch_missing_permission_context_auto_generates_default(self) -> None:
        response = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成部署 checklist",
                "scope": SCOPE,
                "current_context": {"scope": SCOPE, "intent": "生产部署"},
            },
        )

        self.assertTrue(response["ok"], response)
        self.assertIn("context_pack", response)

    def test_heartbeat_missing_permission_context_auto_generates_default(self) -> None:
        response = handle_tool_request(
            "heartbeat.review_due",
            {
                "scope": SCOPE,
                "current_context": {"scope": SCOPE, "intent": "准备初赛提交材料"},
            },
        )

        self.assertTrue(response["ok"], response)
        self.assertIn("candidates", response)

    def test_heartbeat_malformed_permission_context_fails_closed(self) -> None:
        response = handle_tool_request(
            "heartbeat.review_due",
            {
                "scope": SCOPE,
                "current_context": {"scope": SCOPE, "permission": {"request_id": "req_bad", "trace_id": "trace_bad"}},
            },
        )

        self.assert_permission_denied(response, "malformed_permission_context")
        self.assertEqual("req_bad", response["error"]["details"]["request_id"])
        self.assertEqual("trace_bad", response["error"]["details"]["trace_id"])

    def assert_permission_denied(self, response: dict[str, object], reason_code: str) -> None:
        self.assertFalse(response["ok"])
        error = response["error"]  # type: ignore[index]
        self.assertEqual("permission_denied", error["code"])
        self.assertFalse(error["retryable"])
        self.assertEqual(reason_code, error["details"]["reason_code"])


class seeded_service:
    def __enter__(self) -> CopilotService:
        self.tmp = tempfile.NamedTemporaryFile(prefix="copilot_perm_", suffix=".sqlite")
        conn = connect(self.tmp.name)
        init_db(conn)
        self.conn = conn
        repo = MemoryRepository(conn)
        repo.remember(SCOPE, "生产部署必须加 --canary --region cn-shanghai", source_type="unit_test")
        self.service = CopilotService(repository=repo)
        return self.service

    def __exit__(self, *_exc: object) -> None:
        self.conn.close()
        self.tmp.close()


class candidate_service:
    def __enter__(self) -> "candidate_service":
        self.tmp = tempfile.NamedTemporaryFile(prefix="copilot_perm_", suffix=".sqlite")
        self.conn = connect(self.tmp.name)
        init_db(self.conn)
        self.service = CopilotService(repository=MemoryRepository(self.conn))
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：生产部署必须加 --canary --region cn-shanghai。",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "msg_1",
                    "actor_id": "u_author",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
                },
                "current_context": permission_context(action="memory.create_candidate"),
            },
            service=self.service,
        )
        if not created.get("ok"):
            raise AssertionError(created)
        self.candidate_id = str(created["candidate_id"])
        return self

    def __exit__(self, *_exc: object) -> None:
        self.conn.close()
        self.tmp.close()

    def memory_status(self) -> str:
        row = self.conn.execute("SELECT status FROM memories WHERE id = ?", (self.candidate_id,)).fetchone()
        return str(row["status"])

    def create_candidate(self, source_id: str, text: str) -> str:
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": text,
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": source_id,
                    "actor_id": "u_author",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": text,
                },
                "current_context": permission_context(action="memory.create_candidate"),
            },
            service=self.service,
        )
        if not created.get("ok"):
            raise AssertionError(created)
        return str(created["candidate_id"])

    def audit_events(self, action: str) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT event_type, action, actor_id, permission_decision, reason_code
            FROM memory_audit_events
            WHERE action = ?
            ORDER BY created_at, audit_id
            """,
            (action,),
        ).fetchall()
        return [dict(row) for row in rows]


if __name__ == "__main__":
    unittest.main()
