from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from memory_engine.db import connect, init_db
from scripts.openclaw_feishu_remember_router import (
    _infer_bot_mentioned_from_lark_message,
    build_remember_payload,
    route_gateway_natural_interaction,
    route_gateway_group_policy,
    route_gateway_memory_search,
    route_gateway_message,
    route_remember_message,
)

SCOPE = "project:feishu_ai_challenge"
CHAT_ID = "oc_openclaw_remember_router_test"
SENDER_OPEN_ID = "ou_openclaw_remember_sender"


class OpenClawFeishuRememberRouterTest(unittest.TestCase):
    def test_build_remember_payload_uses_repo_contract(self) -> None:
        payload = build_remember_payload(
            text="决定：OpenClaw /remember 必须进入 repo candidate pipeline。",
            message_id="om_router_001",
            chat_id=CHAT_ID,
            sender_open_id=SENDER_OPEN_ID,
        )

        self.assertEqual(SCOPE, payload["scope"])
        self.assertEqual("feishu_message", payload["source"]["source_type"])
        self.assertEqual("om_router_001", payload["source"]["source_id"])
        self.assertEqual(CHAT_ID, payload["source"]["source_chat_id"])
        permission = payload["current_context"]["permission"]
        self.assertEqual("tenant:demo", permission["actor"]["tenant_id"])
        self.assertEqual("org:demo", permission["actor"]["organization_id"])
        self.assertEqual(["member"], permission["actor"]["roles"])
        self.assertEqual("fmc_memory_create_candidate", permission["requested_action"])
        self.assertEqual("team", permission["requested_visibility"])
        self.assertEqual("feishu_chat", permission["source_context"]["entrypoint"])
        self.assertEqual(SCOPE, permission["source_context"]["workspace_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])

    def test_route_remember_message_returns_candidate_review_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_remember_message(
                text="/remember 决定：OpenClaw /remember 应直接返回 interactive candidate card。",
                message_id="om_router_002",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("fmc_memory_create_candidate", result["tool_result"]["bridge"]["tool"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        self.assertEqual("interactive", result["publish"]["mode"])
        card = result["card"]
        self.assertEqual(card, result["publish"]["card"])
        action_blocks = [element for element in card["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(action_blocks))
        labels = [action["text"]["content"] for action in action_blocks[0]["actions"]]
        self.assertIn("确认保存", labels)
        self.assertIn("拒绝候选", labels)

    def test_gateway_explicit_remember_keeps_interactive_card_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="/remember 决定：OpenClaw gateway 显式记忆仍返回审核卡片。",
                message_id="om_router_explicit",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("fmc_memory_create_candidate", result["tool_result"]["bridge"]["tool"])
        self.assertIsNotNone(result["card"])
        action_blocks = [element for element in result["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(action_blocks))

    def test_gateway_card_action_json_routes_before_allowlist_silence(self) -> None:
        tool_result = {
            "ok": True,
            "tool": "memory.confirm",
            "candidate_id": "ver_card_action_json",
            "memory_id": "mem_card_action_json",
            "review_status": "confirmed",
            "status": "active",
            "action": "confirmed",
            "memory": {
                "subject": "OpenClaw 卡片点击",
                "current_value": "OpenClaw 卡片点击 JSON 必须进入审核动作。",
                "status": "active",
            },
        }
        card_action_result = {"ok": True, "tool_result": tool_result, "card": {"elements": []}}
        with patch("scripts.openclaw_feishu_card_action_router.route_card_action", return_value=card_action_result) as routed:
            payload = {"candidate_id": "ver_card_action_json", "memory_engine_action": "merge"}
            result = route_gateway_message(
                text=json.dumps(payload, ensure_ascii=False),
                message_id="openclaw_before_dispatch_card_action",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
            )

        self.assertTrue(result["ok"])
        self.assertEqual("openclaw_gateway_card_action_text", result["routing_reason"])
        self.assertEqual("confirmed", result["tool_result"]["review_status"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertFalse(result["publish"]["suppressed"])
        self.assertIs(result["card"], result["publish"]["card"])
        routed.assert_called_once()
        self.assertEqual("merge", routed.call_args.kwargs["action"])
        self.assertEqual("ver_card_action_json", routed.call_args.kwargs["candidate_id"])

    def test_gateway_versions_card_action_json_routes_to_version_chain(self) -> None:
        tool_result = {
            "ok": True,
            "memory_id": "mem_versions_json",
            "scope": SCOPE,
            "subject": "OpenClaw 版本链",
            "status": "active",
            "active_version": {
                "version": 1,
                "version_no": 1,
                "status": "active",
                "value": "OpenClaw 版本链按钮必须给出可见回复。",
                "is_active": True,
            },
            "versions": [
                {
                    "version": 1,
                    "version_no": 1,
                    "status": "active",
                    "value": "OpenClaw 版本链按钮必须给出可见回复。",
                    "is_active": True,
                }
            ],
            "bridge": {
                "tool": "fmc_memory_explain_versions",
                "request_id": "req_versions_json",
                "trace_id": "trace_versions_json",
                "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
            },
        }
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request", return_value=tool_result) as handled:
            result = route_gateway_message(
                text=json.dumps({"memory_id": "mem_versions_json", "memory_engine_action": "versions"}),
                message_id="openclaw_before_dispatch_versions_click",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.explain_versions", result["tool"])
        self.assertEqual("openclaw_gateway_card_action_versions", result["routing_reason"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertIn("记忆版本链", json.dumps(result["card"], ensure_ascii=False))
        handled.assert_called_once()

    def test_gateway_recall_command_routes_to_first_class_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="/recall 部署参数",
                message_id="om_router_recall",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertEqual("openclaw_gateway_memory_search", result["routing_reason"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertEqual("", result["publish"]["text"])
        self.assertIs(result["card"], result["publish"]["card"])
        bridge = result["tool_result"]["bridge"]
        self.assertEqual("fmc_memory_search", bridge["tool"])
        self.assertEqual("allow", bridge["permission_decision"]["decision"])
        self.assertEqual("openclaw_gateway_live", bridge["permission_decision"]["source_entrypoint"])
        self.assertNotIn("intent_resolution", result)

    def test_gateway_tool_helpers_disable_cognee_auto_init_for_fast_replies(self) -> None:
        tool_result = {
            "ok": True,
            "query": "部署参数",
            "results": [],
            "bridge": {
                "tool": "fmc_memory_search",
                "request_id": "req_fast_gateway_reply",
                "trace_id": "trace_fast_gateway_reply",
                "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
            },
        }
        with patch("scripts.openclaw_feishu_remember_router.CopilotService") as service_cls, patch(
            "scripts.openclaw_feishu_remember_router.handle_tool_request", return_value=tool_result
        ):
            result = route_gateway_memory_search(
                text="/recall 部署参数",
                message_id="om_router_fast_reply",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                query="部署参数",
            )

        self.assertTrue(result["ok"])
        service_cls.assert_called_once()
        self.assertIs(service_cls.call_args.kwargs["auto_init_cognee"], False)

    def test_gateway_bot_mentioned_natural_question_routes_to_search_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="@Feishu Memory Engine bot 生产部署 region 当前应该是什么？",
                message_id="om_router_natural_search",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=True,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertEqual("openclaw_gateway_natural_search", result["routing_reason"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertFalse(result["publish"]["suppressed"])
        self.assertEqual("natural_language", result["intent_resolution"]["mode"])
        self.assertEqual("natural_language_slow_path", result["intent_resolution"]["latency_class"])
        self.assertEqual("search", result["intent_resolution"]["intent"])
        self.assertEqual("deterministic_fallback", result["intent_resolution"]["resolver"])
        bridge = result["tool_result"]["bridge"]
        self.assertEqual("fmc_memory_search", bridge["tool"])

    def test_gateway_natural_search_uses_compact_single_answer_with_chat_time_evidence(self) -> None:
        tool_result = {
            "ok": True,
            "query": "生产部署 region 当前应该是什么？",
            "results": [
                {
                    "memory_id": "mem_prod_region",
                    "subject": "生产部署",
                    "current_value": "不对，生产部署 region 改成 ap-shanghai，仍必须加 --canary",
                    "status": "active",
                    "version": 5,
                    "evidence": [
                        {
                            "source_type": "feishu_message",
                            "source_id": "om_evidence",
                            "source_chat_id": CHAT_ID,
                            "created_at": "2026-04-28T10:46:00+08:00",
                            "quote": "不对，生产部署 region 改成 ap-shanghai，仍必须加 --canary",
                        }
                    ],
                    "matched_via": ["keyword_index"],
                },
                {
                    "memory_id": "mem_irrelevant",
                    "subject": "Dashboard",
                    "current_value": "irrelevant",
                    "evidence": [{"quote": "irrelevant"}],
                },
            ],
            "bridge": {
                "tool": "fmc_memory_search",
                "request_id": "req_demo",
                "trace_id": "trace_demo",
                "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
            },
        }
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request", return_value=tool_result):
            with patch("scripts.openclaw_feishu_remember_router._lookup_lark_chat_name", return_value="Feishu Memory Engine 测试群"):
                result = route_gateway_memory_search(
                    text="@Feishu Memory Engine bot 生产部署 region 当前应该是什么？",
                    message_id="om_router_compact_natural",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    query="生产部署 region 当前应该是什么？",
                    intent_resolution={"mode": "natural_language", "intent": "search"},
                    routing_reason="openclaw_gateway_natural_search",
                )

        card_text = json.dumps(result["card"], ensure_ascii=False)
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertIn("当前答案", card_text)
        self.assertIn("不对，生产部署 region 改成 ap-shanghai，仍必须加 --canary", card_text)
        self.assertIn("群聊：Feishu Memory Engine 测试群", card_text)
        self.assertIn("时间：2026-04-28 10:46", card_text)
        self.assertIn("消息：om_evidence", card_text)
        self.assertIn("旧版本已被 superseded", card_text)
        self.assertNotIn("当前结论 2", card_text)
        self.assertNotIn("Dashboard", card_text)

    def test_gateway_infers_at_mention_from_real_message_id_before_allowlist_ignore(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router._infer_bot_mentioned_from_lark_message", return_value=True):
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "memory.sqlite"
                conn = connect(db_path)
                init_db(conn)
                conn.close()

                result = route_gateway_message(
                    text="生产部署 region 当前应该是什么？",
                    message_id="om_router_inferred_mention",
                    chat_id="oc_not_allowlisted_but_mentioned",
                    sender_open_id=SENDER_OPEN_ID,
                    chat_type="group",
                    bot_mentioned=False,
                    allowlist_chat_ids=[],
                    db_path=str(db_path),
                )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertEqual("openclaw_gateway_natural_search", result["routing_reason"])
        self.assertFalse(result["publish"]["suppressed"])
        self.assertTrue(result["intent_resolution"]["visible_reply_required"])

    def test_mention_lookup_honors_lark_cli_profile_env(self) -> None:
        payload = {
            "data": {
                "messages": [
                    {
                        "content": "hello",
                        "mentions": [{"name": "Feishu Memory Engine bot", "id": "ou_bot"}],
                    }
                ]
            }
        }
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

        with patch.dict("os.environ", {"LARK_CLI_PROFILE": "feishu-ai-challenge"}, clear=False), patch(
            "scripts.openclaw_feishu_remember_router.subprocess.run",
            side_effect=fake_run,
        ):
            self.assertTrue(_infer_bot_mentioned_from_lark_message("om_x_profile_lookup"))

        self.assertIn("--profile", calls[0])
        self.assertIn("feishu-ai-challenge", calls[0])

    def test_gateway_direct_message_natural_question_routes_to_search_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="生产部署 region 当前应该是什么？",
                message_id="om_router_dm_natural_search",
                chat_id="oc_dm_thread",
                sender_open_id=SENDER_OPEN_ID,
                chat_type="p2p",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertEqual("openclaw_gateway_natural_search", result["routing_reason"])
        self.assertFalse(result["publish"]["suppressed"])

    def test_gateway_health_command_with_suffix_does_not_fall_through_to_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="/health 赛前总检 run",
                message_id="om_router_health_suffix",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="p2p",
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.health", result["tool"])
        self.assertEqual("openclaw_gateway_health", result["routing_reason"])
        self.assertIn("Copilot 健康状态", json.dumps(result["card"], ensure_ascii=False))

    def test_gateway_bot_mentioned_natural_candidate_returns_visible_review_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="记住：生产部署 region 以后统一改成 ap-shanghai，仍必须加 --canary。",
                message_id="om_router_natural_candidate",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=True,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("openclaw_gateway_natural_candidate", result["routing_reason"])
        self.assertEqual("create_candidate", result["intent_resolution"]["intent"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertFalse(result["publish"]["suppressed"])
        self.assertIsNotNone(result["card"])

    def test_gateway_bot_mentioned_natural_prefetch_routes_to_prefetch_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="请准备今天上线前 checklist",
                message_id="om_router_natural_prefetch",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=True,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.prefetch", result["tool"])
        self.assertEqual("openclaw_gateway_natural_prefetch", result["routing_reason"])
        self.assertEqual("prefetch", result["intent_resolution"]["intent"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertFalse(result["publish"]["suppressed"])

    def test_gateway_natural_router_uses_llm_intent_when_enabled(self) -> None:
        with patch(
            "scripts.openclaw_feishu_remember_router._classify_natural_language_intent_with_llm",
            return_value={"intent": "prefetch", "query": "LLM 识别的上线任务", "resolver": "llm"},
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "memory.sqlite"
                conn = connect(db_path)
                init_db(conn)
                conn.close()

                result = route_gateway_natural_interaction(
                    text="帮我处理一下今天上线",
                    message_id="om_router_llm_natural_prefetch",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    chat_type="group",
                    bot_mentioned=True,
                    allowlist_chat_ids=[],
                    db_path=str(db_path),
                )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.prefetch", result["tool"])
        self.assertEqual("llm", result["intent_resolution"]["resolver"])
        self.assertEqual("LLM 识别的上线任务", result["tool_result"]["task"])

    def test_gateway_prefetch_command_routes_to_first_class_prefetch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="/prefetch 生成上线 checklist",
                message_id="om_router_prefetch",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.prefetch", result["tool"])
        self.assertEqual("openclaw_gateway_memory_prefetch", result["routing_reason"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertEqual("", result["publish"]["text"])
        self.assertIs(result["card"], result["publish"]["card"])
        bridge = result["tool_result"]["bridge"]
        self.assertEqual("fmc_memory_prefetch", bridge["tool"])
        self.assertEqual("allow", bridge["permission_decision"]["decision"])
        self.assertEqual("openclaw_gateway_live", bridge["permission_decision"]["source_entrypoint"])

    def test_gateway_review_command_routes_to_private_review_inbox_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            with patch.dict(
                "os.environ",
                {
                    "COPILOT_FEISHU_REVIEWER_OPEN_IDS": SENDER_OPEN_ID,
                    "OPENCLAW_FEISHU_REVIEW_DRY_RUN": "1",
                },
                clear=False,
            ):
                for index in range(5):
                    route_gateway_message(
                        text=f"/remember 决定：OpenClaw gateway /review 第 {index} 条候选应进入审核收件箱。",
                        message_id=f"om_router_review_create_{index}",
                        chat_id=CHAT_ID,
                        sender_open_id=SENDER_OPEN_ID,
                        chat_type="group",
                        bot_mentioned=False,
                        allowlist_chat_ids=[],
                        db_path=str(db_path),
                    )
                result = route_gateway_message(
                    text="/review",
                    message_id="om_router_review_inbox",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    chat_type="group",
                    bot_mentioned=False,
                    allowlist_chat_ids=[],
                    db_path=str(db_path),
                )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.review_inbox", result["tool"])
        self.assertEqual("openclaw_gateway_review_inbox", result["routing_reason"])
        self.assertEqual("private_review_dm", result["disposition"])
        self.assertLessEqual(len(result["tool_result"]["items"]), 3)
        action_blocks = [element for element in result["card"]["elements"] if element.get("tag") == "action"]
        self.assertLessEqual(len(action_blocks), 3)
        self.assertEqual("dm", result["publish"]["delivery_mode"])
        self.assertEqual([SENDER_OPEN_ID], result["publish"]["targets"])
        self.assertEqual([SENDER_OPEN_ID], result["publish"]["card"]["open_ids"])
        self.assertEqual("review_inbox", result["message_disposition"]["memory_path"])

    def test_gateway_unmentioned_allowlist_group_message_creates_silent_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="决定：OpenClaw gateway live 静默候选入口必须走 CopilotService，负责人是程俊豪，截止周五。",
                message_id="om_router_silent_candidate",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("passive_candidate_probe", result["routing_reason"])
        self.assertIsNone(result["card"])
        self.assertEqual("silent_no_reply", result["disposition"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])
        self.assertTrue(result["publish"]["suppressed"])
        self.assertEqual("silent_candidate_probe", result["message_disposition"]["memory_path"])
        self.assertEqual("passive_group_detection", result["message_disposition"]["reason_code"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        bridge = result["tool_result"]["bridge"]
        self.assertEqual("fmc_memory_create_candidate", bridge["tool"])
        self.assertEqual("allow", bridge["permission_decision"]["decision"])
        self.assertEqual("scope_access_granted", bridge["permission_decision"]["reason_code"])
        self.assertEqual("openclaw_gateway_live", bridge["permission_decision"]["source_entrypoint"])

    def test_gateway_unmentioned_plain_question_is_ignored_without_tool_call(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request") as handle:
            result = route_gateway_message(
                text="生产部署 region 是什么？",
                message_id="om_router_plain_question",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
            )

        handle.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertIsNone(result["card"])
        self.assertEqual("silent_no_reply", result["disposition"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])
        self.assertEqual("low_memory_signal", result["message_disposition"]["reason_code"])

    def test_gateway_unmentioned_low_signal_message_is_ignored_without_tool_call(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request") as handle:
            result = route_gateway_message(
                text="大家下午三点喝咖啡。",
                message_id="om_router_low_signal",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
            )

        handle.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertIsNone(result["card"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])
        self.assertEqual("low_memory_signal", result["message_disposition"]["reason_code"])

    def test_gateway_non_allowlist_group_message_is_ignored_without_tool_call(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request") as handle:
            result = route_gateway_message(
                text="决定：这个群不在 allowlist，不应该进入候选。",
                message_id="om_router_not_allowlisted",
                chat_id="oc_not_allowlisted",
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
            )

        handle.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertIsNone(result["card"])
        self.assertEqual("chat_not_allowlisted", result["message_disposition"]["reason_code"])

    def test_gateway_enabled_group_policy_allows_passive_message_without_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            with patch.dict("os.environ", {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": SENDER_OPEN_ID}, clear=False):
                enabled = route_gateway_group_policy(
                    text="/enable_memory",
                    message_id="om_router_policy_enable_for_passive",
                    chat_id="oc_policy_enabled_not_allowlisted",
                    sender_open_id=SENDER_OPEN_ID,
                    action="enable",
                    db_path=str(db_path),
                )
                result = route_gateway_message(
                    text="决定：启用群策略后非 allowlist 群也要静默进入候选，负责人是程俊豪。",
                    message_id="om_router_policy_passive",
                    chat_id="oc_policy_enabled_not_allowlisted",
                    sender_open_id=SENDER_OPEN_ID,
                    chat_type="group",
                    bot_mentioned=False,
                    allowlist_chat_ids=[],
                    db_path=str(db_path),
                )

        self.assertTrue(enabled["tool_result"]["ok"], enabled)
        self.assertTrue(result["ok"], result)
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("passive_candidate_probe", result["routing_reason"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])

    def test_gateway_group_settings_returns_pending_policy_card_without_live_listener(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="/settings",
                message_id="om_router_settings",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.group_settings", result["tool"])
        self.assertEqual("openclaw_gateway_group_settings", result["routing_reason"])
        self.assertEqual("openclaw_gateway_live", result["source_entrypoint"])
        self.assertEqual("pending_onboarding", result["tool_result"]["chat_status"])
        self.assertFalse(result["tool_result"]["passive_memory_enabled"])
        self.assertIsNotNone(result["card"])
        self.assertEqual("group_settings", result["message_disposition"]["memory_path"])

    def test_gateway_natural_group_memory_query_replies_even_when_not_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="当前群记忆",
                message_id="om_router_natural_settings",
                chat_id="oc_not_allowlisted_status_query",
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.group_settings", result["tool"])
        self.assertEqual("interactive", result["publish"]["mode"])
        self.assertEqual("group_settings", result["message_disposition"]["memory_path"])
        self.assertEqual("pending_onboarding", result["tool_result"]["chat_status"])

    def test_gateway_enable_memory_by_reviewer_writes_group_policy_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            with patch.dict("os.environ", {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": SENDER_OPEN_ID}, clear=False):
                result = route_gateway_group_policy(
                    text="/enable_memory",
                    message_id="om_router_enable",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    action="enable",
                    db_path=str(db_path),
                )

            conn = connect(db_path)
            try:
                policy = conn.execute(
                    "SELECT status, passive_memory_enabled FROM feishu_group_policies WHERE chat_id = ?",
                    (CHAT_ID,),
                ).fetchone()
                audit = conn.execute(
                    """
                    SELECT permission_decision, reason_code, source_context
                    FROM memory_audit_events
                    WHERE event_type = 'feishu_group_policy_enabled'
                    """
                ).fetchone()
            finally:
                conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.group_enable_memory", result["tool"])
        self.assertEqual("enabled", result["tool_result"]["status"])
        self.assertEqual("active", policy["status"])
        self.assertEqual(1, policy["passive_memory_enabled"])
        self.assertEqual("allow", audit["permission_decision"])
        self.assertEqual("authorized_group_memory_enable", audit["reason_code"])
        self.assertIn("openclaw_gateway_live", audit["source_context"])

    def test_gateway_enable_memory_by_member_is_denied_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            with patch.dict("os.environ", {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": ""}, clear=False):
                result = route_gateway_message(
                    text="/enable_memory",
                    message_id="om_router_enable_denied",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    chat_type="group",
                    bot_mentioned=False,
                    db_path=str(db_path),
                )

            conn = connect(db_path)
            try:
                active_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM feishu_group_policies WHERE chat_id = ? AND status = 'active'",
                    (CHAT_ID,),
                ).fetchone()["count"]
                audit = conn.execute(
                    """
                    SELECT permission_decision, reason_code, source_context
                    FROM memory_audit_events
                    WHERE event_type = 'feishu_group_policy_denied'
                    """
                ).fetchone()
            finally:
                conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.group_enable_memory", result["tool"])
        self.assertFalse(result["tool_result"]["ok"])
        self.assertEqual("permission_denied", result["tool_result"]["status"])
        card_text = json.dumps(result["card"], ensure_ascii=False)
        self.assertIn("普通成员不能开启非 @ 静默企业记忆提取", card_text)
        self.assertIn("OpenClaw gateway group policy gate", card_text)
        self.assertEqual(0, active_count)
        self.assertEqual("deny", audit["permission_decision"])
        self.assertEqual("reviewer_or_admin_required", audit["reason_code"])
        self.assertIn("openclaw_gateway_live", audit["source_context"])

    def test_gateway_enable_memory_with_visible_mention_prefix_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            with patch.dict("os.environ", {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": ""}, clear=False):
                result = route_gateway_message(
                    text="@测试 bot /enable_memory",
                    message_id="om_router_enable_denied_mention_prefix",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    chat_type="group",
                    bot_mentioned=False,
                    db_path=str(db_path),
                )

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.group_enable_memory", result["tool"])
        self.assertFalse(result["tool_result"]["ok"])
        self.assertEqual("permission_denied", result["tool_result"]["status"])
        self.assertEqual("/enable_memory", result["input_text"])

    def test_gateway_disable_memory_by_reviewer_closes_passive_screening(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            with patch.dict("os.environ", {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": SENDER_OPEN_ID}, clear=False):
                route_gateway_group_policy(
                    text="/enable_memory",
                    message_id="om_router_enable_before_disable",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    action="enable",
                    db_path=str(db_path),
                )
                result = route_gateway_group_policy(
                    text="/disable_memory",
                    message_id="om_router_disable",
                    chat_id=CHAT_ID,
                    sender_open_id=SENDER_OPEN_ID,
                    action="disable",
                    db_path=str(db_path),
                )

            conn = connect(db_path)
            try:
                policy = conn.execute(
                    "SELECT status, passive_memory_enabled FROM feishu_group_policies WHERE chat_id = ?",
                    (CHAT_ID,),
                ).fetchone()
            finally:
                conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual("copilot.group_disable_memory", result["tool"])
        self.assertEqual("disabled", result["tool_result"]["status"])
        self.assertEqual("disabled", policy["status"])
        self.assertEqual(0, policy["passive_memory_enabled"])


if __name__ == "__main__":
    unittest.main()
