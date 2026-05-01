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

from memory_engine.copilot.knowledge_site import STATIC_SITE_BOUNDARY, export_knowledge_site
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository, now_ms

DEFAULT_SCOPE = "project:knowledge_site_gate"
FORBIDDEN_SUBSTRINGS = ("demo-secret", "app_secret=demo-secret", "token=demo-secret")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export and verify a read-only LLM Wiki + knowledge graph static site bundle."
    )
    parser.add_argument("--db-path", default=None, help="SQLite database path. Defaults to a temporary seeded DB.")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help=f"Scope to export. Defaults to {DEFAULT_SCOPE}.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to a temporary directory unless --keep-output is set.",
    )
    parser.add_argument(
        "--seed-demo-data",
        action="store_true",
        help="Seed one evidence-backed active memory and graph node before export.",
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="Keep the generated output directory. Requires --output-dir for non-temporary output.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    if args.keep_output and not args.output_dir:
        parser.error("--keep-output requires --output-dir")

    result = run_knowledge_site_export_check(
        db_path=Path(args.db_path).expanduser() if args.db_path else None,
        output_dir=Path(args.output_dir).expanduser() if args.output_dir else None,
        scope=args.scope,
        seed_demo_data=args.seed_demo_data or args.db_path is None,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


def run_knowledge_site_export_check(
    *,
    db_path: Path | None = None,
    output_dir: Path | None = None,
    scope: str = DEFAULT_SCOPE,
    seed_demo_data: bool = False,
) -> dict[str, Any]:
    if db_path is None:
        with (
            tempfile.TemporaryDirectory(prefix="copilot-knowledge-site-db.") as db_tmp,
            tempfile.TemporaryDirectory(prefix="copilot-knowledge-site-out.") as out_tmp,
        ):
            return _run_with_paths(
                db_path=Path(db_tmp) / "memory.sqlite",
                output_dir=Path(out_tmp),
                scope=scope,
                seed_demo_data=True,
                output_is_temporary=True,
            )
    if output_dir is None:
        with tempfile.TemporaryDirectory(prefix="copilot-knowledge-site-out.") as out_tmp:
            return _run_with_paths(
                db_path=db_path,
                output_dir=Path(out_tmp),
                scope=scope,
                seed_demo_data=seed_demo_data,
                output_is_temporary=True,
            )
    return _run_with_paths(
        db_path=db_path,
        output_dir=output_dir,
        scope=scope,
        seed_demo_data=seed_demo_data,
        output_is_temporary=False,
    )


def _run_with_paths(
    *,
    db_path: Path,
    output_dir: Path,
    scope: str,
    seed_demo_data: bool,
    output_is_temporary: bool,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        init_db(conn)
        if seed_demo_data:
            _seed_demo_data(conn, scope=scope)
    finally:
        conn.close()

    export_result = export_knowledge_site(db_path=db_path, output_dir=output_dir, scope=scope)
    checks = _verify_export(output_dir=Path(export_result["output_dir"]), scope=scope)
    failed = {name: check for name, check in checks.items() if check["status"] != "pass"}
    manifest = _read_json(Path(export_result["output_dir"]) / "data" / "manifest.json")
    return {
        "ok": not failed,
        "scope": scope,
        "db_path": str(db_path),
        "output_dir": str(export_result["output_dir"]),
        "output_is_temporary": output_is_temporary,
        "entrypoint": export_result["entrypoint"],
        "manifest_summary": {
            "read_only": manifest.get("read_only"),
            "wiki_card_count": manifest.get("wiki_card_count"),
            "graph_node_count": manifest.get("graph_node_count"),
            "graph_edge_count": manifest.get("graph_edge_count"),
            "boundary": manifest.get("boundary"),
        },
        "checks": checks,
        "failed_checks": sorted(failed),
        "boundary": "static_knowledge_site_export_check_only; no production deployment or live service claim",
        "next_step": "" if not failed else "Inspect generated static site files before sharing the LLM Wiki artifact.",
    }


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
            "决定：静态 LLM Wiki 导出只读取 active curated memory，app_secret=demo-secret 必须脱敏。",
            source_type="knowledge_site_gate",
            source_id="knowledge_site_gate_seed",
            created_by="knowledge_site_gate",
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
                "kgn_knowledge_site_gate_chat",
                "tenant:demo",
                "org:demo",
                "feishu_chat",
                "chat_knowledge_site_gate",
                "Knowledge Site Gate Chat",
                "team",
                "active",
                json.dumps({"note": "token=demo-secret"}, ensure_ascii=False),
                event_time,
                event_time,
                1,
            ),
        )


def _verify_export(*, output_dir: Path, scope: str) -> dict[str, dict[str, Any]]:
    paths = {
        "index": output_dir / "index.html",
        "manifest": output_dir / "data" / "manifest.json",
        "wiki": output_dir / "data" / "wiki.json",
        "graph": output_dir / "data" / "graph.json",
        "summary": output_dir / "data" / "summary.json",
        "markdown": output_dir / "wiki" / f"{_safe_slug(scope)}.md",
    }
    checks: dict[str, dict[str, Any]] = {
        "required_files": _check_required_files(paths),
    }
    manifest = _read_json(paths["manifest"]) if paths["manifest"].exists() else {}
    wiki = _read_json(paths["wiki"]) if paths["wiki"].exists() else {}
    graph = _read_json(paths["graph"]) if paths["graph"].exists() else {}
    index_text = paths["index"].read_text(encoding="utf-8") if paths["index"].exists() else ""
    markdown = paths["markdown"].read_text(encoding="utf-8") if paths["markdown"].exists() else ""
    combined = "\n".join(
        [
            index_text,
            markdown,
            json.dumps(manifest, ensure_ascii=False),
            json.dumps(wiki, ensure_ascii=False),
            json.dumps(graph, ensure_ascii=False),
        ]
    )
    checks["manifest"] = _check_manifest(manifest, scope=scope)
    checks["wiki"] = _check_wiki_payload(wiki)
    checks["graph"] = _check_graph_payload(graph)
    checks["index_ui"] = _check_index_ui(index_text)
    checks["markdown"] = _check_markdown(markdown, scope=scope)
    checks["redaction"] = _check_redaction(combined)
    return checks


def _check_required_files(paths: dict[str, Path]) -> dict[str, Any]:
    missing = [name for name, path in paths.items() if not path.exists()]
    return {
        "status": "pass" if not missing else "fail",
        "description": "Static site export writes index, JSON data files, and scope Markdown.",
        "missing": missing,
    }


def _check_manifest(manifest: dict[str, Any], *, scope: str) -> dict[str, Any]:
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    policy = manifest.get("generation_policy") if isinstance(manifest.get("generation_policy"), dict) else {}
    ok = (
        manifest.get("ok") is True
        and manifest.get("read_only") is True
        and manifest.get("scope") == scope
        and manifest.get("boundary") == STATIC_SITE_BOUNDARY
        and int(manifest.get("wiki_card_count") or 0) >= 1
        and int(manifest.get("graph_node_count") or 0) >= 1
        and files.get("index") == "index.html"
        and files.get("wiki") == "data/wiki.json"
        and files.get("graph") == "data/graph.json"
        and policy.get("raw_events_included") is False
        and policy.get("writes_feishu") is False
    )
    return {
        "status": "pass" if ok else "fail",
        "description": "Manifest preserves read-only staging boundary and expected file map.",
        "wiki_card_count": manifest.get("wiki_card_count"),
        "graph_node_count": manifest.get("graph_node_count"),
    }


def _check_wiki_payload(wiki: dict[str, Any]) -> dict[str, Any]:
    policy = wiki.get("generation_policy") if isinstance(wiki.get("generation_policy"), dict) else {}
    ok = (
        int(wiki.get("card_count") or 0) >= 1
        and len(wiki.get("cards") or []) >= 1
        and policy.get("source") == "active_curated_memory_only"
        and policy.get("raw_events_included") is False
    )
    return {
        "status": "pass" if ok else "fail",
        "description": "Wiki JSON contains active curated memory cards and excludes raw events.",
        "card_count": wiki.get("card_count"),
    }


def _check_graph_payload(graph: dict[str, Any]) -> dict[str, Any]:
    node_types = {node.get("node_type") for node in graph.get("nodes") or []}
    edge_types = {edge.get("edge_type") for edge in graph.get("edges") or []}
    ok = int(graph.get("workspace_node_count") or 0) >= 1 and "memory" in node_types and "grounded_by" in edge_types
    return {
        "status": "pass" if ok else "fail",
        "description": "Graph JSON includes compiled memory graph nodes and evidence edges.",
        "node_types": sorted(item for item in node_types if item),
        "edge_types": sorted(item for item in edge_types if item),
    }


def _check_index_ui(index_text: str) -> dict[str, Any]:
    required = (
        "Feishu Memory Copilot Knowledge Site",
        "Knowledge Graph",
        'id="graphDetail"',
        'id="relationshipFocus"',
        "data-node-id",
        "data-edge-id",
        "Relationship Focus",
        "Evidence paths",
        "window.COPILOT_KNOWLEDGE_SITE",
    )
    missing = [item for item in required if item not in index_text]
    return {
        "status": "pass" if not missing else "fail",
        "description": "index.html embeds searchable Wiki and graph detail UI.",
        "missing": missing,
    }


def _check_markdown(markdown: str, *, scope: str) -> dict[str, Any]:
    ok = f"# 项目记忆卡册：{scope}" in markdown and "不包含 raw events" in markdown
    return {
        "status": "pass" if ok else "fail",
        "description": "Scope Markdown export exists and states raw event exclusion.",
    }


def _check_redaction(combined: str) -> dict[str, Any]:
    leaked = [item for item in FORBIDDEN_SUBSTRINGS if item in combined]
    has_redaction = "[REDACTED]" in combined
    return {
        "status": "pass" if not leaked and has_redaction else "fail",
        "description": "Static site payload redacts seeded secret-like strings.",
        "leaked": leaked,
        "redaction_marker_present": has_redaction,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_slug(value: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()).strip("_")
    return slug or "scope"


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Static Knowledge Site Export Check")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"scope: {result['scope']}")
    print(f"output_dir: {result['output_dir']}")
    for name, check in result["checks"].items():
        print(f"- {name}: {check['status']} ({check['description']})")
    if result["failed_checks"]:
        print(f"failed_checks: {', '.join(result['failed_checks'])}")


if __name__ == "__main__":
    raise SystemExit(main())
