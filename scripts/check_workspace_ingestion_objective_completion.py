#!/usr/bin/env python3
"""Audit the full Feishu workspace ingestion objective against real artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_workspace_productized_ingestion_readiness import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    run_productized_ingestion_check,
)

BOUNDARY = (
    "workspace_objective_completion_audit_only; maps the user objective to repo artifacts and productized "
    "workspace evidence, but does not run ingestion, create Feishu resources, or prove production readiness by itself"
)


@dataclass(frozen=True)
class EvidenceCheck:
    requirement: str
    evidence: str
    path: str
    contains: tuple[str, ...] = ()


ARTIFACT_CHECKS = (
    EvidenceCheck(
        requirement="1. Decide lark-cli vs native Feishu API for workspace ingestion.",
        evidence="Architecture ADR chooses lark-cli-first for OpenClaw pilot and reserves native API for hot paths.",
        path="docs/productization/workspace-ingestion-architecture-adr.md",
        contains=("lark-cli first", "native Feishu OpenAPI", "drive +search", "docs +fetch", "base +"),
    ),
    EvidenceCheck(
        requirement="2. Decide what should be remembered after ingestion.",
        evidence="ADR and review policy define durable memory candidates, exclusions, auto-confirm, and human review.",
        path="docs/productization/workspace-ingestion-architecture-adr.md",
        contains=("Memory Judgment", "Remember candidates", "Do not remember", "review policy"),
    ),
    EvidenceCheck(
        requirement="2. Decide what should be remembered after ingestion.",
        evidence="Review policy implementation classifies auto-confirm vs human-review candidates.",
        path="memory_engine/copilot/review_policy.py",
        contains=("evaluate_review_policy", "auto_confirm", "human_review"),
    ),
    EvidenceCheck(
        requirement="3. Arrange memory routing and reuse group-chat architecture.",
        evidence="Workspace ingestion routes FeishuIngestionSource through the existing candidate pipeline.",
        path="scripts/feishu_workspace_ingest.py",
        contains=("FeishuIngestionSource", "ingest_feishu_source", "workspace_current_context"),
    ),
    EvidenceCheck(
        requirement="3. Arrange memory routing and reuse group-chat architecture.",
        evidence="OpenClaw/Feishu DM routing gate validates first-class fmc_* routing and bridge metadata.",
        path="scripts/check_feishu_dm_routing.py",
        contains=("fmc_memory_search", "first_class", "permission_decision"),
    ),
    EvidenceCheck(
        requirement="4. Combine docs/tables memory with group-chat memory in one governed store.",
        evidence="Mixed-source gate proves chat evidence, document corroboration, and Bitable conflict share one ledger.",
        path="scripts/check_workspace_mixed_source_corroboration_gate.py",
        contains=("feishu_message", "document_feishu", "lark_bitable", "single_governed_memory_row"),
    ),
    EvidenceCheck(
        requirement="4. Combine docs/tables memory with group-chat memory in one governed store.",
        evidence="Same-conclusion gate proves real chat facts can be corroborated by reviewed workspace sources.",
        path="scripts/check_workspace_real_same_conclusion_gate.py",
        contains=("workspace_same_fact_added_as_duplicate", "active_evidence_has_chat_and_workspace"),
    ),
    EvidenceCheck(
        requirement="5. Keep stability while improving Memory Copilot response speed.",
        evidence="Retrieval path records stage-level timing and reuses fallback state.",
        path="memory_engine/copilot/retrieval.py",
        contains=("elapsed_ms", "structured", "keyword", "vector"),
    ),
    EvidenceCheck(
        requirement="5. Keep stability while improving Memory Copilot response speed.",
        evidence="Workspace latency gates cover warm-path and real lark-cli fetch-path checks.",
        path="scripts/check_workspace_real_fetch_latency_gate.py",
        contains=("elapsed_ms", "per_resource_ms", "no_failed_fetch"),
    ),
    EvidenceCheck(
        requirement="6. Rewrite active docs in a Claude Opus 4.6-like human engineering voice, not 4.7.",
        evidence="Style guide freezes the intended doc voice and explicitly excludes Opus 4.7.",
        path="docs/productization/document-writing-style-guide-opus-4-6.md",
        contains=("Opus 4.6", "not Opus 4.7", "human, engineering prose"),
    ),
    EvidenceCheck(
        requirement="Productized full-workspace evidence must gate the completion claim.",
        evidence="Strict productized gate requires non-example evidence for source coverage, scheduler/cursor, ops, and 24h+ long-run.",
        path="scripts/check_workspace_productized_ingestion_readiness.py",
        contains=("source_coverage", "discovery_and_cursoring", "live_long_run", "goal_complete"),
    ),
    EvidenceCheck(
        requirement="Productized evidence patches must be machine-mergeable without manual JSON splicing.",
        evidence="Patch merger accepts collector outputs and reruns the productized readiness gate.",
        path="scripts/merge_workspace_productized_ingestion_evidence.py",
        contains=("production_manifest_patch", "run_productized_ingestion_check", "productized_ready_claim"),
    ),
    EvidenceCheck(
        requirement="Productized source coverage evidence must be collected from real redacted reports.",
        evidence="Source coverage collector emits production_manifest_patch.source_coverage.",
        path="scripts/collect_workspace_source_coverage_evidence.py",
        contains=("production_manifest_patch", "source_coverage", "same_conclusion"),
    ),
    EvidenceCheck(
        requirement="Productized ops/governance/rate-limit evidence must be collected from external proof refs.",
        evidence="Ops/governance collector emits rate_limit, governance, and operations manifest patch sections.",
        path="scripts/collect_workspace_ops_governance_evidence.py",
        contains=("rate_limit_and_backoff", "governance", "operations", "production_manifest_patch"),
    ),
    EvidenceCheck(
        requirement="Productized long-run evidence must be collected from sanitized schedule reports.",
        evidence="Long-run collector emits live_long_run and discovery/cursoring patch sections.",
        path="scripts/collect_workspace_ingestion_long_run_evidence.py",
        contains=("live_long_run", "discovery_and_cursoring", "window_hours", "production_manifest_patch"),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the full Feishu workspace ingestion objective.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_workspace_ingestion_objective_completion_audit(args.manifest.expanduser())
    if args.output:
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["goal_complete"] else 1


def run_workspace_ingestion_objective_completion_audit(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    artifact_items = [_artifact_item(check) for check in ARTIFACT_CHECKS]
    productized = run_productized_ingestion_check(manifest_path)
    productized_item = {
        "requirement": "Production/full-workspace completion claim",
        "evidence": "Productized workspace ingestion readiness gate.",
        "path": str(manifest_path.resolve()),
        "status": "pass" if productized.get("goal_complete") is True else "fail",
        "reason": "productized_gate_complete" if productized.get("goal_complete") is True else "productized_gate_blocked",
        "details": {
            "goal_complete": bool(productized.get("goal_complete")),
            "status": productized.get("status"),
            "failed_checks": productized.get("failed_checks", []),
            "warning_checks": productized.get("warning_checks", []),
            "blockers": productized.get("blockers", []),
        },
    }
    items = [*artifact_items, productized_item]
    blockers = [item for item in items if item["status"] != "pass"]
    goal_complete = not blockers
    return {
        "ok": goal_complete,
        "goal_complete": goal_complete,
        "status": "complete" if goal_complete else "incomplete",
        "boundary": BOUNDARY,
        "objective": _objective_payload(),
        "checklist": items,
        "productized_readiness": productized,
        "blockers": [
            {
                "requirement": item["requirement"],
                "path": item["path"],
                "reason": item["reason"],
                "details": item.get("details", {}),
            }
            for item in blockers
        ],
        "next_step": ""
        if goal_complete
        else "Collect and merge a real non-example productized workspace evidence manifest, then rerun this audit.",
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Objective Completion Audit",
        f"goal_complete: {str(result['goal_complete']).lower()}",
        f"status: {result['status']}",
        f"boundary: {result['boundary']}",
        "",
        "checklist:",
    ]
    for item in result["checklist"]:
        lines.append(f"- {item['status']}: {item['requirement']} [{item['path']}]")
    if result["blockers"]:
        lines.extend(["", "blockers:"])
        for blocker in result["blockers"]:
            lines.append(f"- {blocker['requirement']}: {blocker['reason']} ({blocker['path']})")
        lines.append("")
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _artifact_item(check: EvidenceCheck) -> dict[str, Any]:
    path = ROOT / check.path
    if not path.exists():
        return {
            "requirement": check.requirement,
            "evidence": check.evidence,
            "path": check.path,
            "status": "fail",
            "reason": "file_missing",
            "details": {"missing_path": str(path)},
        }
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in check.contains if needle not in text]
    return {
        "requirement": check.requirement,
        "evidence": check.evidence,
        "path": check.path,
        "status": "pass" if not missing else "fail",
        "reason": "artifact_evidence_present" if not missing else "missing_expected_markers",
        "details": {"missing_markers": missing},
    }


def _objective_payload() -> dict[str, Any]:
    return {
        "deliverables": [
            "lark-cli vs native API decision",
            "workspace document/cloud-doc/sheet/bitable ingestion path",
            "memory selection policy",
            "workspace routing through existing group-chat/CopilotService architecture",
            "shared governed database, evidence, corroboration, and conflict handling",
            "stability and response-speed optimization evidence",
            "active documentation in Opus 4.6-like human engineering style",
            "strict productized full-workspace readiness evidence before completion claim",
        ],
        "completion_rule": (
            "Every artifact check must pass and the productized workspace ingestion readiness gate must report "
            "goal_complete=true on a non-example manifest."
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
