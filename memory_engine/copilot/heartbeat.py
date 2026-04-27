from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from memory_engine.models import normalize_subject, parse_scope
from memory_engine.repository import MemoryRepository

from .permissions import REVIEW_ROLES, check_scope_access, redact_sensitive_text, sensitive_risk_flags
from .schemas import PermissionContext, ValidationError


DEFAULT_COOLDOWN_MS = 24 * 60 * 60 * 1000
DEFAULT_REVIEW_DUE_MS = 7 * 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class ReminderCandidate:
    reminder_id: str
    memory_id: str | None
    scope: str
    subject: str
    current_value: str
    reason: str
    trigger: str
    status: str = "candidate"
    due_at: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    target_actor: dict[str, Any] = field(default_factory=dict)
    cooldown: dict[str, Any] = field(default_factory=dict)
    permission_trace: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = "review_reminder_candidate"
    risk_flags: list[str] = field(default_factory=list)
    gates: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reminder_id": self.reminder_id,
            "memory_id": self.memory_id,
            "scope": self.scope,
            "subject": self.subject,
            "current_value": self.current_value,
            "reason": self.reason,
            "trigger": self.trigger,
            "status": self.status,
            "due_at": self.due_at,
            "evidence": dict(self.evidence),
            "target_actor": dict(self.target_actor),
            "cooldown": dict(self.cooldown),
            "permission_trace": dict(self.permission_trace),
            "recommended_action": self.recommended_action,
            "risk_flags": list(self.risk_flags),
            "gates": dict(self.gates),
            "state_mutation": "none",
        }


def agent_run_summary_candidate(
    *,
    task: str,
    scope: str,
    used_memory_ids: list[str] | None = None,
    missing_context: list[str] | None = None,
    new_candidate_hint: str | None = None,
    actor_id: str = "openclaw_agent",
) -> dict[str, Any]:
    """Return a dry-run candidate for what an agent learned during a task."""

    return {
        "ok": True,
        "surface": "agent_run_summary_candidate",
        "status": "candidate",
        "scope": scope,
        "task": task,
        "used_memory_ids": list(used_memory_ids or []),
        "missing_context": list(missing_context or []),
        "new_candidate_hint": redact_sensitive_text(new_candidate_hint),
        "actor_id": actor_id,
        "state_mutation": "none",
        "recommended_action": "review_agent_run_summary",
        "risk_flags": sensitive_risk_flags(new_candidate_hint),
    }


class HeartbeatReminderEngine:
    """Creates reminder candidates without sending messages or mutating memory."""

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        now_ms: int | None = None,
        cooldown_ms: int = DEFAULT_COOLDOWN_MS,
        review_due_ms: int = DEFAULT_REVIEW_DUE_MS,
    ) -> None:
        self.repository = repository
        self.now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        self.cooldown_ms = cooldown_ms
        self.review_due_ms = review_due_ms

    def generate(
        self,
        *,
        scope: str,
        current_context: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        context = current_context or {}
        permission_error = check_scope_access(scope, context, action="heartbeat.review_due")
        if permission_error is not None:
            return permission_error.to_response()
        permission = _permission_from_context(context)

        rows = self._active_rows(scope)
        candidates = []
        for row in rows:
            candidate = self._candidate_for_row(row, scope=scope, context=context, permission=permission)
            if candidate is None:
                continue
            candidates.append(candidate.to_dict())
            if len(candidates) >= limit:
                break

        return {
            "ok": True,
            "scope": scope,
            "status": "dry_run",
            "candidates": candidates,
            "trace": {
                "sources": ["review_due", "important_not_recalled", "deadline", "thread_similarity"],
                "gates": ["importance", "relevance", "cooldown", "scope_permission", "sensitive_redaction"],
                "state_mutation": "none",
                "request_id": permission.request_id if permission else None,
                "trace_id": permission.trace_id if permission else None,
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "requested_action": "heartbeat.review_due",
                },
            },
        }

    def _candidate_for_row(
        self,
        row: Any,
        *,
        scope: str,
        context: dict[str, Any],
        permission: PermissionContext | None,
    ) -> ReminderCandidate | None:
        trigger = self._trigger(row, context)
        if trigger is None:
            return None

        evidence_quote = row["evidence_quote"] or row["current_value"]
        raw_value = str(row["current_value"] or "")
        raw_reason = self._reason(trigger, row)
        risk_flags = sensitive_risk_flags(raw_value, evidence_quote)
        value = redact_sensitive_text(raw_value)
        reason = redact_sensitive_text(raw_reason)
        evidence = {
            "source_type": row["evidence_source_type"] or "memory",
            "source_id": row["raw_source_id"] or row["evidence_source_event_id"],
            "quote": redact_sensitive_text(evidence_quote),
        }
        due_at = _extract_due_at(raw_value)
        gates = {
            "importance": float(row["importance"] or 0) >= 0.65 or trigger in {"deadline", "review_due", "thread_similarity"},
            "relevance": trigger != "thread_similarity" or self._thread_relevance(row, context) > 0,
            "cooldown": self._cooldown_passed(row),
            "scope_permission": True,
            "sensitive_redaction": not risk_flags or "[REDACTED:" in value or "[REDACTED:" in evidence["quote"],
        }
        if not all(gates.values()):
            return None

        target_actor = _target_actor(permission)
        cooldown = self._cooldown_trace(row)
        permission_trace = _permission_trace(permission)
        status = "candidate"
        recommended_action = "review_reminder_candidate"
        if risk_flags and not _can_review_sensitive(permission):
            status = "withheld"
            value = ""
            reason = "敏感提醒已隐藏，需 reviewer 复核。"
            evidence = {}
            recommended_action = "permission_denied"
            permission_trace = _permission_trace(
                permission,
                decision="redact",
                reason_code="sensitive_content_redacted",
                visible_fields=["subject", "reason", "target_actor", "cooldown"],
                redacted_fields=["current_value", "evidence"],
            )

        return ReminderCandidate(
            reminder_id=f"rem_{row['memory_id']}_{trigger}",
            memory_id=row["memory_id"],
            scope=scope,
            subject=str(row["subject"]),
            current_value=value,
            reason=reason,
            trigger=trigger,
            status=status,
            due_at=due_at,
            evidence=evidence,
            target_actor=target_actor,
            cooldown=cooldown,
            permission_trace=permission_trace,
            recommended_action=recommended_action,
            risk_flags=risk_flags,
            gates=gates,
        )

    def _active_rows(self, scope: str) -> list[Any]:
        parsed = parse_scope(scope)
        return self.repository.conn.execute(
            """
            SELECT
              m.id AS memory_id,
              m.scope_type || ':' || m.scope_id AS scope,
              m.type,
              m.subject,
              m.current_value,
              m.importance,
              m.updated_at,
              m.expires_at,
              m.last_recalled_at,
              m.recall_count,
              e.source_type AS evidence_source_type,
              e.source_event_id AS evidence_source_event_id,
              e.quote AS evidence_quote,
              r.source_id AS raw_source_id
            FROM memories m
            LEFT JOIN memory_evidence e ON e.id = (
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
            ORDER BY m.importance DESC, m.updated_at ASC, m.id
            """,
            (parsed.scope_type, parsed.scope_id),
        ).fetchall()

    def _trigger(self, row: Any, context: dict[str, Any]) -> str | None:
        if row["expires_at"] and int(row["expires_at"]) <= self.now_ms + DEFAULT_COOLDOWN_MS:
            return "deadline"
        if row["type"] == "deadline" or _extract_due_at(str(row["current_value"] or "")):
            return "deadline"
        if int(row["updated_at"] or 0) <= self.now_ms - self.review_due_ms:
            return "review_due"
        if float(row["importance"] or 0) >= 0.8 and not row["last_recalled_at"]:
            return "important_not_recalled"
        if self._thread_relevance(row, context) > 0:
            return "thread_similarity"
        return None

    def _thread_relevance(self, row: Any, context: dict[str, Any]) -> int:
        thread_text = " ".join(
            str(context.get(key) or "")
            for key in ("intent", "thread_topic", "current_message", "task")
        )
        if not thread_text:
            metadata = context.get("metadata")
            if isinstance(metadata, dict):
                thread_text = " ".join(str(value) for value in metadata.values())
        normalized_thread = normalize_subject(thread_text)
        normalized_subject = normalize_subject(str(row["subject"] or ""))
        if not normalized_thread or not normalized_subject:
            return 0
        return 1 if normalized_subject in normalized_thread or normalized_thread in normalized_subject else 0

    def _cooldown_passed(self, row: Any) -> bool:
        last_recalled_at = row["last_recalled_at"]
        if not last_recalled_at:
            return True
        return int(last_recalled_at) <= self.now_ms - self.cooldown_ms

    def _cooldown_trace(self, row: Any) -> dict[str, Any]:
        last_recalled_at = row["last_recalled_at"]
        result: dict[str, Any] = {
            "cooldown_ms": self.cooldown_ms,
            "passed": self._cooldown_passed(row),
        }
        if last_recalled_at:
            last_recalled = int(last_recalled_at)
            result["last_recalled_at"] = last_recalled
            result["next_allowed_at"] = last_recalled + self.cooldown_ms
        return result

    def _reason(self, trigger: str, row: Any) -> str:
        if trigger == "deadline":
            return "这条记忆像是截止时间或发布风险，任务前先提醒。"
        if trigger == "review_due":
            return "这条记忆已经较久没有复核，先生成候选提醒而不直接推送。"
        if trigger == "important_not_recalled":
            return "这条高重要性记忆还没有被召回过，任务前应主动提醒。"
        return "当前线程主题和这条记忆相似，先作为 reminder candidate。"


def _extract_due_at(text: str) -> str | None:
    match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    return match.group(0) if match else None


def _permission_from_context(context: dict[str, Any]) -> PermissionContext | None:
    permission_payload = context.get("permission")
    if not isinstance(permission_payload, dict):
        return None
    try:
        return PermissionContext.from_payload(permission_payload)
    except ValidationError:
        return None


def _target_actor(permission: PermissionContext | None) -> dict[str, Any]:
    if permission is None:
        return {}
    actor = permission.actor.to_dict()
    return {
        key: value
        for key, value in actor.items()
        if key in {"user_id", "open_id", "roles"} and value
    }


def _permission_trace(
    permission: PermissionContext | None,
    *,
    decision: str = "allow",
    reason_code: str = "scope_access_granted",
    visible_fields: list[str] | None = None,
    redacted_fields: list[str] | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "decision": decision,
        "reason_code": reason_code,
        "requested_action": "heartbeat.review_due",
        "visible_fields": list(visible_fields or ["subject", "current_value", "reason", "evidence", "target_actor", "cooldown"]),
        "redacted_fields": list(redacted_fields or []),
    }
    if permission is not None:
        trace.update(
            {
                "request_id": permission.request_id,
                "trace_id": permission.trace_id,
                "requested_visibility": permission.requested_visibility,
                "source_entrypoint": permission.source_context.entrypoint,
            }
        )
    return trace


def _can_review_sensitive(permission: PermissionContext | None) -> bool:
    if permission is None:
        return False
    roles = {role.strip().lower() for role in permission.actor.roles}
    return bool(roles.intersection(REVIEW_ROLES))
