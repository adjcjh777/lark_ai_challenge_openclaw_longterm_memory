from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from memory_engine.extractor import extract_memory, is_override_intent
from memory_engine.models import (
    DECISION_WORDS,
    OVERRIDE_WORDS,
    PREFERENCE_WORDS,
    WORKFLOW_WORDS,
    contains_any,
    parse_scope,
)
from memory_engine.repository import MemoryRepository, new_id, now_ms

from .permissions import sensitive_risk_flags
from .schemas import ConfirmRequest, CopilotError, CreateCandidateRequest, RejectRequest


_PREFIX_SIGNALS = ("记忆", "规则", "结论", "约束", "风险", "负责人", "决定")


class CopilotGovernance:
    """Candidate state transitions owned by the Copilot core."""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def create_candidate(self, request: CreateCandidateRequest) -> dict[str, Any]:
        extracted = extract_memory(request.text)
        evidence = request.source.to_dict()
        risk_flags = self._risk_flags(request)

        if not _has_candidate_signal(request.text):
            return {
                "ok": True,
                "action": "ignored",
                "status": "not_candidate",
                "scope": request.scope,
                "candidate": None,
                "risk_flags": ["low_memory_signal", *risk_flags],
                "conflict": {"has_conflict": False},
                "recommended_action": "ignore",
                "evidence": evidence,
                "reason": "这段内容缺少长期记忆信号，不进入待确认记忆队列。",
            }

        if request.auto_confirm and risk_flags:
            return CopilotError(
                "sensitive_content_blocked",
                "auto_confirm is blocked for sensitive or high-risk candidate content",
                details={"risk_flags": risk_flags},
            ).to_response()

        parsed_scope = parse_scope(request.scope)
        ts = now_ms()
        event_id = self._insert_raw_event(request, extracted.current_value, ts)
        existing = self._find_existing(parsed_scope.scope_type, parsed_scope.scope_id, extracted.type, extracted.normalized_subject)

        with self.repository.conn:
            if existing is None:
                candidate = self._insert_new_candidate(request, extracted, parsed_scope, event_id, ts, risk_flags)
            elif existing["current_value"] == extracted.current_value:
                self._insert_evidence(existing["id"], existing["active_version_id"], request.source.source_type, event_id, request.source.quote, ts)
                candidate = self._duplicate_response(request, extracted, existing, risk_flags)
            else:
                candidate = self._insert_conflict_candidate(request, extracted, existing, event_id, ts, risk_flags)

        if request.auto_confirm and candidate.get("candidate"):
            confirm_request = ConfirmRequest(
                candidate_id=str(candidate["candidate"]["candidate_id"]),
                scope=request.scope,
                actor_id=request.source.actor_id,
                reason="auto_confirm requested after governance checks",
            )
            confirmed = self.confirm(confirm_request)
            if confirmed.get("ok"):
                confirmed["action"] = "auto_confirmed"
            return confirmed

        return candidate

    def confirm(self, request: ConfirmRequest) -> dict[str, Any]:
        memory = self._memory_by_id(request.candidate_id)
        if memory is not None:
            return self._confirm_candidate_memory(request, memory)

        version = self._version_by_id(request.candidate_id)
        if version is not None:
            return self._confirm_candidate_version(request, version)

        return CopilotError(
            "memory_not_found",
            "candidate was not found",
            details={"candidate_id": request.candidate_id},
        ).to_response()

    def reject(self, request: RejectRequest) -> dict[str, Any]:
        memory = self._memory_by_id(request.candidate_id)
        if memory is not None:
            return self._reject_candidate_memory(request, memory)

        version = self._version_by_id(request.candidate_id)
        if version is not None:
            return self._reject_candidate_version(request, version)

        return CopilotError(
            "memory_not_found",
            "candidate was not found",
            details={"candidate_id": request.candidate_id},
        ).to_response()

    def _insert_raw_event(self, request: CreateCandidateRequest, content: str, ts: int) -> str:
        parsed_scope = parse_scope(request.scope)
        event_id = new_id("evt")
        raw_json = {
            "input": request.text,
            "source": request.source.to_dict(),
            "current_context": dict(request.current_context),
            "document_token": request.current_context.get("document_token") or request.source.source_doc_id,
            "document_title": request.current_context.get("document_title"),
        }
        self.repository.conn.execute(
            """
            INSERT INTO raw_events (
              id, source_type, source_id, scope_type, scope_id, sender_id,
              event_time, content, raw_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                request.source.source_type,
                request.source.source_id,
                parsed_scope.scope_type,
                parsed_scope.scope_id,
                request.source.actor_id,
                ts,
                content,
                json.dumps(raw_json, ensure_ascii=False),
                ts,
            ),
        )
        return event_id

    def _insert_new_candidate(
        self,
        request: CreateCandidateRequest,
        extracted: Any,
        parsed_scope: Any,
        event_id: str,
        ts: int,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        memory_id = new_id("mem")
        version_id = new_id("ver")
        self.repository.conn.execute(
            """
            INSERT INTO memories (
              id, scope_type, scope_id, type, subject, normalized_subject,
              current_value, reason, status, confidence, importance,
              source_event_id, active_version_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?)
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
        self._insert_version(version_id, memory_id, 1, extracted, "candidate", event_id, request.source.actor_id, ts, None)
        self._insert_evidence(memory_id, version_id, request.source.source_type, event_id, request.source.quote, ts)
        candidate = self._candidate_payload(
            candidate_id=memory_id,
            memory_id=memory_id,
            version_id=version_id,
            extracted=extracted,
            status="candidate",
            version=1,
            evidence=request.source.to_dict(),
            risk_flags=risk_flags,
            conflict={"has_conflict": False},
        )
        return self._candidate_response("created", request.scope, candidate)

    def _duplicate_response(
        self,
        request: CreateCandidateRequest,
        extracted: Any,
        existing: Any,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        candidate = self._candidate_payload(
            candidate_id=str(existing["id"]),
            memory_id=str(existing["id"]),
            version_id=existing["active_version_id"],
            extracted=extracted,
            status=str(existing["status"]),
            version=self._version_no(str(existing["id"])),
            evidence=request.source.to_dict(),
            risk_flags=["duplicate", *risk_flags],
            conflict={"has_conflict": False},
        )
        return self._candidate_response("duplicate", request.scope, candidate)

    def _insert_conflict_candidate(
        self,
        request: CreateCandidateRequest,
        extracted: Any,
        existing: Any,
        event_id: str,
        ts: int,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        version_no = self._version_no(str(existing["id"])) + 1
        version_id = new_id("ver")
        self._insert_version(
            version_id,
            str(existing["id"]),
            version_no,
            extracted,
            "candidate",
            event_id,
            request.source.actor_id,
            ts,
            existing["active_version_id"],
        )
        self._insert_evidence(str(existing["id"]), version_id, request.source.source_type, event_id, request.source.quote, ts)
        conflict = {
            "has_conflict": True,
            "old_memory_id": str(existing["id"]),
            "old_value": str(existing["current_value"]),
            "old_status": str(existing["status"]),
            "reason": "same type and subject already has an active value",
        }
        flags = ["conflict_candidate", *risk_flags]
        if is_override_intent(extracted.current_value):
            flags.append("override_intent")
        candidate = self._candidate_payload(
            candidate_id=version_id,
            memory_id=str(existing["id"]),
            version_id=version_id,
            extracted=extracted,
            status="candidate",
            version=version_no,
            evidence=request.source.to_dict(),
            risk_flags=flags,
            conflict=conflict,
        )
        return self._candidate_response("candidate_conflict", request.scope, candidate)

    def _confirm_candidate_memory(self, request: ConfirmRequest, memory: Any) -> dict[str, Any]:
        if not self._memory_scope_matches(memory, request.scope):
            return self._scope_error(request.scope)
        if memory["status"] != "candidate":
            return self._not_confirmable(request.candidate_id, str(memory["status"]))
        evidence_error = self._evidence_error(str(memory["id"]), memory["active_version_id"])
        if evidence_error is not None:
            return evidence_error

        ts = now_ms()
        with self.repository.conn:
            self.repository.conn.execute(
                "UPDATE memories SET status = 'active', updated_at = ? WHERE id = ?",
                (ts, memory["id"]),
            )
            self.repository.conn.execute(
                "UPDATE memory_versions SET status = 'active' WHERE id = ?",
                (memory["active_version_id"],),
            )
        return self._status_response("confirmed", self._memory_by_id(str(memory["id"])), candidate_id=str(memory["id"]))

    def _confirm_candidate_version(self, request: ConfirmRequest, version: Any) -> dict[str, Any]:
        memory = self._memory_by_id(str(version["memory_id"]))
        if memory is None:
            return CopilotError("memory_not_found", "candidate parent memory was not found").to_response()
        if not self._memory_scope_matches(memory, request.scope):
            return self._scope_error(request.scope)
        if version["status"] != "candidate":
            return self._not_confirmable(request.candidate_id, str(version["status"]))
        evidence_error = self._evidence_error(str(memory["id"]), str(version["id"]))
        if evidence_error is not None:
            return evidence_error

        old_version_id = memory["active_version_id"]
        ts = now_ms()
        with self.repository.conn:
            if old_version_id:
                self.repository.conn.execute(
                    "UPDATE memory_versions SET status = 'superseded' WHERE id = ?",
                    (old_version_id,),
                )
            self.repository.conn.execute(
                "UPDATE memory_versions SET status = 'active' WHERE id = ?",
                (version["id"],),
            )
            self.repository.conn.execute(
                """
                UPDATE memories
                SET current_value = ?,
                    reason = ?,
                    source_event_id = ?,
                    active_version_id = ?,
                    status = 'active',
                    updated_at = ?
                WHERE id = ?
                """,
                (version["value"], version["reason"], version["source_event_id"], version["id"], ts, memory["id"]),
            )
        response = self._status_response("confirmed", self._memory_by_id(str(memory["id"])), candidate_id=str(version["id"]))
        response["superseded"] = {
            "version_id": old_version_id,
            "value": str(memory["current_value"]),
            "status": "superseded",
        }
        return response

    def _reject_candidate_memory(self, request: RejectRequest, memory: Any) -> dict[str, Any]:
        if not self._memory_scope_matches(memory, request.scope):
            return self._scope_error(request.scope)
        if memory["status"] != "candidate":
            return self._not_confirmable(request.candidate_id, str(memory["status"]))
        ts = now_ms()
        with self.repository.conn:
            self.repository.conn.execute(
                "UPDATE memories SET status = 'rejected', updated_at = ? WHERE id = ?",
                (ts, memory["id"]),
            )
            self.repository.conn.execute(
                "UPDATE memory_versions SET status = 'rejected' WHERE id = ?",
                (memory["active_version_id"],),
            )
        return self._status_response("rejected", self._memory_by_id(str(memory["id"])), candidate_id=str(memory["id"]))

    def _reject_candidate_version(self, request: RejectRequest, version: Any) -> dict[str, Any]:
        memory = self._memory_by_id(str(version["memory_id"]))
        if memory is None:
            return CopilotError("memory_not_found", "candidate parent memory was not found").to_response()
        if not self._memory_scope_matches(memory, request.scope):
            return self._scope_error(request.scope)
        if version["status"] != "candidate":
            return self._not_confirmable(request.candidate_id, str(version["status"]))
        ts = now_ms()
        with self.repository.conn:
            self.repository.conn.execute(
                "UPDATE memory_versions SET status = 'rejected' WHERE id = ?",
                (version["id"],),
            )
            self.repository.conn.execute(
                "UPDATE memories SET updated_at = ? WHERE id = ?",
                (ts, memory["id"]),
            )
        response = self._status_response("rejected", self._memory_by_id(str(memory["id"])), candidate_id=str(version["id"]))
        response["memory"]["status"] = "rejected"
        return response

    def _candidate_response(self, action: str, scope: str, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "action": action,
            "scope": scope,
            "candidate": candidate,
            "candidate_id": candidate["candidate_id"],
            "memory_id": candidate["memory_id"],
            "version_id": candidate["version_id"],
            "status": candidate["status"],
            "risk_flags": candidate["risk_flags"],
            "conflict": candidate["conflict"],
            "recommended_action": candidate["recommended_action"],
            "evidence": candidate["evidence"],
            "memory": candidate["memory"],
            "quote": candidate["evidence"]["quote"],
        }

    def _status_response(self, action: str, memory: Any, *, candidate_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "action": action,
            "candidate_id": candidate_id,
            "memory_id": str(memory["id"]),
            "status": str(memory["status"]),
            "memory": {
                "memory_id": str(memory["id"]),
                "type": str(memory["type"]),
                "subject": str(memory["subject"]),
                "current_value": str(memory["current_value"]),
                "status": str(memory["status"]),
                "version_id": memory["active_version_id"],
            },
        }

    def _candidate_payload(
        self,
        *,
        candidate_id: str,
        memory_id: str,
        version_id: str | None,
        extracted: Any,
        status: str,
        version: int,
        evidence: dict[str, Any],
        risk_flags: list[str],
        conflict: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "candidate_id": candidate_id,
            "memory_id": memory_id,
            "version_id": version_id,
            "type": extracted.type,
            "subject": extracted.subject,
            "current_value": extracted.current_value,
            "summary": extracted.reason,
            "confidence": extracted.confidence,
            "importance": extracted.importance,
            "status": status,
            "version": version,
            "evidence": evidence,
            "risk_flags": risk_flags,
            "conflict": conflict,
            "recommended_action": _recommended_action(risk_flags, conflict),
            "memory": asdict(extracted),
        }

    def _insert_version(
        self,
        version_id: str,
        memory_id: str,
        version_no: int,
        extracted: Any,
        status: str,
        event_id: str,
        created_by: str | None,
        ts: int,
        supersedes_version_id: str | None,
    ) -> None:
        self.repository.conn.execute(
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
        self.repository.conn.execute(
            """
            INSERT INTO memory_evidence (
              id, memory_id, version_id, source_type, source_url,
              source_event_id, quote, created_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (new_id("evi"), memory_id, version_id, source_type, event_id, quote, ts),
        )

    def _find_existing(self, scope_type: str, scope_id: str, memory_type: str, normalized_subject: str) -> Any:
        return self.repository.conn.execute(
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

    def _memory_by_id(self, memory_id: str) -> Any:
        return self.repository.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()

    def _version_by_id(self, version_id: str) -> Any:
        return self.repository.conn.execute("SELECT * FROM memory_versions WHERE id = ?", (version_id,)).fetchone()

    def _version_no(self, memory_id: str) -> int:
        row = self.repository.conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS version_no FROM memory_versions WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return int(row["version_no"])

    def _evidence_error(self, memory_id: str, version_id: str | None) -> dict[str, Any] | None:
        row = self.repository.conn.execute(
            """
            SELECT quote
            FROM memory_evidence
            WHERE memory_id = ?
              AND version_id IS ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (memory_id, version_id),
        ).fetchone()
        if row is not None and str(row["quote"] or "").strip():
            return None
        return CopilotError(
            "candidate_not_confirmable",
            "candidate cannot become active without evidence quote",
            details={"candidate_id": version_id or memory_id, "reason": "evidence_missing"},
        ).to_response()

    def _memory_scope_matches(self, memory: Any, scope: str) -> bool:
        parsed = parse_scope(scope)
        return memory["scope_type"] == parsed.scope_type and memory["scope_id"] == parsed.scope_id

    def _scope_error(self, scope: str) -> dict[str, Any]:
        return CopilotError(
            "permission_denied",
            "candidate scope does not match requested scope",
            details={"requested_scope": scope},
        ).to_response()

    def _not_confirmable(self, candidate_id: str, status: str) -> dict[str, Any]:
        return CopilotError(
            "candidate_not_confirmable",
            "candidate is not in candidate status",
            details={"candidate_id": candidate_id, "status": status},
        ).to_response()

    def _risk_flags(self, request: CreateCandidateRequest) -> list[str]:
        flags = sensitive_risk_flags(request.text, request.source.quote)
        if extract_memory(request.text).confidence < 0.6:
            flags.append("low_confidence")
        return sorted(set(flags))


def _has_candidate_signal(text: str) -> bool:
    stripped = text.strip()
    if contains_any(stripped, DECISION_WORDS + WORKFLOW_WORDS + PREFERENCE_WORDS + OVERRIDE_WORDS):
        return True
    return any(stripped.startswith(f"{prefix}:") or stripped.startswith(f"{prefix}：") for prefix in _PREFIX_SIGNALS)


def _recommended_action(risk_flags: list[str], conflict: dict[str, Any]) -> str:
    if "sensitive_content" in risk_flags:
        return "manual_review_sensitive"
    if conflict.get("has_conflict"):
        return "manual_review_conflict"
    return "review_candidate"
