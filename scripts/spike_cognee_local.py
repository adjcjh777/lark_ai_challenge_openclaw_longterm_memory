from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.cognee_adapter import CogneeMemoryAdapter, load_cognee_client
from memory_engine.copilot.local_env import load_local_env_files, read_key_value_file

DATA_ROOT = Path(".data/cognee/data")
SYSTEM_ROOT = Path(".data/cognee/system")
DATABASE_ROOT = SYSTEM_ROOT / "databases"
EMBEDDING_LOCK_FILE = ROOT / "memory_engine/copilot/embedding-provider.lock"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 2026-04-27 local Cognee SDK spike.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate local paths and adapter wiring without importing Cognee."
    )
    parser.add_argument(
        "--reset-local-data",
        action="store_true",
        help="Delete .data/cognee before running; use after changing embedding dimensions.",
    )
    parser.add_argument("--scope", default="project:feishu_ai_challenge")
    parser.add_argument("--query", default="生产部署参数")
    args = parser.parse_args()

    if args.reset_local_data and SYSTEM_ROOT.parent.exists():
        shutil.rmtree(SYSTEM_ROOT.parent)

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    SYSTEM_ROOT.mkdir(parents=True, exist_ok=True)
    DATABASE_ROOT.mkdir(parents=True, exist_ok=True)
    _load_local_env_files()
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
        _print_blocked(dataset_name, "cognee real SDK call failed before stage reporting", exc)
        return

    _print(
        {
            "ok": result["ok"],
            "dry_run": False,
            "status": "real_run" if result["ok"] else "blocked",
            "dataset_name": dataset_name,
            "blocked": result["blocked"],
            "data_root": str(DATA_ROOT),
            "system_root": str(SYSTEM_ROOT),
            "result": result,
        }
    )


def _configure_local_cognee_paths() -> None:
    embedding_lock = _read_key_value_file(EMBEDDING_LOCK_FILE)

    os.environ.setdefault("DATA_ROOT_DIRECTORY", str(DATA_ROOT.resolve()))
    os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", str(SYSTEM_ROOT.resolve()))
    os.environ.setdefault("DB_PATH", str(DATABASE_ROOT.resolve()))
    os.environ.setdefault("DB_PROVIDER", "sqlite")
    os.environ.setdefault("DB_NAME", "feishu_memory_copilot_cognee")
    os.environ.setdefault("VECTOR_DB_PROVIDER", "lancedb")
    os.environ.setdefault("VECTOR_DB_URL", str((DATABASE_ROOT / "cognee.lancedb").resolve()))
    os.environ.setdefault("GRAPH_DATABASE_PROVIDER", "NETWORKX")
    os.environ.setdefault("GRAPH_FILE_PATH", str((DATABASE_ROOT / "cognee_graph.pkl").resolve()))
    os.environ.setdefault("MONITORING_TOOL", "llmlite")
    os.environ.setdefault("TELEMETRY_DISABLED", "true")
    os.environ.setdefault("EMBEDDING_MODEL", embedding_lock.get("litellm_model", "ollama/qwen3-embedding:0.6b-fp16"))
    os.environ.setdefault("EMBEDDING_ENDPOINT", embedding_lock.get("endpoint", "http://localhost:11434"))
    os.environ.setdefault("EMBEDDING_DIMENSIONS", embedding_lock.get("dimensions", "1024"))


def _missing_provider_configuration() -> str | None:
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    llm_api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    # Ollama doesn't require an API key
    if provider != "ollama" and not llm_api_key:
        return "missing OPENAI_API_KEY or LLM_API_KEY"
    if provider == "custom" and not os.environ.get("LLM_ENDPOINT"):
        return "LLM_ENDPOINT is required for Cognee custom provider"
    if not os.environ.get("EMBEDDING_MODEL"):
        return "EMBEDDING_MODEL is required for Cognee embeddings"
    if os.environ.get("EMBEDDING_MODEL", "").startswith("ollama/") and not os.environ.get("EMBEDDING_ENDPOINT"):
        return "EMBEDDING_ENDPOINT is required for local Ollama embeddings"

    return None


def _load_local_env_files() -> None:
    load_local_env_files(root=ROOT, override=True)


def _read_key_value_file(path: Path) -> dict[str, str]:
    return read_key_value_file(path)


async def _run_real_spike(adapter: CogneeMemoryAdapter, scope: str, query: str) -> dict[str, Any]:
    content = "生产部署必须加 --canary --region cn-shanghai"
    stages: list[dict[str, Any]] = []

    add_result = await _run_stage(
        stages,
        "add",
        adapter.add_raw_event,
        scope,
        content,
        source_type="spike",
        source_id="spike_2026_04_27",
    )
    if add_result["blocked"]:
        return {"ok": False, "blocked": add_result["blocked"], "stages": stages, "result_count": 0, "results": []}

    cognify_result = await _run_stage(stages, "cognify", adapter.cognify_scope, scope)
    if cognify_result["blocked"]:
        stages.append({"stage": "search", "ok": False, "skipped": True, "reason": "cognify did not finish"})
        return {"ok": False, "blocked": cognify_result["blocked"], "stages": stages, "result_count": 0, "results": []}

    search_result = await _run_stage(stages, "search", adapter.search, scope, query)
    if search_result["blocked"]:
        return {"ok": False, "blocked": search_result["blocked"], "stages": stages, "result_count": 0, "results": []}

    results = search_result["value"]
    return {"ok": True, "blocked": None, "stages": stages, "result_count": len(results), "results": results[:3]}


async def _run_stage(stages: list[dict[str, Any]], name: str, func: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        value = await _maybe_await(func(*args, **kwargs))
    except Exception as exc:  # pragma: no cover - depends on local Cognee/provider state
        blocked = f"{name} failed: {type(exc).__name__}: {exc}"
        stages.append({"stage": name, "ok": False, "blocked": blocked})
        return {"blocked": blocked, "value": None}

    stages.append({"stage": name, "ok": True})
    return {"blocked": None, "value": value}


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
