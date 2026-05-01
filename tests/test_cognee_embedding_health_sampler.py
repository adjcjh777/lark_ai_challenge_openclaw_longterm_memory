from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.sample_cognee_embedding_health import (
    _embedding_check_command,
    _parse_json,
    sample_embedding_health,
)


class CogneeEmbeddingHealthSamplerTest(unittest.TestCase):
    def test_appends_timestamped_samples_for_collector_input(self) -> None:
        with tempfile.TemporaryDirectory(prefix="embedding_sampler_") as temp_dir:
            output = Path(temp_dir) / "samples.ndjson"
            result = sample_embedding_health(
                output=output,
                sample_count=2,
                sample_interval_seconds=0,
                checker=_passing_checker,
                now_fn=_clock(
                    "2026-05-01T00:00:00+00:00",
                    "2026-05-01T12:00:00+00:00",
                    "2026-05-01T12:00:01+00:00",
                ),
                sleep_fn=lambda _seconds: None,
            )
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(result["ok"], result)
        self.assertEqual(2, result["successful_sample_count"])
        self.assertEqual("2026-05-01T00:00:00+00:00", rows[0]["sampled_at"])
        self.assertEqual(1, rows[0]["sample_index"])
        self.assertEqual("http://embedding.internal", rows[0]["endpoint"])
        self.assertIn("collect_cognee_embedding_long_run_evidence.py", result["collector_command_hint"])

    def test_failed_sample_is_preserved_without_stopping_collection(self) -> None:
        calls = {"count": 0}

        def checker(_command: list[str], _timeout: float) -> dict[str, object]:
            calls["count"] += 1
            if calls["count"] == 1:
                return _sample(ok=False, status="blocked")
            return _sample()

        with tempfile.TemporaryDirectory(prefix="embedding_sampler_") as temp_dir:
            output = Path(temp_dir) / "samples.ndjson"
            result = sample_embedding_health(
                output=output,
                sample_count=2,
                checker=checker,
                now_fn=_clock(
                    "2026-05-01T00:00:00+00:00",
                    "2026-05-01T01:00:00+00:00",
                    "2026-05-01T01:00:01+00:00",
                ),
                sleep_fn=lambda _seconds: None,
            )
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertFalse(result["ok"], result)
        self.assertEqual(1, result["failed_sample_count"])
        self.assertEqual(2, len(rows))
        self.assertFalse(rows[0]["ok"])
        self.assertTrue(rows[1]["ok"])

    def test_command_includes_optional_provider_overrides(self) -> None:
        command = _embedding_check_command(
            text="sample",
            model="openai/text-embedding-3-large",
            endpoint="https://embedding.internal/v1",
            dimensions=3072,
            timeout=7.5,
        )

        self.assertIn("--model", command)
        self.assertIn("openai/text-embedding-3-large", command)
        self.assertIn("--endpoint", command)
        self.assertIn("https://embedding.internal/v1", command)
        self.assertIn("--dimensions", command)
        self.assertIn("3072", command)

    def test_parser_accepts_noisy_stdout_before_json(self) -> None:
        parsed = _parse_json("Provider List: https://docs.litellm.ai/docs/providers\n{\"ok\": true, \"status\": \"ready\"}\n")

        self.assertEqual({"ok": True, "status": "ready"}, parsed)


def _passing_checker(_command: list[str], _timeout: float) -> dict[str, object]:
    return _sample()


def _sample(*, ok: bool = True, status: str = "ready") -> dict[str, object]:
    return {
        "ok": ok,
        "status": status,
        "check_mode": "live_embedding",
        "model": "ollama/qwen3-embedding:0.6b-fp16",
        "endpoint": "http://embedding.internal?access_token=secret",
        "expected_dimensions": 1024,
        "actual_dimensions": 1024 if ok else 0,
    }


def _clock(*iso_values: str):
    values = [datetime.fromisoformat(value).astimezone(timezone.utc) for value in iso_values]
    index = {"value": 0}

    def now() -> datetime:
        value = values[min(index["value"], len(values) - 1)]
        index["value"] += 1
        return value

    return now


if __name__ == "__main__":
    unittest.main()
