from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.db import connect, init_db
from memory_engine.models import normalize_subject, parse_scope


DEFAULT_SCOPE = "project:day4_demo"


@dataclass(frozen=True)
class DemoMemory:
    memory_id: str
    memory_type: str
    subject: str
    values: tuple[str, ...]
    reason: str | None = None
    importance: float = 0.8


DEMO_MEMORIES = (
    DemoMemory(
        "mem_day4_decision_architecture",
        "decision",
        "架构分层",
        (
            "初版决定 Memory Engine 只使用 SQLite 单层存储。",
            "不对，架构分层改成 SQLite 本地运行库 + Bitable 评委看板双层结构。",
        ),
        "需要同时满足本地稳定运行和评委可视化",
    ),
    DemoMemory(
        "mem_day4_decision_bot_scope",
        "decision",
        "Bot 监听范围",
        ("决定 Day4 Demo 只监听 @机器人消息和单聊，不开启群聊全量消息监听。",),
        "减少权限风险",
    ),
    DemoMemory(
        "mem_day4_decision_benchmark_metric",
        "decision",
        "Benchmark 指标",
        ("最终 Benchmark 汇总采用通过率、冲突准确率、旧值泄露率、证据覆盖率和平均延迟。",),
    ),
    DemoMemory(
        "mem_day4_decision_submission",
        "decision",
        "初赛交付优先级",
        ("决定初赛先交 Memory 白皮书、可运行 Demo 和 Benchmark Report，再做复赛增强项。",),
    ),
    DemoMemory(
        "mem_day4_workflow_deploy",
        "workflow",
        "生产部署",
        (
            "生产部署必须加 --canary --region cn-shanghai，不允许直接全量发布。",
            "不对，生产部署 region 改成 ap-shanghai，但仍然必须加 --canary。",
        ),
        "避免全量发布事故",
    ),
    DemoMemory(
        "mem_day4_workflow_handoff",
        "workflow",
        "每日 handoff",
        ("每日收工必须更新 handoff，包含完成项、验证命令、队友任务和未验证项。",),
    ),
    DemoMemory(
        "mem_day4_workflow_bitable_sync",
        "workflow",
        "Bitable 同步",
        ("Bitable 同步必须先 dry-run，看清 Ledger、Versions、Benchmark 三张表行数后再执行 --write。",),
    ),
    DemoMemory(
        "mem_day4_workflow_bot_test",
        "workflow",
        "真实 Bot 测试",
        ("真实 Bot 测试群里必须使用 @Feishu Memory Engine bot 加命令，单聊时才可以省略 @。",),
    ),
    DemoMemory(
        "mem_day4_preference_docs",
        "preference",
        "文档入口偏好",
        (
            "团队偏好把每日计划和 handoff 分开放，计划写意图和范围，handoff 写结果和证据。",
        ),
        importance=0.6,
    ),
    DemoMemory(
        "mem_day4_preference_language",
        "preference",
        "评委文案偏好",
        ("评委展示文案优先用中文短句，字段名保持英文，便于和代码、Bitable 同步字段对齐。",),
        importance=0.6,
    ),
    DemoMemory(
        "mem_day4_preference_demo_order",
        "preference",
        "Demo 顺序偏好",
        ("Demo 优先展示 Memory Ledger，再展示版本链，最后展示 Benchmark Results。",),
        importance=0.6,
    ),
    DemoMemory(
        "mem_day4_preference_tools",
        "preference",
        "工具偏好",
        ("飞书操作优先使用 lark-cli；只有 CLI 覆盖不了的能力再考虑直接调用 OpenAPI。",),
        importance=0.6,
    ),
    DemoMemory(
        "mem_day4_deadline_whitepaper",
        "deadline",
        "白皮书截止",
        (
            "白皮书初稿截止时间是 2026-05-02 20:00。",
            "不对，白皮书初稿截止改成 2026-05-01 22:00，给录屏留一天缓冲。",
        ),
        "提前留出录屏和 QA 时间",
    ),
    DemoMemory(
        "mem_day4_deadline_benchmark",
        "deadline",
        "Benchmark Report 截止",
        ("Benchmark Report 初稿必须在 2026-05-03 18:00 前完成。",),
    ),
    DemoMemory(
        "mem_day4_deadline_demo_video",
        "deadline",
        "Demo 录屏截止",
        ("Demo 录屏必须在 2026-05-05 21:00 前完成第一版。",),
    ),
    DemoMemory(
        "mem_day4_deadline_teammate_samples",
        "deadline",
        "样例数据截止",
        ("队友补充的 20 条样例记忆需要在今晚 23:30 前交付。",),
    ),
    DemoMemory(
        "mem_day4_risk_token",
        "risk",
        "Token 泄露风险",
        ("风险：Base token、chat_id、open_id 不得写入公开文档或提交到仓库。",),
        "避免公开仓库泄露飞书内部标识",
    ),
    DemoMemory(
        "mem_day4_risk_append_only",
        "risk",
        "重复同步风险",
        ("风险：当前 Bitable 同步是 append-only，重复执行 --write 会重复创建记录。",),
        "初赛看板可接受，生产化需要 upsert",
    ),
    DemoMemory(
        "mem_day4_risk_permission",
        "risk",
        "权限阻塞风险",
        ("风险：Bitable 权限未开通时不能阻塞本地 remember、recall 和 benchmark。",),
        "本地核心能力必须独立可运行",
    ),
    DemoMemory(
        "mem_day4_risk_noise",
        "risk",
        "干扰信息风险",
        ("风险：群聊里大量闲聊会干扰召回，所以记忆必须有 type、subject、status 和版本链。",),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Day 4 demo memories into local SQLite")
    parser.add_argument("--db-path", help="SQLite database path. Defaults to MEMORY_DB_PATH or data/memory.sqlite")
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    args = parser.parse_args()

    conn = connect(args.db_path)
    init_db(conn)
    seed_demo_data(conn, args.scope)
    print(json.dumps({"ok": True, "scope": args.scope, "memory_count": len(DEMO_MEMORIES)}, ensure_ascii=False, indent=2))


def seed_demo_data(conn, scope: str) -> None:
    parsed = parse_scope(scope)
    base_ts = 1777092000000
    with conn:
        _clear_scope(conn, parsed.scope_type, parsed.scope_id)
        for index, memory in enumerate(DEMO_MEMORIES, start=1):
            _insert_memory(conn, parsed, memory, base_ts + index * 60000)


def _clear_scope(conn, scope_type: str, scope_id: str) -> None:
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


def _insert_memory(conn, parsed_scope, memory: DemoMemory, ts: int) -> None:
    active_version_id = f"ver_{memory.memory_id.removeprefix('mem_')}_{len(memory.values)}"
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
            0.82,
            memory.importance,
            f"evt_{memory.memory_id.removeprefix('mem_')}_{len(memory.values)}",
            active_version_id,
            ts,
            ts + (len(memory.values) - 1) * 30000,
        ),
    )
    previous_version_id = None
    for version_no, value in enumerate(memory.values, start=1):
        event_id = f"evt_{memory.memory_id.removeprefix('mem_')}_{version_no}"
        version_id = f"ver_{memory.memory_id.removeprefix('mem_')}_{version_no}"
        version_ts = ts + (version_no - 1) * 30000
        status = "active" if version_no == len(memory.values) else "superseded"
        conn.execute(
            """
            INSERT INTO raw_events (
              id, source_type, source_id, scope_type, scope_id, sender_id,
              event_time, content, raw_json, created_at
            )
            VALUES (?, 'day4_demo_seed', ?, ?, ?, 'demo_seed', ?, ?, ?, ?)
            """,
            (
                event_id,
                event_id,
                parsed_scope.scope_type,
                parsed_scope.scope_id,
                version_ts,
                value,
                json.dumps({"seed": "day4_demo", "memory_id": memory.memory_id}, ensure_ascii=False),
                version_ts,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_versions (
              id, memory_id, version_no, value, reason, status,
              source_event_id, created_by, created_at, supersedes_version_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'day4_demo_seed', ?, ?)
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
            VALUES (?, ?, ?, 'day4_demo_seed', NULL, ?, ?, ?)
            """,
            (
                f"evi_{memory.memory_id.removeprefix('mem_')}_{version_no}",
                memory.memory_id,
                version_id,
                event_id,
                value,
                version_ts,
            ),
        )
        previous_version_id = version_id


if __name__ == "__main__":
    main()
