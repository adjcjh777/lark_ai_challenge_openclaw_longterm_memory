from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from memory_engine.feishu_api_client import run_lark_cli


class FeishuApiClientTest(unittest.TestCase):
    def test_success_result_includes_elapsed_ms(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout='{"data":{"ok":true}}', stderr="")

        with patch("memory_engine.feishu_api_client.subprocess.run", return_value=completed):
            result = run_lark_cli(["drive", "+search"], retries=0)

        self.assertTrue(result.ok)
        self.assertIsInstance(result.elapsed_ms, float)
        self.assertGreaterEqual(result.elapsed_ms, 0.0)

    def test_error_result_includes_elapsed_ms(self) -> None:
        completed = SimpleNamespace(returncode=1, stdout="", stderr="permission denied")

        with patch("memory_engine.feishu_api_client.subprocess.run", return_value=completed):
            result = run_lark_cli(["docs", "+fetch"], retries=0)

        self.assertFalse(result.ok)
        self.assertEqual("permission_denied", result.error_code)
        self.assertIsInstance(result.elapsed_ms, float)
        self.assertGreaterEqual(result.elapsed_ms, 0.0)

    def test_timeout_result_includes_elapsed_ms(self) -> None:
        with patch(
            "memory_engine.feishu_api_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["lark-cli"], timeout=1),
        ):
            result = run_lark_cli(["docs", "+fetch"], retries=0, timeout_seconds=1)

        self.assertFalse(result.ok)
        self.assertEqual("api_error", result.error_code)
        self.assertIsInstance(result.elapsed_ms, float)
        self.assertGreaterEqual(result.elapsed_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
