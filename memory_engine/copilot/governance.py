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
from .schemas import ConfirmRequest, CopilotError, CreateCandidateRequest, ExplainVersionsRequest, RejectRequest

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
        tenant_id = _tenant_id(request.current_context)
        organization_id = _organization_id(request.current_context)
        existing = self._find_existing(
            parsed_scope.scope_type,
            parsed_scope.scope_id,
            tenant_id,
            organization_id,
            extracted.type,
            extracted.normalized_subject,
            allow_type_fallback=True,
        )

        with self.repository.conn:
            if existing is None:
                candidate = self._insert_new_candidate(request, extracted, parsed_scope, event_id, ts, risk_flags)
            elif existing["current_value"] == extracted.current_value:
                self._insert_evidence(
                    existing["id"],
                    existing["active_version_id"],
                    request.source.source_type,
                    event_id,
                    request.source.quote,
                    ts,
                )
                candidate = self._duplicate_response(request, extracted, existing, risk_flags)
            else:
                candidate = self._insert_conflict_candidate(request, extracted, existing, event_id, ts, risk_flags)

        if request.auto_confirm and candidate.get("candidate"):
            confirm_request = ConfirmRequest(
                candidate_id=str(candidate["candidate"]["candidate_id"]),
                scope=request.scope,
                actor_id=request.source.actor_id,
                reason="auto_confirm requested after governance checks",
                current_context=_context_for_auto_confirm(request.current_context),
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

    def needs_evidence(self, request: RejectRequest) -> dict[str, Any]:
        memory = self._memory_by_id(request.candidate_id)
        if memory is not None:
            return self._mark_candidate_memory(request, memory, status="needs_evidence", action="needs_evidence")

        version = self._version_by_id(request.candidate_id)
        if version is not None:
            return self._mark_candidate_version(request, version, status="needs_evidence", action="needs_evidence")

        return CopilotError(
            "memory_not_found",
            "candidate was not found",
            details={"candidate_id": request.candidate_id},
        ).to_response()

    def expire(self, request: RejectRequest) -> dict[str, Any]:
        memory = self._memory_by_id(request.candidate_id)
        if memory is not None:
            return self._mark_candidate_memory(request, memory, status="expired", action="expired")

        version = self._version_by_id(request.candidate_id)
        if version is not None:
            return self._mark_candidate_version(request, version, status="expired", action="expired")

        return CopilotError(
            "memory_not_found",
            "candidate was not found",
            details={"candidate_id": request.candidate_id},
        ).to_response()

    def explain_versions(self, request: ExplainVersionsRequest) -> dict[str, Any]:
        memory = self._memory_by_id(request.memory_id)
        if memory is None:
            return CopilotError(
                "memory_not_found",
                "memory was not found",
                details={"memory_id": request.memory_id},
            ).to_response()
        if not self._memory_scope_matches(memory, request.scope):
            return self._scope_error(request.scope)

        archived_filter = "" if request.include_archived else "AND mv.status != 'archived'"
        rows = self.repository.conn.execute(
            f"""
            SELECT
              mv.id AS version_id,
              mv.version_no,
              mv.value,
              mv.reason,
              mv.status,
              mv.created_by,
              mv.created_at,
              mv.supersedes_version_id,
              e.source_type AS evidence_source_type,
              e.quote AS evidence_quote,
              r.source_id AS evidence_source_id,
              r.raw_json AS raw_json
            FROM memory_versions mv
            LEFT JOIN memory_evidence e ON e.id = (
              SELECT latest_e.id
              FROM memory_evidence latest_e
              WHERE latest_e.memory_id = mv.memory_id
                AND latest_e.version_id = mv.id
              ORDER BY latest_e.created_at DESC
              LIMIT 1
            )
            LEFT JOIN raw_events r ON r.id = COALESCE(e.source_event_id, mv.source_event_id)
            WHERE mv.memory_id = ?
              {archived_filter}
            ORDER BY mv.version_no
            """,
            (request.memory_id,),
        ).fetchall()

        active_version_id = memory["active_version_id"]
        versions = [self._version_payload(row, active_version_id=active_version_id) for row in rows]
        active_version = next((item for item in versions if item["version_id"] == active_version_id), None)
        return {
            "ok": True,
            "tool": "memory.explain_versions",
            "memory_id": str(memory["id"]),
            "scope": request.scope,
            "subject": str(memory["subject"]),
            "type": str(memory["type"]),
            "status": str(memory["status"]),
            "active_version": active_version,
            "versions": versions,
            "supersedes": [
                {
                    "version_id": item["version_id"],
                    "supersedes_version_id": item["supersedes_version_id"],
                    "reason": "这个版本确认后覆盖了旧值，旧值只保留为版本证据，不再作为当前答案。",
                }
                for item in versions
                if item.get("supersedes_version_id")
            ],
            "explanation": self._version_explanation(active_version, versions),
            "user_explanation": self._user_version_explanation(active_version, versions),
        }

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
              id, tenant_id, organization_id, workspace_id, visibility_policy,
              source_type, source_id, scope_type, scope_id, sender_id,
              event_time, content, raw_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                _tenant_id(request.current_context),
                _organization_id(request.current_context),
                _workspace_id(request.current_context, request.scope),
                _visibility_policy(request.current_context),
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
              id, tenant_id, organization_id, workspace_id, visibility_policy,
              scope_type, scope_id, type, subject, normalized_subject,
              current_value, reason, status, confidence, importance,
              owner_id, created_by, updated_by, source_event_id, active_version_id,
              created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                _tenant_id(request.current_context),
                _organization_id(request.current_context),
                _workspace_id(request.current_context, request.scope),
                _visibility_policy(request.current_context),
                parsed_scope.scope_type,
                parsed_scope.scope_id,
                extracted.type,
                extracted.subject,
                extracted.normalized_subject,
                extracted.current_value,
                extracted.reason,
                extracted.confidence,
                extracted.importance,
                request.source.actor_id,
                request.source.actor_id,
                request.source.actor_id,
                event_id,
                version_id,
                ts,
                ts,
            ),
        )
        self._insert_version(
            version_id, memory_id, 1, extracted, "candidate", event_id, request.source.actor_id, ts, None
        )
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
        self._insert_evidence(
            str(existing["id"]), version_id, request.source.source_type, event_id, request.source.quote, ts
        )
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
        return self._status_response(
            "confirmed", self._memory_by_id(str(memory["id"])), candidate_id=str(memory["id"]), actor_id=request.actor_id
        )

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
        response = self._status_response(
            "confirmed", self._memory_by_id(str(memory["id"])), candidate_id=str(version["id"]), actor_id=request.actor_id
        )
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
        return self._status_response(
            "rejected", self._memory_by_id(str(memory["id"])), candidate_id=str(memory["id"]), actor_id=request.actor_id
        )

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
        response = self._status_response(
            "rejected", self._memory_by_id(str(memory["id"])), candidate_id=str(version["id"]), actor_id=request.actor_id
        )
        response["memory"]["status"] = "rejected"
        response["review_status"] = "rejected"
        return response

    def _mark_candidate_memory(self, request: RejectRequest, memory: Any, *, status: str, action: str) -> dict[str, Any]:
        if not self._memory_scope_matches(memory, request.scope):
            return self._scope_error(request.scope)
        if memory["status"] != "candidate":
            return self._not_confirmable(request.candidate_id, str(memory["status"]))
        ts = now_ms()
        with self.repository.conn:
            self.repository.conn.execute(
                "UPDATE memories SET status = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                (status, request.actor_id, ts, memory["id"]),
            )
            self.repository.conn.execute(
                "UPDATE memory_versions SET status = ? WHERE id = ?",
                (status, memory["active_version_id"]),
            )
        return self._status_response(
            action,
            self._memory_by_id(str(memory["id"])),
            candidate_id=str(memory["id"]),
            actor_id=request.actor_id,
        )

    def _mark_candidate_version(self, request: RejectRequest, version: Any, *, status: str, action: str) -> dict[str, Any]:
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
                "UPDATE memory_versions SET status = ? WHERE id = ?",
                (status, version["id"]),
            )
            self.repository.conn.execute(
                "UPDATE memories SET updated_by = ?, updated_at = ? WHERE id = ?",
                (request.actor_id, ts, memory["id"]),
            )
        response = self._status_response(
            action,
            self._memory_by_id(str(memory["id"])),
            candidate_id=str(version["id"]),
            actor_id=request.actor_id,
        )
        response["status"] = status
        response["memory"]["status"] = status
        response["review_status"] = _review_status(status)
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
            "review_status": candidate["review_status"],
            "source_type": candidate["source_type"],
            "risk_level": candidate["risk_level"],
            "conflict_status": candidate["conflict_status"],
            "risk_flags": candidate["risk_flags"],
            "conflict": candidate["conflict"],
            "recommended_action": candidate["recommended_action"],
            "review_queue": candidate["review_queue"],
            "evidence": candidate["evidence"],
            "memory": candidate["memory"],
            "quote": candidate["evidence"]["quote"],
            "owner_id": candidate.get("owner_id"),
        }

    def _status_response(self, action: str, memory: Any, *, candidate_id: str, actor_id: str | None = None) -> dict[str, Any]:
        evidence = self._latest_evidence(str(memory["id"]), memory["active_version_id"])
        version = self._version_no(str(memory["id"]))
        status = str(memory["status"])
        ts = int(memory["updated_at"] or 0)
        return {
            "ok": True,
            "action": action,
            "candidate_id": candidate_id,
            "memory_id": str(memory["id"]),
            "status": status,
            "review_status": _review_status(status),
            "last_handler": actor_id or memory["updated_by"],
            "last_handled_at": ts,
            "review_queue": {
                "review_status": _review_status(status),
                "last_handler": actor_id or memory["updated_by"],
                "last_handled_at": ts,
                "state_mutation": action,
            },
            "memory": {
                "memory_id": str(memory["id"]),
                "type": str(memory["type"]),
                "subject": str(memory["subject"]),
                "current_value": str(memory["current_value"]),
                "owner_id": memory["owner_id"],
                "status": status,
                "version_id": memory["active_version_id"],
                "version": version,
                "summary": memory["reason"],
                "evidence": evidence,
            },
        }

    def _latest_evidence(self, memory_id: str, version_id: str | None) -> dict[str, Any]:
        row = self.repository.conn.execute(
            """
            SELECT source_type, source_event_id, quote
            FROM memory_evidence
            WHERE memory_id = ?
              AND version_id IS ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (memory_id, version_id),
        ).fetchone()
        if row is None:
            return {"source_type": "unknown", "source_id": None, "quote": None}
        return {
            "source_type": row["source_type"],
            "source_id": row["source_event_id"],
            "quote": row["quote"],
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
            "review_status": _review_status(status),
            "source_type": evidence.get("source_type"),
            "risk_level": _risk_level(risk_flags),
            "conflict_status": _conflict_status(conflict),
            "version": version,
            "evidence": evidence,
            "risk_flags": risk_flags,
            "conflict": conflict,
            "recommended_action": _recommended_action(risk_flags, conflict),
            "owner_id": evidence.get("actor_id"),
            "review_queue": {
                "review_status": _review_status(status),
                "source_type": evidence.get("source_type"),
                "risk_level": _risk_level(risk_flags),
                "conflict_status": _conflict_status(conflict),
                "queue_views": _queue_views(risk_flags, conflict),
                "reviewer": None,
                "last_handler": None,
                "last_handled_at": None,
                "state_mutation": "none",
            },
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
              id, memory_id, tenant_id, organization_id, visibility_policy,
              version_no, value, reason, status,
              source_event_id, created_by, created_at, supersedes_version_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                memory_id,
                _tenant_id_from_memory_context(self.repository.conn, memory_id),
                _organization_id_from_memory_context(self.repository.conn, memory_id),
                _visibility_policy_from_memory_context(self.repository.conn, memory_id),
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

    def _insert_evidence(
        self, memory_id: str, version_id: str | None, source_type: str, event_id: str, quote: str, ts: int
    ) -> None:
        self.repository.conn.execute(
            """
            INSERT INTO memory_evidence (
              id, memory_id, version_id, tenant_id, organization_id, visibility_policy,
              source_type, source_url,
              source_event_id, quote, actor_id, ingested_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
            """,
            (
                new_id("evi"),
                memory_id,
                version_id,
                _tenant_id_from_memory_context(self.repository.conn, memory_id),
                _organization_id_from_memory_context(self.repository.conn, memory_id),
                _visibility_policy_from_memory_context(self.repository.conn, memory_id),
                source_type,
                event_id,
                quote,
                None,
                ts,
                ts,
            ),
        )

    def _find_existing(
        self,
        scope_type: str,
        scope_id: str,
        tenant_id: str,
        organization_id: str,
        memory_type: str,
        normalized_subject: str,
        *,
        allow_type_fallback: bool = False,
    ) -> Any:
        exact = self.repository.conn.execute(
            """
            SELECT *
            FROM memories
            WHERE scope_type = ?
              AND scope_id = ?
              AND tenant_id = ?
              AND organization_id = ?
              AND type = ?
              AND normalized_subject = ?
            """,
            (scope_type, scope_id, tenant_id, organization_id, memory_type, normalized_subject),
        ).fetchone()
        if exact is not None or not allow_type_fallback:
            return exact
        return self.repository.conn.execute(
            """
            SELECT *
            FROM memories
            WHERE scope_type = ?
              AND scope_id = ?
              AND tenant_id = ?
              AND organization_id = ?
              AND normalized_subject = ?
              AND status = 'active'
            ORDER BY updated_at DESC, id
            LIMIT 1
            """,
            (scope_type, scope_id, tenant_id, organization_id, normalized_subject),
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

    def _version_payload(self, row: Any, *, active_version_id: str | None) -> dict[str, Any]:
        raw_metadata: dict[str, Any] = {}
        raw_json = row["raw_json"]
        if raw_json:
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                raw_metadata = parsed
        status = str(row["status"])
        is_active = row["version_id"] == active_version_id
        inactive_reason = None
        if status == "superseded":
            inactive_reason = "已被后续确认的新版本覆盖，默认 search 不再把它当当前答案。"
        elif status in {"rejected", "stale", "archived"}:
            inactive_reason = "不是当前有效版本，只能用于审计或版本解释。"
        return {
            "version_id": str(row["version_id"]),
            "version": int(row["version_no"]),
            "value": str(row["value"]),
            "status": status,
            "is_active": is_active,
            "supersedes_version_id": row["supersedes_version_id"],
            "reason": row["reason"],
            "inactive_reason": inactive_reason,
            "created_by": row["created_by"],
            "created_at": int(row["created_at"] or 0),
            "evidence": {
                "source_type": row["evidence_source_type"] or "unknown",
                "source_id": row["evidence_source_id"],
                "quote": row["evidence_quote"],
                "document_token": raw_metadata.get("document_token"),
                "document_title": raw_metadata.get("document_title"),
            },
        }

    def _version_explanation(self, active_version: dict[str, Any] | None, versions: list[dict[str, Any]]) -> str:
        if active_version is None:
            return "当前没有 active 版本，默认 search 不应返回这条记忆。"
        superseded_count = sum(1 for item in versions if item["status"] == "superseded")
        if superseded_count:
            return (
                f"当前有效值是 v{active_version['version']}：{active_version['value']}。"
                f"已有 {superseded_count} 个旧版本失效，旧值只在版本链和证据里保留。"
            )
        return f"当前有效值是 v{active_version['version']}：{active_version['value']}。目前没有被覆盖的旧版本。"

    def _user_version_explanation(
        self, active_version: dict[str, Any] | None, versions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        old_versions = [item for item in versions if item.get("status") == "superseded"]
        if active_version is None:
            return {
                "kind": "memory_version_chain",
                "current_version": None,
                "old_versions": [_old_version_summary(item, active_version=None) for item in old_versions],
                "override_reason": "当前没有 active 版本，这条记忆不会进入默认搜索结果。",
                "evidence_summary": "没有可采用的当前版本证据。",
                "search_boundary": "默认搜索只返回当前 active 版本；非 active 版本只用于版本解释和审计追溯。",
            }

        return {
            "kind": "memory_version_chain",
            "current_version": _current_version_summary(active_version),
            "old_versions": [_old_version_summary(item, active_version=active_version) for item in old_versions],
            "override_reason": _override_reason(active_version, old_versions),
            "evidence_summary": _version_evidence_summary(active_version, old_versions),
            "search_boundary": "默认搜索只返回当前 active 版本；旧版本不会作为当前答案返回。",
        }

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
    if _looks_like_question(stripped):
        return False
    if contains_any(stripped, DECISION_WORDS + WORKFLOW_WORDS + PREFERENCE_WORDS + OVERRIDE_WORDS):
        return True
    return any(stripped.startswith(f"{prefix}:") or stripped.startswith(f"{prefix}：") for prefix in _PREFIX_SIGNALS)


def _looks_like_question(text: str) -> bool:
    lowered = text.lower()
    question_markers = ("？", "?", "是什么", "怎么", "是否", "吗", "是不是")
    return any(marker in text or marker in lowered for marker in question_markers)


def _current_version_summary(version: dict[str, Any]) -> dict[str, Any]:
    return {
        "version_id": version.get("version_id"),
        "version": version.get("version"),
        "status": version.get("status"),
        "value": version.get("value"),
        "reason": version.get("reason"),
        "evidence": _compact_evidence(version),
        "explanation": f"当前采用 v{version.get('version')}，因为它是已经确认的 active 版本。",
    }


def _old_version_summary(version: dict[str, Any], *, active_version: dict[str, Any] | None) -> dict[str, Any]:
    active_version_no = active_version.get("version") if active_version else None
    if active_version_no is None:
        covered_by = None
    else:
        covered_by = f"v{active_version_no}"
    return {
        "version_id": version.get("version_id"),
        "version": version.get("version"),
        "status": version.get("status"),
        "value": version.get("value"),
        "reason": version.get("reason"),
        "evidence": _compact_evidence(version),
        "covered_by": covered_by,
        "inactive_reason": version.get("inactive_reason")
        or "旧版本只保留在版本链里，用于追溯，不会进入默认搜索结果。",
    }


def _override_reason(active_version: dict[str, Any], old_versions: list[dict[str, Any]]) -> str:
    if not old_versions:
        return f"当前采用 v{active_version.get('version')}，因为它是已确认的 active 版本，目前没有旧值被覆盖。"
    old_values = "、".join(str(item.get("value")) for item in old_versions[:3] if item.get("value"))
    if old_values:
        return (
            f"当前采用 v{active_version.get('version')}：{active_version.get('value')}，"
            f"因为新证据已经覆盖旧结论：{old_values}。"
        )
    return f"当前采用 v{active_version.get('version')}，因为新证据已经覆盖旧版本。"


def _version_evidence_summary(active_version: dict[str, Any], old_versions: list[dict[str, Any]]) -> str:
    active_quote = _evidence_quote(active_version)
    if old_versions:
        old_quote = _evidence_quote(old_versions[0])
        if old_quote:
            return f"当前版本证据：{active_quote or active_version.get('value')}；旧版本证据：{old_quote}"
    return f"当前版本证据：{active_quote or active_version.get('value')}"


def _compact_evidence(version: dict[str, Any]) -> dict[str, Any]:
    evidence = version.get("evidence") if isinstance(version.get("evidence"), dict) else {}
    return {
        "source_type": evidence.get("source_type") or "unknown",
        "source_id": evidence.get("source_id"),
        "quote": evidence.get("quote"),
        "summary": _evidence_quote(version) or "没有可展示的证据摘要。",
    }


def _evidence_quote(version: dict[str, Any]) -> str:
    evidence = version.get("evidence") if isinstance(version.get("evidence"), dict) else {}
    quote = evidence.get("quote")
    return str(quote).strip() if quote else ""


def _context_for_auto_confirm(current_context: dict[str, Any]) -> dict[str, Any]:
    context = dict(current_context)
    permission = context.get("permission")
    if isinstance(permission, dict):
        confirm_permission = dict(permission)
        confirm_permission["requested_action"] = "memory.confirm"
        if isinstance(confirm_permission.get("request_id"), str):
            confirm_permission["request_id"] = f"{confirm_permission['request_id']}:confirm"
        context["permission"] = confirm_permission
    return context


def _tenant_id(context: dict[str, Any]) -> str:
    value = context.get("tenant_id")
    if isinstance(value, str) and value:
        return value
    permission = context.get("permission")
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    value = actor.get("tenant_id")
    return value if isinstance(value, str) and value else "tenant:demo"


def _organization_id(context: dict[str, Any]) -> str:
    value = context.get("organization_id")
    if isinstance(value, str) and value:
        return value
    permission = context.get("permission")
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    value = actor.get("organization_id")
    return value if isinstance(value, str) and value else "org:demo"


def _visibility_policy(context: dict[str, Any]) -> str:
    value = context.get("visibility_policy")
    if isinstance(value, str) and value:
        return value
    permission = context.get("permission")
    if isinstance(permission, dict):
        value = permission.get("requested_visibility")
        if isinstance(value, str) and value:
            return value
    return "team"


def _workspace_id(context: dict[str, Any], fallback_scope: str) -> str:
    permission = context.get("permission")
    source_context = permission.get("source_context") if isinstance(permission, dict) else {}
    source_context = source_context if isinstance(source_context, dict) else {}
    value = source_context.get("workspace_id")
    return value if isinstance(value, str) and value else fallback_scope


def _tenant_id_from_memory_context(conn: Any, memory_id: str) -> str:
    return _memory_context_value(conn, memory_id, "tenant_id", "tenant:demo")


def _organization_id_from_memory_context(conn: Any, memory_id: str) -> str:
    return _memory_context_value(conn, memory_id, "organization_id", "org:demo")


def _visibility_policy_from_memory_context(conn: Any, memory_id: str) -> str:
    return _memory_context_value(conn, memory_id, "visibility_policy", "team")


def _memory_context_value(conn: Any, memory_id: str, column: str, fallback: str) -> str:
    row = conn.execute(f"SELECT {column} FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if row is None:
        return fallback
    value = row[column]
    return value if isinstance(value, str) and value else fallback


def _recommended_action(risk_flags: list[str], conflict: dict[str, Any]) -> str:
    if "sensitive_content" in risk_flags:
        return "manual_review_sensitive"
    if conflict.get("has_conflict"):
        return "manual_review_conflict"
    return "review_candidate"


def _review_status(status: str) -> str:
    if status == "candidate":
        return "pending"
    if status == "active":
        return "confirmed"
    if status in {"rejected", "needs_evidence", "expired"}:
        return status
    return status


def _risk_level(risk_flags: list[Any]) -> str:
    flags = {str(flag) for flag in risk_flags}
    if "sensitive_content" in flags:
        return "high"
    if flags & {"conflict_candidate", "low_confidence", "duplicate", "override_intent"}:
        return "medium"
    return "low"


def _conflict_status(conflict: dict[str, Any]) -> str:
    if not conflict.get("has_conflict"):
        return "no_conflict"
    if conflict.get("old_status") == "active":
        return "overrides_active"
    return "possible_conflict"


def _queue_views(risk_flags: list[str], conflict: dict[str, Any]) -> list[str]:
    views = ["待我审核"]
    if conflict.get("has_conflict"):
        views.append("冲突需判断")
    if _risk_level(risk_flags) == "high" or "low_confidence" in {str(flag) for flag in risk_flags}:
        views.append("高风险暂不建议确认")
    return views
