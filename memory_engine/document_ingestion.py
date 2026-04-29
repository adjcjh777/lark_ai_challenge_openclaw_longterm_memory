from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .copilot.permissions import check_scope_access, demo_permission_context
from .copilot.schemas import CopilotError, CreateCandidateRequest
from .copilot.service import CopilotService
from .models import DECISION_WORDS, DEFAULT_SCOPE, OVERRIDE_WORDS, PREFERENCE_WORDS, WORKFLOW_WORDS, contains_any
from .repository import MemoryRepository, now_ms


@dataclass(frozen=True)
class DocumentSource:
    token: str
    title: str
    text: str
    source_type: str


@dataclass(frozen=True)
class FeishuIngestionSource:
    source_type: str
    source_id: str
    title: str
    text: str
    actor_id: str
    created_at: str = "limited_feishu_ingestion"
    source_url: str | None = None
    metadata: dict[str, Any] | None = None


def ingest_document_source(
    repo: MemoryRepository,
    url_or_token: str,
    *,
    scope: str = DEFAULT_SCOPE,
    current_context: dict[str, Any] | None = None,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    is_local_fixture = Path(url_or_token).expanduser().exists()
    feishu_token = None if is_local_fixture else document_token_from_url(url_or_token)
    if not is_local_fixture:
        permission_error = check_scope_access(scope, current_context, action="memory.create_candidate")
        if permission_error is not None:
            return permission_error.to_response()
        source_error = _check_feishu_source_context(feishu_token or "", current_context)
        if source_error is not None:
            return source_error.to_response()

    document = load_document_source(
        url_or_token,
        lark_cli=lark_cli,
        profile=profile,
        as_identity=as_identity,
    )
    candidates = extract_candidate_quotes(document.text, limit=limit)
    results = []
    service = CopilotService(repository=repo)
    for index, quote in enumerate(candidates, start=1):
        source_id = f"{document.token}#candidate-{index}"
        request = CreateCandidateRequest.from_payload(
            {
                "text": quote,
                "scope": scope,
                "source": {
                    "source_type": document.source_type,
                    "source_id": source_id,
                    "actor_id": "document_ingestion",
                    "created_at": "document_ingestion",
                    "quote": quote,
                    "source_doc_id": document.token,
                },
                "current_context": _document_current_context(document, scope, current_context),
            }
        )
        response = service.create_candidate(request)
        response["source_metadata"] = _source_metadata(document, current_context)
        results.append(response)

    created = [result for result in results if result.get("action") in {"created", "candidate_conflict"}]
    duplicates = [result for result in results if result.get("action") == "duplicate"]
    return {
        "ok": True,
        "document": {
            "token": document.token,
            "title": document.title,
            "source_type": document.source_type,
        },
        "ingestion_trace": _ingestion_trace(document, current_context),
        "candidate_count": len(created),
        "duplicate_count": len(duplicates),
        "candidates": results,
    }


def ingest_feishu_source(
    repo: MemoryRepository,
    source: FeishuIngestionSource,
    *,
    scope: str = DEFAULT_SCOPE,
    current_context: dict[str, Any] | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    permission_error = check_scope_access(scope, current_context, action=_permission_action(current_context))
    if permission_error is not None:
        return permission_error.to_response()
    source_error = _check_limited_source_context(source, current_context)
    if source_error is not None:
        return source_error.to_response()

    candidates = extract_candidate_quotes(source.text, limit=limit)
    results = []
    service = CopilotService(repository=repo)
    for index, quote in enumerate(candidates, start=1):
        request = CreateCandidateRequest.from_payload(
            {
                "text": quote,
                "scope": scope,
                "source": _candidate_source_payload(source, quote, index),
                "current_context": _limited_source_current_context(source, scope, current_context),
                "auto_confirm": False,
            }
        )
        response = service.create_candidate(request)
        response["source_metadata"] = _limited_source_metadata(source, current_context)
        results.append(response)

    created = [result for result in results if result.get("action") in {"created", "candidate_conflict"}]
    duplicates = [result for result in results if result.get("action") == "duplicate"]
    return {
        "ok": True,
        "source": {
            "source_type": source.source_type,
            "source_id": source.source_id,
            "title": source.title,
        },
        "source_metadata": _limited_source_metadata(source, current_context),
        "ingestion_trace": _limited_source_trace(source, current_context),
        "candidate_count": len(created),
        "duplicate_count": len(duplicates),
        "candidates": results,
    }


def preflight_feishu_source_access(
    source_type: str,
    source_id: str,
    *,
    scope: str = DEFAULT_SCOPE,
    current_context: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> CopilotError | None:
    """Fail closed before fetching a real Feishu source."""

    permission_error = check_scope_access(scope, current_context, action=_permission_action(current_context))
    if permission_error is not None:
        return permission_error
    synthetic_source = FeishuIngestionSource(
        source_type=source_type,
        source_id=source_id,
        title=source_id,
        text="",
        actor_id="preflight",
        metadata=metadata,
    )
    return _check_limited_source_context(synthetic_source, current_context)


def mark_feishu_source_revoked(
    repo: MemoryRepository,
    *,
    source_type: str,
    source_id: str,
    scope: str = DEFAULT_SCOPE,
    current_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    permission_error = check_scope_access(scope, current_context, action=_permission_action(current_context))
    if permission_error is not None:
        return permission_error.to_response()
    synthetic_source = FeishuIngestionSource(
        source_type=source_type, source_id=source_id, title=source_id, text="", actor_id="source_revocation"
    )
    source_error = _check_limited_source_context(synthetic_source, current_context)
    if source_error is not None:
        return source_error.to_response()

    ts = now_ms()
    rows = repo.conn.execute(
        "SELECT id FROM raw_events WHERE source_type = ? AND (source_id = ? OR source_id LIKE ?)",
        (source_type, source_id, f"{source_id}#candidate-%"),
    ).fetchall()
    event_ids = [str(row["id"]) for row in rows]
    stale_memory_ids: list[str] = []

    with repo.conn:
        repo.conn.execute(
            """
            UPDATE raw_events
            SET source_deleted_at = ?,
                ingestion_status = 'source_revoked'
            WHERE source_type = ? AND (source_id = ? OR source_id LIKE ?)
            """,
            (ts, source_type, source_id, f"{source_id}#candidate-%"),
        )
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            evidence_rows = repo.conn.execute(
                f"SELECT DISTINCT memory_id FROM memory_evidence WHERE source_event_id IN ({placeholders})",
                event_ids,
            ).fetchall()
            stale_memory_ids = [str(row["memory_id"]) for row in evidence_rows]
            repo.conn.execute(
                f"""
                UPDATE memory_evidence
                SET source_deleted_at = ?,
                    redaction_state = 'source_revoked'
                WHERE source_event_id IN ({placeholders})
                """,
                [ts, *event_ids],
            )
        if stale_memory_ids:
            placeholders = ",".join("?" for _ in stale_memory_ids)
            repo.conn.execute(
                f"""
                UPDATE memories
                SET status = 'stale',
                    source_visibility_revoked_at = ?,
                    updated_at = ?
                WHERE id IN ({placeholders})
                  AND status = 'active'
                """,
                [ts, ts, *stale_memory_ids],
            )
            repo.conn.execute(
                f"""
                UPDATE memory_versions
                SET status = 'stale'
                WHERE memory_id IN ({placeholders})
                  AND status = 'active'
                """,
                stale_memory_ids,
            )

    permission, source_context = _permission_parts(current_context)
    repo.record_audit_event(
        event_type="source_permission_revoked",
        action="source.revoked",
        tool_name="limited_feishu_ingestion",
        target_type="source",
        target_id=f"{source_type}:{source_id}",
        actor_id=_actor_id(permission),
        actor_roles=_actor_roles(permission),
        tenant_id=_actor_tenant(permission),
        organization_id=_actor_organization(permission),
        scope=scope,
        permission_decision="allow",
        reason_code="source_permission_revoked",
        request_id=str(permission.get("request_id") or f"req_source_revoked_{source_id}"),
        trace_id=str(permission.get("trace_id") or f"trace_source_revoked_{source_id}"),
        visible_fields=["source_type", "source_id", "status"],
        redacted_fields=["evidence"],
        source_context=source_context,
        created_at=ts,
    )
    return {
        "ok": True,
        "source_type": source_type,
        "source_id": source_id,
        "revoked_at": ts,
        "stale_memory_count": len(stale_memory_ids),
        "stale_memory_ids": stale_memory_ids,
        "recall_policy": "active_recall_hidden_after_source_revocation",
    }


def _document_current_context(
    document: DocumentSource,
    scope: str,
    current_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if current_context is not None:
        context = dict(current_context)
    else:
        context = demo_permission_context(
            "memory.create_candidate",
            scope,
            actor_id="document_ingestion",
            entrypoint="document_ingestion_fixture",
        )
    context.setdefault("document_token", document.token)
    context.setdefault("document_title", document.title)
    return context


def load_document_source(
    url_or_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> DocumentSource:
    path = Path(url_or_token).expanduser()
    if path.exists():
        text = path.read_text(encoding="utf-8")
        return DocumentSource(
            token=str(path.resolve()),
            title=_title_from_markdown(text, path),
            text=text,
            source_type="document_markdown",
        )

    token = document_token_from_url(url_or_token)
    text = fetch_feishu_document_text(token, lark_cli=lark_cli, profile=profile, as_identity=as_identity)
    return DocumentSource(
        token=token,
        title=_title_from_text(text, fallback=token),
        text=text,
        source_type="document_feishu",
    )


def fetch_feishu_document_text(
    token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> str:
    command = [lark_cli]
    if profile:
        command.extend(["--profile", profile])
    if as_identity:
        command.extend(["--as", as_identity])
    command.extend(
        [
            "docs",
            "+fetch",
            "--api-version",
            "v2",
            "--doc",
            token,
            "--doc-format",
            "markdown",
        ]
    )
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return _content_from_lark_fetch_output(completed.stdout)


def _content_from_lark_fetch_output(output: str) -> str:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return output
    data = payload.get("data") if isinstance(payload, dict) else None
    document = data.get("document") if isinstance(data, dict) else None
    content = document.get("content") if isinstance(document, dict) else None
    if isinstance(content, str):
        return content
    return output


def document_token_from_url(url_or_token: str) -> str:
    stripped = url_or_token.strip()
    for pattern in (
        r"/docx/([A-Za-z0-9_-]+)",
        r"/docs/([A-Za-z0-9_-]+)",
        r"[?&]token=([A-Za-z0-9_-]+)",
    ):
        match = re.search(pattern, stripped)
        if match:
            return match.group(1)
    return stripped


def _check_feishu_source_context(token: str, current_context: dict[str, Any] | None) -> CopilotError | None:
    permission = (current_context or {}).get("permission") if isinstance(current_context, dict) else None
    source_context = permission.get("source_context") if isinstance(permission, dict) else None
    document_id = source_context.get("document_id") if isinstance(source_context, dict) else None
    if document_id == token:
        return None

    # 检查是否缺少 permission context
    if permission is None:
        details: dict[str, Any] = {
            "reason_code": "missing_permission_context",
            "action": "memory.create_candidate",
            "requested_document_id": token,
            "visible_fields": [],
            "redacted_fields": ["current_value", "summary", "evidence"],
        }
        return CopilotError(
            "permission_denied",
            "permission context is missing",
            details=details,
        )

    details: dict[str, Any] = {
        "reason_code": "source_context_mismatch",
        "action": "memory.create_candidate",
        "requested_document_id": token,
        "source_context_error": "document_id_mismatch" if document_id else "missing_document_id",
        "visible_fields": [],
        "redacted_fields": ["current_value", "summary", "evidence"],
    }
    if document_id:
        details["permission_document_id"] = document_id
    request_id = permission.get("request_id") if isinstance(permission, dict) else None
    trace_id = permission.get("trace_id") if isinstance(permission, dict) else None
    if isinstance(request_id, str):
        details["request_id"] = request_id
    if isinstance(trace_id, str):
        details["trace_id"] = trace_id
    return CopilotError(
        "permission_denied",
        "permission source_context.document_id does not match requested Feishu source",
        details=details,
    )


def _source_metadata(document: DocumentSource, current_context: dict[str, Any] | None) -> dict[str, Any]:
    _, source_context = _permission_parts(current_context)
    return {
        "source_type": document.source_type,
        "document_token": document.token,
        "document_title": document.title,
        "entrypoint": source_context.get("entrypoint"),
        "document_id": source_context.get("document_id"),
    }


def _ingestion_trace(document: DocumentSource, current_context: dict[str, Any] | None) -> dict[str, Any]:
    permission, source_context = _permission_parts(current_context)
    trace: dict[str, Any] = {
        "source_metadata": _source_metadata(document, current_context),
        "permission_decision": {
            "decision": "allow",
            "reason_code": "scope_access_granted",
            "requested_action": permission.get("requested_action") or "memory.create_candidate",
            "source_entrypoint": source_context.get("entrypoint") or document.source_type,
        },
    }
    request_id = permission.get("request_id")
    trace_id = permission.get("trace_id")
    if isinstance(request_id, str):
        trace["request_id"] = request_id
    if isinstance(trace_id, str):
        trace["trace_id"] = trace_id
    return trace


def _permission_parts(current_context: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    permission = (current_context or {}).get("permission") if isinstance(current_context, dict) else {}
    permission = permission if isinstance(permission, dict) else {}
    source_context = permission.get("source_context")
    source_context = source_context if isinstance(source_context, dict) else {}
    return permission, source_context


def _permission_action(current_context: dict[str, Any] | None) -> str:
    permission, _ = _permission_parts(current_context)
    value = permission.get("requested_action")
    return value if isinstance(value, str) and value else "memory.create_candidate"


def _candidate_source_payload(source: FeishuIngestionSource, quote: str, index: int) -> dict[str, Any]:
    metadata = source.metadata or {}
    payload: dict[str, Any] = {
        "source_type": source.source_type,
        "source_id": f"{source.source_id}#candidate-{index}",
        "actor_id": source.actor_id,
        "created_at": source.created_at,
        "quote": quote,
    }
    if source.source_url:
        payload["source_url"] = source.source_url
    if source.source_type == "feishu_message":
        payload["source_chat_id"] = str(metadata.get("chat_id") or source.source_id)
    if source.source_type in {"document_feishu", "lark_doc"}:
        payload["source_doc_id"] = source.source_id
    if source.source_type == "feishu_task":
        payload["source_task_id"] = source.source_id
    if source.source_type == "feishu_meeting":
        payload["source_meeting_id"] = source.source_id
    if source.source_type == "lark_bitable":
        payload["source_bitable_app_token"] = str(metadata.get("app_token") or "")
        payload["source_bitable_table_id"] = str(metadata.get("table_id") or "")
        payload["source_bitable_record_id"] = str(metadata.get("record_id") or source.source_id)
    return {key: value for key, value in payload.items() if value}


def _limited_source_current_context(
    source: FeishuIngestionSource,
    scope: str,
    current_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context = dict(current_context or {})
    metadata = dict(context.get("metadata") or {}) if isinstance(context.get("metadata"), dict) else {}
    metadata["source_type"] = source.source_type
    metadata["source_id"] = source.source_id
    metadata["source_title"] = source.title
    if source.metadata:
        metadata.update(source.metadata)
    context["metadata"] = metadata
    context.setdefault("scope", scope)
    return context


def _limited_source_metadata(source: FeishuIngestionSource, current_context: dict[str, Any] | None) -> dict[str, Any]:
    _, source_context = _permission_parts(current_context)
    metadata = dict(source.metadata or {})
    return {
        "source_type": source.source_type,
        "source_id": source.source_id,
        "source_title": source.title,
        "source_url": source.source_url,
        "entrypoint": source_context.get("entrypoint"),
        "chat_id": source_context.get("chat_id"),
        "document_id": source_context.get("document_id"),
        "task_id": source_context.get("task_id"),
        "meeting_id": source_context.get("meeting_id"),
        "bitable_record_id": source_context.get("bitable_record_id") or metadata.get("record_id"),
        "bitable_table_id": source_context.get("bitable_table_id") or metadata.get("table_id"),
        "bitable_app_token": source_context.get("bitable_app_token") or metadata.get("app_token"),
    }


def _limited_source_trace(source: FeishuIngestionSource, current_context: dict[str, Any] | None) -> dict[str, Any]:
    permission, source_context = _permission_parts(current_context)
    trace = {
        "source_metadata": _limited_source_metadata(source, current_context),
        "permission_decision": {
            "decision": "allow",
            "reason_code": "scope_access_granted",
            "requested_action": permission.get("requested_action") or "memory.create_candidate",
            "source_entrypoint": source_context.get("entrypoint") or source.source_type,
        },
    }
    request_id = permission.get("request_id")
    trace_id = permission.get("trace_id")
    if isinstance(request_id, str):
        trace["request_id"] = request_id
    if isinstance(trace_id, str):
        trace["trace_id"] = trace_id
    return trace


def _check_limited_source_context(
    source: FeishuIngestionSource,
    current_context: dict[str, Any] | None,
) -> CopilotError | None:
    _, source_context = _permission_parts(current_context)
    expected_key = _source_context_key(source.source_type)
    if expected_key is None:
        return None
    expected_value = _source_expected_value(source, expected_key)
    actual_value = source_context.get(expected_key)
    if actual_value == expected_value:
        return None
    details: dict[str, Any] = {
        "reason_code": "source_context_mismatch",
        "action": _permission_action(current_context),
        "requested_source_type": source.source_type,
        "requested_source_id": source.source_id,
        "source_context_error": f"{expected_key}_mismatch" if actual_value else f"missing_{expected_key}",
        "visible_fields": [],
        "redacted_fields": ["current_value", "summary", "evidence"],
    }
    if actual_value:
        details[f"permission_{expected_key}"] = actual_value
    permission, _ = _permission_parts(current_context)
    if isinstance(permission.get("request_id"), str):
        details["request_id"] = permission["request_id"]
    if isinstance(permission.get("trace_id"), str):
        details["trace_id"] = permission["trace_id"]
    return CopilotError(
        "permission_denied",
        f"permission source_context.{expected_key} does not match requested Feishu source",
        details=details,
    )


def _source_context_key(source_type: str) -> str | None:
    return {
        "feishu_message": "chat_id",
        "document_feishu": "document_id",
        "lark_doc": "document_id",
        "feishu_task": "task_id",
        "feishu_meeting": "meeting_id",
        "lark_bitable": "bitable_record_id",
    }.get(source_type)


def _source_expected_value(source: FeishuIngestionSource, key: str) -> str:
    metadata = source.metadata or {}
    if key == "chat_id":
        return str(metadata.get("chat_id") or source.source_id)
    if key == "bitable_record_id":
        return str(metadata.get("record_id") or source.source_id)
    return source.source_id


def _actor_id(permission: dict[str, Any]) -> str:
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    return str(actor.get("user_id") or actor.get("open_id") or "unknown")


def _actor_roles(permission: dict[str, Any]) -> list[str]:
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    roles = actor.get("roles")
    return [str(role) for role in roles] if isinstance(roles, list) else []


def _actor_tenant(permission: dict[str, Any]) -> str | None:
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    value = actor.get("tenant_id")
    return value if isinstance(value, str) else None


def _actor_organization(permission: dict[str, Any]) -> str | None:
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    value = actor.get("organization_id")
    return value if isinstance(value, str) else None


def extract_candidate_quotes(text: str, *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for block in _iter_candidate_blocks(text):
        normalized = re.sub(r"\s+", " ", block).strip()
        if not normalized or normalized in seen:
            continue
        if _has_candidate_signal(normalized):
            seen.add(normalized)
            candidates.append(normalized)
        if len(candidates) >= limit:
            break
    return candidates


def _iter_candidate_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for line in text.splitlines():
        line = _clean_markdown_line(line)
        if not line:
            continue
        if len(line) <= 240:
            blocks.append(line)
            continue
        blocks.extend(part.strip() for part in re.split(r"[。；;]", line) if part.strip())
    return blocks


def _clean_markdown_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,6}\s+", "", line)
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^\d+[.)、]\s+", "", line)
    line = re.sub(r"^>\s*", "", line)
    return line.strip()


def _has_candidate_signal(text: str) -> bool:
    signal_words = DECISION_WORDS + WORKFLOW_WORDS + PREFERENCE_WORDS + OVERRIDE_WORDS
    if contains_any(text, signal_words):
        return True
    return bool(re.match(r"^(记忆|规则|结论|约束|风险|负责人)[:：]", text))


def _title_from_markdown(text: str, path: Path) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip() or path.stem
    return path.stem


def _title_from_text(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        line = _clean_markdown_line(line)
        if line:
            return line[:80]
    return fallback
