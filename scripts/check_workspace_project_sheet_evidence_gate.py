#!/usr/bin/env python3
"""Read-only gate for project/enterprise normal Sheet evidence.

This gate discovers candidate Sheet resources and inspects their spreadsheet
shape with `sheets +info`. It does not read cell contents, create candidates,
or write the memory DB. Tokens and URLs are redacted from the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.feishu_workspace_fetcher import (  # noqa: E402
    WorkspaceResource,
    discover_workspace_resources,
    inspect_sheet_resource,
    workspace_resource_from_spec,
)

DEFAULT_PROJECT_QUERIES = ("飞书挑战赛", "OpenClaw", "memory", "copilot", "长期记忆")
DEFAULT_PROJECT_KEYWORDS = ("飞书挑战赛", "OpenClaw", "memory", "copilot", "长期记忆", "Memory Copilot")
BOUNDARY = (
    "read_only_project_normal_sheet_evidence_gate; sheets +info only; "
    "no cell reads, no memory DB writes, no full workspace ingestion claim"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find read-only evidence for project/enterprise normal Sheet resources."
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Project search query. Defaults to Feishu Memory Copilot project keywords.",
    )
    parser.add_argument(
        "--project-keyword",
        action="append",
        help="Keyword that makes a discovered Sheet project-scoped. Defaults to project keywords.",
    )
    parser.add_argument(
        "--resource",
        action="append",
        default=[],
        help="Explicit reviewed Sheet resource spec sheet:token[:title]. Explicit resources bypass keyword matching.",
    )
    parser.add_argument("--mine", action="store_true", help="Restrict search to Sheets created by current user.")
    parser.add_argument("--opened-since", default="90d")
    parser.add_argument("--edited-since")
    parser.add_argument("--created-since")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--profile")
    parser.add_argument("--as-identity", default="user")
    parser.add_argument("--allow-cross-tenant", action="store_true")
    parser.add_argument("--min-eligible", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    queries = args.query if args.query else list(DEFAULT_PROJECT_QUERIES)
    keywords = args.project_keyword if args.project_keyword else list(DEFAULT_PROJECT_KEYWORDS)
    resources: list[WorkspaceResource] = []
    for query in queries:
        resources.extend(
            discover_workspace_resources(
                query=query,
                doc_types=["sheet"],
                limit=args.limit,
                max_pages=args.max_pages,
                opened_since=args.opened_since,
                edited_since=args.edited_since,
                created_since=args.created_since,
                mine=args.mine,
                sort="edit_time",
                profile=args.profile,
                as_identity=args.as_identity,
            )
        )
    resources.extend(workspace_resource_from_spec(spec) for spec in args.resource)
    resources = _dedupe_resources(resources)

    candidate_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for resource in resources:
        try:
            inspection = inspect_sheet_resource(resource, profile=args.profile, as_identity=args.as_identity)
        except Exception as exc:
            failures.append(
                {
                    "resource": _redacted_resource(resource),
                    "error": str(exc),
                }
            )
            continue
        candidate_reports.append(
            _candidate_report(
                resource,
                inspection,
                project_keywords=keywords,
                allow_cross_tenant=args.allow_cross_tenant,
            )
        )

    report = build_project_sheet_evidence_report(
        candidates=candidate_reports,
        inspection_failures=failures,
        min_eligible=args.min_eligible,
        queries=queries,
        project_keywords=keywords,
        allow_cross_tenant=args.allow_cross_tenant,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def build_project_sheet_evidence_report(
    *,
    candidates: list[dict[str, Any]],
    inspection_failures: list[dict[str, Any]],
    min_eligible: int,
    queries: list[str],
    project_keywords: list[str],
    allow_cross_tenant: bool,
) -> dict[str, Any]:
    eligible = [item for item in candidates if item.get("eligible_project_normal_sheet")]
    sheet_backed_bitable = [item for item in candidates if item.get("is_sheet_backed_bitable_only")]
    cross_tenant = [item for item in candidates if item.get("is_cross_tenant")]
    normal_not_project = [
        item
        for item in candidates
        if item.get("is_normal_sheet")
        and not item.get("eligible_project_normal_sheet")
        and not item.get("is_cross_tenant")
    ]
    checks = {
        "has_candidate_resources": _min_check(len(candidates), 1),
        "has_eligible_project_normal_sheet": _min_check(len(eligible), min_eligible),
        "no_inspection_failures": _equals_check(len(inspection_failures), 0),
    }
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "boundary": BOUNDARY,
        "mode": "read_only_sheet_shape_evidence",
        "queries": queries,
        "project_keywords": project_keywords,
        "allow_cross_tenant": allow_cross_tenant,
        "summary": {
            "candidate_count": len(candidates),
            "eligible_project_normal_sheet_count": len(eligible),
            "sheet_backed_bitable_only_count": len(sheet_backed_bitable),
            "cross_tenant_candidate_count": len(cross_tenant),
            "normal_not_project_candidate_count": len(normal_not_project),
            "inspection_failure_count": len(inspection_failures),
        },
        "checks": checks,
        "candidates": candidates,
        "inspection_failures": inspection_failures,
        "failures": failures,
        "next_step": ""
        if not failures
        else (
            "Provide an existing project/enterprise normal Sheet token/folder/wiki space, "
            "or approve creation of a controlled test Sheet."
        ),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Project Sheet Evidence Gate",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        f"candidate_count: {report['summary']['candidate_count']}",
        f"eligible_project_normal_sheet_count: {report['summary']['eligible_project_normal_sheet_count']}",
        f"sheet_backed_bitable_only_count: {report['summary']['sheet_backed_bitable_only_count']}",
        f"cross_tenant_candidate_count: {report['summary']['cross_tenant_candidate_count']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(
            f"  {name}: {check['status']} "
            f"(actual={check['actual']}, threshold={check['operator']} {check['threshold']})"
        )
    if report["failures"]:
        lines.append("")
        lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


def _candidate_report(
    resource: WorkspaceResource,
    inspection: dict[str, Any],
    *,
    project_keywords: list[str],
    allow_cross_tenant: bool,
) -> dict[str, Any]:
    redacted = _redacted_resource(resource)
    title = str(redacted.get("title") or "")
    explicit = bool((resource.raw or {}).get("explicit_resource_spec"))
    is_cross_tenant = _is_cross_tenant(resource)
    keyword_match = explicit or _matches_keywords(title, project_keywords)
    is_normal_sheet = bool(inspection.get("is_normal_sheet"))
    eligible = is_normal_sheet and keyword_match and (allow_cross_tenant or not is_cross_tenant)
    return {
        **redacted,
        "is_cross_tenant": is_cross_tenant,
        "keyword_match": keyword_match,
        "explicit_reviewed_resource": explicit,
        "sheet_count": inspection.get("sheet_count", 0),
        "normal_sheet_count": inspection.get("normal_sheet_count", 0),
        "embedded_or_unsupported_sheet_count": inspection.get("embedded_or_unsupported_sheet_count", 0),
        "embedded_resource_types": inspection.get("embedded_resource_types", []),
        "normal_sheet_titles": inspection.get("normal_sheet_titles", []),
        "is_normal_sheet": is_normal_sheet,
        "is_sheet_backed_bitable_only": bool(inspection.get("is_sheet_backed_bitable_only")),
        "eligible_project_normal_sheet": eligible,
    }


def _redacted_resource(resource: WorkspaceResource) -> dict[str, Any]:
    return {
        "resource_type": resource.resource_type,
        "route_type": resource.route_type,
        "title": _strip_highlight(resource.title),
        "token_hash": hashlib.sha256(resource.token.encode("utf-8")).hexdigest()[:12],
        "entity_type": str((resource.raw or {}).get("entity_type") or ""),
    }


def _dedupe_resources(resources: list[WorkspaceResource]) -> list[WorkspaceResource]:
    seen: set[tuple[str, str, str | None]] = set()
    result: list[WorkspaceResource] = []
    for resource in resources:
        key = (resource.route_type, resource.token, resource.table_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(resource)
    return result


def _is_cross_tenant(resource: WorkspaceResource) -> bool:
    raw = resource.raw or {}
    meta = raw.get("result_meta") if isinstance(raw.get("result_meta"), dict) else raw
    return bool(isinstance(meta, dict) and meta.get("is_cross_tenant"))


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in keywords if keyword.strip())


def _strip_highlight(value: str) -> str:
    return re.sub(r"</?h[b]?>", "", value)


def _equals_check(actual: Any, expected: Any) -> dict[str, Any]:
    return {
        "status": "pass" if actual == expected else "fail",
        "actual": actual,
        "threshold": expected,
        "operator": "==",
    }


def _min_check(actual: int | float, threshold: int | float) -> dict[str, Any]:
    return {
        "status": "pass" if actual >= threshold else "fail",
        "actual": actual,
        "threshold": threshold,
        "operator": ">=",
    }


if __name__ == "__main__":
    raise SystemExit(main())
