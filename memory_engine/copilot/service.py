from __future__ import annotations

import logging
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

from .cognee_adapter import CogneeAdapterNotConfigured, CogneeMemoryAdapter
from .embeddings import DeterministicEmbeddingProvider, OllamaEmbeddingProvider, create_embedding_provider
from .governance import CopilotGovernance
from .graph_context import review_targets_for_chat
from .heartbeat import DEFAULT_COOLDOWN_MS, HeartbeatReminderEngine, _reminder_key, parse_review_at_ms
from .orchestrator import MemorySearchOrchestrator
from .permissions import check_scope_access
from .review_inbox import list_review_inbox
from .review_policy import evaluate_review_policy
from .retrieval import LayerAwareRetriever
from .schemas import (
    WORKING_CONTEXT_FIELDS,
    ConfirmRequest,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    HeartbeatReviewDueRequest,
    PermissionContext,
    PrefetchRequest,
    RejectRequest,
    ReminderActionRequest,
    ReviewInboxRequest,
    SearchRequest,
    UndoReviewRequest,
    ValidationError,
    WorkingContext,
)

logger = logging.getLogger(__name__)


class CopilotService:
    """Application service for Copilot-owned memory contracts."""

    def __init__(
        self,
        *,
        repository: MemoryRepository | None = None,
        db_path: str | Path | None = None,
        cognee_adapter: CogneeMemoryAdapter | None = None,
        embedding_provider: OllamaEmbeddingProvider | DeterministicEmbeddingProvider | None = None,
        auto_init_cognee: bool = True,
    ) -> None:
        self.repository = repository
        self.db_path = db_path
        self.cognee_adapter = cognee_adapter
        self._cognee_initialization_attempted = False

        # Initialize embedding provider
        self._embedding_provider = embedding_provider
        self._embedding_provider_initialized = False
        self._embedding_provider_unavailable_reason: str | None = None
        self._reminder_state: dict[str, dict[str, Any]] = {}

        # Auto-initialize Cognee adapter if not provided
        if self.cognee_adapter is None and auto_init_cognee:
            self._try_auto_init_cognee()

    def search(self, request: SearchRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.search",
            request.scope,
            request.current_context.to_dict(),
            target_type="memory",
        )
        if permission_denied is not None:
            return permission_denied

        # Initialize embedding provider if needed
        embedding_provider = self._get_or_init_embedding_provider()
        if embedding_provider is None and self._embedding_provider_unavailable_reason:
            self._record_ops_audit(
                "embedding.provider",
                request.scope,
                request.current_context.to_dict(),
                event_type="embedding_unavailable",
                reason_code="embedding_provider_unavailable_fallback_used",
            )

        retriever = LayerAwareRetriever(
            self._repository(),
            cognee_adapter=self.cognee_adapter,
            embedding_provider=embedding_provider,
        )
        orchestrator = MemorySearchOrchestrator(
            retriever,
            cognee_available=self.cognee_adapter is not None and self.cognee_adapter.is_configured,
        )
        response = orchestrator.search(request).to_dict()
        self._record_audit(
            "memory.search", request.scope, request.current_context.to_dict(), response, target_type="memory"
        )
        return response

    def create_candidate(self, request: CreateCandidateRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.create_candidate",
            request.scope,
            request.current_context,
            target_type="candidate",
        )
        if permission_denied is not None:
            return permission_denied
        auto_confirm_ignored = False
        if request.auto_confirm and _is_real_feishu_source(request.source.source_type):
            request = replace(request, auto_confirm=False)
            auto_confirm_ignored = True
        if request.auto_confirm:
            confirm_permission_error = check_scope_access(
                request.scope,
                _context_for_action(request.current_context, "memory.confirm"),
                action="memory.confirm",
            )
            if confirm_permission_error is not None:
                response = confirm_permission_error.to_response()
                self._record_audit(
                    "memory.confirm",
                    request.scope,
                    _context_for_action(request.current_context, "memory.confirm"),
                    response,
                    target_type="candidate",
                    event_type="permission_denied",
                )
                return response
        response = CopilotGovernance(self._repository()).create_candidate(request)
        if auto_confirm_ignored:
            response["auto_confirm_ignored"] = True
            response["candidate_only_reason"] = "feishu_source_candidate_only"
        review_policy = _review_policy_for_candidate_response(response, request)
        if review_policy is not None:
            response["review_policy"] = review_policy
            review_queue = response.get("review_queue")
            if isinstance(review_queue, dict):
                review_queue["delivery_channel"] = review_policy["delivery_channel"]
                review_queue["review_targets"] = list(review_policy["review_targets"])
                review_queue["visibility_label"] = review_policy["visibility_label"]
            candidate = response.get("candidate")
            if isinstance(candidate, dict):
                candidate["review_policy"] = review_policy
            if (
                review_policy["decision"] == "auto_confirm"
                and response.get("ok")
                and response.get("status") == "candidate"
                and response.get("candidate_id")
            ):
                self._record_audit(
                    "memory.create_candidate",
                    request.scope,
                    request.current_context,
                    response,
                    target_type="candidate",
                    event_type="limited_ingestion_candidate" if _is_real_feishu_source(request.source.source_type) else None,
                )
                confirmed = self.confirm(
                    ConfirmRequest(
                        candidate_id=str(response["candidate_id"]),
                        scope=request.scope,
                        actor_id=request.source.actor_id or "auto_confirm_policy",
                        reason="auto_confirm low-importance memory after review policy checks",
                        current_context=_context_for_policy_auto_confirm(request.current_context),
                    )
                )
                if confirmed.get("ok"):
                    confirmed["action"] = "auto_confirmed"
                    confirmed["review_policy"] = review_policy
                return confirmed
        self._record_audit(
            "memory.create_candidate",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            event_type="limited_ingestion_candidate" if _is_real_feishu_source(request.source.source_type) else None,
        )
        return response

    def confirm(self, request: ConfirmRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.confirm",
            request.scope,
            request.current_context,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        if permission_denied is not None:
            return permission_denied
        response = CopilotGovernance(self._repository()).confirm(request)
        if response.get("ok"):
            response["cognee_sync"] = self._sync_confirmed_memory_to_cognee(request.scope, response)
        self._record_audit(
            "memory.confirm",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        return response

    def reject(self, request: RejectRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.reject",
            request.scope,
            request.current_context,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        if permission_denied is not None:
            return permission_denied
        response = CopilotGovernance(self._repository()).reject(request)
        if response.get("ok"):
            response["cognee_sync"] = self._sync_withdrawn_memory_from_cognee(request.scope, response)
        self._record_audit(
            "memory.reject",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        return response

    def needs_evidence(self, request: RejectRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.needs_evidence",
            request.scope,
            request.current_context,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        if permission_denied is not None:
            return permission_denied
        response = CopilotGovernance(self._repository()).needs_evidence(request)
        self._record_audit(
            "memory.needs_evidence",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        return response

    def expire_candidate(self, request: RejectRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.expire",
            request.scope,
            request.current_context,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        if permission_denied is not None:
            return permission_denied
        response = CopilotGovernance(self._repository()).expire(request)
        self._record_audit(
            "memory.expire",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        return response

    def undo_review(self, request: UndoReviewRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.undo_review",
            request.scope,
            request.current_context,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        if permission_denied is not None:
            return permission_denied
        response = CopilotGovernance(self._repository()).undo_review(request)
        if response.get("ok"):
            response["cognee_sync"] = self._sync_withdrawn_memory_from_cognee(request.scope, response)
        self._record_audit(
            "memory.undo_review",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            target_id=request.candidate_id,
            candidate_id=request.candidate_id,
        )
        return response

    def review_inbox(self, request: ReviewInboxRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.review_inbox",
            request.scope,
            request.current_context,
            target_type="candidate",
        )
        if permission_denied is not None:
            return permission_denied
        permission = _parse_permission(request.current_context.get("permission"))
        actor_id = permission.actor.primary_id() if permission is not None else None
        actor_roles = permission.actor.roles if permission is not None else []
        tenant_id = permission.actor.tenant_id if permission is not None else None
        organization_id = permission.actor.organization_id if permission is not None else None
        response = list_review_inbox(
            self._repository(),
            scope=request.scope,
            tenant_id=tenant_id,
            organization_id=organization_id,
            actor_id=actor_id,
            actor_roles=actor_roles,
            view=request.view,
            limit=request.limit,
        )
        response.update(
            {
                "delivery_channel": "routed_private_review",
                "review_targets": [actor_id] if actor_id else [],
                "open_ids": [actor_id] if actor_id else [],
                "current_context": request.current_context,
            }
        )
        self._record_audit(
            "memory.review_inbox",
            request.scope,
            request.current_context,
            response,
            target_type="candidate",
            event_type="review_inbox_viewed",
        )
        return response

    def explain_versions(self, request: ExplainVersionsRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.explain_versions",
            request.scope,
            request.current_context,
            target_type="memory",
            target_id=request.memory_id,
            memory_id=request.memory_id,
        )
        if permission_denied is not None:
            return permission_denied
        response = CopilotGovernance(self._repository()).explain_versions(request)
        self._record_audit(
            "memory.explain_versions",
            request.scope,
            request.current_context,
            response,
            target_type="memory",
            target_id=request.memory_id,
            memory_id=request.memory_id,
        )
        return response

    def prefetch(self, request: PrefetchRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "memory.prefetch",
            request.scope,
            request.current_context,
            target_type="memory",
        )
        if permission_denied is not None:
            return permission_denied

        search_request = SearchRequest(
            query=_prefetch_query(request.task, request.current_context),
            scope=request.scope,
            top_k=request.top_k,
            filters={"status": "active"},
            current_context=WorkingContext.from_payload(_context_for_internal_search(request.current_context) or None),
        )
        search_response = self.search(search_request)
        if not search_response.get("ok"):
            return search_response

        results = list(search_response.get("results") or [])
        trace = dict(search_response.get("trace") or {})
        relevant = [_compact_memory(result) for result in results]
        risks = [item for item in relevant if item.get("type") == "risk" or _mentions_risk(item.get("current_value"))]
        deadlines = [
            item for item in relevant if item.get("type") == "deadline" or _mentions_deadline(item.get("current_value"))
        ]
        graph_context = _prefetch_graph_context(self._repository(), request.current_context)
        response = {
            "ok": True,
            "tool": "memory.prefetch",
            "task": request.task,
            "scope": request.scope,
            "top_k": request.top_k,
            "context_pack": {
                "summary": _prefetch_summary(request.task, relevant, risks, deadlines),
                "relevant_memories": relevant,
                "graph_context": graph_context,
                "risks": risks,
                "deadlines": deadlines,
                "version_status": [
                    {
                        "memory_id": item.get("memory_id"),
                        "status": item.get("status"),
                        "version": item.get("version"),
                    }
                    for item in relevant
                ],
                "trace_summary": {
                    "strategy": trace.get("strategy"),
                    "layers": trace.get("layers") or [],
                    "returned_count": trace.get("returned_count", len(relevant)),
                    "final_reason": trace.get("final_reason"),
                    "matched_memory_ids": [item.get("memory_id") for item in relevant],
                },
                "stale_superseded_filtered": True,
                "raw_events_included": False,
            },
            "state_mutation": "none",
        }
        self._record_audit("memory.prefetch", request.scope, request.current_context, response, target_type="memory")
        return response

    def heartbeat_review_due(self, request: HeartbeatReviewDueRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "heartbeat.review_due",
            request.scope,
            request.current_context,
            target_type="reminder",
        )
        if permission_denied is not None:
            return permission_denied
        response = HeartbeatReminderEngine(self._repository(), reminder_state=self._reminder_state).generate(
            scope=request.scope,
            current_context=request.current_context,
            limit=request.limit,
        )
        self._record_audit(
            "heartbeat.review_due",
            request.scope,
            request.current_context,
            response,
            target_type="reminder",
            event_type="heartbeat_candidate_generated",
        )
        return response

    def review_reminder(self, request: ReminderActionRequest) -> dict[str, object]:
        permission_denied = self._permission_denied(
            "heartbeat.review_due",
            request.scope,
            request.current_context,
            target_type="reminder",
            target_id=request.reminder_id,
        )
        if permission_denied is not None:
            return permission_denied

        now_ms = int(time.time() * 1000)
        state_key = _reminder_key(request.scope, request.subject, request.trigger, request.reminder_id)
        state = dict(self._reminder_state.get(state_key) or {})
        state.update(
            {
                "reminder_id": request.reminder_id,
                "scope": request.scope,
                "subject": request.subject,
                "trigger": request.trigger,
                "last_action": request.action,
                "last_action_at_ms": now_ms,
            }
        )
        status = "reviewed"
        if request.action == "confirm_useful":
            status = "useful"
            state["cooldown_until_ms"] = now_ms + DEFAULT_COOLDOWN_MS
        elif request.action == "ignore":
            status = "ignored"
            state["cooldown_until_ms"] = now_ms + DEFAULT_COOLDOWN_MS
        elif request.action == "snooze":
            status = "snoozed"
            next_review_at_ms = parse_review_at_ms(request.next_review_at)
            if next_review_at_ms is None and request.snooze_ms:
                next_review_at_ms = now_ms + request.snooze_ms
            if next_review_at_ms is None:
                next_review_at_ms = now_ms + DEFAULT_COOLDOWN_MS
            state["next_review_at_ms"] = next_review_at_ms
            state["next_review_at"] = request.next_review_at or str(next_review_at_ms)
        elif request.action == "mute_same_type":
            status = "muted"
            state["muted"] = True

        self._reminder_state[state_key] = state
        response: dict[str, object] = {
            "ok": True,
            "surface": "reminder_action",
            "reminder_id": request.reminder_id,
            "scope": request.scope,
            "action": request.action,
            "status": status,
            "next_review_at": state.get("next_review_at"),
            "mute_key": state_key,
            "reminder_state": dict(state),
            "state_mutation": "reminder_review_state_only",
            "active_memory_mutation": "none",
            "real_push_sent": False,
        }
        self._record_audit(
            "heartbeat.review_due",
            request.scope,
            request.current_context,
            response,
            target_type="reminder",
            target_id=request.reminder_id,
            event_type="reminder_action_reviewed",
        )
        return response

    def _get_or_init_embedding_provider(self) -> OllamaEmbeddingProvider | DeterministicEmbeddingProvider | None:
        """Get or initialize the embedding provider.

        Returns the OllamaEmbeddingProvider if available, otherwise None
        (which will cause LayerAwareRetriever to use DeterministicEmbeddingProvider).
        """
        if self._embedding_provider_initialized:
            return self._embedding_provider

        self._embedding_provider_initialized = True

        # Use provided provider if available
        if self._embedding_provider is not None:
            self._embedding_provider_unavailable_reason = None
            return self._embedding_provider

        # Try to create OllamaEmbeddingProvider
        provider_name = os.environ.get("EMBEDDING_PROVIDER", "ollama")
        if provider_name != "ollama":
            self._embedding_provider = create_embedding_provider(provider=provider_name, fallback=True)
            self._embedding_provider_unavailable_reason = None
            return self._embedding_provider

        try:
            provider = create_embedding_provider(provider="ollama", fallback=False)
            if isinstance(provider, OllamaEmbeddingProvider):
                self._embedding_provider = provider
                self._embedding_provider_unavailable_reason = None
                logger.info("OllamaEmbeddingProvider initialized successfully")
                return self._embedding_provider
        except Exception as exc:
            self._embedding_provider_unavailable_reason = f"provider_init_failed:{exc.__class__.__name__}"
            logger.debug(
                "Failed to initialize OllamaEmbeddingProvider: %s. "
                "Will use DeterministicEmbeddingProvider as fallback.",
                exc,
            )

        if self._embedding_provider_unavailable_reason is None:
            self._embedding_provider_unavailable_reason = "ollama_provider_unavailable"
        return None

    def _repository(self) -> MemoryRepository:
        if self.repository is not None:
            return self.repository
        conn = connect(self.db_path)
        init_db(conn)
        self.repository = MemoryRepository(conn)
        return self.repository

    def _try_auto_init_cognee(self) -> None:
        """Attempt to auto-initialize Cognee adapter with configuration validation.

        This method logs at debug level instead of raising exceptions to allow
        graceful fallback to repository-based retrieval without noisy warnings
        in test environments.
        """
        if self._cognee_initialization_attempted:
            return

        self._cognee_initialization_attempted = True
        try:
            self.cognee_adapter = CogneeMemoryAdapter()
            # Attempt to load client to validate configuration
            self.cognee_adapter.ensure_client()
            logger.info("Cognee adapter auto-initialized successfully")
        except CogneeAdapterNotConfigured as exc:
            logger.debug(
                "Cognee adapter auto-initialization skipped: %s. Falling back to repository-based retrieval.", exc
            )
            self.cognee_adapter = None
        except Exception as exc:
            logger.debug(
                "Unexpected error during Cognee adapter auto-initialization: %s. "
                "Falling back to repository-based retrieval.",
                exc,
            )
            self.cognee_adapter = None

    def _permission_denied(
        self,
        action: str,
        scope: str,
        current_context: dict[str, Any],
        *,
        target_type: str,
        target_id: str | None = None,
        memory_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, object] | None:
        permission_error = check_scope_access(scope, current_context, action=action)
        if permission_error is None:
            return None
        response = permission_error.to_response()
        self._record_audit(
            action,
            scope,
            current_context,
            response,
            target_type=target_type,
            target_id=target_id,
            memory_id=memory_id,
            candidate_id=candidate_id,
            event_type="permission_denied",
        )
        return response

    def _record_audit(
        self,
        action: str,
        scope: str,
        current_context: dict[str, Any],
        response: dict[str, object],
        *,
        target_type: str,
        target_id: str | None = None,
        memory_id: str | None = None,
        candidate_id: str | None = None,
        event_type: str | None = None,
    ) -> None:
        repo = self._repository()
        audit = _audit_payload(
            action,
            scope,
            current_context,
            response,
            target_type=target_type,
            target_id=target_id,
            memory_id=memory_id,
            candidate_id=candidate_id,
            event_type=event_type,
        )
        with repo.conn:
            repo.record_audit_event(**audit)

    def _record_ops_audit(
        self,
        action: str,
        scope: str,
        current_context: dict[str, Any],
        *,
        event_type: str,
        reason_code: str,
    ) -> None:
        repo = self._repository()
        permission_payload = current_context.get("permission") if isinstance(current_context, dict) else None
        permission = _parse_permission(permission_payload)
        actor = _audit_actor(permission_payload, permission)
        with repo.conn:
            repo.record_audit_event(
                event_type=event_type,
                action=action,
                tool_name=action,
                target_type="ops",
                actor_id=actor["actor_id"],
                actor_roles=actor["roles"],
                tenant_id=actor["tenant_id"],
                organization_id=actor["organization_id"],
                scope=scope,
                permission_decision="withhold",
                reason_code=reason_code,
                request_id=_permission_field(permission_payload, permission, "request_id"),
                trace_id=_permission_field(permission_payload, permission, "trace_id"),
                visible_fields=["provider", "fallback", "reason_code"],
                redacted_fields=["query", "content", "evidence", "raw_text"],
                source_context=_source_context(permission_payload, permission),
            )

    def _sync_confirmed_memory_to_cognee(self, scope: str, response: dict[str, object]) -> dict[str, object]:
        if self.cognee_adapter is None or not self.cognee_adapter.is_configured:
            return {"status": "skipped", "reason": "cognee_adapter_unavailable", "fallback": "repository_ledger"}
        memory = response.get("memory")
        if not isinstance(memory, dict):
            return {"status": "skipped", "reason": "memory_payload_missing", "fallback": "repository_ledger"}
        try:
            result = self.cognee_adapter.sync_curated_memory(scope, memory)
        except Exception as exc:
            return {
                "status": "fallback_used",
                "reason": f"cognee_sync_failed:{exc.__class__.__name__}",
                "fallback": "repository_ledger",
            }
        return {
            "status": "pass",
            "dataset_name": result.get("dataset_name"),
            "memory_id": result.get("memory_id"),
            "version": result.get("version"),
            "fallback": None,
        }

    def _sync_withdrawn_memory_from_cognee(self, scope: str, response: dict[str, object]) -> dict[str, object]:
        if self.cognee_adapter is None or not self.cognee_adapter.is_configured:
            return {"status": "skipped", "reason": "cognee_adapter_unavailable", "fallback": "repository_ledger"}
        memory_id = response.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id:
            return {"status": "skipped", "reason": "memory_id_missing", "fallback": "repository_ledger"}
        try:
            result = self.cognee_adapter.sync_memory_withdrawal(
                scope,
                memory_id,
                candidate_id=response.get("candidate_id"),
                action=response.get("action"),
                provenance="copilot_ledger",
            )
        except Exception as exc:
            return {
                "status": "fallback_used",
                "reason": f"cognee_withdrawal_failed:{exc.__class__.__name__}",
                "fallback": "repository_ledger",
            }
        return {
            "status": "pass",
            "dataset_name": result.get("dataset_name"),
            "memory_id": result.get("memory_id"),
            "fallback": None,
        }


def _working_context_only(context: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in context.items() if key in WORKING_CONTEXT_FIELDS}


def _context_for_internal_search(context: dict[str, object]) -> dict[str, object]:
    return _context_for_action(_working_context_only(context), "memory.search")


def _context_for_action(context: dict[str, object], action: str) -> dict[str, object]:
    next_context = dict(context)
    permission = next_context.get("permission")
    if isinstance(permission, dict):
        next_permission = dict(permission)
        next_permission["requested_action"] = action
        if isinstance(next_permission.get("request_id"), str):
            next_permission["request_id"] = f"{next_permission['request_id']}:{action.rsplit('.', 1)[-1]}"
        next_context["permission"] = next_permission
    return next_context


def _context_for_policy_auto_confirm(context: dict[str, object]) -> dict[str, object]:
    next_context = _context_for_action(context, "memory.confirm")
    permission = next_context.get("permission")
    if isinstance(permission, dict):
        next_permission = dict(permission)
        actor = next_permission.get("actor")
        if isinstance(actor, dict):
            next_actor = dict(actor)
            roles = next_actor.get("roles")
            role_list = [str(role) for role in roles] if isinstance(roles, list) else []
            if not any(role in {"reviewer", "owner", "admin"} for role in role_list):
                role_list.append("reviewer")
            next_actor["roles"] = role_list
            next_permission["actor"] = next_actor
        next_permission["auto_confirm_policy"] = "low_importance_safe_candidate"
        next_context["permission"] = next_permission
    return next_context


def _is_real_feishu_source(source_type: str) -> bool:
    normalized = source_type.strip().lower()
    return normalized.startswith("feishu_") or normalized in {"document_feishu", "lark_doc", "lark_bitable"}


def _review_policy_for_candidate_response(
    response: dict[str, object], request: CreateCandidateRequest
) -> dict[str, object] | None:
    if not response.get("ok") or not isinstance(response.get("candidate"), dict):
        return None
    candidate = dict(response["candidate"])  # type: ignore[index]
    permission = request.current_context.get("permission") if isinstance(request.current_context, dict) else {}
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    return evaluate_review_policy(
        candidate={
            **candidate,
            "scope": request.scope,
            "visibility_policy": request.current_context.get("visibility_policy"),
        },
        risk_flags=list(response.get("risk_flags") or []),
        conflict=response.get("conflict") if isinstance(response.get("conflict"), dict) else {},
        source=request.source.to_dict(),
        actor=actor if isinstance(actor, dict) else None,
        current_context=request.current_context,
    )


def _audit_payload(
    action: str,
    scope: str,
    current_context: dict[str, Any],
    response: dict[str, object],
    *,
    target_type: str,
    target_id: str | None,
    memory_id: str | None,
    candidate_id: str | None,
    event_type: str | None,
) -> dict[str, Any]:
    permission_payload = current_context.get("permission") if isinstance(current_context, dict) else None
    permission = _parse_permission(permission_payload)
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    error_details = error.get("details") if isinstance(error.get("details"), dict) else {}
    denied = error.get("code") == "permission_denied"
    decision = "deny" if denied else "allow"
    reason_code = str(error_details.get("reason_code") or ("permission_denied" if denied else "scope_access_granted"))
    response_memory_id = _string_response_field(response, "memory_id")
    response_candidate_id = _string_response_field(response, "candidate_id")
    resolved_memory_id = memory_id or response_memory_id
    resolved_candidate_id = candidate_id or response_candidate_id
    resolved_target_id = target_id or resolved_candidate_id or resolved_memory_id
    actor = _audit_actor(permission_payload, permission)
    request_id = error_details.get("request_id") if isinstance(error_details.get("request_id"), str) else None
    trace_id = error_details.get("trace_id") if isinstance(error_details.get("trace_id"), str) else None
    return {
        "event_type": event_type or _event_type(action, denied),
        "action": action,
        "tool_name": action,
        "target_type": target_type,
        "target_id": resolved_target_id,
        "memory_id": resolved_memory_id,
        "candidate_id": resolved_candidate_id,
        "actor_id": actor["actor_id"],
        "actor_roles": actor["roles"],
        "tenant_id": actor["tenant_id"],
        "organization_id": actor["organization_id"],
        "scope": scope,
        "permission_decision": decision,
        "reason_code": reason_code,
        "request_id": request_id or _permission_field(permission_payload, permission, "request_id"),
        "trace_id": trace_id or _permission_field(permission_payload, permission, "trace_id"),
        "visible_fields": _visible_fields(action, denied),
        "redacted_fields": _redacted_fields(error_details, denied),
        "source_context": _source_context(permission_payload, permission),
    }


def _parse_permission(permission_payload: Any) -> PermissionContext | None:
    if not isinstance(permission_payload, dict):
        return None
    try:
        return PermissionContext.from_payload(permission_payload)
    except ValidationError:
        return None


def _audit_actor(permission_payload: Any, permission: PermissionContext | None) -> dict[str, Any]:
    if permission is not None:
        return {
            "actor_id": permission.actor.primary_id() or "unknown",
            "roles": list(permission.actor.roles),
            "tenant_id": permission.actor.tenant_id,
            "organization_id": permission.actor.organization_id,
        }
    actor = permission_payload.get("actor") if isinstance(permission_payload, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    roles = actor.get("roles")
    return {
        "actor_id": _first_string(actor, "user_id", "open_id") or "unknown",
        "roles": list(roles) if isinstance(roles, list) and all(isinstance(role, str) for role in roles) else [],
        "tenant_id": str(actor.get("tenant_id") or "tenant:demo"),
        "organization_id": str(actor.get("organization_id") or "org:demo"),
    }


def _source_context(permission_payload: Any, permission: PermissionContext | None) -> dict[str, Any]:
    if permission is not None:
        return permission.source_context.to_dict()
    source_context = permission_payload.get("source_context") if isinstance(permission_payload, dict) else {}
    return dict(source_context) if isinstance(source_context, dict) else {}


def _permission_field(permission_payload: Any, permission: PermissionContext | None, field_name: str) -> str | None:
    if permission is not None:
        value = getattr(permission, field_name)
        return value if isinstance(value, str) and value else None
    if isinstance(permission_payload, dict):
        value = permission_payload.get(field_name)
        return value if isinstance(value, str) and value else None
    return None


def _string_response_field(response: dict[str, object], field_name: str) -> str | None:
    value = response.get(field_name)
    return value if isinstance(value, str) and value else None


def _first_string(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event_type(action: str, denied: bool) -> str:
    if denied:
        return "permission_denied"
    if action == "memory.confirm":
        return "candidate_confirmed"
    if action == "memory.reject":
        return "candidate_rejected"
    if action == "memory.needs_evidence":
        return "candidate_needs_evidence"
    if action == "memory.expire":
        return "candidate_expired"
    if action == "memory.undo_review":
        return "candidate_review_undone"
    if action == "memory.create_candidate":
        return "candidate_created"
    if action == "heartbeat.review_due":
        return "heartbeat_candidate_generated"
    return "permission_allowed"


def _visible_fields(action: str, denied: bool) -> list[str]:
    if denied:
        return []
    if action == "memory.search":
        return ["memory_id", "subject", "current_value", "evidence", "trace"]
    if action in {"memory.confirm", "memory.reject"}:
        return ["candidate_id", "memory_id", "status"]
    if action in {"memory.needs_evidence", "memory.expire", "memory.undo_review"}:
        return ["candidate_id", "memory_id", "review_status", "last_handler", "last_handled_at"]
    if action == "memory.create_candidate":
        return ["candidate_id", "status", "evidence", "risk_flags"]
    if action == "heartbeat.review_due":
        return ["reminder_id", "subject", "reason", "target_actor", "cooldown"]
    return ["ok", "trace"]


def _redacted_fields(error_details: dict[str, Any], denied: bool) -> list[str]:
    value = error_details.get("redacted_fields")
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return ["current_value", "summary", "evidence"] if denied else []


def _prefetch_query(task: str, context: dict[str, object]) -> str:
    parts = [task]
    for key in ("intent", "thread_topic", "current_message", "task"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    metadata = context.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(value) for value in metadata.values() if isinstance(value, str) and value.strip())
    return " ".join(parts)


def _compact_memory(memory: dict[str, object]) -> dict[str, object]:
    evidence = memory.get("evidence") if isinstance(memory.get("evidence"), list) else []
    compact_evidence = []
    for item in evidence[:2]:
        if not isinstance(item, dict):
            continue
        compact_evidence.append(
            {
                "source_type": item.get("source_type"),
                "source_id": item.get("source_id"),
                "quote": item.get("quote"),
            }
        )
    return {
        "memory_id": memory.get("memory_id"),
        "type": memory.get("type"),
        "subject": memory.get("subject"),
        "current_value": memory.get("current_value"),
        "status": memory.get("status"),
        "layer": memory.get("layer"),
        "version": memory.get("version"),
        "score": memory.get("score"),
        "evidence": compact_evidence,
        "matched_via": memory.get("matched_via") or [],
        "why_ranked": memory.get("why_ranked") or {},
    }


def _prefetch_graph_context(repository: MemoryRepository, current_context: dict[str, object]) -> dict[str, object]:
    permission_payload = current_context.get("permission") if isinstance(current_context, dict) else None
    permission = _parse_permission(permission_payload)
    chat_id = _context_chat_id(current_context, permission_payload)
    if permission is None or not chat_id:
        return {
            "source_chat_id": chat_id,
            "related_people": [],
            "policy": "graph_context_unavailable_without_permission_or_chat",
        }

    related_people = review_targets_for_chat(
        repository.conn,
        chat_id=chat_id,
        tenant_id=permission.actor.tenant_id,
        organization_id=permission.actor.organization_id,
        limit=8,
    )
    return {
        "source_chat_id": chat_id,
        "related_people": related_people,
        "policy": "feishu_chat_membership_only",
        "raw_message_content_included": False,
    }


def _context_chat_id(current_context: dict[str, object], permission_payload: object) -> str | None:
    value = current_context.get("chat_id") if isinstance(current_context, dict) else None
    if isinstance(value, str) and value:
        return value
    source_context = permission_payload.get("source_context") if isinstance(permission_payload, dict) else {}
    if isinstance(source_context, dict):
        value = source_context.get("chat_id")
        if isinstance(value, str) and value:
            return value
    return None


def _mentions_risk(value: object) -> bool:
    text = str(value or "").lower()
    return any(keyword in text for keyword in ("risk", "风险", "blocked", "blocker"))


def _mentions_deadline(value: object) -> bool:
    text = str(value or "")
    return "deadline" in text.lower() or "截止" in text or "上线前" in text


def _prefetch_summary(
    task: str,
    relevant: list[dict[str, object]],
    risks: list[dict[str, object]],
    deadlines: list[dict[str, object]],
) -> str:
    if not relevant:
        return f"{task}: 未找到可带入任务上下文的 active 记忆。"
    parts = [f"{task}: 找到 {len(relevant)} 条可带入任务前上下文的 active 记忆"]
    if risks:
        parts.append(f"{len(risks)} 条风险")
    if deadlines:
        parts.append(f"{len(deadlines)} 条截止时间")
    return "，".join(parts) + "。"
