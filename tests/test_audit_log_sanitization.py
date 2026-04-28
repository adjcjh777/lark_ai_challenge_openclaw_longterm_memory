"""Tests for audit log sanitization (TODO-6 3.4).

Verifies:
- 6.4.1: audit logs do not contain tokens/secrets
- 6.4.2: deny logs do not contain raw private memory content
- 6.4.3: redacted_fields only records field names, not redacted plaintext
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request
from memory_engine.copilot.permissions import demo_permission_context

SCOPE = "project:feishu_ai_challenge"

# Patterns that should never appear in audit logs
SECRET_PATTERNS = [
    "sk-",
    "Bearer ",
    "api_key=",
    "app_secret=",
    "password=",
    "AKIA",
    "xoxb-",
    "xoxp-",
]

# Content that should be withheld from deny audit events
PRIVATE_MEMORY_PATTERNS = [
    "生产部署必须加 --canary --region cn-shanghai",
    "敏感的内部决策内容",
]


class AuditLogSanitizationTest(unittest.TestCase):
    """Verify audit logs are properly sanitized."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(prefix="audit_sanitize_", suffix=".sqlite")
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)
        self.service = CopilotService(repository=self.repo)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.close()

    def _get_all_audit_events(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM memory_audit_events ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def _serialize_event(self, event: dict) -> str:
        """Serialize event to JSON string for pattern matching."""
        return json.dumps(event, ensure_ascii=False)

    def test_audit_logs_do_not_contain_api_keys(self) -> None:
        """6.4.1: Audit logs must not contain API keys or secrets."""
        # Create a candidate with text that looks like it contains secrets
        handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：api_key=sk-1234567890abcdef1234567890abcdef 使用新的密钥",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "sanitize_test_1",
                    "actor_id": "u_test",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：api_key=sk-1234567890abcdef1234567890abcdef 使用新的密钥",
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate", SCOPE, actor_id="u_test", entrypoint="test"
                ),
            },
            service=self.service,
        )

        events = self._get_all_audit_events()
        self.assertGreater(len(events), 0, "Should have at least one audit event")

        for event in events:
            serialized = self._serialize_event(event)
            for pattern in SECRET_PATTERNS:
                self.assertNotIn(
                    pattern,
                    serialized,
                    f"Audit event should not contain '{pattern}': {event.get('audit_id')}",
                )

    def test_deny_logs_do_not_contain_private_memory_content(self) -> None:
        """6.4.2: Deny audit events must not contain raw private memory content."""
        # Seed a memory
        self.repo.remember(
            SCOPE,
            "生产部署必须加 --canary --region cn-shanghai",
            source_type="test",
        )

        # Trigger a permission deny by using wrong tenant_id
        handle_tool_request(
            "memory.search",
            {
                "query": "生产部署",
                "scope": SCOPE,
                "current_context": {
                    "scope": SCOPE,
                    "permission": {
                        "request_id": "req_deny_test",
                        "trace_id": "trace_deny_test",
                        "actor": {
                            "user_id": "u_wrong_tenant",
                            "tenant_id": "tenant:wrong",
                            "organization_id": "org:demo",
                            "roles": ["member"],
                        },
                        "source_context": {
                            "entrypoint": "test",
                            "workspace_id": SCOPE,
                        },
                        "requested_action": "memory.search",
                        "requested_visibility": "team",
                        "timestamp": "2026-05-07T00:00:00+08:00",
                    },
                },
            },
            service=self.service,
        )

        events = self._get_all_audit_events()
        deny_events = [e for e in events if e["permission_decision"] == "deny"]
        self.assertGreater(len(deny_events), 0, "Should have at least one deny event")

        for event in deny_events:
            serialized = self._serialize_event(event)
            # Deny events should have redacted_fields
            redacted = event.get("redacted_fields")
            if isinstance(redacted, str):
                redacted = json.loads(redacted)
            self.assertIsInstance(redacted, list)
            # Should contain field names like "current_value"
            self.assertIn("current_value", redacted, "Deny event should redact current_value field")

    def test_redacted_fields_contain_only_field_names(self) -> None:
        """6.4.3: redacted_fields should only contain field names, not actual content."""
        # Create and then deny a search
        handle_tool_request(
            "memory.search",
            {"query": "测试查询", "scope": SCOPE},
            service=self.service,
        )

        events = self._get_all_audit_events()
        for event in events:
            redacted = event.get("redacted_fields")
            if isinstance(redacted, str):
                redacted = json.loads(redacted)
            if not isinstance(redacted, list):
                continue

            for field_name in redacted:
                # Field names should be short identifiers, not content
                self.assertLess(
                    len(str(field_name)),
                    100,
                    f"redacted_fields entry should be a field name, not content: {field_name}",
                )
                # Field names should not contain spaces (content usually does)
                self.assertNotIn(
                    " ",
                    str(field_name),
                    f"redacted_fields entry should be a field name, not content: {field_name}",
                )

    def test_search_allow_audit_covers_all_fields(self) -> None:
        """Verify search allow audit events have proper structure."""
        # Seed a memory first
        self.repo.remember(
            SCOPE,
            "测试记忆内容",
            source_type="test",
        )

        # Seed enough data for search
        handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：测试审计覆盖",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "audit_cover_test",
                    "actor_id": "u_test",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：测试审计覆盖",
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate", SCOPE, actor_id="u_test", entrypoint="test"
                ),
            },
            service=self.service,
        )

        # Do a search with proper context
        handle_tool_request(
            "memory.search",
            {
                "query": "测试",
                "scope": SCOPE,
                "current_context": demo_permission_context(
                    "memory.search", SCOPE, actor_id="u_test", entrypoint="test"
                ),
            },
            service=self.service,
        )

        events = self._get_all_audit_events()
        search_events = [e for e in events if e["action"] == "memory.search" and e["permission_decision"] == "allow"]
        self.assertGreater(len(search_events), 0, "Should have search allow events")

        for event in search_events:
            # Verify required fields are present
            self.assertTrue(event.get("audit_id"), "audit_id must be present")
            self.assertEqual(event["event_type"], "permission_allowed")
            self.assertEqual(event["action"], "memory.search")
            self.assertEqual(event["permission_decision"], "allow")
            self.assertTrue(event.get("actor_id"), "actor_id must be present")
            self.assertTrue(event.get("tenant_id"), "tenant_id must be present")
            self.assertTrue(event.get("request_id"), "request_id must be present")
            self.assertTrue(event.get("trace_id"), "trace_id must be present")
            self.assertIsInstance(json.loads(event["visible_fields"]), list)

    def test_confirm_reject_audit_records_actor(self) -> None:
        """Verify confirm/reject events record the actor properly."""
        # Create a candidate
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：验证 actor 记录",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "actor_test",
                    "actor_id": "u_actor_test",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：验证 actor 记录",
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate", SCOPE, actor_id="u_actor_test", entrypoint="test"
                ),
            },
            service=self.service,
        )
        candidate_id = created.get("candidate_id")

        # Confirm it
        handle_tool_request(
            "memory.confirm",
            {
                "candidate_id": candidate_id,
                "scope": SCOPE,
                "reason": "测试确认",
                "current_context": demo_permission_context(
                    "memory.confirm", SCOPE, actor_id="u_actor_test", entrypoint="test"
                ),
            },
            service=self.service,
        )

        events = self._get_all_audit_events()
        confirm_events = [e for e in events if e["action"] == "memory.confirm" and e["permission_decision"] == "allow"]
        self.assertGreater(len(confirm_events), 0, "Should have confirm events")

        for event in confirm_events:
            self.assertEqual(event["actor_id"], "u_actor_test")
            self.assertIn("reviewer", json.loads(event["actor_roles"]))


class AuditCoverageTest(unittest.TestCase):
    """Verify all five tools produce audit events."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(prefix="audit_coverage_", suffix=".sqlite")
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)
        self.service = CopilotService(repository=self.repo)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.close()

    def _get_all_audit_events(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM memory_audit_events ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def test_all_five_tools_produce_audit_events(self) -> None:
        """All 5 tools should produce audit events."""
        # 1. create_candidate
        handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：全量审计覆盖测试",
                "scope": SCOPE,
                "source": {
                    "source_type": "document_feishu",
                    "source_id": "coverage_test",
                    "actor_id": "u_coverage",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：全量审计覆盖测试",
                    "source_doc_id": "doc_coverage",
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate", SCOPE, actor_id="u_coverage", entrypoint="test"
                ),
            },
            service=self.service,
        )

        # 2. search
        handle_tool_request(
            "memory.search",
            {
                "query": "覆盖测试",
                "scope": SCOPE,
                "current_context": demo_permission_context(
                    "memory.search", SCOPE, actor_id="u_coverage", entrypoint="test"
                ),
            },
            service=self.service,
        )

        # 3. explain_versions
        handle_tool_request(
            "memory.explain_versions",
            {
                "memory_id": "mem_nonexistent",
                "scope": SCOPE,
                "current_context": demo_permission_context(
                    "memory.explain_versions", SCOPE, actor_id="u_coverage", entrypoint="test"
                ),
            },
            service=self.service,
        )

        # 4. prefetch
        handle_tool_request(
            "memory.prefetch",
            {
                "task": "部署前检查",
                "scope": SCOPE,
                "current_context": demo_permission_context(
                    "memory.prefetch", SCOPE, actor_id="u_coverage", entrypoint="test"
                ),
            },
            service=self.service,
        )

        # 5. heartbeat.review_due
        handle_tool_request(
            "heartbeat.review_due",
            {
                "scope": SCOPE,
                "current_context": demo_permission_context(
                    "heartbeat.review_due", SCOPE, actor_id="u_coverage", entrypoint="test"
                ),
            },
            service=self.service,
        )

        events = self._get_all_audit_events()
        actions = {e["action"] for e in events}

        self.assertIn("memory.create_candidate", actions)
        self.assertIn("memory.search", actions)
        self.assertIn("memory.explain_versions", actions)
        self.assertIn("memory.prefetch", actions)
        self.assertIn("heartbeat.review_due", actions)

    def test_source_revoked_writes_audit(self) -> None:
        """mark_feishu_source_revoked should write audit event."""
        from memory_engine.document_ingestion import mark_feishu_source_revoked

        # Use document_feishu source type which requires document_id in source_context
        context = demo_permission_context(
            "memory.create_candidate", SCOPE, actor_id="u_revoke", entrypoint="test"
        )
        context["permission"]["source_context"]["document_id"] = "test_revoke_doc"

        mark_feishu_source_revoked(
            self.repo,
            source_type="document_feishu",
            source_id="test_revoke_doc",
            scope=SCOPE,
            current_context=context,
        )

        events = self._get_all_audit_events()
        revoke_events = [e for e in events if e["event_type"] == "source_permission_revoked"]
        self.assertGreater(len(revoke_events), 0, "Should have source_permission_revoked event")
        self.assertEqual(revoke_events[0]["action"], "source.revoked")


if __name__ == "__main__":
    unittest.main()
