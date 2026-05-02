from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from scripts.openclaw_feishu_card_action_router import route_card_action
from scripts.openclaw_feishu_remember_router import route_remember_message

CHAT_ID = "oc_openclaw_card_router_test"
OWNER_OPEN_ID = "ou_openclaw_card_owner"
OTHER_OPEN_ID = "ou_other_member"


class OpenClawFeishuCardActionRouterTest(unittest.TestCase):
    def test_owner_confirm_returns_final_status_card_without_buttons(self) -> None:
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
        self.assertEqual(["撤销这次处理"], [action["text"]["content"] for action in actions[0]["actions"]])

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
        self.assertEqual(["撤销这次处理"], [action["text"]["content"] for action in actions[0]["actions"]])

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
        self.assertEqual(["撤销这次处理"], [action["text"]["content"] for action in actions[0]["actions"]])

    def test_reject_conflict_version_final_card_shows_rejected_candidate_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            first = route_remember_message(
                text="/remember 决定：冲突拒绝测试旧值。",
                message_id="om_reject_conflict_value_001",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            route_card_action(
                action="confirm",
                candidate_id=first["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_reject_conflict_initial",
                db_path=str(db_path),
            )
            conflict = route_remember_message(
                text="/remember 决定：冲突拒绝测试新候选值。",
                message_id="om_reject_conflict_value_002",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )

            rejected = route_card_action(
                action="reject",
                candidate_id=conflict["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_reject_conflict_value",
                db_path=str(db_path),
            )

        rendered = str(rejected["card"])
        self.assertTrue(rejected["ok"])
        self.assertEqual("rejected", rejected["tool_result"]["review_status"])
        self.assertIn("冲突拒绝测试新候选值", rendered)
        self.assertNotIn("冲突拒绝测试旧值", rendered)

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
        self.assertEqual(["撤销这次处理"], [action["text"]["content"] for action in actions[0]["actions"]])

    def test_owner_undo_after_confirm_returns_candidate_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            created = route_remember_message(
                text="/remember 决定：确认后撤销必须回到候选态。",
                message_id="om_owner_undo_001",
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
                token="card_action_undo_confirm_first",
                db_path=str(db_path),
            )
            undone = route_card_action(
                action="undo",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_undo_confirm_second",
                db_path=str(db_path),
            )

        self.assertTrue(undone["ok"])
        self.assertEqual("memory.undo_review", undone["tool_result"]["bridge"]["tool"])
        self.assertEqual("candidate", undone["tool_result"]["memory"]["status"])
        actions = [element for element in undone["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(actions))

    def test_replayed_confirm_token_after_undo_does_not_confirm_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            created = route_remember_message(
                text="/remember 决定：旧确认 token 重放不能覆盖撤销结果。",
                message_id="om_owner_replay_001",
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
                token="card_action_replay_confirm",
                db_path=str(db_path),
            )
            route_card_action(
                action="undo",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_replay_undo",
                db_path=str(db_path),
            )
            replayed = route_card_action(
                action="confirm",
                candidate_id=candidate_id,
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_replay_confirm",
                db_path=str(db_path),
            )

        self.assertTrue(replayed["ok"])
        self.assertTrue(replayed["tool_result"]["idempotent"])
        self.assertEqual("card_action_token_already_processed", replayed["tool_result"]["idempotent_reason"])
        self.assertEqual("candidate", replayed["tool_result"]["memory"]["status"])
        self.assertEqual("pending", replayed["tool_result"]["review_status"])

    def test_merge_action_confirms_conflict_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            first = route_remember_message(
                text="/remember 决定：合并入口旧值 A。",
                message_id="om_merge_action_001",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            route_card_action(
                action="confirm",
                candidate_id=first["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_merge_initial",
                db_path=str(db_path),
            )
            conflict = route_remember_message(
                text="/remember 决定：合并入口新值 B。",
                message_id="om_merge_action_002",
                chat_id=CHAT_ID,
                sender_open_id=OWNER_OPEN_ID,
                db_path=str(db_path),
            )
            merged = route_card_action(
                action="merge",
                candidate_id=conflict["tool_result"]["candidate_id"],
                chat_id=CHAT_ID,
                operator_open_id=OWNER_OPEN_ID,
                token="card_action_merge_confirm",
                db_path=str(db_path),
            )

        self.assertTrue(merged["ok"])
        self.assertEqual("fmc_memory_confirm", merged["tool_result"]["bridge"]["tool"])
        self.assertEqual("confirmed", merged["tool_result"]["review_status"])
        self.assertIn("合并入口新值 B", merged["tool_result"]["memory"]["current_value"])


if __name__ == "__main__":
    unittest.main()
