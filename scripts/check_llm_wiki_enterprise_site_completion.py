#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

OBJECTIVE = "做完整版可上线的 llm wiki 企业知识站，将其与知识图谱结合起来去做后台可展示的知识图谱后台，同时优化当前的后台 ui 设计"


@dataclass(frozen=True)
class EvidenceCheck:
    requirement: str
    evidence: str
    path: str
    contains: tuple[str, ...] = ()


STAGING_CHECKS = (
    EvidenceCheck(
        requirement="LLM Wiki enterprise knowledge site",
        evidence="Static exporter exists and writes a read-only site artifact.",
        path="scripts/export_copilot_knowledge_site.py",
        contains=("export_knowledge_site",),
    ),
    EvidenceCheck(
        requirement="LLM Wiki enterprise knowledge site",
        evidence="Static export verifier generates and checks Wiki/Graph/Markdown artifacts.",
        path="scripts/check_copilot_knowledge_site_export.py",
        contains=("run_knowledge_site_export_check", "required_files", "redaction"),
    ),
    EvidenceCheck(
        requirement="LLM Wiki enterprise knowledge site",
        evidence="Knowledge site manifest includes wiki, graph, Markdown export, and no-production boundary.",
        path="memory_engine/copilot/knowledge_site.py",
        contains=(
            "data/manifest.json",
            "data/wiki.json",
            "data/graph.json",
            "wiki/{filename}",
            "no production deployment",
        ),
    ),
    EvidenceCheck(
        requirement="LLM Wiki enterprise knowledge site",
        evidence="Static knowledge site has unit coverage.",
        path="tests/test_copilot_knowledge_site.py",
        contains=("export_knowledge_site",),
    ),
    EvidenceCheck(
        requirement="Knowledge graph integration",
        evidence="Live admin exposes graph workspace API and appends compiled memory graph.",
        path="memory_engine/copilot/admin.py",
        contains=("def graph_workspace", "_append_compiled_memory_graph", "grounded_by"),
    ),
    EvidenceCheck(
        requirement="Knowledge graph integration",
        evidence="Storage graph contract is documented with node and edge tables.",
        path="docs/productization/contracts/storage-contract.md",
        contains=("knowledge_graph_nodes", "knowledge_graph_edges"),
    ),
    EvidenceCheck(
        requirement="Visible knowledge graph backend",
        evidence="Admin UI has a Graph tab and graph detail panel.",
        path="memory_engine/copilot/admin.py",
        contains=('data-view="graph"', "graph-detail", "/api/graph"),
    ),
    EvidenceCheck(
        requirement="Visible knowledge graph backend",
        evidence="Admin API and graph behavior have unit coverage.",
        path="tests/test_copilot_admin.py",
        contains=("graph_workspace", "api/graph", "tenant_id"),
    ),
    EvidenceCheck(
        requirement="Admin UI optimization",
        evidence="Playwright smoke covers desktop/mobile graph detail and overflow checks.",
        path="scripts/check_copilot_admin_ui_smoke.py",
        contains=("admin_desktop_graph", "admin_mobile_graph", "horizontal overflow"),
    ),
    EvidenceCheck(
        requirement="Admin UI optimization",
        evidence="Static site UI exposes graph detail and search/filter surface.",
        path="memory_engine/copilot/knowledge_site.py",
        contains=("graphDetail", "search", "nodeDetail", "edgeDetail"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Strict admin readiness gate exists.",
        path="scripts/check_copilot_admin_readiness.py",
        contains=("run_admin_readiness", "min_wiki_cards", "access_policy"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Deploy bundle verifier exists and preserves production-blocked boundary.",
        path="scripts/check_copilot_admin_deploy_bundle.py",
        contains=("staging_bundle_ok", "production_blocked", "not_production_domain_tls"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Production evidence manifest gate exists for real DB, IdP, TLS, monitoring, and long-run proof.",
        path="scripts/check_copilot_admin_production_evidence.py",
        contains=("run_production_evidence_check", "production_ready", "productized_live_long_run"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Production evidence manifest example documents required proof without real secrets.",
        path="deploy/copilot-admin.production-evidence.example.json",
        contains=(
            "copilot_admin_production_evidence/v1",
            "production_db",
            "enterprise_idp_sso",
            "production_domain_tls",
            "production_monitoring",
        ),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Admin env lint validates example/runtime files without leaking token values.",
        path="scripts/check_copilot_admin_env_file.py",
        contains=("check_admin_env_file", "redacted_summary", "no token values printed"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Reverse-proxy SSO header gate has executable staging verifier.",
        path="scripts/check_copilot_admin_sso_gate.py",
        contains=("no_header_denied", "viewer_export_forbidden", "not_real_enterprise_idp"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Prometheus alert-rule verifier exists for staging alerts.",
        path="scripts/check_prometheus_alert_rules.py",
        contains=("CopilotWikiCardsMissing", "CopilotGraphNodesMissing"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="SQLite staging backup and restore drill exists.",
        path="scripts/backup_copilot_storage.py",
        contains=("restore", "manifest"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Systemd and Nginx deployment templates exist.",
        path="deploy/copilot-admin.nginx.example",
        contains=("X-Forwarded-Email", "proxy_pass"),
    ),
    EvidenceCheck(
        requirement="Launch gates",
        evidence="Systemd deployment template exists.",
        path="deploy/copilot-admin.service.example",
        contains=("ExecStart", "FEISHU_MEMORY_COPILOT_ADMIN"),
    ),
    EvidenceCheck(
        requirement="No-overclaim boundary",
        evidence="Completion audit states staging status and production gaps.",
        path="docs/productization/llm-wiki-enterprise-site-completion-audit.md",
        contains=("staging 已完成", "生产 DB", "真实企业 IdP", "productized live"),
    ),
    EvidenceCheck(
        requirement="No-overclaim boundary",
        evidence="Launch runbook states local/staging scope and non-production SSO boundary.",
        path="docs/productization/admin-llm-wiki-launch-runbook.md",
        contains=("本地 / staging", "真实企业 IdP", "productized live", "check_copilot_admin_sso_gate.py"),
    ),
)

PRODUCTION_BLOCKERS = (
    {
        "id": "production_db",
        "description": "Production DB / PostgreSQL / PITR deployment has not been validated.",
        "evidence": "Current artifacts cover SQLite staging backup / restore, not production PostgreSQL.",
    },
    {
        "id": "enterprise_idp_sso",
        "description": "Real enterprise IdP / Feishu SSO production validation is not complete.",
        "evidence": "SSO verifier covers loopback reverse-proxy headers only.",
    },
    {
        "id": "production_domain_tls",
        "description": "Production domain and TLS certificate delivery are not evidenced.",
        "evidence": "Deployment templates exist, but no production host/certificate proof is present.",
    },
    {
        "id": "production_monitoring",
        "description": "Production Prometheus/Grafana / Alertmanager delivery is not validated.",
        "evidence": "Alert-rule artifact exists for staging; production scrape/alert delivery is not proven.",
    },
    {
        "id": "productized_live_long_run",
        "description": "Productized live long-running evidence is not complete.",
        "evidence": "Plan and gates exist; long-running live logs and operational proof are not present.",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the LLM Wiki enterprise knowledge site objective against concrete repository artifacts."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-production-ready",
        action="store_true",
        help="Return a failing exit code while known production blockers remain.",
    )
    args = parser.parse_args()

    result = run_completion_audit()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    if not result["staging_ok"]:
        return 1
    if args.require_production_ready and not result["goal_complete"]:
        return 1
    return 0


def run_completion_audit() -> dict[str, Any]:
    checks = [_evaluate_check(check) for check in STAGING_CHECKS]
    missing = [check for check in checks if check["status"] != "pass"]
    prompt_to_artifact = _prompt_to_artifact(checks)
    blockers = list(PRODUCTION_BLOCKERS)
    staging_ok = not missing
    goal_complete = staging_ok and not blockers
    return {
        "objective": OBJECTIVE,
        "staging_ok": staging_ok,
        "goal_complete": goal_complete,
        "status": "staging_verified_production_blocked" if staging_ok and blockers else "incomplete",
        "prompt_to_artifact": prompt_to_artifact,
        "checks": checks,
        "missing_or_weak_checks": missing,
        "production_blockers": blockers,
        "next_step": ""
        if goal_complete
        else "Do not mark the objective complete until production blockers have real deployment evidence.",
    }


def _evaluate_check(check: EvidenceCheck) -> dict[str, Any]:
    path = ROOT / check.path
    exists = path.exists()
    missing_patterns: list[str] = []
    if exists and check.contains:
        text = path.read_text(encoding="utf-8")
        missing_patterns = [pattern for pattern in check.contains if pattern not in text]
    status = "pass" if exists and not missing_patterns else "fail"
    return {
        "requirement": check.requirement,
        "evidence": check.evidence,
        "path": check.path,
        "status": status,
        "exists": exists,
        "required_patterns": list(check.contains),
        "missing_patterns": missing_patterns,
    }


def _prompt_to_artifact(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requirements = [
        "LLM Wiki enterprise knowledge site",
        "Knowledge graph integration",
        "Visible knowledge graph backend",
        "Admin UI optimization",
        "Launch gates",
        "No-overclaim boundary",
    ]
    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        items = [check for check in checks if check["requirement"] == requirement]
        rows.append(
            {
                "requirement": requirement,
                "status": "pass" if items and all(item["status"] == "pass" for item in items) else "fail",
                "evidence_paths": [item["path"] for item in items],
            }
        )
    return rows


def _print_text(result: dict[str, Any]) -> None:
    print("LLM Wiki Enterprise Site Completion Audit")
    print(f"staging_ok: {str(result['staging_ok']).lower()}")
    print(f"goal_complete: {str(result['goal_complete']).lower()}")
    print(f"status: {result['status']}")
    for row in result["prompt_to_artifact"]:
        print(f"- {row['requirement']}: {row['status']}")
    if result["production_blockers"]:
        print("production_blockers:")
        for blocker in result["production_blockers"]:
            print(f"- {blocker['id']}: {blocker['description']}")


if __name__ == "__main__":
    raise SystemExit(main())
