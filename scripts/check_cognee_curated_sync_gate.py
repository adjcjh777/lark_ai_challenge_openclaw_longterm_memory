from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.cognee_adapter import CogneeMemoryAdapter, load_cognee_client  # noqa: E402
from memory_engine.copilot.local_env import load_local_env_files, read_key_value_file  # noqa: E402
from memory_engine.copilot.schemas import CandidateSource, ConfirmRequest, CreateCandidateRequest  # noqa: E402
from memory_engine.copilot.service import CopilotService  # noqa: E402
from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.repository import MemoryRepository  # noqa: E402

EMBEDDING_LOCK_FILE = ROOT / "memory_engine/copilot/embedding-provider.lock"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify real Cognee SDK curated memory sync through CopilotService.confirm in an isolated store."
    )
    parser.add_argument("--scope", default="project:feishu_ai_challenge")
    parser.add_argument("--data-root", default=None, help="Cognee DATA_ROOT_DIRECTORY. Defaults to a temp dir.")
    parser.add_argument("--system-root", default=None, help="Cognee SYSTEM_ROOT_DIRECTORY. Defaults under data root.")
    parser.add_argument("--llm-provider", default=os.environ.get("LLM_PROVIDER") or "ollama")
    parser.add_argument("--llm-endpoint", default=os.environ.get("LLM_ENDPOINT") or "http://localhost:11434")
    parser.add_argument("--llm-model", default=os.environ.get("LLM_MODEL") or "qwen3.5:0.8b")
    parser.add_argument("--json", action="store_true", help="Print compact JSON only.")
    args = parser.parse_args()

    with _temporary_roots(args.data_root, args.system_root) as roots:
        report = run_gate(
            scope=args.scope,
            data_root=roots["data_root"],
            system_root=roots["system_root"],
            llm_provider=args.llm_provider,
            llm_endpoint=args.llm_endpoint,
            llm_model=args.llm_model,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


def run_gate(
    *,
    scope: str,
    data_root: Path,
    system_root: Path,
    llm_provider: str,
    llm_endpoint: str,
    llm_model: str,
) -> dict[str, Any]:
    load_local_env_files(root=ROOT, override=False)
    _configure_environment(
        data_root=data_root,
        system_root=system_root,
        llm_provider=llm_provider,
        llm_endpoint=llm_endpoint,
        llm_model=llm_model,
    )
    db_file = tempfile.NamedTemporaryFile(prefix="cognee_curated_sync_", suffix=".sqlite")
    conn = None
    try:
        conn = connect(Path(db_file.name))
        init_db(conn)
        repo = MemoryRepository(conn)
        adapter = CogneeMemoryAdapter(client=load_cognee_client())
        service = CopilotService(repository=repo, cognee_adapter=adapter, auto_init_cognee=False)
        permission = _permission(scope, requested_action="memory.create_candidate")
        source = CandidateSource(
            source_type="unit_test",
            source_id="cognee_curated_sync_gate",
            actor_id="ou_cognee_gate",
            created_at="2026-05-01T00:00:00+08:00",
            quote="决定：Cognee curated sync gate 需要同步 confirmed curated memory。",
        )
        created = service.create_candidate(
            CreateCandidateRequest(
                text="决定：Cognee curated sync gate 需要同步 confirmed curated memory。",
                scope=scope,
                source=source,
                current_context={"permission": permission},
            )
        )
        confirmed = service.confirm(
            ConfirmRequest(
                candidate_id=created["candidate_id"],
                scope=scope,
                actor_id="ou_cognee_gate",
                reason="real cognee curated sync gate",
                current_context={"permission": _permission(scope, requested_action="memory.confirm")},
            )
        )
        cognee_sync = confirmed.get("cognee_sync") if isinstance(confirmed.get("cognee_sync"), dict) else {}
        ok = bool(confirmed.get("ok")) and cognee_sync.get("status") == "pass" and not cognee_sync.get("fallback")
        return {
            "ok": ok,
            "gate": "cognee_curated_sync",
            "scope": scope,
            "dataset_name": cognee_sync.get("dataset_name"),
            "memory_id": cognee_sync.get("memory_id"),
            "cognee_sync": cognee_sync,
            "data_root": str(data_root),
            "system_root": str(system_root),
            "production_boundary": "isolated local/staging Cognee gate; not a long-running embedding service.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "gate": "cognee_curated_sync",
            "scope": scope,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "data_root": str(data_root),
            "system_root": str(system_root),
            "production_boundary": "isolated local/staging Cognee gate; not a long-running embedding service.",
        }
    finally:
        if conn is not None:
            conn.close()
        db_file.close()


def _configure_environment(
    *,
    data_root: Path,
    system_root: Path,
    llm_provider: str,
    llm_endpoint: str,
    llm_model: str,
) -> None:
    embedding_lock = read_key_value_file(EMBEDDING_LOCK_FILE)
    database_root = system_root / "databases"
    data_root.mkdir(parents=True, exist_ok=True)
    system_root.mkdir(parents=True, exist_ok=True)
    database_root.mkdir(parents=True, exist_ok=True)

    os.environ["DATA_ROOT_DIRECTORY"] = str(data_root.resolve())
    os.environ["SYSTEM_ROOT_DIRECTORY"] = str(system_root.resolve())
    os.environ["DB_PATH"] = str(database_root.resolve())
    os.environ.setdefault("DB_PROVIDER", "sqlite")
    os.environ.setdefault("DB_NAME", "feishu_memory_copilot_cognee")
    os.environ.setdefault("VECTOR_DB_PROVIDER", "lancedb")
    os.environ["VECTOR_DB_URL"] = str((database_root / "cognee.lancedb").resolve())
    os.environ.setdefault("GRAPH_DATABASE_PROVIDER", "NETWORKX")
    os.environ["GRAPH_FILE_PATH"] = str((database_root / "cognee_graph.pkl").resolve())
    os.environ.setdefault("MONITORING_TOOL", "llmlite")
    os.environ.setdefault("TELEMETRY_DISABLED", "true")
    os.environ["LLM_PROVIDER"] = llm_provider
    os.environ["LLM_ENDPOINT"] = llm_endpoint
    os.environ["LLM_MODEL"] = llm_model
    os.environ.setdefault("EMBEDDING_MODEL", embedding_lock.get("litellm_model", "ollama/qwen3-embedding:0.6b-fp16"))
    os.environ.setdefault("EMBEDDING_ENDPOINT", embedding_lock.get("endpoint", "http://localhost:11434"))
    os.environ.setdefault("EMBEDDING_DIMENSIONS", embedding_lock.get("dimensions", "1024"))


def _permission(scope: str, *, requested_action: str) -> dict[str, Any]:
    return {
        "request_id": f"req_cognee_curated_sync_{requested_action.replace('.', '_')}",
        "trace_id": f"trace_cognee_curated_sync_{requested_action.replace('.', '_')}",
        "actor": {
            "user_id": "ou_cognee_gate",
            "tenant_id": "tenant:demo",
            "organization_id": "org:demo",
            "roles": ["member", "reviewer"],
        },
        "source_context": {"entrypoint": "cognee_curated_sync_gate", "workspace_id": scope},
        "requested_action": requested_action,
        "requested_visibility": "team",
        "timestamp": "2026-05-01T00:00:00+08:00",
    }


class _temporary_roots:
    def __init__(self, data_root: str | None, system_root: str | None) -> None:
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self._data_root = Path(data_root) if data_root else None
        self._system_root = Path(system_root) if system_root else None

    def __enter__(self) -> dict[str, Path]:
        if self._data_root and self._system_root:
            return {"data_root": self._data_root, "system_root": self._system_root}
        self._temp_dir = tempfile.TemporaryDirectory(prefix="copilot_cognee_gate_")
        root = Path(self._temp_dir.name)
        return {
            "data_root": self._data_root or root / "data",
            "system_root": self._system_root or root / "system",
        }

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()


if __name__ == "__main__":
    main()
