from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_cognee_curated_sync_gate import load_cognee_gate_env_defaults


class CogneeCuratedSyncGateTest(unittest.TestCase):
    def test_env_local_overrides_env_and_process_env_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "LLM_PROVIDER=ollama",
                        "LLM_MODEL=qwen3.5:0.8b",
                        "LLM_ENDPOINT=http://localhost:11434",
                        "LLM_API_KEY=",
                    ]
                ),
                encoding="utf-8",
            )
            (root / ".env.local").write_text(
                "\n".join(
                    [
                        "LLM_PROVIDER=custom",
                        "LLM_MODEL=gpt-5.3-codex-high",
                        "LLM_ENDPOINT=https://right.codes/codex/v1",
                        "LLM_API_KEY=local-secret",
                    ]
                ),
                encoding="utf-8",
            )

            values = load_cognee_gate_env_defaults(
                root=root,
                environ={"LLM_MODEL": "process-model"},
            )

        self.assertEqual("custom", values["LLM_PROVIDER"])
        self.assertEqual("process-model", values["LLM_MODEL"])
        self.assertEqual("https://right.codes/codex/v1", values["LLM_ENDPOINT"])
        self.assertEqual("local-secret", values["LLM_API_KEY"])


if __name__ == "__main__":
    unittest.main()
