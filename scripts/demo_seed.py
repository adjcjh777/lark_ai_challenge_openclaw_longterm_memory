from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.heartbeat import HeartbeatReminderEngine, agent_run_summary_candidate
from memory_engine.copilot.permissions import demo_permission_context
from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request, supported_tool_names, validate_tool_request
from memory_engine.db import connect, init_db
from memory_engine.models import normalize_subject, parse_scope
from memory_engine.repository import MemoryRepository

DEFAULT_SCOPE = "project:feishu_ai_challenge"
BASE_TS = 1777852800000  # 2026-05-04 00:00:00 +08:00


@dataclass(frozen=True)
class DemoMemory:
    memory_id: str
    memory_type: str
    subject: str
    values: tuple[str, ...]
    reason: str
    importance: float = 0.8


DEMO_MEMORIES = (
    DemoMemory(
        memory_id="mem_demo_deploy_region",
        memory_type="decision",
        subject="生产部署 region",
        values=(
            "生产部署 region 固定 cn-shanghai，发布时必须加 --canary。",
            "不对，生产部署 region 改成 ap-shanghai，发布时仍必须加 --canary。",
        ),
        reason="演示冲突更新后只召回 active 当前值",
        importance=0.95,
    ),
    DemoMemory(
        memory_id="mem_demo_demo_entry",
        memory_type="decision",
        subject="Demo 演示入口",
        values=(
            "Demo 编排先从旧 Feishu Bot 命令开始。",
            "不对，Demo 编排改为 OpenClaw memory.search / memory.prefetch 优先，旧 Bot 只作为 fallback。",
        ),
        reason="演示 OpenClaw-native 主线，不回退成 CLI-first",
        importance=0.9,
    ),
    DemoMemory(
        memory_id="mem_demo_submission_deadline",
        memory_type="deadline",
        subject="初赛提交截止",
        values=("初赛提交材料需要在 2026-05-07 中午前完成，录屏和截图必须提前准备。",),
        reason="演示 heartbeat reminder candidate",
        importance=0.9,
    ),
    DemoMemory(
        memory_id="mem_demo_secret_risk",
        memory_type="risk",
        subject="飞书凭证安全",
        values=("风险：Feishu app_secret=demo-secret-value 不得写入公开 README 或提交到仓库。",),
        reason="演示 reminder dry-run 中的敏感信息遮挡",
        importance=0.85,
    ),
)


SEARCH_PAYLOAD = {
    "query": "生产部署 region 和 canary 参数",
    "scope": DEFAULT_SCOPE,
    "top_k": 3,
    "filters": {"status": "active", "type": "decision"},
    "current_context": {},
}


PREFETCH_PAYLOAD = {
    "task": "生成今天的生产部署 checklist",
    "scope": DEFAULT_SCOPE,
    "current_context": {},
    "top_k": 5,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed and replay the 2026-05-04 OpenClaw-native Copilot demo without touching Feishu production space."
    )
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument(
        "--db-path",
        help="Optional SQLite path. If omitted, a temporary database is used and removed after the run.",
    )
    parser.add_argument("--json-output", help="Optional path for full replay JSON, usually under ignored reports/.")
    args = parser.parse_args()

    with _demo_database(args.db_path) as db_path:
        conn = connect(db_path)
        try:
            init_db(conn)
            repo = MemoryRepository(conn)
            seed_demo_memories(conn, args.scope)
            replay = build_replay(repo, args.scope, str(db_path), persistent=bool(args.db_path))
        finally:
            conn.close()

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(_compact_summary(replay, output_path), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(replay, ensure_ascii=False, indent=2))


def seed_demo_memories(conn: sqlite3.Connection, scope: str) -> None:
    parsed_scope = parse_scope(scope)
    with conn:
        _clear_scope(conn, parsed_scope.scope_type, parsed_scope.scope_id)
        for index, memory in enumerate(DEMO_MEMORIES, start=1):
            _insert_memory(conn, parsed_scope, memory, BASE_TS + index * 60000)


def build_replay(repo: MemoryRepository, scope: str, db_path: str, *, persistent: bool) -> dict[str, Any]:
    service = CopilotService(repository=repo)
    search_payload = _with_scope(SEARCH_PAYLOAD, scope)
    search_payload["current_context"] = _demo_context(
        "memory.search",
        scope,
        intent="回答历史决策问题",
        thread_topic="生产部署",
        session_id="openclaw-demo-session",
    )
    prefetch_payload = _with_scope(PREFETCH_PAYLOAD, scope)
    prefetch_payload["current_context"] = _demo_context(
        "memory.prefetch",
        scope,
        intent="准备生产部署 checklist",
        thread_topic="生产部署",
        session_id="openclaw-demo-session",
        task_id="demo-prefetch-001",
        metadata={"current_message": "请帮我生成今天上线前的部署检查清单。"},
    )

    search = handle_tool_request("memory.search", search_payload, service=service)
    versions_payload = {
        "memory_id": "mem_demo_deploy_region",
        "scope": scope,
        "current_context": _demo_context(
            "memory.explain_versions",
            scope,
            intent="解释生产部署 region 的版本链",
            thread_topic="生产部署",
            session_id="openclaw-demo-session",
        ),
    }
    versions = handle_tool_request(
        "memory.explain_versions",
        versions_payload,
        service=service,
    )
    prefetch = handle_tool_request("memory.prefetch", prefetch_payload, service=service)
    reminder = HeartbeatReminderEngine(repo, now_ms=BASE_TS + 3600000).generate(
        scope=scope,
        current_context=_demo_context(
            "heartbeat.review_due",
            scope,
            intent="准备初赛提交材料和上线 checklist",
            thread_topic="生产部署 Demo",
            session_id="openclaw-demo-session",
        ),
    )
    summary_candidate = agent_run_summary_candidate(
        task="2026-05-04 Demo dry-run",
        scope=scope,
        used_memory_ids=["mem_demo_deploy_region", "mem_demo_submission_deadline"],
        missing_context=["live OpenClaw gateway 状态需要现场再确认"],
        new_candidate_hint="Demo 讲解词：先讲用户痛点，再展示 Agent 自动调用 memory.search 和 memory.prefetch。",
    )

    return {
        "ok": True,
        "date": "2026-05-04",
        "scope": scope,
        "db_path": db_path,
        "persistent_db": persistent,
        "production_feishu_write": False,
        "seeded_memory_ids": [memory.memory_id for memory in DEMO_MEMORIES],
        "openclaw_example_contract": validate_examples(),
        "steps": [
            {
                "name": "historical_decision_search",
                "tool": "memory.search",
                "input": search_payload,
                "output": search,
                "proves": "历史决策召回带 active 状态、evidence、matched_via 和 why_ranked。",
            },
            {
                "name": "conflict_update_version_chain",
                "tool": "memory.explain_versions",
                "input": versions_payload,
                "output": versions,
                "proves": "旧 cn-shanghai 保留为 superseded 证据，但默认当前答案只用 ap-shanghai。",
            },
            {
                "name": "task_prefetch_context_pack",
                "tool": "memory.prefetch",
                "input": prefetch_payload,
                "output": prefetch,
                "proves": "Agent 任务前拿到 compact context pack，不包含 raw events，不修改记忆状态。",
            },
            {
                "name": "heartbeat_reminder_candidate_dry_run",
                "tool": "heartbeat.reminder_candidate_dry_run",
                "input": {
                    "scope": scope,
                    "thread_topic": "生产部署 Demo",
                    "state_mutation": "none",
                },
                "output": reminder,
                "proves": "主动提醒只生成 candidate / dry-run，并对敏感内容做遮挡。",
            },
            {
                "name": "agent_run_summary_candidate",
                "tool": "agent_run_summary_candidate",
                "input": {"task": "2026-05-04 Demo dry-run", "scope": scope},
                "output": summary_candidate,
                "proves": "Agent 任务结束后只生成待确认总结，不绕过治理层自动写 active memory。",
            },
        ],
    }


def validate_examples() -> dict[str, Any]:
    examples_dir = ROOT / "agent_adapters" / "openclaw" / "examples"
    supported = set(supported_tool_names())
    examples = []
    for path in sorted(examples_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        step_results = []
        for step in payload.get("steps", []):
            tool_name = step.get("tool")
            arguments = step.get("arguments")
            parsed = validate_tool_request(tool_name, arguments)
            step_results.append(
                {
                    "tool": tool_name,
                    "declared": tool_name in supported,
                    "valid_request": bool(parsed.get("ok")),
                    "error": parsed.get("error"),
                }
            )
        examples.append({"file": str(path.relative_to(ROOT)), "steps": step_results})
    return {
        "ok": all(step["declared"] and step["valid_request"] for item in examples for step in item["steps"]),
        "examples": examples,
    }


def _demo_context(action: str, scope: str, **values: Any) -> dict[str, Any]:
    context = demo_permission_context(action, scope, actor_id="openclaw_demo", entrypoint="demo_replay")
    context["allowed_scopes"] = [scope]
    context.update({key: value for key, value in values.items() if value is not None})
    return context


def _insert_memory(conn: sqlite3.Connection, parsed_scope: Any, memory: DemoMemory, ts: int) -> None:
    suffix = memory.memory_id.removeprefix("mem_")
    active_version_id = f"ver_{suffix}_{len(memory.values)}"
    current_value = memory.values[-1]
    conn.execute(
        """
        INSERT INTO memories (
          id, scope_type, scope_id, type, subject, normalized_subject,
          current_value, reason, status, confidence, importance,
          source_event_id, active_version_id, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
        """,
        (
            memory.memory_id,
            parsed_scope.scope_type,
            parsed_scope.scope_id,
            memory.memory_type,
            memory.subject,
            normalize_subject(memory.subject),
            current_value,
            memory.reason,
            0.9,
            memory.importance,
            f"evt_{suffix}_{len(memory.values)}",
            active_version_id,
            ts,
            ts + (len(memory.values) - 1) * 30000,
        ),
    )
    previous_version_id = None
    for version_no, value in enumerate(memory.values, start=1):
        event_id = f"evt_{suffix}_{version_no}"
        version_id = f"ver_{suffix}_{version_no}"
        version_ts = ts + (version_no - 1) * 30000
        status = "active" if version_no == len(memory.values) else "superseded"
        conn.execute(
            """
            INSERT INTO raw_events (
              id, source_type, source_id, scope_type, scope_id, sender_id,
              event_time, content, raw_json, created_at
            )
            VALUES (?, 'demo_seed', ?, ?, ?, 'demo_seed', ?, ?, ?, ?)
            """,
            (
                event_id,
                event_id,
                parsed_scope.scope_type,
                parsed_scope.scope_id,
                version_ts,
                value,
                json.dumps({"seed": "2026-05-04-demo", "memory_id": memory.memory_id}, ensure_ascii=False),
                version_ts,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_versions (
              id, memory_id, version_no, value, reason, status,
              source_event_id, created_by, created_at, supersedes_version_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'demo_seed', ?, ?)
            """,
            (
                version_id,
                memory.memory_id,
                version_no,
                value,
                memory.reason,
                status,
                event_id,
                version_ts,
                previous_version_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_evidence (
              id, memory_id, version_id, source_type, source_url,
              source_event_id, quote, created_at
            )
            VALUES (?, ?, ?, 'demo_seed', NULL, ?, ?, ?)
            """,
            (
                f"evi_{suffix}_{version_no}",
                memory.memory_id,
                version_id,
                event_id,
                value,
                version_ts,
            ),
        )
        previous_version_id = version_id


def _clear_scope(conn: sqlite3.Connection, scope_type: str, scope_id: str) -> None:
    memory_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM memories WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        ).fetchall()
    ]
    raw_event_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM raw_events WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        ).fetchall()
    ]
    if memory_ids:
        placeholders = ",".join("?" for _ in memory_ids)
        conn.execute(f"DELETE FROM memory_evidence WHERE memory_id IN ({placeholders})", memory_ids)
        conn.execute(f"DELETE FROM memory_versions WHERE memory_id IN ({placeholders})", memory_ids)
        conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", memory_ids)
    if raw_event_ids:
        placeholders = ",".join("?" for _ in raw_event_ids)
        conn.execute(f"DELETE FROM raw_events WHERE id IN ({placeholders})", raw_event_ids)


def _with_scope(payload: dict[str, Any], scope: str) -> dict[str, Any]:
    updated = json.loads(json.dumps(payload, ensure_ascii=False))
    updated["scope"] = scope
    context = updated.get("current_context")
    if isinstance(context, dict):
        context["scope"] = scope
        if "allowed_scopes" in context:
            context["allowed_scopes"] = [scope]
    return updated


def _compact_summary(replay: dict[str, Any], output_path: Path) -> dict[str, Any]:
    steps = []
    for step in replay["steps"]:
        output = step["output"]
        steps.append(
            {
                "name": step["name"],
                "tool": step["tool"],
                "ok": isinstance(output, dict) and output.get("ok") is True,
                "proves": step["proves"],
            }
        )
    return {
        "ok": replay["ok"],
        "date": replay["date"],
        "scope": replay["scope"],
        "production_feishu_write": replay["production_feishu_write"],
        "json_output": str(output_path),
        "openclaw_example_contract_ok": replay["openclaw_example_contract"]["ok"],
        "steps": steps,
    }


class _demo_database:
    def __init__(self, db_path: str | None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            return self.db_path
        self.temp_dir = tempfile.TemporaryDirectory(prefix="feishu_memory_demo_")
        return Path(self.temp_dir.name) / "demo.sqlite"

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


if __name__ == "__main__":
    main()
