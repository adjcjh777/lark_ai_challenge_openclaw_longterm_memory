#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.cognee_adapter import (  # noqa: E402
    CogneeMemoryAdapter,
    _resolve_awaitable,
    load_cognee_client,
)
from scripts.check_cognee_curated_sync_gate import (  # noqa: E402
    _configure_environment,
    apply_cognee_gate_env_defaults,
    load_cognee_gate_env_defaults,
)
from scripts.collect_cognee_embedding_long_run_evidence import _parse_json_object  # noqa: E402

BOUNDARY = (
    "cognee_persistent_readback_gate_only; reopens an existing local/staging Cognee store and searches for "
    "the synced curated memory, but does not prove 24h embedding service uptime by itself"
)

AdapterFactory = Callable[[], CogneeMemoryAdapter]


def main() -> int:
    env_defaults = load_cognee_gate_env_defaults(root=ROOT)
    parser = argparse.ArgumentParser(
        description=(
            "Verify that a Cognee curated-sync report points to a persistent store that can be reopened and searched."
        )
    )
    parser.add_argument("--curated-sync-report", required=True, type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--llm-provider", default=env_defaults.get("LLM_PROVIDER") or "ollama")
    parser.add_argument("--llm-endpoint", default=env_defaults.get("LLM_ENDPOINT") or "http://localhost:11434")
    parser.add_argument("--llm-model", default=env_defaults.get("LLM_MODEL") or "qwen3.5:0.8b")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = read_curated_sync_report(args.curated_sync_report)
    result = verify_cognee_persistent_readback(
        curated_sync_report=report,
        query=args.query,
        llm_provider=args.llm_provider,
        llm_endpoint=args.llm_endpoint,
        llm_model=args.llm_model,
    )
    if args.output:
        args.output.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.output.expanduser().write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def verify_cognee_persistent_readback(
    *,
    curated_sync_report: dict[str, Any],
    query: str = "",
    llm_provider: str = "ollama",
    llm_endpoint: str = "http://localhost:11434",
    llm_model: str = "qwen3.5:0.8b",
    adapter_factory: AdapterFactory | None = None,
) -> dict[str, Any]:
    scope = str(curated_sync_report.get("scope") or "project:feishu_ai_challenge")
    memory_id = str(curated_sync_report.get("memory_id") or "")
    dataset_name = str(curated_sync_report.get("dataset_name") or "")
    data_root = Path(str(curated_sync_report.get("data_root") or ""))
    system_root = Path(str(curated_sync_report.get("system_root") or ""))
    search_query = query or memory_id or "Cognee curated sync gate"
    checks = {
        "curated_sync_report_ok": _check(bool(curated_sync_report.get("ok")), "Curated-sync report is successful."),
        "memory_id_present": _check(bool(memory_id), "Curated-sync report includes memory_id."),
        "data_root_exists": _check(data_root.exists(), "Cognee data root exists.", path=str(data_root)),
        "system_root_exists": _check(system_root.exists(), "Cognee system root exists.", path=str(system_root)),
    }
    search_results: list[dict[str, Any]] = []
    search_error: dict[str, str] | None = None
    if all(check["status"] == "pass" for check in checks.values()):
        try:
            apply_cognee_gate_env_defaults(root=ROOT)
            _configure_environment(
                data_root=data_root,
                system_root=system_root,
                llm_provider=llm_provider,
                llm_endpoint=llm_endpoint,
                llm_model=llm_model,
            )
            adapter = adapter_factory() if adapter_factory else CogneeMemoryAdapter(client=load_cognee_client())
            checks["store_reopened"] = _check(True, "Cognee store was reopened in this process.")
            search_results = _resolve_awaitable(adapter.search(scope, search_query))
            checks["reopened_search_ok"] = _check(
                _matches_synced_memory(search_results, memory_id=memory_id),
                "Post-reopen search/readback found the synced curated memory.",
                result_count=len(search_results),
            )
        except Exception as exc:
            search_error = {"type": type(exc).__name__, "message": str(exc)}
            checks["store_reopened"] = _check(False, "Cognee store could not be reopened.", **search_error)
            checks["reopened_search_ok"] = _check(False, "Post-reopen search/readback failed.", **search_error)
    else:
        checks["store_reopened"] = _check(False, "Skipped because prerequisite report/root checks failed.")
        checks["reopened_search_ok"] = _check(False, "Skipped because prerequisite report/root checks failed.")
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "dataset_name": dataset_name,
        "memory_id": memory_id,
        "data_root": str(data_root),
        "system_root": str(system_root),
        "query": search_query,
        "checks": checks,
        "failed_checks": failed,
        "search_result_count": len(search_results),
        "matched_memory": not failed and checks["reopened_search_ok"]["status"] == "pass",
        "search_error": search_error,
        "sample_results": _redacted_sample_results(search_results),
        "next_step": ""
        if not failed
        else "Fix Cognee persistent store/readback, then pass this report to collect_cognee_embedding_long_run_evidence.py.",
    }


def read_curated_sync_report(path: Path) -> dict[str, Any]:
    parsed = _parse_json_object(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object or noisy stdout ending in one")
    return parsed


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Cognee Persistent Store Readback",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
        f"dataset_name: {result['dataset_name']}",
        f"memory_id: {result['memory_id']}",
        f"search_result_count: {result['search_result_count']}",
    ]
    if result["failed_checks"]:
        lines.append("failed_checks:")
        lines.extend(f"  - {name}" for name in result["failed_checks"])
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _matches_synced_memory(results: list[dict[str, Any]], *, memory_id: str) -> bool:
    for result in results:
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        if memory_id and memory_id in encoded:
            return True
        if "Cognee curated sync gate" in encoded:
            return True
    return False


def _redacted_sample_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for result in results[:3]:
        sample.append(
            {
                "memory_id": result.get("memory_id"),
                "rank": result.get("rank"),
                "score": result.get("score"),
                "status": result.get("status"),
                "matched_via": result.get("matched_via"),
                "current_value_preview": str(result.get("current_value") or "")[:240],
            }
        )
    return sample


def _check(ok: bool, description: str, **details: Any) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "description": description, **details}


if __name__ == "__main__":
    raise SystemExit(main())
