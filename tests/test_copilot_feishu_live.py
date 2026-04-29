from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_engine.copilot.feishu_live import handle_copilot_message_event, invocation_from_event
from memory_engine.db import connect, init_db
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import DryRunPublisher
from memory_engine.repository import MemoryRepository

CHAT_ID = "oc_copilot_live_test"
SCOPE = "project:feishu_ai_challenge"


def payload(message_id: str, text: str, *, sender_type: str = "user", chat_id: str = CHAT_ID) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_live_user"},
                "sender_type": sender_type,
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": "group",
                "message_type": "text",
                "content": f'{{"text":"{text}"}}',
                "create_time": "1777351200000",
            },
        },
    }


def card_action_payload(action_value: dict) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger"},
        "event": {
            "token": "card_token_live",
            "operator": {"open_id": "ou_live_user"},
            "context": {"open_chat_id": CHAT_ID},
            "action": {"value": action_value},
        },
    }


class CopilotFeishuLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.config = FeishuConfig(
            bot_mode="reply",
            default_scope=SCOPE,
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
            card_mode="text",
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def handle(self, message_id: str, text: str) -> dict:
        event = message_event_from_payload(payload(message_id, text))
        self.assertIsNotNone(event)
        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            return handle_copilot_message_event(
                self.conn,
                event,
                DryRunPublisher(),
                self.config,
                dry_run=True,
            )

    def reply_text(self, result: dict) -> str:
        return result["publish"]["text"]

    def test_remember_routes_to_copilot_candidate_not_old_active_memory(self) -> None:
        result = self.handle("om_live_candidate", "/remember 决定：生产部署必须加 --canary --region cn-shanghai")

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        self.assertIn("不会自动成为 active memory", self.reply_text(result))
        self.assertIsNone(MemoryRepository(self.conn).recall(SCOPE, "生产部署参数"))

    def test_confirm_then_search_uses_copilot_tool_bridge(self) -> None:
        created = self.handle("om_live_create", "/remember 决定：生产部署必须加 --canary --region cn-shanghai")
        candidate_id = created["tool_result"]["candidate_id"]

        confirmed = self.handle("om_live_confirm", f"/confirm {candidate_id}")
        self.assertTrue(confirmed["ok"])
        self.assertEqual("memory.confirm", confirmed["tool"])
        self.assertIn("Memory Copilot 已确认候选记忆", self.reply_text(confirmed))

        search = self.handle("om_live_search", "生产部署 region 是什么？")
        self.assertTrue(search["ok"])
        self.assertEqual("memory.search", search["tool"])
        self.assertIn("只返回 active 当前结论", self.reply_text(search))
        self.assertIn("--canary", self.reply_text(search))
        self.assertIn("request_id", search["tool_result"]["bridge"])

    def test_natural_confirm_resolves_recent_candidate_without_internal_id(self) -> None:
        created = self.handle("om_live_create_natural_confirm", "记住：生产部署必须加 --canary，region 用 ap-shanghai。")
        self.assertEqual("memory.create_candidate", created["tool"])
        self.assertIn("你可以直接回复：确认这条", self.reply_text(created))

        confirmed = self.handle("om_live_confirm_natural", "确认这条")

        self.assertTrue(confirmed["ok"])
        self.assertEqual("memory.confirm", confirmed["tool"])
        self.assertEqual("natural_confirm_recent_candidate", confirmed["routing_reason"])
        self.assertEqual(created["tool_result"]["candidate_id"], confirmed["tool_result"]["candidate_id"])
        self.assertIn("下一步：这条记忆已经成为当前有效结论", self.reply_text(confirmed))

    def test_natural_reject_resolves_recent_candidate_without_internal_id(self) -> None:
        created = self.handle("om_live_create_natural_reject", "记住：生产部署 rollback 负责人是程俊豪，截止周五，必须提前录屏。")

        rejected = self.handle("om_live_reject_natural", "不要记这个")

        self.assertTrue(rejected["ok"])
        self.assertEqual("memory.reject", rejected["tool"])
        self.assertEqual("natural_reject_recent_candidate", rejected["routing_reason"])
        self.assertEqual(created["tool_result"]["candidate_id"], rejected["tool_result"]["candidate_id"])
        self.assertIn("不会成为当前有效记忆", self.reply_text(rejected))

    def test_natural_version_question_resolves_recent_memory_without_internal_id(self) -> None:
        self.handle("om_live_seed_old_region", "/remember 决定：生产部署 region 固定 cn-shanghai。")
        self.handle("om_live_confirm_old_region", "确认这条")
        updated = self.handle("om_live_update_region", "不对，生产部署 region 以后统一改成 ap-shanghai。")
        self.assertEqual("memory.create_candidate", updated["tool"])
        self.handle("om_live_confirm_updated_region", "确认这条")

        explained = self.handle("om_live_explain_natural", "为什么旧值不用了？")

        self.assertTrue(explained["ok"])
        self.assertEqual("memory.explain_versions", explained["tool"])
        self.assertEqual("natural_versions_recent_memory", explained["routing_reason"])
        self.assertEqual(updated["tool_result"]["memory_id"], explained["tool_result"]["memory_id"])
        reply = self.reply_text(explained)
        self.assertIn("当前结论", reply)
        self.assertIn("ap-shanghai", reply)
        self.assertIn("旧版本", reply)

    def test_search_reply_puts_audit_metadata_after_user_answer(self) -> None:
        self.handle("om_live_create_audit_order", "/remember 决定：生产部署必须加 --canary --region cn-shanghai")
        self.handle("om_live_confirm_audit_order", "确认这条")

        search = self.handle("om_live_search_audit_order", "生产部署 region 是什么？")
        reply = self.reply_text(search)

        self.assertLess(reply.index("结论："), reply.index("审计详情"))
        self.assertLess(reply.index("下一步："), reply.index("审计详情"))
        self.assertGreater(reply.index("request_id"), reply.index("审计详情"))

    def test_natural_task_request_routes_to_prefetch(self) -> None:
        event = message_event_from_payload(payload("om_live_prefetch", "请准备今天上线前 checklist"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        self.assertEqual("memory.prefetch", invocation.tool_name)
        self.assertEqual("natural_prefetch", invocation.reason)
        self.assertEqual(SCOPE, invocation.payload["scope"])

    def test_task_command_places_task_id_in_permission_source_context(self) -> None:
        event = message_event_from_payload(payload("om_live_task_fetch", "/task task_123"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        self.assertEqual("feishu.fetch_task", invocation.tool_name)
        self.assertNotIn("source_context", invocation.payload["current_context"])
        self.assertEqual("memory.create_candidate", permission["requested_action"])
        self.assertEqual("task_123", permission["source_context"]["task_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])

    def test_meeting_command_places_meeting_id_in_permission_source_context(self) -> None:
        event = message_event_from_payload(payload("om_live_meeting_fetch", "/meeting minute_123"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        self.assertEqual("feishu.fetch_meeting", invocation.tool_name)
        self.assertNotIn("source_context", invocation.payload["current_context"])
        self.assertEqual("memory.create_candidate", permission["requested_action"])
        self.assertEqual("minute_123", permission["source_context"]["meeting_id"])

    def test_bitable_command_places_record_id_in_permission_source_context(self) -> None:
        event = message_event_from_payload(payload("om_live_bitable_fetch", "/bitable app_1 tbl_1 rec_1"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        source_context = permission["source_context"]
        self.assertEqual("feishu.fetch_bitable", invocation.tool_name)
        self.assertNotIn("source_context", invocation.payload["current_context"])
        self.assertEqual("memory.create_candidate", permission["requested_action"])
        self.assertEqual("app_1", source_context["bitable_app_token"])
        self.assertEqual("tbl_1", source_context["bitable_table_id"])
        self.assertEqual("rec_1", source_context["bitable_record_id"])

    def test_permission_context_maps_real_feishu_tenant_org_and_chat(self) -> None:
        event = message_event_from_payload(payload("om_live_real_perm", "生产部署 region 是什么？"))
        self.assertIsNotNone(event)

        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_TENANT_ID": "tenant:feishu-prod",
                "COPILOT_FEISHU_ORGANIZATION_ID": "org:feishu-ai",
                "COPILOT_FEISHU_VISIBILITY": "organization",
            },
            clear=False,
        ):
            invocation = invocation_from_event(event, scope=SCOPE)

        context = invocation.payload["current_context"]
        permission = context["permission"]
        self.assertEqual("tenant:feishu-prod", context["tenant_id"])
        self.assertEqual("org:feishu-ai", context["organization_id"])
        self.assertEqual(CHAT_ID, context["chat_id"])
        self.assertEqual("tenant:feishu-prod", permission["actor"]["tenant_id"])
        self.assertEqual("org:feishu-ai", permission["actor"]["organization_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])
        self.assertEqual("organization", permission["requested_visibility"])

    def test_chat_allowlist_ignores_non_sandbox_chat_without_reply(self) -> None:
        event = message_event_from_payload(payload("om_live_wrong_chat", "/health"))
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_ALLOWED_CHAT_IDS": "oc_other_chat"}, clear=False):
            result = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertEqual("chat not in COPILOT_FEISHU_ALLOWED_CHAT_IDS", result["reason"])
        self.assertNotIn("publish", result)

    def test_new_disallowed_group_is_discovered_as_graph_node_without_ingesting_content(self) -> None:
        new_chat_id = "oc_new_product_group"
        event = message_event_from_payload(
            payload(
                "om_live_new_group_discovered",
                "/remember 决定：新群里的真实消息不能在未授权时入库。",
                chat_id=new_chat_id,
            )
        )
        self.assertIsNotNone(event)

        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": CHAT_ID,
                "COPILOT_FEISHU_TENANT_ID": "tenant:feishu-prod",
                "COPILOT_FEISHU_ORGANIZATION_ID": "org:feishu-ai",
            },
            clear=False,
        ):
            result = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertEqual("chat not in COPILOT_FEISHU_ALLOWED_CHAT_IDS", result["reason"])
        self.assertEqual("discovered", result["graph_node"]["status"])
        node = self.conn.execute(
            """
            SELECT node_type, node_key, label, tenant_id, organization_id, status, observation_count
            FROM knowledge_graph_nodes
            WHERE node_type = 'feishu_chat' AND node_key = ?
            """,
            (new_chat_id,),
        ).fetchone()
        self.assertIsNotNone(node)
        self.assertEqual("feishu_chat", node["node_type"])
        self.assertEqual(new_chat_id, node["node_key"])
        self.assertEqual("Feishu group oc_new_product_group", node["label"])
        self.assertEqual("tenant:feishu-prod", node["tenant_id"])
        self.assertEqual("org:feishu-ai", node["organization_id"])
        self.assertEqual("discovered", node["status"])
        self.assertEqual(1, node["observation_count"])
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) AS count FROM raw_events").fetchone()["count"]
        )
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) AS count FROM memories").fetchone()["count"]
        )

    def test_allowed_group_candidate_links_to_discovered_chat_graph_node(self) -> None:
        new_chat_id = "oc_allowed_product_group"
        event = message_event_from_payload(
            payload(
                "om_live_allowed_group_candidate",
                "/remember 决定：新产品群的上线窗口固定为每周四下午。",
                chat_id=new_chat_id,
            )
        )
        self.assertIsNotNone(event)

        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": new_chat_id,
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*",
            },
            clear=False,
        ):
            result = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("active", result["graph_node"]["status"])
        self.assertEqual(new_chat_id, result["graph_node"]["node_key"])
        node = self.conn.execute(
            """
            SELECT node_type, node_key, status, observation_count
            FROM knowledge_graph_nodes
            WHERE node_type = 'feishu_chat' AND node_key = ?
            """,
            (new_chat_id,),
        ).fetchone()
        self.assertIsNotNone(node)
        self.assertEqual("active", node["status"])
        self.assertEqual(1, node["observation_count"])
        raw = self.conn.execute("SELECT raw_json FROM raw_events WHERE source_id = ?", (event.message_id,)).fetchone()
        self.assertIsNotNone(raw)
        self.assertIn(new_chat_id, raw["raw_json"])

    def test_disallowed_group_does_not_create_user_or_message_graph_nodes(self) -> None:
        new_chat_id = "oc_disallowed_private_group"
        event = message_event_from_payload(
            payload(
                "om_live_disallowed_user_message",
                "/remember 决定：未授权群不应记录用户和消息事件。",
                chat_id=new_chat_id,
            )
        )
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_ALLOWED_CHAT_IDS": CHAT_ID}, clear=False):
            result = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertTrue(result["ignored"])
        self.assertEqual(
            2,
            self.conn.execute("SELECT COUNT(*) AS count FROM knowledge_graph_nodes").fetchone()["count"],
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) AS count FROM knowledge_graph_nodes WHERE node_type IN ('feishu_user', 'feishu_message')"
            ).fetchone()["count"],
        )

    def test_allowed_group_records_user_message_and_relationship_edges(self) -> None:
        chat_id = "oc_graph_context_group"
        event = message_event_from_payload(
            payload(
                "om_live_graph_message",
                "/remember 决定：图谱只存消息事件节点，正文仍走 candidate/evidence。",
                chat_id=chat_id,
            )
        )
        self.assertIsNotNone(event)

        with patch.dict(
            os.environ,
            {"COPILOT_FEISHU_ALLOWED_CHAT_IDS": chat_id, "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"},
            clear=False,
        ):
            result = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertTrue(result["ok"])
        user = self.conn.execute(
            "SELECT id, node_key FROM knowledge_graph_nodes WHERE node_type = 'feishu_user' AND node_key = ?",
            ("ou_live_user",),
        ).fetchone()
        message = self.conn.execute(
            "SELECT id, node_key, metadata_json FROM knowledge_graph_nodes WHERE node_type = 'feishu_message'",
        ).fetchone()
        chat = self.conn.execute(
            "SELECT id FROM knowledge_graph_nodes WHERE node_type = 'feishu_chat' AND node_key = ?",
            (chat_id,),
        ).fetchone()
        self.assertIsNotNone(user)
        self.assertIsNotNone(message)
        self.assertIsNotNone(chat)
        self.assertEqual("om_live_graph_message", message["node_key"])
        self.assertIn("raw_text_not_stored_in_graph_node", message["metadata_json"])
        self.assertEqual(
            1,
            self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM knowledge_graph_edges
                WHERE edge_type = 'member_of_feishu_chat'
                  AND source_node_id = ?
                  AND target_node_id = ?
                """,
                (user["id"], chat["id"]),
            ).fetchone()["count"],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM knowledge_graph_edges
                WHERE edge_type = 'sent_feishu_message'
                  AND source_node_id = ?
                  AND target_node_id = ?
                """,
                (user["id"], message["id"]),
            ).fetchone()["count"],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM knowledge_graph_edges
                WHERE edge_type = 'contains_feishu_message'
                  AND source_node_id = ?
                  AND target_node_id = ?
                """,
                (chat["id"], message["id"]),
            ).fetchone()["count"],
        )

    def test_same_user_across_groups_is_one_node_with_group_specific_membership_edges(self) -> None:
        first_chat = "oc_graph_group_one"
        second_chat = "oc_graph_group_two"
        for message_id, chat_id in (
            ("om_live_graph_group_one", first_chat),
            ("om_live_graph_group_two", second_chat),
        ):
            event = message_event_from_payload(
                payload(message_id, "/remember 决定：同一个用户跨群只应有一个用户节点。", chat_id=chat_id)
            )
            self.assertIsNotNone(event)
            with patch.dict(
                os.environ,
                {"COPILOT_FEISHU_ALLOWED_CHAT_IDS": f"{first_chat},{second_chat}", "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"},
                clear=False,
            ):
                handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        user = self.conn.execute(
            "SELECT id FROM knowledge_graph_nodes WHERE node_type = 'feishu_user' AND node_key = 'ou_live_user'"
        ).fetchone()
        self.assertIsNotNone(user)
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) AS count FROM knowledge_graph_nodes WHERE node_type = 'feishu_user' AND node_key = 'ou_live_user'"
            ).fetchone()["count"],
        )
        self.assertEqual(
            2,
            self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM knowledge_graph_edges
                WHERE edge_type = 'member_of_feishu_chat'
                  AND source_node_id = ?
                """,
                (user["id"],),
            ).fetchone()["count"],
        )

    def test_health_redacts_live_ids(self) -> None:
        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": CHAT_ID,
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "ou_sensitive_reviewer",
            },
            clear=False,
        ):
            result = handle_copilot_message_event(
                self.conn,
                message_event_from_payload(payload("om_live_health", "/health")),
                DryRunPublisher(),
                self.config,
                dry_run=True,
            )

        reply = self.reply_text(result)
        self.assertIn("群聊 allowlist：configured (1)", reply)
        self.assertIn("reviewer 配置：configured (1)", reply)
        self.assertNotIn(CHAT_ID, reply)
        self.assertNotIn("ou_sensitive_reviewer", reply)

    def test_missing_reviewer_role_denies_confirm(self) -> None:
        created = self.handle("om_live_create_member", "/remember 决定：OpenClaw 固定 2026.4.24")
        candidate_id = created["tool_result"]["candidate_id"]
        event = message_event_from_payload(payload("om_live_denied", f"/confirm {candidate_id}"))
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": ""}, clear=False):
            denied = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertFalse(denied["tool_result"]["ok"])
        self.assertEqual("permission_denied", denied["tool_result"]["error"]["code"])
        self.assertIn("安全拒绝", self.reply_text(denied))

    def test_interactive_candidate_card_click_confirms_via_current_operator_permission(self) -> None:
        config = FeishuConfig(
            bot_mode="reply",
            default_scope=SCOPE,
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
            card_mode="interactive",
        )
        event = message_event_from_payload(
            payload("om_live_interactive_candidate", "/remember 决定：飞书卡片确认必须可点击。")
        )
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            created = handle_copilot_message_event(self.conn, event, DryRunPublisher(), config, dry_run=True)

        self.assertTrue(created["ok"])
        self.assertEqual("interactive", created["publish"]["mode"])
        card = created["publish"]["card"]
        self.assertIsNotNone(card)
        action_blocks = [element for element in card["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(action_blocks))
        confirm_button = next(action for action in action_blocks[0]["actions"] if action["text"]["content"] == "确认保存")
        self.assertEqual("confirm", confirm_button["value"]["memory_engine_action"])
        self.assertEqual(created["tool_result"]["candidate_id"], confirm_button["value"]["candidate_id"])
        self.assertNotIn("current_context", confirm_button["value"])

        click_event = message_event_from_payload(card_action_payload(confirm_button["value"]))
        self.assertIsNotNone(click_event)
        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            clicked = handle_copilot_message_event(self.conn, click_event, DryRunPublisher(), config, dry_run=True)

        self.assertTrue(clicked["ok"])
        self.assertEqual("memory.confirm", clicked["tool"])
        self.assertEqual(created["tool_result"]["candidate_id"], clicked["tool_result"]["candidate_id"])
        self.assertEqual("active", clicked["tool_result"]["memory"]["status"])
        self.assertTrue(clicked["message_id"].startswith("card_action_"))

    def test_interactive_candidate_card_hides_review_buttons_for_non_reviewer(self) -> None:
        config = FeishuConfig(
            bot_mode="reply",
            default_scope=SCOPE,
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
            card_mode="interactive",
        )
        event = message_event_from_payload(
            payload("om_live_interactive_member_candidate", "/remember 决定：非 reviewer 不能点确认。")
        )
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": ""}, clear=False):
            created = handle_copilot_message_event(self.conn, event, DryRunPublisher(), config, dry_run=True)

        self.assertTrue(created["ok"])
        card = created["publish"]["card"]
        rendered = str(card)
        self.assertNotIn("确认保存", rendered)
        self.assertNotIn("拒绝候选", rendered)

    def test_interactive_candidate_card_secondary_actions_route_to_service(self) -> None:
        config = FeishuConfig(
            bot_mode="reply",
            default_scope=SCOPE,
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
            card_mode="interactive",
        )
        event = message_event_from_payload(
            payload("om_live_interactive_secondary", "/remember 决定：卡片二级动作也必须可用。")
        )
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            created = handle_copilot_message_event(self.conn, event, DryRunPublisher(), config, dry_run=True)

        action_blocks = [element for element in created["publish"]["card"]["elements"] if element.get("tag") == "action"]
        needs_evidence = next(action for action in action_blocks[0]["actions"] if action["text"]["content"] == "要求补证据")
        click_event = message_event_from_payload(card_action_payload(needs_evidence["value"]))
        self.assertIsNotNone(click_event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            clicked = handle_copilot_message_event(self.conn, click_event, DryRunPublisher(), config, dry_run=True)

        self.assertTrue(clicked["ok"])
        self.assertEqual("memory.needs_evidence", clicked["tool"])
        self.assertEqual("needs_evidence", clicked["tool_result"]["status"])
        self.assertEqual("needs_evidence", clicked["tool_result"]["review_status"])

    def test_forged_interactive_card_click_by_non_reviewer_fails_closed(self) -> None:
        config = FeishuConfig(
            bot_mode="reply",
            default_scope=SCOPE,
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
            card_mode="interactive",
        )
        event = message_event_from_payload(
            payload("om_live_interactive_forged", "/remember 决定：伪造卡片点击不能越权。")
        )
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            created = handle_copilot_message_event(self.conn, event, DryRunPublisher(), config, dry_run=True)

        candidate_id = created["tool_result"]["candidate_id"]
        forged_click = message_event_from_payload(
            card_action_payload({"memory_engine_action": "confirm", "candidate_id": candidate_id})
        )
        self.assertIsNotNone(forged_click)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": ""}, clear=False):
            denied = handle_copilot_message_event(self.conn, forged_click, DryRunPublisher(), config, dry_run=True)

        self.assertFalse(denied["tool_result"]["ok"])
        self.assertEqual("memory.confirm", denied["tool"])
        self.assertEqual("permission_denied", denied["tool_result"]["error"]["code"])
        row = self.conn.execute("SELECT status FROM memories WHERE id = ?", (candidate_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual("candidate", row["status"])


if __name__ == "__main__":
    unittest.main()
