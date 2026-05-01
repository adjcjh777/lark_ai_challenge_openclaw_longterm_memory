#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import AdminQueryService
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository, now_ms

DEFAULT_SCOPE = "project:graph_quality_gate"
FORBIDDEN_SUBSTRINGS = ("app_secret=", "access_token=", "refresh_token=", "demo-secret")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local/staging Copilot knowledge graph quality for the admin Graph backend."
    )
    parser.add_argument("--db-path", default=None, help="SQLite database path. Defaults to a temporary seeded DB.")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help=f"Seed/check scope. Defaults to {DEFAULT_SCOPE}.")
    parser.add_argument(
        "--seed-demo-data",
        action="store_true",
        help="Seed an evidence-backed active memory and one storage graph edge before checking.",
    )
    parser.add_argument("--tenant-id", default=None, help="Optional tenant_id graph filter.")
    parser.add_argument("--organization-id", default=None, help="Optional organization_id graph filter.")
    parser.add_argument("--min-nodes", type=int, default=2, help="Minimum visible graph nodes.")
    parser.add_argument("--min-edges", type=int, default=1, help="Minimum visible graph edges.")
    parser.add_argument(
        "--max-orphan-ratio",
        type=float,
        default=0.35,
        help="Maximum allowed ratio of visible nodes without an incident edge.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    report = run_graph_quality_check(
        db_path=Path(args.db_path).expanduser() if args.db_path else None,
        scope=args.scope,
        seed_demo_data=args.seed_demo_data or args.db_path is None,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        min_nodes=args.min_nodes,
        min_edges=args.min_edges,
        max_orphan_ratio=args.max_orphan_ratio,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_graph_quality_check(
    *,
    db_path: Path | None = None,
    scope: str = DEFAULT_SCOPE,
    seed_demo_data: bool = False,
    tenant_id: str | None = None,
    organization_id: str | None = None,
    min_nodes: int = 2,
    min_edges: int = 1,
    max_orphan_ratio: float = 0.35,
) -> dict[str, Any]:
    if db_path is None:
        with tempfile.TemporaryDirectory(prefix="copilot-graph-quality.") as tmp:
            return _run_with_db(
                db_path=Path(tmp) / "memory.sqlite",
                scope=scope,
                seed_demo_data=True,
                tenant_id=tenant_id,
                organization_id=organization_id,
                min_nodes=min_nodes,
                min_edges=min_edges,
                max_orphan_ratio=max_orphan_ratio,
                temporary_db=True,
            )
    return _run_with_db(
        db_path=db_path,
        scope=scope,
        seed_demo_data=seed_demo_data,
        tenant_id=tenant_id,
        organization_id=organization_id,
        min_nodes=min_nodes,
        min_edges=min_edges,
        max_orphan_ratio=max_orphan_ratio,
        temporary_db=False,
    )


def _run_with_db(
    *,
    db_path: Path,
    scope: str,
    seed_demo_data: bool,
    tenant_id: str | None,
    organization_id: str | None,
    min_nodes: int,
    min_edges: int,
    max_orphan_ratio: float,
    temporary_db: bool,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        init_db(conn)
        if seed_demo_data:
            _seed_demo_data(conn, scope=scope)
        service = AdminQueryService(conn)
        graph = service.graph_workspace(
            tenant_id=tenant_id,
            organization_id=organization_id,
            limit=200,
        )
        checks = _quality_checks(
            graph,
            min_nodes=min_nodes,
            min_edges=min_edges,
            max_orphan_ratio=max_orphan_ratio,
        )
    finally:
        conn.close()
    failed = {name: check for name, check in checks.items() if check["status"] != "pass"}
    return {
        "ok": not failed,
        "db_path": str(db_path),
        "temporary_db": temporary_db,
        "filters": {
            "tenant_id": tenant_id,
            "organization_id": organization_id,
        },
        "summary": {
            "workspace_node_count": graph.get("workspace_node_count"),
            "workspace_edge_count": graph.get("workspace_edge_count"),
            "nodes_by_type": graph.get("nodes_by_type"),
            "edges_by_type": graph.get("edges_by_type"),
        },
        "checks": checks,
        "failed_checks": sorted(failed),
        "boundary": "local/staging graph quality gate only; no production graph governance or long-running live claim",
        "next_step": ""
        if not failed
        else "Inspect graph endpoints, tenant coverage, and compiled memory evidence edges.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Knowledge Graph Quality Gate",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(f"- {name}: {check.get('status')} {check.get('message', '')}".rstrip())
    return "\n".join(lines)


def _seed_demo_data(conn: sqlite3.Connection, *, scope: str) -> None:
    repo = MemoryRepository(conn)
    existing = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM memories
        WHERE status = 'active' AND (scope_type || ':' || scope_id) = ?
        """,
        (scope,),
    ).fetchone()["count"]
    if int(existing or 0) == 0:
        repo.remember(
            scope,
            "决定：Graph Admin 必须展示 active memory 到 evidence source 的 grounded_by 关系。",
            source_type="graph_quality_gate",
            source_id="graph_quality_source",
            created_by="graph_quality_gate",
        )
    event_time = now_ms()
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_graph_nodes (
              id, tenant_id, organization_id, node_type, node_key, label,
              visibility_policy, status, metadata_json, first_seen_at,
              last_seen_at, observation_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "kgn_graph_quality_chat",
                "tenant:demo",
                "org:demo",
                "feishu_chat",
                "chat_graph_quality",
                "Graph Quality Review Chat",
                "team",
                "active",
                json.dumps({"channel": "quality_gate"}, ensure_ascii=False),
                event_time,
                event_time,
                2,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_graph_nodes (
              id, tenant_id, organization_id, node_type, node_key, label,
              visibility_policy, status, metadata_json, first_seen_at,
              last_seen_at, observation_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "kgn_graph_quality_user",
                "tenant:demo",
                "org:demo",
                "feishu_user",
                "ou_graph_quality",
                "Graph Quality Reviewer",
                "team",
                "active",
                "{}",
                event_time,
                event_time,
                2,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_graph_edges (
              id, tenant_id, organization_id, source_node_id, target_node_id,
              edge_type, metadata_json, first_seen_at, last_seen_at, observation_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "kge_graph_quality_member",
                "tenant:demo",
                "org:demo",
                "kgn_graph_quality_user",
                "kgn_graph_quality_chat",
                "member_of",
                "{}",
                event_time,
                event_time,
                2,
            ),
        )


def _quality_checks(
    graph: dict[str, Any],
    *,
    min_nodes: int,
    min_edges: int,
    max_orphan_ratio: float,
) -> dict[str, dict[str, Any]]:
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    node_ids = {str(node.get("id")) for node in nodes}
    edge_endpoints = {
        str(edge.get(endpoint))
        for edge in edges
        for endpoint in ("source_node_id", "target_node_id")
        if edge.get(endpoint)
    }
    missing_endpoints = sorted(endpoint for endpoint in edge_endpoints if endpoint not in node_ids)
    orphan_nodes = sorted(node_id for node_id in node_ids if node_id not in edge_endpoints)
    orphan_ratio = (len(orphan_nodes) / len(node_ids)) if node_ids else 1.0
    node_types = {str(node.get("node_type")) for node in nodes}
    edge_types = {str(edge.get("edge_type")) for edge in edges}
    missing_tenancy = [
        str(node.get("id"))
        for node in nodes
        if not str(node.get("tenant_id") or "").strip() or not str(node.get("organization_id") or "").strip()
    ]
    serialized = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False).lower()
    leaked = sorted(token for token in FORBIDDEN_SUBSTRINGS if token.lower() in serialized)
    return {
        "workspace_size": _check(
            len(nodes) >= min_nodes and len(edges) >= min_edges,
            f"{len(nodes)} nodes / {len(edges)} edges",
            {"min_nodes": min_nodes, "min_edges": min_edges},
        ),
        "compiled_memory_graph": _check(
            "memory" in node_types and "evidence_source" in node_types and "grounded_by" in edge_types,
            "compiled memory -> grounded_by -> evidence_source graph present",
            {"node_types": sorted(node_types), "edge_types": sorted(edge_types)},
        ),
        "edge_endpoints": _check(
            not missing_endpoints,
            "all visible edge endpoints are present in visible nodes",
            {"missing_endpoints": missing_endpoints},
        ),
        "tenant_coverage": _check(
            not missing_tenancy,
            "all visible nodes include tenant_id and organization_id",
            {"missing_node_ids": missing_tenancy},
        ),
        "orphan_ratio": _check(
            orphan_ratio <= max_orphan_ratio,
            f"orphan_ratio={orphan_ratio:.4f}",
            {"orphan_node_ids": orphan_nodes, "max_orphan_ratio": max_orphan_ratio},
        ),
        "secret_redaction": _check(
            not leaked,
            "graph payload has no known secret-like substrings",
            {"forbidden_substrings_found": leaked},
        ),
    }


def _check(ok: bool, message: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "message": message, **extra}


if __name__ == "__main__":
    raise SystemExit(main())
