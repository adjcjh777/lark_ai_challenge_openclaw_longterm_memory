from __future__ import annotations

import json
from typing import Any

from memory_engine.models import parse_scope
from memory_engine.repository import MemoryRepository

from .permissions import DEFAULT_ORGANIZATION_ID, DEFAULT_TENANT_ID, sensitive_risk_flags
from .review_policy import evaluate_review_policy

VALID_VIEWS = {"all", "mine", "conflicts", "high_risk"}


def list_review_inbox(
    repository: MemoryRepository,
    *,
    scope: str,
    tenant_id: str | None = None,
    organization_id: str | None = None,
    actor_id: str | None = None,
    actor_roles: list[str] | tuple[str, ...] | set[str] | None = None,
    view: str = "all",
    limit: int = 10,
) -> dict[str, Any]:
    """Return a presentation-safe review inbox for pending candidate memories.

    This module is intentionally read-only: confirm/reject/needs-evidence remain
    owned by CopilotService and the governance state machine.
    """

    if view not in VALID_VIEWS:
        raise ValueError(f"view must be one of: {', '.join(sorted(VALID_VIEWS))}")

    parsed_scope = parse_scope(scope)
    tenant = tenant_id or DEFAULT_TENANT_ID
    organization = organization_id or DEFAULT_ORGANIZATION_ID
    rows = [
        *_candidate_memory_rows(repository, parsed_scope.scope_type, parsed_scope.scope_id, tenant, organization),
        *_candidate_version_rows(repository, parsed_scope.scope_type, parsed_scope.scope_id, tenant, organization),
    ]
    items = [_row_to_item(row) for row in rows]
    items.sort(key=lambda item: (-int(item["_sort_at"] or 0), item["candidate_id"]))

    accessible_items = _accessible_items(items, actor_id=actor_id, actor_roles=actor_roles)

    counts = {
        "all": len(accessible_items),
        "mine": sum(1 for item in accessible_items if _matches_mine(item, actor_id)),
        "conflicts": sum(1 for item in accessible_items if _matches_conflicts(item)),
        "high_risk": sum(1 for item in accessible_items if _matches_high_risk(item)),
    }

    visible = [_public_item(item) for item in accessible_items if _matches_view(item, view, actor_id)]
    safe_limit = max(0, int(limit))
    return {
        "ok": True,
        "scope": scope,
        "view": view,
        "items": visible[:safe_limit],
        "counts": counts,
    }


def _candidate_memory_rows(
    repository: MemoryRepository,
    scope_type: str,
    scope_id: str,
    tenant_id: str,
    organization_id: str,
) -> list[Any]:
    return repository.conn.execute(
        """
        SELECT
          'memory' AS item_kind,
          m.id AS candidate_id,
          m.id AS memory_id,
          m.active_version_id AS version_id,
          m.subject AS subject,
          m.type AS type,
          m.current_value AS new_value,
          NULL AS old_value,
          m.status AS status,
          m.owner_id AS owner_id,
          m.visibility_policy AS visibility_policy,
          m.updated_at AS sort_at,
          NULL AS supersedes_version_id,
          e.source_type AS source_type,
          e.quote AS evidence_quote,
          r.raw_json AS raw_json
        FROM memories m
        LEFT JOIN memory_evidence e ON e.id = (
          SELECT latest_e.id
          FROM memory_evidence latest_e
          WHERE latest_e.memory_id = m.id
            AND latest_e.version_id IS m.active_version_id
          ORDER BY latest_e.created_at DESC
          LIMIT 1
        )
        LEFT JOIN raw_events r ON r.id = COALESCE(e.source_event_id, m.source_event_id)
        WHERE m.scope_type = ?
          AND m.scope_id = ?
          AND m.tenant_id = ?
          AND m.organization_id = ?
          AND m.status = 'candidate'
        """,
        (scope_type, scope_id, tenant_id, organization_id),
    ).fetchall()


def _candidate_version_rows(
    repository: MemoryRepository,
    scope_type: str,
    scope_id: str,
    tenant_id: str,
    organization_id: str,
) -> list[Any]:
    return repository.conn.execute(
        """
        SELECT
          'version' AS item_kind,
          mv.id AS candidate_id,
          m.id AS memory_id,
          mv.id AS version_id,
          m.subject AS subject,
          m.type AS type,
          mv.value AS new_value,
          m.current_value AS old_value,
          mv.status AS status,
          COALESCE(mv.created_by, m.owner_id) AS owner_id,
          mv.visibility_policy AS visibility_policy,
          mv.created_at AS sort_at,
          mv.supersedes_version_id AS supersedes_version_id,
          e.source_type AS source_type,
          e.quote AS evidence_quote,
          r.raw_json AS raw_json
        FROM memory_versions mv
        JOIN memories m ON m.id = mv.memory_id
        LEFT JOIN memory_evidence e ON e.id = (
          SELECT latest_e.id
          FROM memory_evidence latest_e
          WHERE latest_e.memory_id = mv.memory_id
            AND latest_e.version_id IS mv.id
          ORDER BY latest_e.created_at DESC
          LIMIT 1
        )
        LEFT JOIN raw_events r ON r.id = COALESCE(e.source_event_id, mv.source_event_id)
        WHERE m.scope_type = ?
          AND m.scope_id = ?
          AND m.tenant_id = ?
          AND m.organization_id = ?
          AND mv.status = 'candidate'
          AND NOT (m.status = 'candidate' AND mv.id IS m.active_version_id)
        """,
        (scope_type, scope_id, tenant_id, organization_id),
    ).fetchall()


def _row_to_item(row: Any) -> dict[str, Any]:
    raw_metadata = _parse_raw_json(row["raw_json"])
    source = _source_from_metadata(raw_metadata, row)
    current_context = _context_from_metadata(raw_metadata)
    conflict = _conflict_for_row(row)
    flags = sensitive_risk_flags(row["new_value"], row["evidence_quote"])
    risk_level = _risk_level(flags, conflict)
    review_policy = evaluate_review_policy(
        candidate={
            "subject": row["subject"],
            "type": row["type"],
            "current_value": row["new_value"],
            "visibility_policy": row["visibility_policy"],
        },
        risk_flags=flags,
        conflict=conflict,
        source=source,
        current_context=current_context,
    )
    review_targets = review_policy.get("review_targets")
    if not isinstance(review_targets, list):
        review_targets = []

    return {
        "candidate_id": str(row["candidate_id"]),
        "memory_id": str(row["memory_id"]),
        "subject": row["subject"],
        "type": row["type"],
        "new_value": row["new_value"],
        "old_value": row["old_value"],
        "status": row["status"],
        "conflict_status": "conflict" if conflict["has_conflict"] else "none",
        "risk_level": risk_level,
        "owner_id": row["owner_id"],
        "source_type": row["source_type"] or source.get("source_type") or "unknown",
        "evidence_quote": row["evidence_quote"],
        "visibility_policy": row["visibility_policy"],
        "review_targets": [str(target) for target in review_targets if str(target)],
        "_risk_flags": flags,
        "_sort_at": row["sort_at"],
    }


def _parse_raw_json(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _source_from_metadata(raw_metadata: dict[str, Any], row: Any) -> dict[str, Any]:
    source = raw_metadata.get("source")
    if not isinstance(source, dict):
        source = {}
    result = dict(source)
    result.setdefault("source_type", row["source_type"])
    result.setdefault("actor_id", row["owner_id"])
    return result


def _context_from_metadata(raw_metadata: dict[str, Any]) -> dict[str, Any]:
    context = raw_metadata.get("current_context")
    return dict(context) if isinstance(context, dict) else {}


def _conflict_for_row(row: Any) -> dict[str, Any]:
    has_conflict = bool(row["item_kind"] == "version" or row["supersedes_version_id"])
    return {
        "has_conflict": has_conflict,
        "memory_id": row["memory_id"] if has_conflict else None,
        "old_value": row["old_value"],
    }


def _risk_level(flags: list[str], conflict: dict[str, Any]) -> str:
    if flags:
        return "high"
    if conflict.get("has_conflict"):
        return "medium"
    return "low"


def _matches_view(item: dict[str, Any], view: str, actor_id: str | None) -> bool:
    if view == "all":
        return True
    if view == "mine":
        return _matches_mine(item, actor_id)
    if view == "conflicts":
        return _matches_conflicts(item)
    if view == "high_risk":
        return _matches_high_risk(item)
    return False


def _accessible_items(
    items: list[dict[str, Any]],
    *,
    actor_id: str | None,
    actor_roles: list[str] | tuple[str, ...] | set[str] | None,
) -> list[dict[str, Any]]:
    if _can_review_all(actor_roles):
        return items
    return [item for item in items if _matches_mine(item, actor_id)]


def _can_review_all(actor_roles: list[str] | tuple[str, ...] | set[str] | None) -> bool:
    roles = {str(role).strip().lower() for role in (actor_roles or []) if str(role).strip()}
    return bool(roles.intersection({"admin", "reviewer"}))


def _matches_mine(item: dict[str, Any], actor_id: str | None) -> bool:
    if not actor_id:
        return False
    return actor_id == item.get("owner_id") or actor_id in set(item.get("review_targets") or [])


def _matches_conflicts(item: dict[str, Any]) -> bool:
    return item.get("conflict_status") == "conflict"


def _matches_high_risk(item: dict[str, Any]) -> bool:
    return item.get("risk_level") in {"high", "medium"} or bool(item.get("_risk_flags"))


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.startswith("_")}
