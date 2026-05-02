from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_cognee_curated_sync_gate
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

    def test_json_mode_redirects_gate_stdout_noise_to_stderr(self) -> None:
        def noisy_gate(**_: object) -> dict[str, object]:
            print("sdk noisy stdout")
            return {"ok": True, "gate": "cognee_curated_sync"}

        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.check_cognee_curated_sync_gate.run_gate",
            side_effect=noisy_gate,
        ):
            data_root = Path(tmp) / "data"
            system_root = Path(tmp) / "system"
            with patch.object(
                check_cognee_curated_sync_gate.sys,
                "argv",
                [
                    "check_cognee_curated_sync_gate.py",
                    "--data-root",
                    str(data_root),
                    "--system-root",
                    str(system_root),
                    "--json",
                ],
            ):
                with patch("sys.stdout") as stdout, patch("sys.stderr") as stderr:
                    check_cognee_curated_sync_gate.main()

        stdout_text = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        stderr_text = "".join(call.args[0] for call in stderr.write.call_args_list if call.args)
        self.assertIn('"ok": true', stdout_text)
        self.assertNotIn("sdk noisy stdout", stdout_text)
        self.assertIn("sdk noisy stdout", stderr_text)


if __name__ == "__main__":
    unittest.main()
