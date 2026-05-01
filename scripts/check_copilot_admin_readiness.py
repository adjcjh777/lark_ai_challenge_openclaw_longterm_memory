#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import (
    ADMIN_TOKEN_ENV_NAMES,
    ADMIN_VIEWER_TOKEN_ENV_NAMES,
    AdminQueryService,
    DEFAULT_ADMIN_HOST,
)
from memory_engine.db import db_path_from_env

REQUIRED_TABLES = {
    "memories",
    "memory_versions",
    "memory_evidence",
    "memory_audit_events",
    "knowledge_graph_nodes",
    "knowledge_graph_edges",
}
STATUS_ORDER = ("pass", "fail", "warning")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local admin LLM Wiki / graph readiness without starting a production service."
    )
    parser.add_argument("--db-path", default=str(db_path_from_env()), help="SQLite database path.")
    parser.add_argument("--host", default=DEFAULT_ADMIN_HOST, help="Planned admin bind host.")
    parser.add_argument("--admin-token", default=None, help="Planned admin bearer token.")
    parser.add_argument("--viewer-token", default=None, help="Planned read-only admin viewer bearer token.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on missing admin auth, empty Wiki cards, or missing compiled graph nodes.",
    )
    parser.add_argument(
        "--min-wiki-cards",
        type=int,
        default=None,
        help="Minimum active evidence-backed Wiki cards required. Defaults to 1 in --strict mode, else 0.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    report = run_admin_readiness(
        db_path=Path(args.db_path),
        host=args.host,
        admin_token=args.admin_token or _admin_token_from_env(),
        viewer_token=args.viewer_token or _admin_viewer_token_from_env(),
        strict=args.strict,
        min_wiki_cards=args.min_wiki_cards,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
        print("")
        print("JSON: python3 scripts/check_copilot_admin_readiness.py --json")
    return 0 if report["ok"] else 1


def run_admin_readiness(
    *,
    db_path: Path,
    host: str,
    admin_token: str | None,
    viewer_token: str | None = None,
    strict: bool = False,
    min_wiki_cards: int | None = None,
) -> dict[str, Any]:
    required_wiki_cards = 1 if strict and min_wiki_cards is None else int(min_wiki_cards or 0)
    checks: dict[str, dict[str, Any]] = {
        "remote_bind_auth": _remote_bind_auth_check(
            host=host,
            admin_token=admin_token,
            viewer_token=viewer_token,
            require_auth=strict,
        ),
        "access_policy": _access_policy_check(
            admin_token=admin_token,
            viewer_token=viewer_token,
            require_export_admin=strict or required_wiki_cards > 0,
        ),
    }
    if not db_path.exists():
        checks["database"] = {
            "status": "fail",
            "path": str(db_path),
            "next_step": "Run `python3 -m memory_engine init-db` or pass --db-path.",
        }
        return _report(checks)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            service = AdminQueryService(conn)
            checks["database"] = {"status": "pass", "path": str(db_path)}
            checks["storage_schema"] = _storage_schema_check(conn)
            checks["wiki"] = _wiki_check(service, min_cards=required_wiki_cards)
            checks["wiki_export"] = _wiki_export_check(service, require_export=strict or required_wiki_cards > 0)
            checks["graph"] = _graph_check(service, require_compiled_memory=strict)
            checks["read_only_api"] = {
                "status": "pass",
                "supported_methods": ["GET", "HEAD"],
                "blocked_methods": ["POST", "PUT", "PATCH", "DELETE"],
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        checks["database"] = {"status": "fail", "path": str(db_path), "error": str(exc)}
    return _report(checks)


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin LLM Wiki / Graph Readiness",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(f"- {name}: {check.get('status')}{_summary(check)}")
    lines.append("")
    lines.append(f"status_counts: {json.dumps(report['status_counts'], ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines)


def _storage_schema_check(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()
    present = {str(row["name"]) for row in rows}
    missing = sorted(REQUIRED_TABLES - present)
    return {
        "status": "pass" if not missing else "fail",
        "missing_tables": missing,
        "required_tables": sorted(REQUIRED_TABLES),
    }


def _wiki_check(service: AdminQueryService, *, min_cards: int) -> dict[str, Any]:
    wiki = service.wiki_overview(limit=20)
    policy = wiki.get("generation_policy") or {}
    policy_ok = (
        policy.get("source") == "active_curated_memory_only"
        and policy.get("raw_events_included") is False
        and policy.get("requires_evidence") is True
        and policy.get("writes_feishu") is False
    )
    card_count = int(wiki.get("card_count") or 0)
    if not policy_ok:
        status = "fail"
    elif card_count < min_cards:
        status = "fail"
    elif card_count == 0:
        status = "warning"
    else:
        status = "pass"
    return {
        "status": status,
        "card_count": card_count,
        "min_cards": min_cards,
        "generation_policy": policy,
        "next_step": ""
        if card_count >= max(1, min_cards)
        else f"Confirm at least {max(1, min_cards)} active memories with evidence before launch.",
    }


def _wiki_export_check(service: AdminQueryService, *, require_export: bool) -> dict[str, Any]:
    wiki = service.wiki_overview(limit=20)
    scopes = wiki.get("scopes") or []
    if not scopes:
        return {
            "status": "fail" if require_export else "warning",
            "scope": None,
            "next_step": "Confirm active memories with evidence before exporting a Wiki page.",
        }
    scope = str(scopes[0]["scope"])
    markdown = service.wiki_export_markdown(scope=scope)
    has_expected_shape = (
        markdown.startswith(f"# 项目记忆卡册：{scope}")
        and "active curated memory" in markdown
        and "不包含 raw events" in markdown
    )
    return {
        "status": "pass" if has_expected_shape else "fail",
        "scope": scope,
        "markdown_bytes": len(markdown.encode("utf-8")),
        "next_step": "" if has_expected_shape else "Inspect /api/wiki/export output before sharing the admin site.",
    }


def _graph_check(service: AdminQueryService, *, require_compiled_memory: bool) -> dict[str, Any]:
    graph = service.graph_workspace(limit=80)
    workspace_nodes = int(graph.get("workspace_node_count") or 0)
    workspace_edges = int(graph.get("workspace_edge_count") or 0)
    has_compiled_memory = any(node.get("node_type") == "memory" for node in graph.get("nodes") or [])
    if require_compiled_memory and not has_compiled_memory:
        status = "fail"
    elif workspace_nodes == 0:
        status = "warning"
    elif has_compiled_memory:
        status = "pass"
    else:
        status = "warning"
    return {
        "status": status,
        "storage_node_total": graph.get("node_total"),
        "storage_edge_total": graph.get("edge_total"),
        "workspace_node_count": workspace_nodes,
        "workspace_edge_count": workspace_edges,
        "compiled_memory_nodes": has_compiled_memory,
        "require_compiled_memory": require_compiled_memory,
        "next_step": "" if has_compiled_memory else "Confirm active memories with evidence or ingest graph context.",
    }


def _remote_bind_auth_check(
    *,
    host: str,
    admin_token: str | None,
    viewer_token: str | None,
    require_auth: bool,
) -> dict[str, Any]:
    remote_bind = host not in {"127.0.0.1", "localhost", "::1"}
    if (remote_bind or require_auth) and not (admin_token or viewer_token):
        return {
            "status": "fail",
            "host": host,
            "auth": "missing",
            "next_step": "Set an admin or viewer token before launch.",
        }
    return {
        "status": "pass" if admin_token or viewer_token else "warning",
        "host": host,
        "auth": "enabled" if admin_token or viewer_token else "disabled_local_only",
        "next_step": "" if admin_token or viewer_token else "Set an access token before any shared/staging deployment.",
    }


def _access_policy_check(
    *,
    admin_token: str | None,
    viewer_token: str | None,
    require_export_admin: bool,
) -> dict[str, Any]:
    if admin_token and viewer_token and admin_token == viewer_token:
        return {
            "status": "fail",
            "admin_token_configured": True,
            "viewer_token_configured": True,
            "viewer_token_can_export": True,
            "next_step": "Use distinct admin and viewer tokens before launch.",
        }
    if require_export_admin and not admin_token:
        return {
            "status": "fail",
            "admin_token_configured": False,
            "viewer_token_configured": bool(viewer_token),
            "viewer_token_can_export": False,
            "next_step": "Set FEISHU_MEMORY_COPILOT_ADMIN_TOKEN for Wiki export.",
        }
    status = "pass" if admin_token else "warning"
    return {
        "status": status,
        "admin_token_configured": bool(admin_token),
        "viewer_token_configured": bool(viewer_token),
        "viewer_token_can_export": False,
        "next_step": "" if admin_token else "Viewer-only mode can browse but cannot export Wiki markdown.",
    }


def _report(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in STATUS_ORDER}
    for check in checks.values():
        status = str(check.get("status") or "fail")
        counts[status if status in counts else "fail"] += 1
    return {
        "ok": counts["fail"] == 0,
        "boundary": "admin readiness only; no production deployment or productized live claim.",
        "checks": checks,
        "status_counts": counts,
    }


def _admin_token_from_env() -> str | None:
    for name in ADMIN_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _admin_viewer_token_from_env() -> str | None:
    for name in ADMIN_VIEWER_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _summary(check: dict[str, Any]) -> str:
    bits = []
    for key in ("card_count", "workspace_node_count", "workspace_edge_count", "auth", "path"):
        if key in check:
            bits.append(f"{key}={check[key]}")
    return " " + " ".join(bits) if bits else ""


if __name__ == "__main__":
    raise SystemExit(main())
