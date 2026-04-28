from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.feishu_runtime import FeishuRunLogger


class FeishuRuntimeLoggingTest(unittest.TestCase):
    def test_run_logger_writes_timestamped_ndjson_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FeishuRunLogger(Path(temp_dir) / "feishu-bot")

            logger.write("listen_start", profile="feishu-ai-challenge")
            logger.write("event_result", ok=True, command="reject")

            self.assertTrue(logger.path.exists())
            self.assertTrue(logger.path.name.startswith("feishu-listen-"))
            self.assertTrue(logger.path.name.endswith(".ndjson"))

            records = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["listen_start", "event_result"], [record["event"] for record in records])
            self.assertIn("T", records[0]["ts"])
            self.assertEqual("reject", records[1]["command"])


if __name__ == "__main__":
    unittest.main()
