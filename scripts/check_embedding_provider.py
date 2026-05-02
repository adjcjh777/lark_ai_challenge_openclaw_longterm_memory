from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.local_env import load_local_env_files, read_key_value_file

LOCK_FILE = ROOT / "memory_engine/copilot/embedding-provider.lock"
DEFAULT_TEXT = "生产部署参数"


def main() -> None:
    _load_local_env_files()

    parser = argparse.ArgumentParser(description="Check the local embedding provider before running Cognee.")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL"))
    parser.add_argument("--endpoint", default=os.environ.get("EMBEDDING_ENDPOINT"))
    parser.add_argument("--dimensions", type=int, default=_env_int("EMBEDDING_DIMENSIONS"))
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    lock = _read_lock()
    model = args.model or lock.get("litellm_model") or "ollama/qwen3-embedding:0.6b-fp16"
    endpoint = args.endpoint or lock.get("endpoint") or "http://localhost:11434"
    expected_dimensions = args.dimensions or int(lock.get("dimensions", "1024"))

    try:
        result = asyncio.run(
            asyncio.wait_for(
                _embed_once(
                    model=model, endpoint=endpoint, text=args.text, api_key=os.environ.get("EMBEDDING_API_KEY")
                ),
                timeout=args.timeout,
            )
        )
    except Exception as exc:
        _print(
            {
                "ok": False,
                "status": "blocked",
                "model": model,
                "endpoint": endpoint,
                "expected_dimensions": expected_dimensions,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "hint": _hint(model),
            }
        )
        sys.exit(1)

    actual_dimensions = len(result)
    ollama_model = model.removeprefix("ollama/")
    _print(
        {
            "ok": actual_dimensions == expected_dimensions,
            "status": "ready" if actual_dimensions == expected_dimensions else "dimension_mismatch",
            "check_mode": "live_embedding",
            "model": model,
            "ollama_model": ollama_model,
            "endpoint": endpoint,
            "expected_dimensions": expected_dimensions,
            "actual_dimensions": actual_dimensions,
            "sample": args.text,
            "cleanup_required": model.startswith("ollama/"),
            "cleanup_command": f"ollama stop {ollama_model}" if model.startswith("ollama/") else None,
        }
    )
    if actual_dimensions != expected_dimensions:
        sys.exit(1)


async def _embed_once(*, model: str, endpoint: str, text: str, api_key: str | None = None) -> list[float]:
    try:
        import litellm
    except ModuleNotFoundError as exc:
        raise RuntimeError("litellm is not installed; install project dependencies first") from exc

    response = await litellm.aembedding(
        model=model,
        input=[text],
        api_base=endpoint,
        api_key=api_key,
    )
    embedding = response.data[0]["embedding"]
    return list(embedding)


def _read_lock() -> dict[str, str]:
    return read_key_value_file(LOCK_FILE)


def _load_local_env_files() -> None:
    load_local_env_files(root=ROOT, override=True)


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if not value:
        return None
    return int(value)


def _hint(model: str) -> str:
    ollama_model = model.removeprefix("ollama/")
    return f"Start Ollama and run: ollama pull {ollama_model}"


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
