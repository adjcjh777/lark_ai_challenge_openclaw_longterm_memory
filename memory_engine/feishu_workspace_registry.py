"""SQLite registry for repeatable Feishu workspace ingestion.

The registry is deliberately small: it tracks discovery runs, source revisions,
and ingestion status so the workspace pilot can skip unchanged sources and mark
missing/revoked sources without creating a second memory pipeline.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from .document_ingestion import FeishuIngestionSource
from .feishu_workspace_fetcher import WorkspaceResource


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class RegistryDecision:
    should_fetch: bool
    reason: str
    revision: str | None = None
    previous_status: str | None = None


def discovery_filter_key(
    *,
    query: str,
    doc_types: Iterable[str],
    edited_since: str | None = None,
    edited_until: str | None = None,
    opened_since: str | None = None,
    opened_until: str | None = None,
    created_since: str | None = None,
    created_until: str | None = None,
    commented_since: str | None = None,
    commented_until: str | None = None,
    folder_tokens: str | None = None,
    space_ids: str | None = None,
    mine: bool = False,
    creator_ids: str | None = None,
    sharer_ids: str | None = None,
    chat_ids: str | None = None,
    sort: str | None = None,
    explicit_resources: Iterable[str] = (),
    skip_discovery: bool = False,
    folder_walk_tokens: Iterable[str] = (),
    folder_walk_root: bool = False,
    wiki_space_walk_ids: Iterable[str] = (),
    walk_max_depth: int | None = None,
) -> str:
    payload = {
        "query": query or "",
        "doc_types": sorted(item.strip().lower() for item in doc_types if item.strip()),
        "edited_since": edited_since or "",
        "edited_until": edited_until or "",
        "opened_since": opened_since or "",
        "opened_until": opened_until or "",
        "created_since": created_since or "",
        "created_until": created_until or "",
        "commented_since": commented_since or "",
        "commented_until": commented_until or "",
        "folder_tokens": folder_tokens or "",
        "space_ids": space_ids or "",
        "mine": bool(mine),
        "creator_ids": creator_ids or "",
        "sharer_ids": sharer_ids or "",
        "chat_ids": chat_ids or "",
        "sort": sort or "",
        "explicit_resources": sorted(str(item).strip() for item in explicit_resources if str(item).strip()),
        "skip_discovery": bool(skip_discovery),
        "folder_walk_tokens": sorted(str(item).strip() for item in folder_walk_tokens if str(item).strip()),
        "folder_walk_root": bool(folder_walk_root),
        "wiki_space_walk_ids": sorted(str(item).strip() for item in wiki_space_walk_ids if str(item).strip()),
        "walk_max_depth": walk_max_depth,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def start_workspace_ingestion_run(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
    query: str,
    doc_types: Iterable[str],
    filters: dict[str, Any],
    mode: str,
    boundary: str,
) -> str:
    run_id = f"wsrun_{uuid.uuid4().hex[:16]}"
    ts = now_ms()
    conn.execute(
        """
        INSERT INTO feishu_workspace_ingestion_runs (
          run_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
          query, doc_types_json, filters_json, mode, status, boundary, started_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
        """,
        (
            run_id,
            tenant_id,
            organization_id,
            workspace_id,
            filter_key,
            query or "",
            json.dumps(list(doc_types), ensure_ascii=False),
            json.dumps(filters, ensure_ascii=False, sort_keys=True),
            mode,
            boundary,
            ts,
        ),
    )
    conn.commit()
    return run_id


def finish_workspace_ingestion_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    resource_count: int,
    fetched_count: int,
    ingested_count: int,
    skipped_unchanged_count: int,
    failed_count: int,
    stale_marked_count: int = 0,
) -> None:
    conn.execute(
        """
        UPDATE feishu_workspace_ingestion_runs
        SET status = ?,
            finished_at = ?,
            resource_count = ?,
            fetched_count = ?,
            ingested_count = ?,
            skipped_unchanged_count = ?,
            failed_count = ?,
            stale_marked_count = ?
        WHERE run_id = ?
        """,
        (
            status,
            now_ms(),
            resource_count,
            fetched_count,
            ingested_count,
            skipped_unchanged_count,
            failed_count,
            stale_marked_count,
            run_id,
        ),
    )
    conn.commit()


def get_workspace_discovery_cursor(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM feishu_workspace_discovery_cursors
        WHERE tenant_id = ?
          AND organization_id = ?
          AND workspace_id = ?
          AND discovery_filter_key = ?
        """,
        (tenant_id, organization_id, workspace_id, filter_key),
    ).fetchone()
    return dict(row) if row is not None else None


def reset_workspace_discovery_cursor(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
) -> None:
    conn.execute(
        """
        DELETE FROM feishu_workspace_discovery_cursors
        WHERE tenant_id = ?
          AND organization_id = ?
          AND workspace_id = ?
          AND discovery_filter_key = ?
        """,
        (tenant_id, organization_id, workspace_id, filter_key),
    )
    conn.commit()


def record_workspace_discovery_cursor(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
    run_id: str,
    page_token: str | None,
    pages_seen: int,
    resource_count: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    ts = now_ms()
    status = "active" if page_token else "completed"
    completed_at = ts if status == "completed" else None
    conn.execute(
        """
        INSERT INTO feishu_workspace_discovery_cursors (
          cursor_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
          page_token, status, page_count, resource_count, last_run_id,
          first_seen_at, updated_at, completed_at, filters_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, organization_id, workspace_id, discovery_filter_key) DO UPDATE SET
          page_token = excluded.page_token,
          status = excluded.status,
          page_count = feishu_workspace_discovery_cursors.page_count + excluded.page_count,
          resource_count = feishu_workspace_discovery_cursors.resource_count + excluded.resource_count,
          last_run_id = excluded.last_run_id,
          updated_at = excluded.updated_at,
          completed_at = excluded.completed_at,
          filters_json = excluded.filters_json
        """,
        (
            f"wscur_{uuid.uuid4().hex[:16]}",
            tenant_id,
            organization_id,
            workspace_id,
            filter_key,
            page_token,
            status,
            pages_seen,
            resource_count,
            run_id,
            ts,
            ts,
            completed_at,
            json.dumps(filters, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()
    return {
        "status": status,
        "next_page_token": page_token,
        "pages_seen": pages_seen,
        "resource_count": resource_count,
    }


def record_discovered_resource(
    conn: sqlite3.Connection,
    *,
    resource: WorkspaceResource,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
    run_id: str,
) -> RegistryDecision:
    ts = now_ms()
    source_key = resource_source_key(resource)
    revision = resource_revision(resource)
    previous = conn.execute(
        """
        SELECT status, revision, last_ingested_at
        FROM feishu_workspace_source_registry
        WHERE tenant_id = ?
          AND organization_id = ?
          AND workspace_id = ?
          AND source_key = ?
        """,
        (tenant_id, organization_id, workspace_id, source_key),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO feishu_workspace_source_registry (
          registry_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
          source_key, resource_type, route_type, token, title, url, obj_type, table_id,
          revision, status, metadata_json, first_seen_at, last_seen_at, last_seen_run_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?, ?)
        ON CONFLICT(tenant_id, organization_id, workspace_id, source_key) DO UPDATE SET
          discovery_filter_key = excluded.discovery_filter_key,
          resource_type = excluded.resource_type,
          route_type = excluded.route_type,
          token = excluded.token,
          title = excluded.title,
          url = excluded.url,
          obj_type = excluded.obj_type,
          table_id = excluded.table_id,
          revision = excluded.revision,
          status = CASE
            WHEN feishu_workspace_source_registry.status IN ('revoked', 'stale')
              THEN 'rediscovered'
            ELSE feishu_workspace_source_registry.status
          END,
          error_code = NULL,
          error_message = NULL,
          metadata_json = excluded.metadata_json,
          last_seen_at = excluded.last_seen_at,
          last_seen_run_id = excluded.last_seen_run_id
        """,
        (
            f"wsreg_{uuid.uuid4().hex[:16]}",
            tenant_id,
            organization_id,
            workspace_id,
            filter_key,
            source_key,
            resource.resource_type,
            resource.route_type,
            resource.token,
            resource.title,
            resource.url,
            resource.obj_type,
            resource.table_id,
            revision,
            json.dumps(resource.raw or {}, ensure_ascii=False, sort_keys=True),
            ts,
            ts,
            run_id,
        ),
    )
    conn.commit()
    if previous is None:
        return RegistryDecision(True, "new_resource", revision=revision)
    if revision and previous["revision"] == revision and previous["last_ingested_at"]:
        return RegistryDecision(
            False,
            "unchanged_revision",
            revision=revision,
            previous_status=str(previous["status"]),
        )
    return RegistryDecision(True, "changed_or_unversioned", revision=revision, previous_status=str(previous["status"]))


def record_fetch_error(
    conn: sqlite3.Connection,
    *,
    resource: WorkspaceResource,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    run_id: str,
    error_code: str,
    error_message: str,
) -> None:
    status = "revoked" if error_code in {"permission_denied", "resource_not_found"} else "error"
    revoked_at = now_ms() if status == "revoked" else None
    conn.execute(
        """
        UPDATE feishu_workspace_source_registry
        SET status = ?,
            error_code = ?,
            error_message = ?,
            revoked_at = COALESCE(?, revoked_at),
            last_fetched_at = ?,
            last_fetched_run_id = ?
        WHERE tenant_id = ?
          AND organization_id = ?
          AND workspace_id = ?
          AND source_key = ?
        """,
        (
            status,
            error_code,
            error_message[:1000],
            revoked_at,
            now_ms(),
            run_id,
            tenant_id,
            organization_id,
            workspace_id,
            resource_source_key(resource),
        ),
    )
    conn.commit()


def record_source_ingested(
    conn: sqlite3.Connection,
    *,
    source: FeishuIngestionSource,
    resource: WorkspaceResource,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
    run_id: str,
    candidate_count: int,
    duplicate_count: int,
) -> None:
    ts = now_ms()
    metadata = dict(source.metadata or {})
    source_key = ingestion_source_key(source)
    conn.execute(
        """
        INSERT INTO feishu_workspace_source_registry (
          registry_id, tenant_id, organization_id, workspace_id, discovery_filter_key,
          source_key, resource_type, route_type, source_type, source_id, token, title,
          url, obj_type, table_id, sheet_id, app_token, record_id, revision,
          content_fingerprint, status, candidate_count, duplicate_count, metadata_json,
          first_seen_at, last_seen_at, last_fetched_at, last_ingested_at,
          last_seen_run_id, last_fetched_run_id, last_ingested_run_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ingested',
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, organization_id, workspace_id, source_key) DO UPDATE SET
          discovery_filter_key = excluded.discovery_filter_key,
          resource_type = excluded.resource_type,
          route_type = excluded.route_type,
          source_type = excluded.source_type,
          source_id = excluded.source_id,
          token = excluded.token,
          title = excluded.title,
          url = excluded.url,
          obj_type = excluded.obj_type,
          table_id = excluded.table_id,
          sheet_id = excluded.sheet_id,
          app_token = excluded.app_token,
          record_id = excluded.record_id,
          revision = excluded.revision,
          content_fingerprint = excluded.content_fingerprint,
          status = 'ingested',
          candidate_count = excluded.candidate_count,
          duplicate_count = excluded.duplicate_count,
          error_code = NULL,
          error_message = NULL,
          metadata_json = excluded.metadata_json,
          last_seen_at = excluded.last_seen_at,
          last_fetched_at = excluded.last_fetched_at,
          last_ingested_at = excluded.last_ingested_at,
          last_seen_run_id = excluded.last_seen_run_id,
          last_fetched_run_id = excluded.last_fetched_run_id,
          last_ingested_run_id = excluded.last_ingested_run_id
        """,
        (
            f"wsreg_{uuid.uuid4().hex[:16]}",
            tenant_id,
            organization_id,
            workspace_id,
            filter_key,
            source_key,
            resource.resource_type,
            resource.route_type,
            source.source_type,
            source.source_id,
            resource.token,
            source.title,
            source.source_url or resource.url,
            resource.obj_type,
            str(metadata.get("table_id") or resource.table_id or "") or None,
            str(metadata.get("sheet_id") or "") or None,
            str(metadata.get("app_token") or "") or None,
            str(metadata.get("record_id") or "") or None,
            resource_revision(resource),
            content_fingerprint(source.text),
            candidate_count,
            duplicate_count,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ts,
            ts,
            ts,
            ts,
            run_id,
            run_id,
            run_id,
        ),
    )
    conn.execute(
        """
        UPDATE feishu_workspace_source_registry
        SET status = 'ingested',
            source_type = COALESCE(source_type, ?),
            source_id = COALESCE(source_id, ?),
            content_fingerprint = ?,
            candidate_count = ?,
            duplicate_count = ?,
            last_fetched_at = ?,
            last_ingested_at = ?,
            last_fetched_run_id = ?,
            last_ingested_run_id = ?
        WHERE tenant_id = ?
          AND organization_id = ?
          AND workspace_id = ?
          AND source_key = ?
        """,
        (
            source.source_type,
            source.source_id,
            content_fingerprint(source.text),
            candidate_count,
            duplicate_count,
            ts,
            ts,
            run_id,
            run_id,
            tenant_id,
            organization_id,
            workspace_id,
            resource_source_key(resource),
        ),
    )
    conn.commit()


def mark_missing_sources_stale(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    tenant_id: str,
    organization_id: str,
    filter_key: str,
    run_id: str,
) -> int:
    ts = now_ms()
    cursor = conn.execute(
        """
        UPDATE feishu_workspace_source_registry
        SET status = 'stale',
            stale_at = COALESCE(stale_at, ?)
        WHERE tenant_id = ?
          AND organization_id = ?
          AND workspace_id = ?
          AND discovery_filter_key = ?
          AND last_seen_run_id != ?
          AND status NOT IN ('revoked', 'stale')
        """,
        (ts, tenant_id, organization_id, workspace_id, filter_key, run_id),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def resource_source_key(resource: WorkspaceResource) -> str:
    return f"resource:{resource.route_type}:{resource.token}"


def ingestion_source_key(source: FeishuIngestionSource) -> str:
    metadata = source.metadata or {}
    if source.source_type == "lark_sheet":
        return f"source:lark_sheet:{metadata.get('sheet_token') or source.source_id}:{metadata.get('sheet_id') or ''}"
    if source.source_type == "lark_bitable":
        return (
            "source:lark_bitable:"
            f"{metadata.get('app_token') or ''}:"
            f"{metadata.get('table_id') or ''}:"
            f"{metadata.get('record_id') or source.source_id}"
        )
    return f"source:{source.source_type}:{source.source_id}"


def resource_revision(resource: WorkspaceResource) -> str | None:
    raw = resource.raw or {}
    for key in (
        "revision",
        "version",
        "update_time",
        "updated_time",
        "modified_time",
        "latest_modify_time",
        "edit_time",
        "last_edited_time",
    ):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    nested = raw.get("doc") or raw.get("document") or raw.get("resource") or {}
    if isinstance(nested, dict):
        for key in ("revision", "version", "update_time", "updated_time", "modified_time", "edit_time"):
            value = nested.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
