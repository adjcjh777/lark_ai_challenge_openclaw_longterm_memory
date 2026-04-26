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

from memory_engine.copilot.cognee_adapter import CogneeMemoryAdapter, load_cognee_client


DATA_ROOT = Path(".data/cognee/data")
SYSTEM_ROOT = Path(".data/cognee/system")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 2026-04-27 local Cognee SDK spike.")
    parser.add_argument("--dry-run", action="store_true", help="Validate local paths and adapter wiring without importing Cognee.")
    parser.add_argument("--scope", default="project:feishu_ai_challenge")
    parser.add_argument("--query", default="生产部署参数")
    args = parser.parse_args()

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    SYSTEM_ROOT.mkdir(parents=True, exist_ok=True)
    _configure_local_cognee_paths()

    adapter = CogneeMemoryAdapter()
    dataset_name = adapter.dataset_for_scope(args.scope)

    if args.dry_run:
        _print(
            {
                "ok": True,
                "dry_run": True,
                "status": "dry_run",
                "dataset_name": dataset_name,
                "data_root": str(DATA_ROOT),
                "system_root": str(SYSTEM_ROOT),
                "blocked": None,
            }
        )
        return

    try:
        cognee = load_cognee_client()
    except ModuleNotFoundError as exc:
        _print_blocked(dataset_name, "cognee SDK is not installed", exc)
        return

    missing_provider = _missing_provider_configuration()
    if missing_provider:
        _print(
            {
                "ok": False,
                "dry_run": False,
                "status": "blocked",
                "dataset_name": dataset_name,
                "blocked": missing_provider,
                "data_root": str(DATA_ROOT),
                "system_root": str(SYSTEM_ROOT),
            }
        )
        return

    adapter = CogneeMemoryAdapter(client=cognee)
    try:
        result = asyncio.run(_run_real_spike(adapter, args.scope, args.query))
    except Exception as exc:  # pragma: no cover - depends on local Cognee/provider state
        _print_blocked(dataset_name, "cognee real SDK call failed", exc)
        return

    _print(
        {
            "ok": True,
            "dry_run": False,
            "status": "real_run",
            "dataset_name": dataset_name,
            "data_root": str(DATA_ROOT),
            "system_root": str(SYSTEM_ROOT),
            "result": result,
        }
    )


def _configure_local_cognee_paths() -> None:
    os.environ.setdefault("DATA_ROOT_DIRECTORY", str(DATA_ROOT.resolve()))
    os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", str(SYSTEM_ROOT.resolve()))
    os.environ.setdefault("DB_PROVIDER", "sqlite")
    os.environ.setdefault("DB_NAME", "feishu_memory_copilot_cognee")
    os.environ.setdefault("VECTOR_DB_PROVIDER", "lancedb")
    os.environ.setdefault("GRAPH_DATABASE_PROVIDER", "kuzu")
    os.environ.setdefault("TELEMETRY_DISABLED", "true")


def _missing_provider_configuration() -> str | None:
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY") and not os.environ.get("LLM_API_KEY"):
        return "missing OPENAI_API_KEY or LLM_API_KEY for Cognee default OpenAI provider"

    embedding_provider = os.environ.get("EMBEDDING_PROVIDER")
    if provider != "openai" and not embedding_provider:
        return "non-OpenAI LLM_PROVIDER is set but EMBEDDING_PROVIDER is missing"
    return None


async def _run_real_spike(adapter: CogneeMemoryAdapter, scope: str, query: str) -> dict[str, Any]:
    content = "生产部署必须加 --canary --region cn-shanghai"
    await _maybe_await(adapter.add_raw_event(scope, content, source_type="spike", source_id="spike_2026_04_27"))
    await _maybe_await(adapter.cognify_scope(scope))
    results = await _maybe_await(adapter.search(scope, query))
    return {"result_count": len(results), "results": results[:3]}


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _print_blocked(dataset_name: str, reason: str, exc: Exception) -> None:
    _print(
        {
            "ok": False,
            "dry_run": False,
            "status": "blocked",
            "dataset_name": dataset_name,
            "blocked": reason,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "data_root": str(DATA_ROOT),
            "system_root": str(SYSTEM_ROOT),
        }
    )


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
