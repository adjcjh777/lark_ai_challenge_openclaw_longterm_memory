#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import AdminQueryService, AdminSsoConfig, create_admin_server
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

DEFAULT_SCOPE = "project:sso_gate"
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_VIEWER_EMAIL = "reader@example.com"
DEFAULT_ALLOWED_DOMAIN = "example.com"
BOUNDARY = "staging_reverse_proxy_sso_header_gate_only; not_real_enterprise_idp_or_feishu_sso_production_validation"


@dataclass(frozen=True)
class _HttpResult:
    status: int
    body: str
    headers: dict[str, str]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the Copilot Admin reverse-proxy SSO header gate on a loopback staging server. "
            "This does not validate a real enterprise IdP."
        )
    )
    parser.add_argument("--db-path", default=None, help="Optional SQLite DB path. Defaults to a temporary seeded DB.")
    parser.add_argument(
        "--seed-demo-data",
        action="store_true",
        help="Seed one evidence-backed active memory before running checks. Defaults on when --db-path is omitted.",
    )
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help=f"Wiki export scope. Defaults to {DEFAULT_SCOPE}.")
    parser.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL, help="SSO admin email identity.")
    parser.add_argument("--viewer-email", default=DEFAULT_VIEWER_EMAIL, help="SSO viewer email identity.")
    parser.add_argument("--allowed-domain", default=DEFAULT_ALLOWED_DOMAIN, help="Allowed viewer email domain.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    seed_demo_data = args.seed_demo_data or args.db_path is None
    result = run_sso_gate_check(
        db_path=Path(args.db_path).expanduser() if args.db_path else None,
        seed_demo_data=seed_demo_data,
        scope=args.scope,
        admin_email=args.admin_email,
        viewer_email=args.viewer_email,
        allowed_domain=args.allowed_domain,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


def run_sso_gate_check(
    *,
    db_path: Path | None = None,
    seed_demo_data: bool = False,
    scope: str = DEFAULT_SCOPE,
    admin_email: str = DEFAULT_ADMIN_EMAIL,
    viewer_email: str = DEFAULT_VIEWER_EMAIL,
    allowed_domain: str = DEFAULT_ALLOWED_DOMAIN,
) -> dict[str, Any]:
    if db_path is None:
        with tempfile.TemporaryDirectory(prefix="copilot-admin-sso-gate.") as tmpdir:
            return _run_with_db(
                db_path=Path(tmpdir) / "memory.sqlite",
                seed_demo_data=True,
                scope=scope,
                admin_email=admin_email,
                viewer_email=viewer_email,
                allowed_domain=allowed_domain,
            )
    return _run_with_db(
        db_path=db_path,
        seed_demo_data=seed_demo_data,
        scope=scope,
        admin_email=admin_email,
        viewer_email=viewer_email,
        allowed_domain=allowed_domain,
    )


def _run_with_db(
    *,
    db_path: Path,
    seed_demo_data: bool,
    scope: str,
    admin_email: str,
    viewer_email: str,
    allowed_domain: str,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        init_db(conn)
        if seed_demo_data:
            _seed_demo_memory(conn, scope=scope)
        wiki = AdminQueryService(conn).wiki_overview(scope=scope, limit=5)
        preflight = {
            "scope": scope,
            "wiki_card_count": int(wiki.get("card_count") or 0),
            "seed_demo_data": seed_demo_data,
        }
    finally:
        conn.close()

    sso_config = AdminSsoConfig(
        enabled=True,
        admin_users=frozenset({admin_email.lower()}),
        viewer_users=frozenset({viewer_email.lower()}),
        allowed_domains=frozenset({allowed_domain.lower()}),
    )
    server = create_admin_server("127.0.0.1", 0, db_path, sso_config=sso_config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks: dict[str, dict[str, Any]] = {
        "wiki_card_preflight": {
            "status": "pass" if int(preflight["wiki_card_count"]) > 0 else "fail",
            "description": "Target scope has at least one evidence-backed active Wiki card.",
            "wiki_card_count": int(preflight["wiki_card_count"]),
        }
    }
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        checks["no_header_denied"] = _expect_status(
            _request(base_url, "/api/summary"),
            expected_status=401,
            description="Missing SSO headers are rejected for /api/summary.",
        )
        checks["viewer_summary_allowed"] = _expect_json_ok(
            _request(base_url, "/api/summary", email=viewer_email),
            description="Viewer identity from the allowed domain can read summary.",
        )
        checks["viewer_export_forbidden"] = _expect_status(
            _request(base_url, f"/api/wiki/export?scope={_url_scope(scope)}", email=viewer_email),
            expected_status=403,
            description="Viewer identity cannot export Wiki markdown.",
        )
        admin_export = _request(base_url, f"/api/wiki/export?scope={_url_scope(scope)}", email=admin_email)
        checks["admin_export_allowed"] = _expect_markdown_export(
            admin_export,
            scope=scope,
            description="Admin SSO identity can export evidence-backed Wiki markdown.",
        )
        checks["metrics_requires_authenticated_identity"] = _expect_status(
            _request(base_url, "/metrics"),
            expected_status=401,
            description="Prometheus metrics reject requests without SSO identity.",
        )
        checks["viewer_metrics_allowed"] = _expect_body_contains(
            _request(base_url, "/metrics", email=viewer_email),
            expected_status=200,
            needle="copilot_admin_wiki_card_count",
            description="Authenticated viewer can scrape staging metrics.",
        )
        checks["health_reports_sso_policy"] = _expect_health_policy(
            _request(base_url, "/api/health", email=admin_email),
            description="Health output reports configured SSO header policy.",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    failed = {name: check for name, check in checks.items() if check["status"] != "pass"}
    return {
        "ok": not failed,
        "boundary": BOUNDARY,
        "db_path": str(db_path),
        "server": {
            "host": "127.0.0.1",
            "bind_scope": "loopback_only",
        },
        "sso": {
            "enabled": True,
            "admin_email": admin_email,
            "viewer_email": viewer_email,
            "allowed_domain": allowed_domain,
            "user_header": sso_config.user_header,
            "email_header": sso_config.email_header,
        },
        "preflight": preflight,
        "checks": checks,
        "failed_checks": sorted(failed),
        "next_step": ""
        if not failed
        else "Keep the admin backend behind a loopback reverse proxy and inspect failed SSO gate checks.",
    }


def _seed_demo_memory(conn: sqlite3.Connection, *, scope: str) -> None:
    existing = AdminQueryService(conn).wiki_overview(scope=scope, limit=1)
    if int(existing.get("card_count") or 0) > 0:
        return
    repo = MemoryRepository(conn)
    repo.remember(
        scope,
        "决定：Copilot Admin SSO header gate 只能在 loopback reverse proxy 后验证。",
        source_type="sso_gate_verifier",
        source_id="sso_gate_verifier_seed",
        created_by="sso_gate_verifier",
    )


def _request(base_url: str, path: str, *, email: str | None = None) -> _HttpResult:
    headers = {"X-Forwarded-Email": email} if email else {}
    try:
        with urlopen(Request(f"{base_url}{path}", headers=headers), timeout=5) as response:
            return _HttpResult(
                status=response.status,
                body=response.read().decode("utf-8"),
                headers=dict(response.headers.items()),
            )
    except HTTPError as exc:
        return _HttpResult(
            status=exc.code,
            body=exc.read().decode("utf-8"),
            headers=dict(exc.headers.items()),
        )


def _expect_status(result: _HttpResult, *, expected_status: int, description: str) -> dict[str, Any]:
    return {
        "status": "pass" if result.status == expected_status else "fail",
        "description": description,
        "expected_http_status": expected_status,
        "actual_http_status": result.status,
    }


def _expect_json_ok(result: _HttpResult, *, description: str) -> dict[str, Any]:
    payload = _json_payload(result.body)
    ok = result.status == 200 and payload.get("ok") is True
    return {
        "status": "pass" if ok else "fail",
        "description": description,
        "expected_http_status": 200,
        "actual_http_status": result.status,
        "ok": payload.get("ok"),
    }


def _expect_markdown_export(result: _HttpResult, *, scope: str, description: str) -> dict[str, Any]:
    has_scope = scope in result.body or f"项目记忆卡册：{scope}" in result.body
    no_raw_events = "raw events" in result.body
    ok = result.status == 200 and has_scope and no_raw_events
    return {
        "status": "pass" if ok else "fail",
        "description": description,
        "expected_http_status": 200,
        "actual_http_status": result.status,
        "contains_scope": has_scope,
        "states_raw_events_excluded": no_raw_events,
    }


def _expect_body_contains(
    result: _HttpResult,
    *,
    expected_status: int,
    needle: str,
    description: str,
) -> dict[str, Any]:
    contains = needle in result.body
    return {
        "status": "pass" if result.status == expected_status and contains else "fail",
        "description": description,
        "expected_http_status": expected_status,
        "actual_http_status": result.status,
        "contains": needle if contains else None,
    }


def _expect_health_policy(result: _HttpResult, *, description: str) -> dict[str, Any]:
    payload = _json_payload(result.body)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    policy = data.get("access_policy") if isinstance(data.get("access_policy"), dict) else {}
    ok = (
        result.status == 200
        and payload.get("ok") is True
        and data.get("auth") == "enabled"
        and policy.get("sso_enabled") is True
        and policy.get("sso_admin_users_configured") is True
        and policy.get("sso_allowed_domains_configured") is True
    )
    return {
        "status": "pass" if ok else "fail",
        "description": description,
        "expected_http_status": 200,
        "actual_http_status": result.status,
        "sso_enabled": policy.get("sso_enabled"),
        "sso_admin_users_configured": policy.get("sso_admin_users_configured"),
        "sso_allowed_domains_configured": policy.get("sso_allowed_domains_configured"),
    }


def _json_payload(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _url_scope(scope: str) -> str:
    return scope.replace(":", "%3A")


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Admin SSO Header Gate")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"boundary: {result['boundary']}")
    print(f"db_path: {result['db_path']}")
    for name, check in result["checks"].items():
        print(f"- {name}: {check['status']} ({check['description']})")
    if result["failed_checks"]:
        print(f"failed_checks: {', '.join(result['failed_checks'])}")


if __name__ == "__main__":
    raise SystemExit(main())
