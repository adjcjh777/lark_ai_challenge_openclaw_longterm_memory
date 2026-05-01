#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import AdminQueryService
from memory_engine.db import connect, db_path_from_env, init_db
from memory_engine.repository import MemoryRepository, now_ms
from scripts.check_copilot_admin_deploy_bundle import run_deploy_bundle_check
from scripts.check_copilot_admin_production_evidence import (
    DEFAULT_MANIFEST_PATH as DEFAULT_PRODUCTION_EVIDENCE_MANIFEST_PATH,
)
from scripts.check_copilot_admin_production_evidence import run_production_evidence_check
from scripts.check_copilot_audit_readonly_gate import run_audit_readonly_gate
from scripts.check_llm_wiki_enterprise_site_completion import run_completion_audit

SCHEMA_VERSION = "copilot_admin_launch_evidence/v1"
BOUNDARY = (
    "local/staging launch evidence bundle only; not production DB, real enterprise IdP, TLS, "
    "production monitoring, or productized long-running live proof"
)
FORBIDDEN_SUBSTRINGS = ("app_secret=", "access_token=", "refresh_token=", "demo-secret", "raw-admin-token")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a local/staging Copilot Admin LLM Wiki / Graph launch evidence bundle."
    )
    parser.add_argument("--db-path", default=str(db_path_from_env()), help="SQLite database path.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write JSON evidence files. Defaults to a temporary directory.",
    )
    parser.add_argument("--scope", default="project:feishu_ai_challenge", help="Wiki scope to export.")
    parser.add_argument("--tenant-id", default="tenant:demo", help="Tenant filter for audit evidence.")
    parser.add_argument("--organization-id", default="org:demo", help="Organization filter for audit evidence.")
    parser.add_argument("--audit-min-events", type=int, default=1, help="Minimum tenant/org audit rows.")
    parser.add_argument(
        "--production-evidence-manifest",
        default=str(DEFAULT_PRODUCTION_EVIDENCE_MANIFEST_PATH),
        help="Production evidence manifest to include.",
    )
    parser.add_argument(
        "--seed-demo-data",
        action="store_true",
        help="Seed demo data before exporting. Intended for tests and temporary bundles only.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON manifest.")
    args = parser.parse_args()

    if args.output_dir:
        manifest = export_launch_evidence_bundle(
            db_path=Path(args.db_path).expanduser(),
            output_dir=Path(args.output_dir).expanduser(),
            scope=args.scope,
            tenant_id=args.tenant_id,
            organization_id=args.organization_id,
            audit_min_events=args.audit_min_events,
            production_evidence_manifest=Path(args.production_evidence_manifest).expanduser(),
            seed_demo_data=args.seed_demo_data,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="copilot-launch-evidence.") as tmp:
            manifest = export_launch_evidence_bundle(
                db_path=Path(args.db_path).expanduser(),
                output_dir=Path(tmp),
                scope=args.scope,
                tenant_id=args.tenant_id,
                organization_id=args.organization_id,
                audit_min_events=args.audit_min_events,
                production_evidence_manifest=Path(args.production_evidence_manifest).expanduser(),
                seed_demo_data=args.seed_demo_data,
            )
            # Keep the manifest useful after the temporary directory is removed.
            manifest["temporary_output_dir"] = True
            manifest["files"] = {name: Path(path).name for name, path in manifest["files"].items()}

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_manifest(manifest))
    return 0 if manifest["ok"] else 1


def export_launch_evidence_bundle(
    *,
    db_path: Path,
    output_dir: Path,
    scope: str,
    tenant_id: str,
    organization_id: str,
    audit_min_events: int,
    production_evidence_manifest: Path = DEFAULT_PRODUCTION_EVIDENCE_MANIFEST_PATH,
    seed_demo_data: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        init_db(conn)
        if seed_demo_data:
            _seed_demo_data(conn, scope=scope, tenant_id=tenant_id, organization_id=organization_id)
        service = AdminQueryService(conn)
        reports = {
            "summary": service.summary(),
            "wiki": service.wiki_overview(scope=scope, tenant_id=tenant_id, organization_id=organization_id, limit=50),
            "graph": service.graph_workspace(tenant_id=tenant_id, organization_id=organization_id, limit=200),
            "graph_quality": service.graph_quality(tenant_id=tenant_id, organization_id=organization_id),
            "audit": service.list_audit(tenant_id=tenant_id, organization_id=organization_id, limit=50),
            "launch_readiness": service.launch_readiness(),
        }
    finally:
        conn.close()

    reports["audit_readonly_gate"] = run_audit_readonly_gate(
        db_path=db_path,
        seed_demo_data=False,
        tenant_id=tenant_id,
        organization_id=organization_id,
        min_events=audit_min_events,
    )
    reports["deploy_bundle"] = run_deploy_bundle_check()
    reports["production_evidence"] = run_production_evidence_check(production_evidence_manifest)
    reports["completion_audit"] = run_completion_audit()

    files: dict[str, str] = {}
    for name, payload in reports.items():
        files[name] = str(_write_json(output_dir / f"{name.replace('_', '-')}.json", payload))

    redaction = _redaction_check(output_dir)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "ok": _reports_ok(reports) and redaction["status"] == "pass",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "db_path": str(db_path),
        "output_dir": str(output_dir),
        "scope": scope,
        "filters": {"tenant_id": tenant_id, "organization_id": organization_id},
        "files": files,
        "staging_ok": bool(reports["completion_audit"].get("staging_ok")),
        "goal_complete": bool(reports["completion_audit"].get("goal_complete")),
        "production_blocked": bool(reports["deploy_bundle"].get("production_blocked"))
        or bool(reports["completion_audit"].get("production_blockers")),
        "production_blockers": reports["completion_audit"].get("production_blockers") or [],
        "redaction": redaction,
        "boundary": BOUNDARY,
        "next_step": (
            "Replace example production evidence with real DB, IdP, TLS, monitoring, and long-run proof before "
            "claiming production launch."
        ),
    }
    manifest_path = _write_json(output_dir / "manifest.json", manifest)
    manifest["files"]["manifest"] = str(manifest_path)
    return manifest


def _reports_ok(reports: dict[str, Any]) -> bool:
    return (
        bool(reports["graph_quality"].get("ok"))
        and bool(reports["audit_readonly_gate"].get("ok"))
        and bool(reports["deploy_bundle"].get("staging_bundle_ok"))
        and bool(reports["completion_audit"].get("staging_ok"))
        and not bool(reports["completion_audit"].get("goal_complete"))
    )


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _redaction_check(output_dir: Path) -> dict[str, Any]:
    leaked: dict[str, list[str]] = {}
    for path in sorted(output_dir.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        found = [token for token in FORBIDDEN_SUBSTRINGS if token in text]
        if found:
            leaked[path.name] = found
    return {
        "status": "pass" if not leaked else "fail",
        "forbidden_substrings_found": leaked,
    }


def _seed_demo_data(conn: sqlite3.Connection, *, scope: str, tenant_id: str, organization_id: str) -> None:
    repo = MemoryRepository(conn)
    memory = repo.remember(
        scope,
        "决定：Launch evidence bundle 必须只读导出 LLM Wiki、Graph、Audit 和 production blocker 证据。",
        source_type="launch_evidence_gate",
        source_id="launch_evidence_source",
        created_by="launch_evidence_gate",
    )
    now = now_ms()
    with conn:
        conn.execute(
            "UPDATE memories SET tenant_id = ?, organization_id = ? WHERE id = ?",
            (tenant_id, organization_id, memory["memory_id"]),
        )
        conn.execute(
            "UPDATE memory_versions SET tenant_id = ?, organization_id = ? WHERE memory_id = ?",
            (tenant_id, organization_id, memory["memory_id"]),
        )
        conn.execute(
            "UPDATE memory_evidence SET tenant_id = ?, organization_id = ? WHERE memory_id = ?",
            (tenant_id, organization_id, memory["memory_id"]),
        )
        repo.record_audit_event(
            event_type="candidate_created",
            action="memory.create_candidate",
            actor_id="u_launch_evidence",
            actor_roles=["reviewer"],
            tenant_id=tenant_id,
            organization_id=organization_id,
            scope=scope,
            permission_decision="allow",
            reason_code="scope_access_granted",
            request_id="req_launch_evidence",
            trace_id="trace_launch_evidence",
            source_context={"access_token": "demo-secret"},
            created_at=now,
        )


def format_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin Launch Evidence Bundle",
        f"ok: {str(manifest['ok']).lower()}",
        f"output_dir: {manifest.get('output_dir')}",
        f"staging_ok: {str(manifest.get('staging_ok')).lower()}",
        f"goal_complete: {str(manifest.get('goal_complete')).lower()}",
        f"production_blocked: {str(manifest.get('production_blocked')).lower()}",
        f"boundary: {manifest.get('boundary')}",
        "",
        "files:",
    ]
    for name, path in sorted((manifest.get("files") or {}).items()):
        lines.append(f"- {name}: {path}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
