from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_engine.copilot.local_env import (
    env_overrides_for_embedding_config,
    load_local_env_files,
    read_key_value_file,
)


class LocalEnvTest(unittest.TestCase):
    def test_env_local_overrides_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "LLM_MODEL=old-model\nEMBEDDING_MODEL=ollama/qwen3\n",
                encoding="utf-8",
            )
            (root / ".env.local").write_text(
                "LLM_MODEL=deepseek-v4-flash\nEMBEDDING_MODEL=openai/text-embedding-v4\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                loaded = load_local_env_files(root=root, override=True)

                self.assertEqual("deepseek-v4-flash", os.environ["LLM_MODEL"])
                self.assertEqual("openai/text-embedding-v4", os.environ["EMBEDDING_MODEL"])
                self.assertEqual("openai/text-embedding-v4", loaded["EMBEDDING_MODEL"])

    def test_read_key_value_file_strips_quotes_and_ignores_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env.local"
            path.write_text(
                "# comment\nLLM_PROVIDER='custom'\nEMPTY_LINE_SKIP\nEMBEDDING_DIMENSIONS=\"1024\"\n",
                encoding="utf-8",
            )

            self.assertEqual(
                {"LLM_PROVIDER": "custom", "EMBEDDING_DIMENSIONS": "1024"},
                read_key_value_file(path),
            )

    def test_embedding_env_overrides_use_runtime_names(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EMBEDDING_PROVIDER": "openai_compatible",
                "EMBEDDING_MODEL": "openai/text-embedding-v4",
                "EMBEDDING_ENDPOINT": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "EMBEDDING_DIMENSIONS": "1024",
            },
            clear=True,
        ):
            self.assertEqual(
                {
                    "provider": "openai_compatible",
                    "litellm_model": "openai/text-embedding-v4",
                    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "dimensions": "1024",
                },
                env_overrides_for_embedding_config(),
            )


if __name__ == "__main__":
    unittest.main()
