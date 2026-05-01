from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from memory_engine.repository import MemoryRepository, now_ms


ACTIVE_STATUS = "active"
PENDING_STATUS = "pending_onboarding"
DISABLED_STATUS = "disabled"


def get_group_policy(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    tenant_id: str,
    organization_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM feishu_group_policies
        WHERE tenant_id = ? AND organization_id = ? AND chat_id = ?
        """,
        (tenant_id, organization_id, chat_id),
    ).fetchone()
    return _row_to_policy(row) if row else None


def ensure_group_policy(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    tenant_id: str,
    organization_id: str,
    scope: str,
    visibility_policy: str,
    actor_id: str,
    status: str = PENDING_STATUS,
) -> dict[str, Any]:
    existing = get_group_policy(
        conn,
        chat_id=chat_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
    )
    if existing:
        return existing
    now = now_ms()
    policy_id = _policy_id(tenant_id, organization_id, chat_id)
    conn.execute(
        """
        INSERT INTO feishu_group_policies (
          id, tenant_id, organization_id, chat_id, scope, visibility_policy,
          status, passive_memory_enabled, reviewer_open_ids, owner_open_ids,
          notes, created_by, updated_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, '[]', ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            tenant_id,
            organization_id,
            chat_id,
            scope,
            visibility_policy,
            status,
            json.dumps([actor_id] if actor_id else [], ensure_ascii=False),
            "Created when the bot first observed this group. Passive memory remains off until explicitly enabled.",
            actor_id or "unknown",
            actor_id or "unknown",
            now,
            now,
        ),
    )
    return get_group_policy(
        conn,
        chat_id=chat_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
    ) or {}


def enable_group_memory(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    tenant_id: str,
    organization_id: str,
    scope: str,
    visibility_policy: str,
    actor_id: str,
    actor_roles: list[str],
    reviewer_open_ids: list[str] | None = None,
    source_entrypoint: str = "feishu_test_group",
) -> dict[str, Any]:
    now = now_ms()
    existing = ensure_group_policy(
        conn,
        chat_id=chat_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
        scope=scope,
        visibility_policy=visibility_policy,
        actor_id=actor_id,
    )
    owners = sorted(set(_json_list(existing.get("owner_open_ids")) + ([actor_id] if actor_id else [])))
    reviewers = sorted(set((reviewer_open_ids or []) + _json_list(existing.get("reviewer_open_ids"))))
    policy_id = existing.get("id") or _policy_id(tenant_id, organization_id, chat_id)
    conn.execute(
        """
        INSERT INTO feishu_group_policies (
          id, tenant_id, organization_id, chat_id, scope, visibility_policy,
          status, passive_memory_enabled, reviewer_open_ids, owner_open_ids,
          notes, created_by, updated_by, created_at, updated_at, last_enabled_at, disabled_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(tenant_id, organization_id, chat_id) DO UPDATE SET
          scope = excluded.scope,
          visibility_policy = excluded.visibility_policy,
          status = excluded.status,
          passive_memory_enabled = excluded.passive_memory_enabled,
          reviewer_open_ids = excluded.reviewer_open_ids,
          owner_open_ids = excluded.owner_open_ids,
          notes = excluded.notes,
          updated_by = excluded.updated_by,
          updated_at = excluded.updated_at,
          last_enabled_at = excluded.last_enabled_at,
          disabled_at = NULL
        """,
        (
            policy_id,
            tenant_id,
            organization_id,
            chat_id,
            scope,
            visibility_policy,
            ACTIVE_STATUS,
            json.dumps(reviewers, ensure_ascii=False),
            json.dumps(owners, ensure_ascii=False),
            "Passive memory screening is enabled for this group by an authorized reviewer/admin.",
            existing.get("created_by") or actor_id or "unknown",
            actor_id or "unknown",
            int(existing.get("created_at") or now),
            now,
            now,
        ),
    )
    MemoryRepository(conn).record_audit_event(
        event_type="feishu_group_policy_enabled",
        action="feishu.group_policy.enable",
        tool_name="copilot.group_enable_memory",
        target_type="feishu_group_policy",
        target_id=policy_id,
        actor_id=actor_id or "unknown",
        actor_roles=actor_roles,
        tenant_id=tenant_id,
        organization_id=organization_id,
        scope=scope,
        permission_decision="allow",
        reason_code="authorized_group_memory_enable",
        request_id=f"req_{policy_id}_{now}",
        trace_id=f"trace_{policy_id}_{now}",
        visible_fields=["chat_id", "scope", "visibility_policy", "status", "passive_memory_enabled"],
        source_context={"entrypoint": source_entrypoint, "chat_id": chat_id},
        created_at=now,
    )
    return get_group_policy(
        conn,
        chat_id=chat_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
    ) or {}


def disable_group_memory(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    tenant_id: str,
    organization_id: str,
    scope: str,
    visibility_policy: str,
    actor_id: str,
    actor_roles: list[str],
    source_entrypoint: str = "feishu_test_group",
) -> dict[str, Any]:
    now = now_ms()
    existing = ensure_group_policy(
        conn,
        chat_id=chat_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
        scope=scope,
        visibility_policy=visibility_policy,
        actor_id=actor_id,
    )
    policy_id = existing.get("id") or _policy_id(tenant_id, organization_id, chat_id)
    conn.execute(
        """
        UPDATE feishu_group_policies
        SET status = ?,
            passive_memory_enabled = 0,
            updated_by = ?,
            updated_at = ?,
            disabled_at = ?,
            notes = ?
        WHERE tenant_id = ? AND organization_id = ? AND chat_id = ?
        """,
        (
            DISABLED_STATUS,
            actor_id or "unknown",
            now,
            now,
            "Passive memory screening was disabled for this group.",
            tenant_id,
            organization_id,
            chat_id,
        ),
    )
    MemoryRepository(conn).record_audit_event(
        event_type="feishu_group_policy_disabled",
        action="feishu.group_policy.disable",
        tool_name="copilot.group_disable_memory",
        target_type="feishu_group_policy",
        target_id=policy_id,
        actor_id=actor_id or "unknown",
        actor_roles=actor_roles,
        tenant_id=tenant_id,
        organization_id=organization_id,
        scope=scope,
        permission_decision="allow",
        reason_code="authorized_group_memory_disable",
        request_id=f"req_{policy_id}_{now}",
        trace_id=f"trace_{policy_id}_{now}",
        visible_fields=["chat_id", "scope", "visibility_policy", "status", "passive_memory_enabled"],
        source_context={"entrypoint": source_entrypoint, "chat_id": chat_id},
        created_at=now,
    )
    return get_group_policy(
        conn,
        chat_id=chat_id,
        tenant_id=tenant_id,
        organization_id=organization_id,
    ) or {}


def record_group_policy_denied(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    tenant_id: str,
    organization_id: str,
    scope: str,
    actor_id: str,
    actor_roles: list[str],
    action: str,
    source_entrypoint: str = "feishu_test_group",
) -> str:
    now = now_ms()
    policy_id = _policy_id(tenant_id, organization_id, chat_id)
    return MemoryRepository(conn).record_audit_event(
        event_type="feishu_group_policy_denied",
        action=action,
        tool_name=action,
        target_type="feishu_group_policy",
        target_id=policy_id,
        actor_id=actor_id or "unknown",
        actor_roles=actor_roles,
        tenant_id=tenant_id,
        organization_id=organization_id,
        scope=scope,
        permission_decision="deny",
        reason_code="reviewer_or_admin_required",
        request_id=f"req_{policy_id}_{now}",
        trace_id=f"trace_{policy_id}_{now}",
        redacted_fields=["group_policy_write"],
        source_context={"entrypoint": source_entrypoint, "chat_id": chat_id},
        created_at=now,
    )


def group_policy_allows_passive_memory(policy: dict[str, Any] | None) -> bool:
    if not policy:
        return False
    return policy.get("status") == ACTIVE_STATUS and bool(policy.get("passive_memory_enabled"))


def _row_to_policy(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    policy = dict(row)
    policy["passive_memory_enabled"] = bool(policy.get("passive_memory_enabled"))
    policy["reviewer_open_ids"] = _json_list(policy.get("reviewer_open_ids"))
    policy["owner_open_ids"] = _json_list(policy.get("owner_open_ids"))
    return policy


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item)]


def _policy_id(tenant_id: str, organization_id: str, chat_id: str) -> str:
    digest = hashlib.sha1(f"{tenant_id}:{organization_id}:{chat_id}".encode("utf-8")).hexdigest()[:16]
    return f"feishu_group_policy_{digest}"
