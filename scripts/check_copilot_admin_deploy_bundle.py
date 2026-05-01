#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = (
    "staging_deploy_bundle_static_check_only; not_production_domain_tls_idp_monitoring_or_long_running_live_validation"
)


@dataclass(frozen=True)
class BundleCheck:
    name: str
    path: str
    description: str
    required_patterns: tuple[str, ...]
    forbidden_patterns: tuple[str, ...] = ()


CHECKS = (
    BundleCheck(
        name="nginx_tls_reverse_proxy",
        path="deploy/copilot-admin.nginx.example",
        description="Nginx template terminates TLS, redirects HTTP, and proxies only to loopback admin backend.",
        required_patterns=(
            "listen 80;",
            "return 301 https://$host$request_uri;",
            "listen 443 ssl http2;",
            "ssl_certificate",
            "ssl_certificate_key",
            "ssl_protocols TLSv1.2 TLSv1.3",
            "proxy_pass http://127.0.0.1:8765",
        ),
        forbidden_patterns=("proxy_pass http://0.0.0.0", "proxy_pass http://admin.example.com"),
    ),
    BundleCheck(
        name="nginx_sso_headers",
        path="deploy/copilot-admin.nginx.example",
        description="Nginx template documents reverse-proxy SSO identity headers without embedding secrets.",
        required_patterns=(
            "auth_request",
            "X-Forwarded-User",
            "X-Forwarded-Email",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS",
        ),
        forbidden_patterns=("app_secret", "access_token", "Bearer "),
    ),
    BundleCheck(
        name="systemd_service",
        path="deploy/copilot-admin.service.example",
        description="systemd template starts the local admin server from repo code with environment-file configuration.",
        required_patterns=(
            "WorkingDirectory=/opt/feishu_ai_challenge",
            "EnvironmentFile=/etc/feishu-memory-copilot/admin.env",
            "scripts/start_copilot_admin.py",
            "--host ${FEISHU_MEMORY_COPILOT_ADMIN_HOST}",
            "--port ${FEISHU_MEMORY_COPILOT_ADMIN_PORT}",
            "--db-path ${MEMORY_DB_PATH}",
        ),
        forbidden_patterns=("FEISHU_MEMORY_COPILOT_ADMIN_TOKEN=", "COPILOT_ADMIN_TOKEN="),
    ),
    BundleCheck(
        name="systemd_hardening",
        path="deploy/copilot-admin.service.example",
        description="systemd template includes basic process hardening and restart behavior.",
        required_patterns=("Restart=on-failure", "NoNewPrivileges=true", "PrivateTmp=true", "ProtectSystem=full"),
    ),
    BundleCheck(
        name="monitoring_alerts",
        path="deploy/monitoring/copilot-admin-alerts.yml",
        description="Staging Prometheus alert rules include Wiki, Graph, tenant policy, audit, and production blocker alerts.",
        required_patterns=(
            "CopilotWikiCardsMissing",
            "CopilotGraphNodesMissing",
            "CopilotTenantPolicyMissing",
            "CopilotAuditLedgerEmpty",
            "CopilotProductionStillBlocked",
            "CopilotProductionMonitoringBlocker",
        ),
    ),
    BundleCheck(
        name="admin_readiness_gate",
        path="scripts/check_copilot_admin_readiness.py",
        description="Strict admin readiness gate checks Wiki cards, graph, launch readiness, and access policy.",
        required_patterns=("run_admin_readiness", "min_wiki_cards", "launch_readiness", "access_policy"),
    ),
    BundleCheck(
        name="sso_header_gate",
        path="scripts/check_copilot_admin_sso_gate.py",
        description="SSO verifier covers loopback reverse-proxy header behavior and keeps IdP boundary explicit.",
        required_patterns=("no_header_denied", "viewer_export_forbidden", "not_real_enterprise_idp"),
    ),
    BundleCheck(
        name="completion_audit_gate",
        path="scripts/check_llm_wiki_enterprise_site_completion.py",
        description="Completion audit maps the user objective to artifacts and keeps production blockers explicit.",
        required_patterns=("staging_ok", "goal_complete", "production_blockers"),
    ),
    BundleCheck(
        name="backup_restore_gate",
        path="scripts/backup_copilot_storage.py",
        description="SQLite staging backup verifier supports manifest, integrity check, and restore path.",
        required_patterns=("manifest", "integrity", "restore"),
    ),
    BundleCheck(
        name="launch_runbook",
        path="docs/productization/admin-llm-wiki-launch-runbook.md",
        description="Launch runbook documents staging scope, deployment checks, and no-overclaim boundaries.",
        required_patterns=("本地 / staging", "check_copilot_admin_sso_gate.py", "真实企业 IdP", "productized live"),
    ),
)

PRODUCTION_BLOCKERS = (
    {
        "id": "real_domain_tls",
        "description": "Template has TLS placeholders, but no real production domain or certificate has been validated.",
    },
    {
        "id": "real_enterprise_idp",
        "description": "SSO is verified only as loopback reverse-proxy header behavior, not real enterprise IdP login.",
    },
    {
        "id": "production_database",
        "description": "Bundle still targets SQLite staging storage; production PostgreSQL/PITR is not deployed.",
    },
    {
        "id": "production_monitoring_delivery",
        "description": "Alert rules are present, but production Prometheus/Grafana/Alertmanager delivery is not proven.",
    },
    {
        "id": "long_running_live_ops",
        "description": "No productized live long-run logs, on-call proof, or rollback drill evidence is present.",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the Copilot Admin LLM Wiki / Graph deploy bundle without claiming production deployment."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-production-ready",
        action="store_true",
        help="Return a failing exit code while known production blockers remain.",
    )
    args = parser.parse_args()

    result = run_deploy_bundle_check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    if not result["staging_bundle_ok"]:
        return 1
    if args.require_production_ready and result["production_blocked"]:
        return 1
    return 0


def run_deploy_bundle_check() -> dict[str, Any]:
    checks = [_evaluate_check(check) for check in CHECKS]
    failed = [check for check in checks if check["status"] != "pass"]
    staging_bundle_ok = not failed
    return {
        "ok": staging_bundle_ok,
        "staging_bundle_ok": staging_bundle_ok,
        "production_blocked": bool(PRODUCTION_BLOCKERS),
        "boundary": BOUNDARY,
        "checks": checks,
        "failed_checks": failed,
        "production_blockers": list(PRODUCTION_BLOCKERS),
        "next_step": ""
        if staging_bundle_ok
        else "Fix failed deploy bundle checks before sharing the LLM Wiki / Graph admin package.",
    }


def _evaluate_check(check: BundleCheck) -> dict[str, Any]:
    path = ROOT / check.path
    exists = path.exists()
    missing_patterns: list[str] = []
    present_forbidden_patterns: list[str] = []
    if exists:
        text = path.read_text(encoding="utf-8")
        missing_patterns = [pattern for pattern in check.required_patterns if pattern not in text]
        present_forbidden_patterns = [pattern for pattern in check.forbidden_patterns if pattern in text]
    status = "pass" if exists and not missing_patterns and not present_forbidden_patterns else "fail"
    return {
        "name": check.name,
        "path": check.path,
        "description": check.description,
        "status": status,
        "exists": exists,
        "missing_patterns": missing_patterns,
        "present_forbidden_patterns": present_forbidden_patterns,
    }


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Admin Deploy Bundle Check")
    print(f"staging_bundle_ok: {str(result['staging_bundle_ok']).lower()}")
    print(f"production_blocked: {str(result['production_blocked']).lower()}")
    print(f"boundary: {result['boundary']}")
    for check in result["checks"]:
        print(f"- {check['name']}: {check['status']} ({check['description']})")
    if result["production_blockers"]:
        print("production_blockers:")
        for blocker in result["production_blockers"]:
            print(f"- {blocker['id']}: {blocker['description']}")


if __name__ == "__main__":
    raise SystemExit(main())
