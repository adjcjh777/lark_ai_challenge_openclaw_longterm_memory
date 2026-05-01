#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import AdminQueryService, create_admin_server
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository, now_ms
from scripts.query_audit_events import count_events, format_csv, query_events, summary_multi

DEFAULT_SCOPE = "project:audit_readonly_gate"
FORBIDDEN_SUBSTRINGS = ("demo-secret", "access_token=demo", "refresh-token-demo", "raw-admin-token")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the local/staging Copilot audit read-only gate for CLI and Admin API surfaces."
    )
    parser.add_argument("--db-path", default=None, help="SQLite database path. Defaults to a temporary seeded DB.")
    parser.add_argument("--seed-demo-data", action="store_true", help="Seed audit rows before checking.")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help=f"Seed/check scope. Defaults to {DEFAULT_SCOPE}.")
    parser.add_argument("--tenant-id", default="tenant:demo", help="Tenant expected in the read-only audit view.")
    parser.add_argument("--organization-id", default="org:demo", help="Organization expected in the audit view.")
    parser.add_argument("--min-events", type=int, default=3, help="Minimum matching audit events.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    report = run_audit_readonly_gate(
        db_path=Path(args.db_path).expanduser() if args.db_path else None,
        seed_demo_data=args.seed_demo_data or args.db_path is None,
        scope=args.scope,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        min_events=args.min_events,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_audit_readonly_gate(
    *,
    db_path: Path | None = None,
    seed_demo_data: bool = False,
    scope: str = DEFAULT_SCOPE,
    tenant_id: str = "tenant:demo",
    organization_id: str = "org:demo",
    min_events: int = 3,
) -> dict[str, Any]:
    if db_path is None:
        with tempfile.TemporaryDirectory(prefix="copilot-audit-readonly.") as tmp:
            return _run_with_db(
                db_path=Path(tmp) / "memory.sqlite",
                seed_demo_data=True,
                scope=scope,
                tenant_id=tenant_id,
                organization_id=organization_id,
                min_events=min_events,
                temporary_db=True,
            )
    return _run_with_db(
        db_path=db_path,
        seed_demo_data=seed_demo_data,
        scope=scope,
        tenant_id=tenant_id,
        organization_id=organization_id,
        min_events=min_events,
        temporary_db=False,
    )


def _run_with_db(
    *,
    db_path: Path,
    seed_demo_data: bool,
    scope: str,
    tenant_id: str,
    organization_id: str,
    min_events: int,
    temporary_db: bool,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        init_db(conn)
        if seed_demo_data:
            _seed_demo_data(conn, scope=scope, tenant_id=tenant_id, organization_id=organization_id)
        checks = _run_checks(
            conn, db_path=db_path, tenant_id=tenant_id, organization_id=organization_id, min_events=min_events
        )
    finally:
        conn.close()

    failed = {name: check for name, check in checks.items() if check["status"] != "pass"}
    return {
        "ok": not failed,
        "db_path": str(db_path),
        "temporary_db": temporary_db,
        "filters": {"tenant_id": tenant_id, "organization_id": organization_id},
        "checks": checks,
        "failed_checks": sorted(failed),
        "boundary": "local/staging audit read-only gate only; no production IdP, DB, monitoring, or long-running live claim",
        "next_step": ""
        if not failed
        else "Inspect audit filters, redaction, Admin API method policy, and seeded audit evidence.",
    }


def _run_checks(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    tenant_id: str,
    organization_id: str,
    min_events: int,
) -> dict[str, dict[str, Any]]:
    matching_events = query_events(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        limit=50,
    )
    other_tenant_events = query_events(conn, tenant_id="tenant:other", limit=50)
    summary = summary_multi(conn)
    csv_output = format_csv(matching_events)
    serialized = json.dumps({"events": matching_events, "summary": summary, "csv": csv_output}, ensure_ascii=False)
    leaked = sorted(token for token in FORBIDDEN_SUBSTRINGS if token in serialized)
    before_count = count_events(conn)
    admin_api = _check_admin_api(db_path, tenant_id=tenant_id, organization_id=organization_id)
    after_count = count_events(conn)
    service_audit = AdminQueryService(conn).list_audit(
        tenant_id=tenant_id,
        organization_id=organization_id,
        limit=50,
    )
    return {
        "audit_rows_present": _check(
            len(matching_events) >= min_events,
            f"{len(matching_events)} matching tenant/org audit events",
            {"min_events": min_events},
        ),
        "tenant_org_filter": _check(
            all(
                event.get("tenant_id") == tenant_id and event.get("organization_id") == organization_id
                for event in matching_events
            )
            and all(event.get("tenant_id") == "tenant:other" for event in other_tenant_events),
            "CLI audit query respects tenant_id and organization_id filters",
            {"other_tenant_event_count": len(other_tenant_events)},
        ),
        "source_context_redaction": _check(
            not leaked,
            "audit source_context output has no known secret-like values",
            {"forbidden_substrings_found": leaked},
        ),
        "csv_export": _check(
            "audit_id,event_type" in csv_output and "source_context" in csv_output,
            "CSV export includes audit headers and flattened source_context",
            {"csv_bytes": len(csv_output.encode("utf-8"))},
        ),
        "summary": _check(
            int(summary.get("total") or 0) >= min_events,
            f"{int(summary.get('total') or 0)} audit events summarized",
            {"sections": sorted(key for key in summary if key.startswith("by_"))},
        ),
        "admin_api_readonly": _check(
            bool(admin_api.get("ok")) and before_count == after_count,
            str(admin_api.get("message") or "Admin API audit read-only gate checked"),
            {"before_count": before_count, "after_count": after_count, **admin_api},
        ),
        "service_readonly_view": _check(
            int(service_audit.get("total") or 0) >= min_events
            and all(item.get("tenant_id") == tenant_id for item in service_audit.get("items") or []),
            "AdminQueryService audit view returns tenant-scoped read-only items",
            {"service_total": service_audit.get("total")},
        ),
    }


def _check_admin_api(db_path: Path, *, tenant_id: str, organization_id: str) -> dict[str, Any]:
    server = create_admin_server("127.0.0.1", 0, db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        payload = _http_json(f"{base_url}/api/audit?tenant_id={tenant_id}&organization_id={organization_id}&limit=50")
        post_denied = _http_post_denied(f"{base_url}/api/audit")
        items = payload.get("data", {}).get("items") or []
        serialized = json.dumps(payload, ensure_ascii=False)
        leaked = sorted(token for token in FORBIDDEN_SUBSTRINGS if token in serialized)
        return {
            "ok": bool(payload.get("ok")) and bool(items) and post_denied and not leaked,
            "message": "Admin /api/audit is filterable, redacted, and rejects POST writes",
            "api_item_count": len(items),
            "post_denied": post_denied,
            "forbidden_substrings_found": leaked,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _http_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_denied(url: str) -> bool:
    request = Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        urlopen(request, timeout=5)
    except HTTPError as exc:
        return exc.code == 405
    return False


def _seed_demo_data(conn: sqlite3.Connection, *, scope: str, tenant_id: str, organization_id: str) -> None:
    repo = MemoryRepository(conn)
    now = now_ms()
    rows = [
        {
            "event_type": "candidate_created",
            "action": "memory.create_candidate",
            "permission_decision": "allow",
            "reason_code": "scope_access_granted",
            "actor_id": "u_reviewer",
            "source_context": {"chat_id": "chat_demo", "access_token": "demo-secret"},
        },
        {
            "event_type": "permission_denied",
            "action": "memory.search",
            "permission_decision": "deny",
            "reason_code": "tenant_mismatch",
            "actor_id": "u_denied",
            "source_context": {"note": "access_token=demo", "nested": {"refresh_token": "refresh-token-demo"}},
        },
        {
            "event_type": "ingestion_failed",
            "action": "memory.create_candidate",
            "permission_decision": "withhold",
            "reason_code": "feishu_fetch_failed",
            "actor_id": "u_ingest",
            "source_context": {"authorization": "raw-admin-token"},
        },
    ]
    with conn:
        for index, row in enumerate(rows):
            repo.record_audit_event(
                event_type=str(row["event_type"]),
                action=str(row["action"]),
                actor_id=str(row["actor_id"]),
                actor_roles=["reviewer"] if index == 0 else ["member"],
                tenant_id=tenant_id,
                organization_id=organization_id,
                scope=scope,
                permission_decision=str(row["permission_decision"]),
                reason_code=str(row["reason_code"]),
                request_id=f"req_audit_gate_{index}",
                trace_id=f"trace_audit_gate_{index}",
                visible_fields=["audit_id", "event_type", "permission_decision"],
                redacted_fields=["source_context.access_token", "source_context.authorization"],
                source_context=row["source_context"],
                created_at=now + index,
            )
        repo.record_audit_event(
            event_type="candidate_created",
            action="memory.create_candidate",
            actor_id="u_other",
            tenant_id="tenant:other",
            organization_id="org:other",
            scope=scope,
            permission_decision="allow",
            reason_code="scope_access_granted",
            request_id="req_audit_gate_other",
            trace_id="trace_audit_gate_other",
            created_at=now + 10,
        )


def _check(ok: bool, message: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "message": message, **extra}


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Audit Read-Only Gate",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(f"- {name}: {check.get('status')} {check.get('message', '')}".rstrip())
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
