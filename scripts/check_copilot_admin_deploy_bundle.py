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
        name="admin_env_example",
        path="deploy/copilot-admin.env.example",
        description="Sanitized admin.env example documents required runtime settings without real credentials.",
        required_patterns=(
            "MEMORY_DB_PATH=/opt/feishu_ai_challenge/data/memory.sqlite",
            "FEISHU_MEMORY_COPILOT_ADMIN_PRODUCTION_EVIDENCE_MANIFEST=/opt/feishu_ai_challenge/deploy/copilot-admin.production-evidence.example.json",
            "FEISHU_MEMORY_COPILOT_ADMIN_HOST=127.0.0.1",
            "FEISHU_MEMORY_COPILOT_ADMIN_PORT=8765",
            "FEISHU_MEMORY_COPILOT_ADMIN_TOKEN=__CHANGE_ME_ADMIN_TOKEN__",
            "FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN=__CHANGE_ME_VIEWER_TOKEN__",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED=0",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS=example.com",
            "not real enterprise IdP production validation",
        ),
        forbidden_patterns=("app_secret=", "access_token=", "Bearer ", "sk-", "rightcode_"),
    ),
    BundleCheck(
        name="admin_env_lint",
        path="scripts/check_copilot_admin_env_file.py",
        description="admin.env lint validates example/runtime files without printing secret values.",
        required_patterns=(
            "check_admin_env_file",
            "redacted_summary",
            "no token values printed",
            "DEFAULT_EXAMPLE_PATH",
        ),
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
        name="audit_readonly_gate",
        path="scripts/check_copilot_audit_readonly_gate.py",
        description="Audit read-only verifier covers tenant/org filters, redaction, CSV export, and no-write API policy.",
        required_patterns=(
            "run_audit_readonly_gate",
            "source_context_redaction",
            "admin_api_readonly",
            "POST writes",
        ),
    ),
    BundleCheck(
        name="launch_evidence_bundle_export",
        path="scripts/export_copilot_admin_launch_evidence.py",
        description="Launch evidence exporter writes local/staging Wiki, Graph, Audit, and blocker JSON artifacts.",
        required_patterns=(
            "export_launch_evidence_bundle",
            "copilot_admin_launch_evidence/v1",
            "graph_quality",
            "audit_readonly_gate",
            "production_blockers",
        ),
    ),
    BundleCheck(
        name="completion_audit_gate",
        path="scripts/check_llm_wiki_enterprise_site_completion.py",
        description="Completion audit maps the user objective to artifacts and keeps production blockers explicit.",
        required_patterns=("staging_ok", "goal_complete", "production_blockers"),
    ),
    BundleCheck(
        name="production_evidence_gate",
        path="scripts/check_copilot_admin_production_evidence.py",
        description="Production evidence manifest gate validates external DB, SSO, TLS, monitoring, and long-run proof.",
        required_patterns=(
            "run_production_evidence_check",
            "production_ready",
            "productized_live_long_run",
            "does not create production DB",
        ),
    ),
    BundleCheck(
        name="production_db_evidence_collector",
        path="scripts/collect_copilot_production_db_evidence.py",
        description="Production DB evidence collector emits a PostgreSQL/PITR manifest patch without deploying storage.",
        required_patterns=(
            "collect_production_db_evidence",
            "production_manifest_patch",
            "production_db",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="production_db_live_probe",
        path="scripts/check_copilot_production_db_probe.py",
        description="Production DB live probe validates an existing PostgreSQL endpoint through a DSN env var.",
        required_patterns=(
            "run_production_db_probe",
            "production_db",
            "pg_isready",
            "production_db_live_probe_only",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="external_production_evidence_collector",
        path="scripts/collect_copilot_external_production_evidence.py",
        description="External production evidence collector emits IdP, TLS, and monitoring manifest patches.",
        required_patterns=(
            "collect_external_production_evidence",
            "enterprise_idp_sso",
            "production_domain_tls",
            "production_monitoring",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="production_idp_entrypoint_probe",
        path="scripts/check_copilot_admin_idp_probe.py",
        description="Enterprise IdP entrypoint probe validates Admin unauthenticated guard and external IdP evidence refs.",
        required_patterns=(
            "run_idp_probe",
            "enterprise_idp_sso",
            "unauthenticated_guard",
            "enterprise_idp_entrypoint_probe_only",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="production_tls_live_probe",
        path="scripts/check_copilot_admin_tls_probe.py",
        description="TLS live probe validates an existing HTTPS endpoint, certificate hostname/expiry, and HSTS.",
        required_patterns=(
            "run_tls_probe",
            "production_domain_tls",
            "Strict-Transport-Security",
            "live_tls_probe_only",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="production_monitoring_live_probe",
        path="scripts/check_copilot_admin_monitoring_probe.py",
        description="Monitoring live probe validates Admin /metrics, Grafana URL, alert route, and delivery refs.",
        required_patterns=(
            "run_monitoring_probe",
            "production_monitoring",
            "copilot_admin_launch_production_blocked",
            "live_monitoring_probe_only",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="long_run_evidence_collector",
        path="scripts/collect_copilot_admin_long_run_evidence.py",
        description="Long-run evidence collector probes a running Admin backend and emits a productized live manifest patch.",
        required_patterns=(
            "collect_long_run_evidence",
            "production_manifest_patch",
            "productized_live_long_run",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="production_evidence_patch_merger",
        path="scripts/merge_copilot_production_evidence.py",
        description="Production evidence patch merger combines collector outputs and validates the merged manifest.",
        required_patterns=(
            "merge_production_evidence_patches",
            "production_manifest_patch",
            "run_production_evidence_check",
            "require-production-ready",
            "production_ready_claim",
        ),
    ),
    BundleCheck(
        name="production_evidence_manifest_example",
        path="deploy/copilot-admin.production-evidence.example.json",
        description="Example manifest lists required production evidence without real secrets.",
        required_patterns=(
            "copilot_admin_production_evidence/v1",
            "production_db",
            "enterprise_idp_sso",
            "production_domain_tls",
            "production_monitoring",
            "productized_live_long_run",
        ),
        forbidden_patterns=("app_secret=", "access_token=", "Bearer ", "sk-", "rightcode_"),
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
        required_patterns=(
            "本地 / staging",
            "check_copilot_admin_sso_gate.py",
            "check_copilot_audit_readonly_gate.py",
            "export_copilot_admin_launch_evidence.py",
            "真实企业 IdP",
            "productized live",
        ),
    ),
)

PRODUCTION_BLOCKERS = (
    {
        "id": "real_domain_tls",
        "description": "TLS live probe and evidence collector exist, but no real production domain/certificate/HSTS evidence is present.",
    },
    {
        "id": "real_enterprise_idp",
        "description": "IdP entrypoint probe and evidence collector exist, but no real enterprise IdP login evidence is present.",
    },
    {
        "id": "production_database",
        "description": "Production DB live probe and evidence collector exist, but real PostgreSQL/PITR deployment evidence is not present.",
    },
    {
        "id": "production_monitoring_delivery",
        "description": "Monitoring live probe and evidence collector exist, but production Prometheus/Grafana/Alertmanager delivery is not proven.",
    },
    {
        "id": "long_running_live_ops",
        "description": "Long-run evidence collector exists, but no real productized live 24h logs, on-call proof, or rollback drill evidence is present.",
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
