#!/usr/bin/env python3
"""Discover Feishu workspace resources and route them into candidate ingestion.

This is a controlled pilot entrypoint. It uses lark-cli for discovery/fetching,
constructs per-source permission context, and then reuses the existing
FeishuIngestionSource -> CopilotService path. It is not a daemon and it does
not claim production full-workspace ingestion.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.db import connect, db_path_from_env, init_db
from memory_engine.document_ingestion import FeishuIngestionSource, ingest_feishu_source, mark_feishu_source_revoked
from memory_engine.feishu_workspace_fetcher import (
    WorkspaceActor,
    WorkspaceResource,
    discover_workspace_resource_batch,
    discover_workspace_resources,
    fetch_workspace_resource_sources,
    workspace_current_context,
)
from memory_engine.feishu_workspace_registry import (
    discovery_filter_key,
    finish_workspace_ingestion_run,
    get_workspace_discovery_cursor,
    record_workspace_discovery_cursor,
    record_discovered_resource,
    record_fetch_error,
    record_source_ingested,
    reset_workspace_discovery_cursor,
    start_workspace_ingestion_run,
    mark_missing_sources_stale,
)
from memory_engine.repository import MemoryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled Feishu workspace ingestion pilot")
    parser.add_argument("--query", default="", help="Drive search query; empty string browses by filters")
    parser.add_argument(
        "--doc-types",
        default="doc,docx,wiki,sheet,bitable",
        help="Comma-separated drive doc types for discovery",
    )
    parser.add_argument("--edited-since", help="Filter resources edited since this time, e.g. 30d")
    parser.add_argument("--edited-until", help="Filter resources edited before this time")
    parser.add_argument("--opened-since", help="Filter resources opened since this time, e.g. 30d")
    parser.add_argument("--opened-until", help="Filter resources opened before this time")
    parser.add_argument("--created-since", help="Filter resources created since this time, e.g. 2026-05-01")
    parser.add_argument("--created-until", help="Filter resources created before this time")
    parser.add_argument("--commented-since", help="Filter resources commented since this time")
    parser.add_argument("--commented-until", help="Filter resources commented before this time")
    parser.add_argument("--folder-tokens", help="Comma-separated Drive folder tokens")
    parser.add_argument("--space-ids", help="Comma-separated Wiki space IDs")
    parser.add_argument("--mine", action="store_true", help="Restrict discovery to docs created by the current user")
    parser.add_argument("--creator-ids", help="Comma-separated creator open_ids")
    parser.add_argument("--sharer-ids", help="Comma-separated sharer open_ids")
    parser.add_argument("--chat-ids", help="Comma-separated chat IDs")
    parser.add_argument("--sort", help="Drive search sort: default, edit_time, edit_time_asc, open_time, create_time")
    parser.add_argument("--limit", type=int, default=20, help="Maximum resources to discover")
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum drive search pages")
    parser.add_argument("--max-sheet-rows", type=int, default=80, help="Maximum rows read from each sheet")
    parser.add_argument("--max-bitable-records", type=int, default=50, help="Maximum records per Base table")
    parser.add_argument("--candidate-limit", type=int, default=12, help="Maximum candidate quotes per source")
    parser.add_argument("--scope", default="project:feishu_ai_challenge", help="Memory scope/workspace id")
    parser.add_argument("--profile", help="lark-cli profile")
    parser.add_argument("--as-identity", default="user", help="lark-cli identity: user or bot")
    parser.add_argument("--actor-user-id", help="Reviewer/operator user_id for permission context")
    parser.add_argument("--actor-open-id", help="Reviewer/operator open_id for permission context")
    parser.add_argument("--tenant-id", default="tenant:demo")
    parser.add_argument("--organization-id", default="org:demo")
    parser.add_argument("--roles", default="member,reviewer", help="Comma-separated actor roles")
    parser.add_argument("--dry-run", action="store_true", help="Only discover resources; do not fetch content or write DB")
    parser.add_argument(
        "--no-skip-unchanged",
        action="store_true",
        help="Fetch resources even when registry revision has not changed",
    )
    parser.add_argument(
        "--mark-missing-stale",
        action="store_true",
        help="Mark registry sources from the same discovery filter stale when absent from this run",
    )
    parser.add_argument("--resume-cursor", action="store_true", help="Resume discovery from the saved page token")
    parser.add_argument("--reset-cursor", action="store_true", help="Clear the saved cursor before this run")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")

    args = parser.parse_args()
    if not args.dry_run and not (args.actor_user_id or args.actor_open_id):
        parser.error("--actor-user-id or --actor-open-id is required when not using --dry-run")
    doc_types = [item.strip() for item in args.doc_types.split(",") if item.strip()]
    filter_key = discovery_filter_key(
        query=args.query,
        doc_types=doc_types,
        edited_since=args.edited_since,
        edited_until=args.edited_until,
        opened_since=args.opened_since,
        opened_until=args.opened_until,
        created_since=args.created_since,
        created_until=args.created_until,
        commented_since=args.commented_since,
        commented_until=args.commented_until,
        folder_tokens=args.folder_tokens,
        space_ids=args.space_ids,
        mine=args.mine,
        creator_ids=args.creator_ids,
        sharer_ids=args.sharer_ids,
        chat_ids=args.chat_ids,
        sort=args.sort,
    )

    if args.dry_run:
        resources = discover_workspace_resources(
            query=args.query,
            doc_types=doc_types,
            limit=args.limit,
            max_pages=args.max_pages,
            edited_since=args.edited_since,
            edited_until=args.edited_until,
            opened_since=args.opened_since,
            opened_until=args.opened_until,
            created_since=args.created_since,
            created_until=args.created_until,
            commented_since=args.commented_since,
            commented_until=args.commented_until,
            folder_tokens=args.folder_tokens,
            space_ids=args.space_ids,
            mine=args.mine,
            creator_ids=args.creator_ids,
            sharer_ids=args.sharer_ids,
            chat_ids=args.chat_ids,
            sort=args.sort,
            profile=args.profile,
            as_identity=args.as_identity,
        )
        return _emit(
            {
                "ok": True,
                "mode": "dry_run",
                "boundary": "resource_discovery_only_no_fetch_no_write",
                "discovery_filter_key": filter_key,
                "resource_count": len(resources),
                "resources": [_resource_summary(resource) for resource in resources],
            },
            as_json=args.json,
        )

    actor = WorkspaceActor(
        user_id=args.actor_user_id,
        open_id=args.actor_open_id,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        roles=tuple(role.strip() for role in args.roles.split(",") if role.strip()),
    )
    conn = connect(db_path_from_env())
    init_db(conn)
    repo = MemoryRepository(conn)
    cursor_before: dict[str, Any] | None = None
    if args.reset_cursor:
        reset_workspace_discovery_cursor(
            conn,
            workspace_id=args.scope,
            tenant_id=args.tenant_id,
            organization_id=args.organization_id,
            filter_key=filter_key,
        )
    start_page_token = None
    if args.resume_cursor:
        cursor_before = get_workspace_discovery_cursor(
            conn,
            workspace_id=args.scope,
            tenant_id=args.tenant_id,
            organization_id=args.organization_id,
            filter_key=filter_key,
        )
        if cursor_before and cursor_before.get("status") == "active":
            start_page_token = str(cursor_before.get("page_token") or "") or None
    discovery_batch = discover_workspace_resource_batch(
        query=args.query,
        doc_types=doc_types,
        limit=args.limit,
        max_pages=args.max_pages,
        edited_since=args.edited_since,
        edited_until=args.edited_until,
        opened_since=args.opened_since,
        opened_until=args.opened_until,
        created_since=args.created_since,
        created_until=args.created_until,
        commented_since=args.commented_since,
        commented_until=args.commented_until,
        folder_tokens=args.folder_tokens,
        space_ids=args.space_ids,
        mine=args.mine,
        creator_ids=args.creator_ids,
        sharer_ids=args.sharer_ids,
        chat_ids=args.chat_ids,
        sort=args.sort,
        profile=args.profile,
        as_identity=args.as_identity,
        start_page_token=start_page_token,
    )
    resources = discovery_batch.resources
    source_results: list[dict[str, Any]] = []
    filters = {
        "edited_since": args.edited_since,
        "edited_until": args.edited_until,
        "opened_since": args.opened_since,
        "opened_until": args.opened_until,
        "created_since": args.created_since,
        "created_until": args.created_until,
        "commented_since": args.commented_since,
        "commented_until": args.commented_until,
        "folder_tokens": args.folder_tokens,
        "space_ids": args.space_ids,
        "mine": args.mine,
        "creator_ids": args.creator_ids,
        "sharer_ids": args.sharer_ids,
        "chat_ids": args.chat_ids,
        "sort": args.sort,
        "resume_cursor": args.resume_cursor,
        "start_page_token": start_page_token,
    }
    run_id = start_workspace_ingestion_run(
        conn,
        workspace_id=args.scope,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        filter_key=filter_key,
        query=args.query,
        doc_types=doc_types,
        filters=filters,
        mode="controlled_workspace_ingestion_pilot",
        boundary="candidate_pipeline_only_with_registry_no_production_daemon_no_raw_event_embedding",
    )
    cursor_after: dict[str, Any] | None = None
    fetched_count = 0
    skipped_unchanged_count = 0
    failed_count = 0
    stale_marked_count = 0
    try:
        for resource in resources:
            decision = record_discovered_resource(
                conn,
                resource=resource,
                workspace_id=args.scope,
                tenant_id=args.tenant_id,
                organization_id=args.organization_id,
                filter_key=filter_key,
                run_id=run_id,
            )
            if decision.should_fetch is False and not args.no_skip_unchanged:
                skipped_unchanged_count += 1
                source_results.append(
                    {
                        "resource": _resource_summary(resource),
                        "ok": True,
                        "stage": "skip",
                        "reason": decision.reason,
                        "revision": decision.revision,
                    }
                )
                continue
            try:
                sources = fetch_workspace_resource_sources(
                    resource,
                    max_sheet_rows=args.max_sheet_rows,
                    max_bitable_records=args.max_bitable_records,
                    profile=args.profile,
                    as_identity=args.as_identity,
                )
                fetched_count += 1
            except Exception as exc:
                failed_count += 1
                error_code = _fetch_error_code(exc)
                error_message = str(exc)
                record_fetch_error(
                    conn,
                    resource=resource,
                    workspace_id=args.scope,
                    tenant_id=args.tenant_id,
                    organization_id=args.organization_id,
                    run_id=run_id,
                    error_code=error_code,
                    error_message=error_message,
                )
                if error_code in {"permission_denied", "resource_not_found"}:
                    _mark_precise_source_revoked(repo, resource, scope=args.scope, actor=actor)
                source_results.append(
                    {
                        "resource": _resource_summary(resource),
                        "ok": False,
                        "stage": "fetch",
                        "error_code": error_code,
                        "error": error_message,
                    }
                )
                continue
            for source in sources:
                context = workspace_current_context(scope=args.scope, actor=actor, source=source)
                result = ingest_feishu_source(
                    repo,
                    source,
                    scope=args.scope,
                    current_context=context,
                    limit=args.candidate_limit,
                )
                if result.get("ok"):
                    record_source_ingested(
                        conn,
                        source=source,
                        resource=resource,
                        workspace_id=args.scope,
                        tenant_id=args.tenant_id,
                        organization_id=args.organization_id,
                        filter_key=filter_key,
                        run_id=run_id,
                        candidate_count=int(result.get("candidate_count") or 0),
                        duplicate_count=int(result.get("duplicate_count") or 0),
                    )
                source_results.append(
                    {
                        "resource": _resource_summary(resource),
                        "source": {
                            "source_type": source.source_type,
                            "source_id": source.source_id,
                            "title": source.title,
                        },
                        "ok": bool(result.get("ok")),
                        "candidate_count": result.get("candidate_count", 0),
                        "duplicate_count": result.get("duplicate_count", 0),
                        "error": result.get("error"),
                    }
                )
        if args.mark_missing_stale:
            stale_marked_count = mark_missing_sources_stale(
                conn,
                workspace_id=args.scope,
                tenant_id=args.tenant_id,
                organization_id=args.organization_id,
                filter_key=filter_key,
                run_id=run_id,
            )
        cursor_after = record_workspace_discovery_cursor(
            conn,
            workspace_id=args.scope,
            tenant_id=args.tenant_id,
            organization_id=args.organization_id,
            filter_key=filter_key,
            run_id=run_id,
            page_token=discovery_batch.next_page_token,
            pages_seen=discovery_batch.pages_seen,
            resource_count=len(resources),
            filters=filters,
        )
    finally:
        finish_workspace_ingestion_run(
            conn,
            run_id=run_id,
            status="completed" if failed_count == 0 else "completed_with_errors",
            resource_count=len(resources),
            fetched_count=fetched_count,
            ingested_count=sum(1 for item in source_results if item.get("candidate_count") is not None),
            skipped_unchanged_count=skipped_unchanged_count,
            failed_count=failed_count,
            stale_marked_count=stale_marked_count,
        )
        conn.close()

    return _emit(
        {
            "ok": True,
            "mode": "controlled_workspace_ingestion_pilot",
            "boundary": "candidate_pipeline_only_with_registry_no_production_daemon_no_raw_event_embedding",
            "run_id": run_id,
            "discovery_filter_key": filter_key,
            "discovery": {
                "pages_seen": discovery_batch.pages_seen,
                "start_page_token": start_page_token,
                "next_page_token": discovery_batch.next_page_token,
                "exhausted": discovery_batch.exhausted,
                "cursor_before": _cursor_summary(cursor_before),
                "cursor_after": cursor_after,
            },
            "resource_count": len(resources),
            "source_count": len(source_results),
            "fetched_count": fetched_count,
            "skipped_unchanged_count": skipped_unchanged_count,
            "failed_count": failed_count,
            "stale_marked_count": stale_marked_count,
            "candidate_count": sum(int(item.get("candidate_count") or 0) for item in source_results),
            "duplicate_count": sum(int(item.get("duplicate_count") or 0) for item in source_results),
            "results": source_results,
        },
        as_json=args.json,
    )


def _resource_summary(resource) -> dict[str, Any]:
    return {
        "resource_type": resource.resource_type,
        "route_type": resource.route_type,
        "token": resource.token,
        "title": resource.title,
        "url": resource.url,
    }


def _cursor_summary(cursor: dict[str, Any] | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    return {
        "status": cursor.get("status"),
        "page_token": cursor.get("page_token"),
        "page_count": cursor.get("page_count"),
        "resource_count": cursor.get("resource_count"),
        "last_run_id": cursor.get("last_run_id"),
    }


def _fetch_error_code(exc: Exception) -> str:
    text = str(exc).lower()
    if "permission_denied" in text or "permission denied" in text or "权限" in text or "forbidden" in text:
        return "permission_denied"
    if "resource_not_found" in text or "not found" in text or "不存在" in text or "404" in text:
        return "resource_not_found"
    return "api_error"


def _mark_precise_source_revoked(
    repo: MemoryRepository,
    resource: WorkspaceResource,
    *,
    scope: str,
    actor: WorkspaceActor,
) -> None:
    source = _revocable_source_for_resource(resource)
    if source is None:
        return
    context = workspace_current_context(scope=scope, actor=actor, source=source)
    mark_feishu_source_revoked(repo, source_type=source.source_type, source_id=source.source_id, scope=scope, current_context=context)


def _revocable_source_for_resource(resource: WorkspaceResource) -> FeishuIngestionSource | None:
    if resource.route_type == "document":
        return FeishuIngestionSource(
            source_type="document_feishu",
            source_id=resource.token,
            title=resource.title,
            text="",
            actor_id="workspace_document_revocation",
            source_url=resource.url,
            metadata={"document_id": resource.token},
        )
    if resource.route_type == "sheet":
        return FeishuIngestionSource(
            source_type="lark_sheet",
            source_id=resource.token,
            title=resource.title,
            text="",
            actor_id="workspace_sheet_revocation",
            source_url=resource.url,
            metadata={"sheet_token": resource.token},
        )
    return None


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"mode: {payload['mode']}")
    print(f"boundary: {payload['boundary']}")
    print(f"resources: {payload.get('resource_count', 0)}")
    if "source_count" in payload:
        print(f"sources: {payload['source_count']}")
        print(f"run_id: {payload.get('run_id')}")
        discovery = payload.get("discovery") if isinstance(payload.get("discovery"), dict) else {}
        print(f"next_page_token: {discovery.get('next_page_token')}")
        print(f"discovery_exhausted: {str(discovery.get('exhausted')).lower()}")
        print(f"skipped_unchanged: {payload.get('skipped_unchanged_count', 0)}")
        print(f"candidates: {payload.get('candidate_count', 0)}")
        print(f"duplicates: {payload.get('duplicate_count', 0)}")
        print(f"failed: {payload.get('failed_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
