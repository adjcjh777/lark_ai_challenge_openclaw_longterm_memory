from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from scripts.openclaw_feishu_card_action_router import route_card_action
from scripts.openclaw_feishu_remember_router import route_remember_message

CHAT_ID = "oc_openclaw_card_router_test"
OWNER_OPEN_ID = "ou_openclaw_card_owner"
OTHER_OPEN_ID = "ou_other_member"


class OpenClawFeishuCardActionRouterTest(unittest.TestCase):
    def test_owner_confirm_returns_locked_status_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            created = route_remember_message(
                text="/remember 决定：owner 点击确认后其他按钮应变灰。",
                message_id="om_owner_action_001",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            candidate_id = created["tool_result"]["candidate_id"]

            confirmed = route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_owner_confirm",
                db_path=str(db_path),
            )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("fmc_memory_confirm", confirmed["tool_result"]["bridge"]["tool"])
        self.assertEqual("confirmed", confirmed["tool_result"]["review_status"])
        actions = [element for element in confirmed["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(actions))
        labels = [action["text"]["content"] for action in actions[0]["actions"]]
        self.assertEqual(["确认保存", "拒绝候选", "要求补证据", "标记过期"], labels)
        self.assertTrue(all(action.get("disabled") for action in actions[0]["actions"]))
        self.assertEqual("primary", actions[0]["actions"][0]["type"])
        self.assertEqual("default", actions[0]["actions"][1]["type"])

    def test_non_owner_confirm_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            created = route_remember_message(
                text="/remember 决定：非 owner 点击确认必须失败。",
                message_id="om_owner_action_002",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            candidate_id = created["tool_result"]["candidate_id"]

            denied = route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OTHER_OPEN_ID,
                token="card_action_other_confirm",
                db_path=str(db_path),
            )

        self.assertFalse(denied["ok"])
        self.assertEqual("permission_denied", denied["tool_result"]["error"]["code"])

    def test_conflict_version_creator_can_confirm_when_parent_owner_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            first = route_remember_message(
                text="/remember 决定：冲突版本 owner 回退测试值 A。",
                message_id="om_conflict_owner_action_001",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            route_card_action(
                action="confirm",
                candidate_id=first["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_initial_confirm",
                db_path=str(db_path),
            )

            conn = connect(db_path)
            conn.execute(
                "UPDATE memories SET owner_id = NULL WHERE id = ?",
                (first["tool_result"]["memory_id"],),
            )
            conn.commit()
            conn.close()

            conflict = route_remember_message(
                text="/remember 决定：冲突版本 owner 回退测试值 B。",
                message_id="om_conflict_owner_action_002",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            self.assertTrue(conflict["tool_result"]["candidate_id"].startswith("ver_"))

            confirmed = route_card_action(
                action="confirm",
                candidate_id=conflict["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_conflict_owner_confirm",
                db_path=str(db_path),
            )

        self.assertTrue(confirmed["ok"])
        self.assertEqual("confirmed", confirmed["tool_result"]["review_status"])

    def test_duplicate_confirm_returns_confirmed_card_instead_of_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            created = route_remember_message(
                text="/remember 决定：重复点击确认必须保持 confirmed，不得覆盖失败卡。",
                message_id="om_duplicate_confirm_001",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            candidate_id = created["tool_result"]["candidate_id"]
            first = route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_duplicate_confirm_first",
                db_path=str(db_path),
            )
            second = route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_duplicate_confirm_second",
                db_path=str(db_path),
            )

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["tool_result"]["idempotent"])
        self.assertEqual("confirmed", second["tool_result"]["review_status"])
        actions = [element for element in second["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(actions))
        self.assertTrue(all(action.get("disabled") for action in actions[0]["actions"]))
        self.assertEqual("primary", actions[0]["actions"][0]["type"])

    def test_reject_after_confirm_returns_current_confirmed_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            created = route_remember_message(
                text="/remember 决定：确认后的拒绝事件必须按当前状态幂等返回。",
                message_id="om_duplicate_confirm_002",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            candidate_id = created["tool_result"]["candidate_id"]
            route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_confirm_before_late_reject",
                db_path=str(db_path),
            )
            late_reject = route_card_action(
                action="reject",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_late_reject_after_confirm",
                db_path=str(db_path),
            )

        self.assertTrue(late_reject["ok"])
        self.assertTrue(late_reject["tool_result"]["idempotent"])
        self.assertEqual("confirmed", late_reject["tool_result"]["review_status"])
        actions = [element for element in late_reject["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual("primary", actions[0]["actions"][0]["type"])
        self.assertEqual("default", actions[0]["actions"][1]["type"])

    def test_duplicate_confirm_on_conflict_version_returns_confirmed_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            first = route_remember_message(
                text="/remember 决定：冲突版本重复确认初始值 A。",
                message_id="om_duplicate_version_confirm_001",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            route_card_action(
                action="confirm",
                candidate_id=first["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_duplicate_version_initial",
                db_path=str(db_path),
            )
            conflict = route_remember_message(
                text="/remember 决定：冲突版本重复确认新值 B。",
                message_id="om_duplicate_version_confirm_002",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            candidate_id = conflict["tool_result"]["candidate_id"]
            self.assertTrue(candidate_id.startswith("ver_"))
            route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_duplicate_version_first",
                db_path=str(db_path),
            )
            duplicate = route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_duplicate_version_second",
                db_path=str(db_path),
            )

        self.assertTrue(duplicate["ok"])
        self.assertTrue(duplicate["tool_result"]["idempotent"])
        self.assertEqual("confirmed", duplicate["tool_result"]["review_status"])
        actions = [element for element in duplicate["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual("primary", actions[0]["actions"][0]["type"])
        self.assertTrue(all(action.get("disabled") for action in actions[0]["actions"]))


if __name__ == "__main__":
    unittest.main()
