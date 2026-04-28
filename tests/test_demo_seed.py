from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from scripts.demo_seed import build_replay, seed_demo_memories

SCOPE = "project:feishu_ai_challenge"


class DemoSeedReplayTest(unittest.TestCase):
    def test_demo_replay_steps_are_all_green(self) -> None:
        with tempfile.TemporaryDirectory(prefix="demo_seed_test_") as temp_dir:
            db_path = Path(temp_dir) / "demo.sqlite"
            conn = connect(db_path)
            try:
                init_db(conn)
                repo = MemoryRepository(conn)
                seed_demo_memories(conn, SCOPE)
                replay = build_replay(repo, SCOPE, str(db_path), persistent=False)
            finally:
                conn.close()

        failed_steps = [
            step["name"]
            for step in replay["steps"]
            if isinstance(step.get("output"), dict) and not step["output"].get("ok")
        ]
        self.assertEqual([], failed_steps)
        self.assertTrue(replay["openclaw_example_contract"]["ok"])
        self.assertFalse(replay["production_feishu_write"])

    def test_demo_replay_uses_explicit_permission_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="demo_seed_test_") as temp_dir:
            db_path = Path(temp_dir) / "demo.sqlite"
            conn = connect(db_path)
            try:
                init_db(conn)
                repo = MemoryRepository(conn)
                seed_demo_memories(conn, SCOPE)
                replay = build_replay(repo, SCOPE, str(db_path), persistent=False)
            finally:
                conn.close()

        tool_steps = [step for step in replay["steps"] if step["tool"].startswith("memory.")]
        self.assertGreaterEqual(len(tool_steps), 3)
        for step in tool_steps:
            permission = step["input"]["current_context"]["permission"]
            self.assertEqual(step["tool"], permission["requested_action"])
            self.assertEqual(SCOPE, permission["source_context"]["workspace_id"])


if __name__ == "__main__":
    unittest.main()
