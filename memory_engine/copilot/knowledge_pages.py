from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from memory_engine.models import parse_scope
from memory_engine.repository import MemoryRepository


@dataclass(frozen=True)
class CompiledMemoryCard:
    memory_id: str
    subject: str
    memory_type: str
    current_value: str
    version: int | None
    evidence_quote: str | None
    evidence_source_type: str | None
    evidence_source_id: str | None
    superseded_version_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "subject": self.subject,
            "type": self.memory_type,
            "current_value": self.current_value,
            "version": self.version,
            "evidence": {
                "quote": self.evidence_quote,
                "source_type": self.evidence_source_type,
                "source_id": self.evidence_source_id,
            },
            "superseded_version_count": self.superseded_version_count,
        }


def compile_project_memory_cards(repository: MemoryRepository, *, scope: str) -> dict[str, Any]:
    cards = _active_memory_cards(repository, scope=scope)
    open_questions = _open_question_count(repository, scope=scope)
    markdown = _render_markdown(scope=scope, cards=cards, open_questions=open_questions)
    return {
        "ok": True,
        "scope": scope,
        "card_count": len(cards),
        "open_question_count": open_questions,
        "cards": [card.to_dict() for card in cards],
        "markdown": markdown,
        "generation_policy": {
            "source": "active_curated_memory_only",
            "raw_events_included": False,
            "requires_evidence": True,
            "writes_feishu": False,
        },
    }


def _active_memory_cards(repository: MemoryRepository, *, scope: str) -> list[CompiledMemoryCard]:
    parsed_scope = parse_scope(scope)
    rows = repository.conn.execute(
        """
        SELECT
          m.id AS memory_id,
          m.type AS memory_type,
          m.subject,
          m.current_value,
          v.version_no,
          e.source_type AS evidence_source_type,
          e.quote AS evidence_quote,
          r.source_id AS raw_source_id,
          r.raw_json AS raw_json,
          (
            SELECT COUNT(*)
            FROM memory_versions old_v
            WHERE old_v.memory_id = m.id
              AND old_v.status = 'superseded'
          ) AS superseded_version_count
        FROM memories m
        LEFT JOIN memory_versions v ON v.id = m.active_version_id
        LEFT JOIN memory_evidence e
          ON e.id = (
            SELECT latest_e.id
            FROM memory_evidence latest_e
            WHERE latest_e.memory_id = m.id
              AND latest_e.version_id = m.active_version_id
            ORDER BY latest_e.created_at DESC
            LIMIT 1
          )
        LEFT JOIN raw_events r ON r.id = e.source_event_id
        WHERE m.scope_type = ?
          AND m.scope_id = ?
          AND m.status = 'active'
          AND e.quote IS NOT NULL
          AND TRIM(e.quote) != ''
        ORDER BY m.subject, m.updated_at DESC, m.id
        """,
        (parsed_scope.scope_type, parsed_scope.scope_id),
    ).fetchall()
    cards: list[CompiledMemoryCard] = []
    for row in rows:
        cards.append(
            CompiledMemoryCard(
                memory_id=str(row["memory_id"]),
                subject=str(row["subject"]),
                memory_type=str(row["memory_type"]),
                current_value=str(row["current_value"]),
                version=int(row["version_no"]) if row["version_no"] is not None else None,
                evidence_quote=str(row["evidence_quote"]) if row["evidence_quote"] is not None else None,
                evidence_source_type=str(row["evidence_source_type"]) if row["evidence_source_type"] else None,
                evidence_source_id=_evidence_source_id(row),
                superseded_version_count=int(row["superseded_version_count"] or 0),
            )
        )
    return cards


def _open_question_count(repository: MemoryRepository, *, scope: str) -> int:
    parsed_scope = parse_scope(scope)
    row = repository.conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM memories
        WHERE scope_type = ?
          AND scope_id = ?
          AND status IN ('candidate', 'needs_evidence')
        """,
        (parsed_scope.scope_type, parsed_scope.scope_id),
    ).fetchone()
    return int(row["count"] if row else 0)


def _render_markdown(*, scope: str, cards: list[CompiledMemoryCard], open_questions: int) -> str:
    lines = [
        f"# 项目记忆卡册：{scope}",
        "",
        "本页由 active curated memory 编译生成，只展示当前有效结论和证据，不包含 raw events。",
        "",
        "## 摘要",
        "",
        f"- 当前有效记忆：{len(cards)} 条",
        f"- 待确认 / 待补证据问题：{open_questions} 条",
        "",
        "## 记忆卡片",
        "",
    ]
    for card in cards:
        lines.extend(_card_lines(card))
    if not cards:
        lines.append("_当前没有带证据的 active memory。_")
    return "\n".join(lines).rstrip() + "\n"


def _card_lines(card: CompiledMemoryCard) -> list[str]:
    lines = [
        f"### {card.subject}",
        "",
        f"- 当前结论：{card.current_value}",
        f"- 类型：{card.memory_type}",
        f"- 版本：v{card.version or 1}",
        f"- 证据：{card.evidence_quote or '无'}",
        f"- 来源：{card.evidence_source_type or 'unknown'} / {card.evidence_source_id or 'unknown'}",
    ]
    if card.superseded_version_count:
        lines.append(f"- 历史覆盖：{card.superseded_version_count} 个旧版本已 superseded")
    else:
        lines.append("- 历史覆盖：暂无旧版本")
    lines.append("")
    return lines


def _evidence_source_id(row: Any) -> str | None:
    if row["raw_source_id"]:
        return str(row["raw_source_id"])
    raw_json = row["raw_json"]
    if not raw_json:
        return None
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    source = parsed.get("source")
    if isinstance(source, dict) and source.get("source_id"):
        return str(source["source_id"])
    return None
