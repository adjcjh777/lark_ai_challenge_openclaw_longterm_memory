from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from typing import Any

from .extractor import extract_memory, is_override_intent, subject_for_query
from .models import parse_scope, normalize_subject


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class MemoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def remember(
        self,
        scope: str,
        content: str,
        *,
        source_type: str = "manual_cli",
        source_id: str | None = None,
        sender_id: str | None = None,
        created_by: str | None = "cli",
    ) -> dict[str, Any]:
        parsed_scope = parse_scope(scope)
        extracted = extract_memory(content)
        ts = now_ms()
        event_id = new_id("evt")
        source_id = source_id or event_id

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO raw_events (
                  id, source_type, source_id, scope_type, scope_id, sender_id,
                  event_time, content, raw_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    source_type,
                    source_id,
                    parsed_scope.scope_type,
                    parsed_scope.scope_id,
                    sender_id,
                    ts,
                    extracted.current_value,
                    json.dumps({"input": content}, ensure_ascii=False),
                    ts,
                ),
            )

            existing = self._find_memory(
                parsed_scope.scope_type,
                parsed_scope.scope_id,
                extracted.type,
                extracted.normalized_subject,
            )

            if existing is None:
                return self._insert_new_memory(extracted, parsed_scope, event_id, source_type, created_by, ts)

            if existing["current_value"] == extracted.current_value:
                self._insert_evidence(existing["id"], existing["active_version_id"], source_type, event_id, extracted.current_value, ts)
                return self._result(
                    "duplicate",
                    existing["id"],
                    existing["active_version_id"],
                    extracted,
                    self._active_version_no(existing["id"]),
                )

            if not is_override_intent(extracted.current_value):
                return self._result(
                    "needs_manual_review",
                    existing["id"],
                    existing["active_version_id"],
                    extracted,
                    self._active_version_no(existing["id"]),
                    note="same subject has a different value but no Day 1 override intent was detected",
                )

            return self._supersede_memory(existing, extracted, event_id, source_type, created_by, ts)

    def recall(self, scope: str, query: str) -> dict[str, Any] | None:
        parsed_scope = parse_scope(scope)
        query_subject = subject_for_query(query)
        normalized_query_subject = normalize_subject(query_subject)
        ts = now_ms()

        rows = self.conn.execute(
            """
            SELECT *
            FROM memories
            WHERE scope_type = ?
              AND scope_id = ?
              AND status = 'active'
            """,
            (parsed_scope.scope_type, parsed_scope.scope_id),
        ).fetchall()

        scored = [(self._score_recall(row, query, normalized_query_subject), row) for row in rows]
        scored = [(score, row) for score, row in scored if score > 0]
        if not scored:
            return None

        _, memory = max(scored, key=lambda item: item[0])
        version = self.conn.execute(
            "SELECT * FROM memory_versions WHERE id = ?",
            (memory["active_version_id"],),
        ).fetchone()
        evidence = self.conn.execute(
            """
            SELECT e.*, r.source_id
            FROM memory_evidence e
            LEFT JOIN raw_events r ON r.id = e.source_event_id
            WHERE e.memory_id = ?
              AND e.version_id = ?
            ORDER BY e.created_at DESC
            LIMIT 1
            """,
            (memory["id"], memory["active_version_id"]),
        ).fetchone()

        with self.conn:
            self.conn.execute(
                """
                UPDATE memories
                SET last_recalled_at = ?,
                    recall_count = recall_count + 1
                WHERE id = ?
                """,
                (ts, memory["id"]),
            )

        return {
            "answer": memory["current_value"],
            "memory_id": memory["id"],
            "status": memory["status"],
            "subject": memory["subject"],
            "type": memory["type"],
            "source": {
                "source_type": evidence["source_type"] if evidence else None,
                "source_id": evidence["source_id"] if evidence else None,
                "quote": evidence["quote"] if evidence else None,
            },
            "version": version["version_no"] if version else None,
        }

    def versions(self, memory_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, version_no, value, reason, status, source_event_id, supersedes_version_id
            FROM memory_versions
            WHERE memory_id = ?
            ORDER BY version_no
            """,
            (memory_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def has_source_event(self, source_type: str, source_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM raw_events
            WHERE source_type = ?
              AND source_id = ?
            LIMIT 1
            """,
            (source_type, source_id),
        ).fetchone()
        return row is not None

    def record_raw_event(
        self,
        scope: str,
        content: str,
        *,
        source_type: str,
        source_id: str,
        sender_id: str | None = None,
        raw_json: dict[str, Any] | None = None,
        event_time: int | None = None,
    ) -> str:
        parsed_scope = parse_scope(scope)
        ts = now_ms()
        event_id = new_id("evt")
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO raw_events (
                  id, source_type, source_id, scope_type, scope_id, sender_id,
                  event_time, content, raw_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    source_type,
                    source_id,
                    parsed_scope.scope_type,
                    parsed_scope.scope_id,
                    sender_id,
                    event_time or ts,
                    content,
                    json.dumps(raw_json, ensure_ascii=False) if raw_json is not None else None,
                    ts,
                ),
            )
        return event_id

    def add_noise_event(self, scope: str, content: str, *, source_type: str = "benchmark_noise") -> None:
        parsed_scope = parse_scope(scope)
        ts = now_ms()
        event_id = new_id("evt")
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO raw_events (
                  id, source_type, source_id, scope_type, scope_id, sender_id,
                  event_time, content, raw_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?)
                """,
                (
                    event_id,
                    source_type,
                    event_id,
                    parsed_scope.scope_type,
                    parsed_scope.scope_id,
                    ts,
                    content,
                    ts,
                ),
            )

    def _find_memory(self, scope_type: str, scope_id: str, memory_type: str, normalized_subject: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT *
            FROM memories
            WHERE scope_type = ?
              AND scope_id = ?
              AND type = ?
              AND normalized_subject = ?
            """,
            (scope_type, scope_id, memory_type, normalized_subject),
        ).fetchone()

    def _insert_new_memory(self, extracted, parsed_scope, event_id: str, source_type: str, created_by: str | None, ts: int) -> dict[str, Any]:
        memory_id = new_id("mem")
        version_id = new_id("ver")
        self.conn.execute(
            """
            INSERT INTO memories (
              id, scope_type, scope_id, type, subject, normalized_subject,
              current_value, reason, status, confidence, importance,
              source_event_id, active_version_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                parsed_scope.scope_type,
                parsed_scope.scope_id,
                extracted.type,
                extracted.subject,
                extracted.normalized_subject,
                extracted.current_value,
                extracted.reason,
                extracted.confidence,
                extracted.importance,
                event_id,
                version_id,
                ts,
                ts,
            ),
        )
        self._insert_version(version_id, memory_id, 1, extracted, "active", event_id, created_by, ts, None)
        self._insert_evidence(memory_id, version_id, source_type, event_id, extracted.current_value, ts)
        return self._result("created", memory_id, version_id, extracted, 1)

    def _supersede_memory(self, existing, extracted, event_id: str, source_type: str, created_by: str | None, ts: int) -> dict[str, Any]:
        old_version_id = existing["active_version_id"]
        new_version_no = self._active_version_no(existing["id"]) + 1
        new_version_id = new_id("ver")
        self.conn.execute(
            "UPDATE memory_versions SET status = 'superseded' WHERE id = ?",
            (old_version_id,),
        )
        self._insert_version(
            new_version_id,
            existing["id"],
            new_version_no,
            extracted,
            "active",
            event_id,
            created_by,
            ts,
            old_version_id,
        )
        self._insert_evidence(existing["id"], new_version_id, source_type, event_id, extracted.current_value, ts)
        self.conn.execute(
            """
            UPDATE memories
            SET current_value = ?,
                reason = ?,
                confidence = ?,
                importance = ?,
                source_event_id = ?,
                active_version_id = ?,
                updated_at = ?,
                status = 'active'
            WHERE id = ?
            """,
            (
                extracted.current_value,
                extracted.reason,
                extracted.confidence,
                extracted.importance,
                event_id,
                new_version_id,
                ts,
                existing["id"],
            ),
        )
        return self._result("superseded", existing["id"], new_version_id, extracted, new_version_no, superseded_version_id=old_version_id)

    def _insert_version(
        self,
        version_id: str,
        memory_id: str,
        version_no: int,
        extracted,
        status: str,
        event_id: str,
        created_by: str | None,
        ts: int,
        supersedes_version_id: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_versions (
              id, memory_id, version_no, value, reason, status,
              source_event_id, created_by, created_at, supersedes_version_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                memory_id,
                version_no,
                extracted.current_value,
                extracted.reason,
                status,
                event_id,
                created_by,
                ts,
                supersedes_version_id,
            ),
        )

    def _insert_evidence(self, memory_id: str, version_id: str | None, source_type: str, event_id: str, quote: str, ts: int) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_evidence (
              id, memory_id, version_id, source_type, source_url,
              source_event_id, quote, created_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (new_id("evi"), memory_id, version_id, source_type, event_id, quote, ts),
        )

    def _active_version_no(self, memory_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS version_no FROM memory_versions WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return int(row["version_no"])

    def _score_recall(self, memory, query: str, normalized_query_subject: str) -> int:
        score = 0
        normalized_memory_subject = memory["normalized_subject"]
        if normalized_memory_subject == normalized_query_subject:
            score += 100
        if memory["subject"] in query:
            score += 50

        haystack = f"{memory['subject']} {memory['current_value']}".lower()
        query_chars = set(query.lower().replace(" ", ""))
        score += sum(1 for char in query_chars if char in haystack)
        return score

    def _result(
        self,
        action: str,
        memory_id: str,
        version_id: str | None,
        extracted,
        version_no: int,
        **extra: Any,
    ) -> dict[str, Any]:
        result = {
            "action": action,
            "memory_id": memory_id,
            "version_id": version_id,
            "version": version_no,
            "memory": asdict(extracted),
        }
        result.update(extra)
        return result
