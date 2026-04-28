from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.permissions import demo_permission_context
from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

DEFAULT_SCOPE = "project:feishu_ai_challenge"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce Phase B OpenClaw runtime evidence by exercising Copilot memory tools through handle_tool_request."
    )
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--db-path", help="Optional SQLite path. If omitted, a temporary database is used.")
    parser.add_argument("--json-output", help="Optional path for full evidence JSON, usually under ignored reports/.")
    args = parser.parse_args()

    with _evidence_database(args.db_path) as db_path:
        evidence = build_evidence(args.scope, str(db_path), persistent=bool(args.db_path))

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(compact_summary(evidence, output_path), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


def build_evidence(
    scope: str = DEFAULT_SCOPE, db_path: str | None = None, *, persistent: bool = False
) -> dict[str, Any]:
    path = db_path
    if path is None:
        with tempfile.TemporaryDirectory(prefix="openclaw_runtime_evidence_") as tmp:
            return _build_evidence_with_db(scope, str(Path(tmp) / "evidence.sqlite"), persistent=False)
    return _build_evidence_with_db(scope, path, persistent=persistent)


def _build_evidence_with_db(scope: str, db_path: str, *, persistent: bool) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        init_db(conn)
        repo = MemoryRepository(conn)
        _seed_active_memory(repo, scope)
        service = CopilotService(repository=repo)

        search = _run_search(service, scope)
        candidate = _run_candidate_confirm(service, scope)
        prefetch = _run_prefetch(service, scope)
        flows = [search, candidate, prefetch]

        return {
            "ok": all(flow["ok"] for flow in flows),
            "phase": "Phase B",
            "runtime_boundary": "OpenClaw Agent runtime can invoke this script through exec; each flow then enters handle_tool_request() -> CopilotService.",
            "scope": scope,
            "db_path": db_path,
            "persistent_db": persistent,
            "production_feishu_write": False,
            "flows": flows,
        }
    finally:
        conn.close()


def _seed_active_memory(repo: MemoryRepository, scope: str) -> None:
    repo.remember(
        scope,
        "决定：Phase B OpenClaw runtime 验收必须记录 request_id、trace_id 和 permission_decision；不能把 local bridge 冒充 production live。",
        source_type="openclaw_runtime_seed",
    )
    repo.remember(
        scope,
        "决定：任务前 checklist 必须先调用 memory.prefetch 汇总 active memory、evidence 和风险边界。",
        source_type="openclaw_runtime_seed",
    )


def _run_search(service: CopilotService, scope: str) -> dict[str, Any]:
    payload = {
        "query": "Phase B OpenClaw runtime 验收要记录什么",
        "scope": scope,
        "top_k": 3,
        "current_context": _context("memory.search", scope, "req_phase_b_search", "trace_phase_b_search"),
    }
    output = handle_tool_request("memory.search", payload, service=service)
    return _flow("historical_decision_search", "memory.search", payload, output)


def _run_candidate_confirm(service: CopilotService, scope: str) -> dict[str, Any]:
    create_payload = {
        "text": "决定：Phase B runtime evidence 文档必须保留真实 OpenClaw run id 和失败回退说明。",
        "scope": scope,
        "source": {
            "source_type": "openclaw_agent_runtime",
            "source_id": "phase-b-runtime-flow-2",
            "actor_id": "openclaw_agent_main",
            "created_at": "2026-04-28T13:20:00+08:00",
            "quote": "决定：Phase B runtime evidence 文档必须保留真实 OpenClaw run id 和失败回退说明。",
        },
        "current_context": _context(
            "memory.create_candidate",
            scope,
            "req_phase_b_create_candidate",
            "trace_phase_b_candidate_confirm",
        ),
    }
    created = handle_tool_request("memory.create_candidate", create_payload, service=service)
    candidate_id = created.get("candidate_id")
    confirm_payload = {
        "candidate_id": candidate_id,
        "scope": scope,
        "actor_id": "openclaw_agent_main",
        "reason": "Phase B runtime evidence flow confirms candidate through CopilotService.",
        "current_context": _context(
            "memory.confirm",
            scope,
            "req_phase_b_confirm",
            "trace_phase_b_candidate_confirm",
        ),
    }
    confirmed = (
        handle_tool_request("memory.confirm", confirm_payload, service=service) if isinstance(candidate_id, str) else {}
    )
    output = {
        "ok": bool(created.get("ok")) and bool(confirmed.get("ok")),
        "create_candidate": created,
        "confirm": confirmed,
    }
    return _flow("candidate_create_then_confirm", "memory.create_candidate + memory.confirm", create_payload, output)


def _run_prefetch(service: CopilotService, scope: str) -> dict[str, Any]:
    payload = {
        "task": "整理 Phase B OpenClaw runtime 验收 checklist",
        "scope": scope,
        "top_k": 5,
        "current_context": {
            **_context("memory.prefetch", scope, "req_phase_b_prefetch", "trace_phase_b_prefetch"),
            "user_intent": "prepare Phase B evidence checklist",
            "thread_topic": "OpenClaw runtime validation",
            "session_id": "openclaw-agent-main-phase-b",
        },
    }
    output = handle_tool_request("memory.prefetch", payload, service=service)
    return _flow("task_prefetch_context_pack", "memory.prefetch", payload, output)


def _context(action: str, scope: str, request_id: str, trace_id: str) -> dict[str, Any]:
    context = demo_permission_context(
        action, scope, actor_id="openclaw_agent_main", entrypoint="openclaw_agent_runtime"
    )
    context["allowed_scopes"] = [scope]
    permission = context["permission"]
    permission["request_id"] = request_id
    permission["trace_id"] = trace_id
    permission["actor"]["roles"] = ["member", "reviewer"]
    permission["timestamp"] = "2026-04-28T13:20:00+08:00"
    return context


def _flow(name: str, tool: str, input_payload: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    bridge = _extract_bridge(output)
    return {
        "name": name,
        "tool": tool,
        "ok": _flow_ok(output),
        "input": input_payload,
        "output": output,
        "request_id": bridge.get("request_id"),
        "trace_id": bridge.get("trace_id"),
        "permission_decision": bridge.get("permission_decision"),
    }


def _flow_ok(output: dict[str, Any]) -> bool:
    if output.get("ok") is True:
        return True
    return bool(output.get("create_candidate", {}).get("ok") and output.get("confirm", {}).get("ok"))


def _extract_bridge(output: dict[str, Any]) -> dict[str, Any]:
    bridge = output.get("bridge")
    if isinstance(bridge, dict):
        return bridge
    confirm = output.get("confirm")
    if isinstance(confirm, dict) and isinstance(confirm.get("bridge"), dict):
        return confirm["bridge"]
    created = output.get("create_candidate")
    if isinstance(created, dict) and isinstance(created.get("bridge"), dict):
        return created["bridge"]
    return {}


def compact_summary(evidence: dict[str, Any], output_path: Path) -> dict[str, Any]:
    return {
        "ok": evidence["ok"],
        "phase": evidence["phase"],
        "runtime_boundary": evidence["runtime_boundary"],
        "json_output": str(output_path),
        "production_feishu_write": evidence["production_feishu_write"],
        "flows": [
            {
                "name": flow["name"],
                "tool": flow["tool"],
                "ok": flow["ok"],
                "request_id": flow["request_id"],
                "trace_id": flow["trace_id"],
                "permission_decision": flow["permission_decision"],
            }
            for flow in evidence["flows"]
        ],
    }


class _evidence_database:
    def __init__(self, db_path: str | None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            return self.db_path
        self.temp_dir = tempfile.TemporaryDirectory(prefix="openclaw_runtime_evidence_")
        return Path(self.temp_dir.name) / "evidence.sqlite"

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


if __name__ == "__main__":
    main()
