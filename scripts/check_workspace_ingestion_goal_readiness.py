#!/usr/bin/env python3
"""Completion gate for the Feishu workspace ingestion objective.

The gate is intentionally conservative. It combines the two remaining
hard-evidence gates with static checks for the already documented product
decisions. It only returns pass when project/enterprise normal Sheet evidence
and real same-conclusion chat/workspace corroboration are both present.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.db import connect, init_db  # noqa: E402
from memory_engine.feishu_workspace_fetcher import (  # noqa: E402
    WorkspaceActor,
    discover_workspace_resources,
    fetch_workspace_resource_sources,
    inspect_sheet_resource,
    workspace_resource_from_spec,
)
from scripts.check_workspace_project_sheet_evidence_gate import (  # noqa: E402
    DEFAULT_PROJECT_KEYWORDS,
    DEFAULT_PROJECT_QUERIES,
    _candidate_report,
    _dedupe_resources,
    _redacted_resource,
    build_project_sheet_evidence_report,
)
from scripts.check_workspace_real_same_conclusion_sample_finder import (  # noqa: E402
    chat_inputs_from_event_logs,
    run_sample_finder,
)

BOUNDARY = (
    "workspace_ingestion_goal_readiness_gate; combines real project Sheet evidence, real same-conclusion "
    "corroboration evidence, and static repo artifact checks; no production full-workspace ingestion claim"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check readiness for the workspace ingestion objective.")
    parser.add_argument("--event-log", type=Path, action="append", required=True)
    parser.add_argument("--expected-chat-id")
    parser.add_argument(
        "--resource",
        action="append",
        required=True,
        help="Reviewed workspace resource spec type:token[:title]. Resource identifiers are not echoed in the report.",
    )
    parser.add_argument("--scope", default="workspace:feishu")
    parser.add_argument("--actor-user-id")
    parser.add_argument("--actor-open-id")
    parser.add_argument("--tenant-id", default="tenant:demo")
    parser.add_argument("--organization-id", default="org:demo")
    parser.add_argument("--roles", default="member,reviewer")
    parser.add_argument("--profile")
    parser.add_argument("--as-identity", default="user")
    parser.add_argument("--max-sheet-rows", type=int, default=20)
    parser.add_argument("--max-bitable-records", type=int, default=3)
    parser.add_argument("--candidate-limit-per-chat", type=int, default=5)
    parser.add_argument("--sheet-query", action="append")
    parser.add_argument("--project-keyword", action="append")
    parser.add_argument("--sheet-resource", action="append", default=[])
    parser.add_argument("--sheet-opened-since", default="90d")
    parser.add_argument("--sheet-limit", type=int, default=20)
    parser.add_argument("--sheet-max-pages", type=int, default=2)
    parser.add_argument("--allow-cross-tenant-sheet", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not (args.actor_user_id or args.actor_open_id):
        parser.error("--actor-user-id or --actor-open-id is required")

    actor = WorkspaceActor(
        user_id=args.actor_user_id,
        open_id=args.actor_open_id,
        tenant_id=args.tenant_id,
        organization_id=args.organization_id,
        roles=tuple(role.strip() for role in args.roles.split(",") if role.strip()),
    )
    sheet_report = run_project_sheet_check(
        queries=args.sheet_query or list(DEFAULT_PROJECT_QUERIES),
        project_keywords=args.project_keyword or list(DEFAULT_PROJECT_KEYWORDS),
        explicit_resources=sheet_resources_from_specs(args.resource, args.sheet_resource),
        opened_since=args.sheet_opened_since,
        limit=args.sheet_limit,
        max_pages=args.sheet_max_pages,
        allow_cross_tenant=args.allow_cross_tenant_sheet,
        profile=args.profile,
        as_identity=args.as_identity,
    )
    same_conclusion_report = run_same_conclusion_check(
        event_logs=args.event_log,
        expected_chat_id=args.expected_chat_id,
        resources=args.resource,
        actor=actor,
        scope=args.scope,
        profile=args.profile,
        as_identity=args.as_identity,
        max_sheet_rows=args.max_sheet_rows,
        max_bitable_records=args.max_bitable_records,
        candidate_limit_per_chat=args.candidate_limit_per_chat,
    )
    report = build_readiness_report(
        project_root=PROJECT_ROOT,
        sheet_report=sheet_report,
        same_conclusion_report=same_conclusion_report,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_project_sheet_check(
    *,
    queries: list[str],
    project_keywords: list[str],
    explicit_resources: list[str],
    opened_since: str,
    limit: int,
    max_pages: int,
    allow_cross_tenant: bool,
    profile: str | None,
    as_identity: str | None,
) -> dict[str, Any]:
    resources = []
    for query in queries:
        resources.extend(
            discover_workspace_resources(
                query=query,
                doc_types=["sheet"],
                limit=limit,
                max_pages=max_pages,
                opened_since=opened_since,
                sort="edit_time",
                profile=profile,
                as_identity=as_identity,
            )
        )
    resources.extend(workspace_resource_from_spec(spec) for spec in explicit_resources)
    resources = _dedupe_resources(resources)

    candidates: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for resource in resources:
        try:
            inspection = inspect_sheet_resource(resource, profile=profile, as_identity=as_identity)
        except Exception as exc:
            failures.append({"resource": _redacted_resource(resource), "error": str(exc)})
            continue
        candidates.append(
            _candidate_report(
                resource,
                inspection,
                project_keywords=project_keywords,
                allow_cross_tenant=allow_cross_tenant,
            )
        )
    return build_project_sheet_evidence_report(
        candidates=candidates,
        inspection_failures=failures,
        min_eligible=1,
        queries=queries,
        project_keywords=project_keywords,
        allow_cross_tenant=allow_cross_tenant,
    )


def sheet_resources_from_specs(resources: list[str], sheet_resources: list[str]) -> list[str]:
    """Return explicit Sheet specs from both readiness resource inputs.

    `--resource sheet:...` should count for the project normal Sheet evidence
    gate as well as same-conclusion source fetching. `--sheet-resource` remains
    as a dedicated override for operators that want the Sheet evidence pool to
    differ from the same-conclusion resource pool.
    """

    specs = list(sheet_resources)
    specs.extend(spec for spec in resources if _resource_type_from_spec(spec) in {"sheet", "sheets", "spreadsheet"})
    return _dedupe_specs(specs)


def run_same_conclusion_check(
    *,
    event_logs: list[Path],
    expected_chat_id: str | None,
    resources: list[str],
    actor: WorkspaceActor,
    scope: str,
    profile: str | None,
    as_identity: str | None,
    max_sheet_rows: int,
    max_bitable_records: int,
    candidate_limit_per_chat: int,
) -> dict[str, Any]:
    chats = chat_inputs_from_event_logs(event_logs, expected_chat_id=expected_chat_id)
    resource_sources = []
    fetch_failures = 0
    for spec in resources:
        resource = workspace_resource_from_spec(spec)
        try:
            resource_sources.extend(
                fetch_workspace_resource_sources(
                    resource,
                    max_sheet_rows=max_sheet_rows,
                    max_bitable_records=max_bitable_records,
                    profile=profile,
                    as_identity=as_identity,
                )
            )
        except Exception:
            fetch_failures += 1
    with tempfile.TemporaryDirectory() as temp_dir:
        conn = connect(Path(temp_dir) / "workspace-readiness.sqlite")
        try:
            init_db(conn)
            return run_sample_finder(
                conn,
                chats=chats,
                resource_sources=resource_sources,
                fetch_failure_count=fetch_failures,
                actor=actor,
                scope=scope,
                candidate_limit_per_chat=candidate_limit_per_chat,
            )
        finally:
            conn.close()


def build_readiness_report(
    *,
    project_root: Path,
    sheet_report: dict[str, Any],
    same_conclusion_report: dict[str, Any],
) -> dict[str, Any]:
    evidence = _static_evidence(project_root)
    checks = {
        "lark_cli_first_architecture_decision": _equals_check(evidence["lark_cli_first"], True),
        "memory_judgment_policy_documented": _equals_check(evidence["memory_policy"], True),
        "route_reuses_copilot_service": _equals_check(evidence["route_reuse"], True),
        "shared_governed_ledger_documented": _equals_check(evidence["shared_ledger"], True),
        "performance_gates_documented": _equals_check(evidence["performance_gates"], True),
        "opus_4_6_doc_style_boundary_documented": _equals_check(evidence["opus_4_6_boundary"], True),
        "project_enterprise_normal_sheet_evidence": _equals_check(bool(sheet_report.get("ok")), True),
        "real_same_conclusion_corroboration_evidence": _equals_check(
            bool(same_conclusion_report.get("ok")), True
        ),
    }
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    blockers = []
    if "project_enterprise_normal_sheet_evidence" in failures:
        blockers.append(
            "Provide an existing project/enterprise normal Sheet resource, folder, or wiki space, "
            "or explicitly approve creation of a controlled test Sheet."
        )
    if "real_same_conclusion_corroboration_evidence" in failures:
        blockers.append(
            "Capture a real Feishu chat message that repeats a durable fact already present in a reviewed "
            "document, Sheet, or Bitable source."
        )
    return {
        "ok": not failures,
        "status": "pass" if not failures else "blocked",
        "goal_complete": not failures,
        "boundary": BOUNDARY,
        "checks": checks,
        "failures": failures,
        "blockers": blockers,
        "sheet_summary": (sheet_report.get("summary") or {}),
        "same_conclusion_summary": (same_conclusion_report.get("summary") or {}),
        "static_evidence": evidence,
        "next_step": "" if not failures else "Resolve the listed blockers, then rerun this readiness gate.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Goal Readiness",
        f"status: {report['status']}",
        f"goal_complete: {str(report['goal_complete']).lower()}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(
            f"  {name}: {check['status']} "
            f"(actual={check['actual']}, threshold={check['operator']} {check['threshold']})"
        )
    if report["blockers"]:
        lines.append("")
        lines.append("blockers:")
        for blocker in report["blockers"]:
            lines.append(f"  - {blocker}")
    return "\n".join(lines)


def _static_evidence(project_root: Path) -> dict[str, bool]:
    adr = _read(project_root / "docs/productization/workspace-ingestion-architecture-adr.md")
    style = _read(project_root / "docs/productization/document-writing-style-guide-opus-4-6.md")
    return {
        "lark_cli_first": "lark-cli first" in adr and "native Feishu OpenAPI" in adr,
        "memory_policy": "Remember candidates when the source contains" in adr
        and "Do not remember" in adr,
        "route_reuse": "FeishuIngestionSource" in adr
        and "CopilotService" in adr
        and "candidate pipeline" in adr,
        "shared_ledger": "one governed ledger" in adr and "Evidence rows" in adr,
        "performance_gates": "latency gate" in adr and "bounded" in adr,
        "opus_4_6_boundary": "Opus 4.6" in style and "4.7" in style,
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _resource_type_from_spec(spec: str) -> str:
    return spec.split(":", 1)[0].strip().lower()


def _dedupe_specs(specs: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for spec in specs:
        if spec in seen:
            continue
        seen.add(spec)
        result.append(spec)
    return result


def _equals_check(actual: Any, expected: Any) -> dict[str, Any]:
    return {
        "status": "pass" if actual == expected else "fail",
        "actual": actual,
        "threshold": expected,
        "operator": "==",
    }


if __name__ == "__main__":
    raise SystemExit(main())
