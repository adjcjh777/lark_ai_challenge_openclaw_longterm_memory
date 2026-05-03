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
from memory_engine.document_ingestion import ingest_feishu_source
from memory_engine.feishu_workspace_fetcher import (
    WorkspaceActor,
    discover_workspace_resources,
    fetch_workspace_resource_sources,
    workspace_current_context,
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
    parser.add_argument("--opened-since", help="Filter resources opened since this time, e.g. 30d")
    parser.add_argument("--created-since", help="Filter resources created since this time, e.g. 2026-05-01")
    parser.add_argument("--folder-tokens", help="Comma-separated Drive folder tokens")
    parser.add_argument("--space-ids", help="Comma-separated Wiki space IDs")
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
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")

    args = parser.parse_args()
    if not args.dry_run and not (args.actor_user_id or args.actor_open_id):
        parser.error("--actor-user-id or --actor-open-id is required when not using --dry-run")

    resources = discover_workspace_resources(
        query=args.query,
        doc_types=[item.strip() for item in args.doc_types.split(",") if item.strip()],
        limit=args.limit,
        max_pages=args.max_pages,
        edited_since=args.edited_since,
        opened_since=args.opened_since,
        created_since=args.created_since,
        folder_tokens=args.folder_tokens,
        space_ids=args.space_ids,
        profile=args.profile,
        as_identity=args.as_identity,
    )
    if args.dry_run:
        return _emit(
            {
                "ok": True,
                "mode": "dry_run",
                "boundary": "resource_discovery_only_no_fetch_no_write",
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
    source_results: list[dict[str, Any]] = []
    try:
        for resource in resources:
            try:
                sources = fetch_workspace_resource_sources(
                    resource,
                    max_sheet_rows=args.max_sheet_rows,
                    max_bitable_records=args.max_bitable_records,
                    profile=args.profile,
                    as_identity=args.as_identity,
                )
            except Exception as exc:
                source_results.append(
                    {
                        "resource": _resource_summary(resource),
                        "ok": False,
                        "stage": "fetch",
                        "error": str(exc),
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
    finally:
        conn.close()

    return _emit(
        {
            "ok": True,
            "mode": "controlled_workspace_ingestion_pilot",
            "boundary": "candidate_pipeline_only_no_production_daemon_no_raw_event_embedding",
            "resource_count": len(resources),
            "source_count": len(source_results),
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


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"mode: {payload['mode']}")
    print(f"boundary: {payload['boundary']}")
    print(f"resources: {payload.get('resource_count', 0)}")
    if "source_count" in payload:
        print(f"sources: {payload['source_count']}")
        print(f"candidates: {payload.get('candidate_count', 0)}")
        print(f"duplicates: {payload.get('duplicate_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
