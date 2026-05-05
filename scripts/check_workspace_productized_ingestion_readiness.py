#!/usr/bin/env python3
"""Validate evidence for productized Feishu workspace ingestion.

This is stricter than the controlled workspace readiness gate. It does not
perform ingestion and it does not make a production claim by itself; it only
checks whether a redacted evidence manifest proves the requirements that would
justify saying "full workspace ingestion is complete".
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evidence_patch_merge import (  # noqa: E402
    contains_any,
    count_number,
    flatten_strings,
    has_evidence_refs,
    is_iso_datetime,
    real_value,
)

DEFAULT_MANIFEST_PATH = ROOT / "deploy" / "workspace-ingestion.production-evidence.example.json"
SCHEMA_VERSION = "workspace_productized_ingestion_evidence/v1"
BOUNDARY = (
    "productized_workspace_ingestion_evidence_gate_only; does not run a crawler, create production storage, "
    "or prove full workspace ingestion without a non-example evidence manifest"
)
REQUIRED_SECTIONS = (
    "source_coverage",
    "discovery_and_cursoring",
    "rate_limit_and_backoff",
    "governance",
    "operations",
    "live_long_run",
)
REQUIRED_SOURCE_TYPES = ("document_feishu", "lark_sheet", "lark_bitable")
REQUIRED_WORKSPACE_SURFACES = ("document", "sheet", "bitable", "wiki")
SECRET_VALUE_MARKERS = (
    "app_secret=",
    "access_token=",
    "refresh_token=",
    "Bearer ",
    "sk-",
    "rightcode_",
)
PLACEHOLDER_MARKERS = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1")
_has_evidence_refs = partial(has_evidence_refs, placeholder_markers=PLACEHOLDER_MARKERS)
_real_value = partial(real_value, placeholder_markers=PLACEHOLDER_MARKERS)
_is_iso_datetime = is_iso_datetime
_count = count_number


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether Feishu workspace ingestion has production/full-workspace evidence."
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-productized-ready",
        action="store_true",
        help="Return non-zero unless every productized readiness check passes on a non-example manifest.",
    )
    args = parser.parse_args()

    report = run_productized_ingestion_check(Path(args.manifest).expanduser())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    if args.require_productized_ready and not report["goal_complete"]:
        return 1
    return 0 if report["ok"] else 1


def run_productized_ingestion_check(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        return _failure(
            manifest_path=manifest_path,
            check_name="manifest_file",
            description="Productized workspace ingestion evidence manifest exists.",
            details={"missing": str(manifest_path)},
            next_step="Create a redacted evidence manifest from deploy/workspace-ingestion.production-evidence.example.json.",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _failure(
            manifest_path=manifest_path,
            check_name="manifest_json",
            description="Productized workspace ingestion evidence manifest is valid JSON.",
            details={"error": str(exc)},
            next_step="Fix manifest JSON syntax before rerunning the productized workspace ingestion gate.",
        )
    if not isinstance(manifest, dict):
        manifest = {}

    is_example = bool(manifest.get("example"))
    checks = {
        "manifest_shape": _check_manifest_shape(manifest),
        "secret_redaction": _check_secret_redaction(manifest),
        "source_coverage": _check_source_coverage(manifest.get("source_coverage"), is_example=is_example),
        "discovery_and_cursoring": _check_discovery_and_cursoring(
            manifest.get("discovery_and_cursoring"), is_example=is_example
        ),
        "rate_limit_and_backoff": _check_rate_limit_and_backoff(
            manifest.get("rate_limit_and_backoff"), is_example=is_example
        ),
        "governance": _check_governance(manifest.get("governance"), is_example=is_example),
        "operations": _check_operations(manifest.get("operations"), is_example=is_example),
        "live_long_run": _check_live_long_run(manifest.get("live_long_run"), is_example=is_example),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] == "fail")
    warnings = sorted(name for name, check in checks.items() if check["status"] == "warning")
    goal_complete = not is_example and not failed and not warnings
    return {
        "ok": not failed,
        "goal_complete": goal_complete,
        "status": "pass" if goal_complete else "blocked",
        "example_manifest": is_example,
        "manifest_path": str(manifest_path),
        "boundary": BOUNDARY,
        "checks": checks,
        "failed_checks": failed,
        "warning_checks": warnings,
        "blockers": [] if goal_complete else _blockers_for(failed + warnings),
        "next_step": ""
        if goal_complete
        else "Collect organic source coverage, scheduler/cursor, rate-limit, governance, ops, and 24h+ long-run evidence.",
    }


def _check_manifest_shape(manifest: dict[str, Any]) -> dict[str, Any]:
    missing = [section for section in REQUIRED_SECTIONS if not isinstance(manifest.get(section), dict)]
    ok = manifest.get("schema_version") == SCHEMA_VERSION and not missing
    return {
        "status": "pass" if ok else "fail",
        "description": "Manifest uses the expected schema and contains every required evidence section.",
        "schema_version": manifest.get("schema_version"),
        "missing_sections": missing,
    }


def _check_secret_redaction(manifest: dict[str, Any]) -> dict[str, Any]:
    leaked = sorted({value for value in flatten_strings(manifest) if contains_any(value, SECRET_VALUE_MARKERS)})
    return {
        "status": "pass" if not leaked else "fail",
        "description": "Manifest does not contain token or secret-like values.",
        "leaked_value_count": len(leaked),
    }


def _check_source_coverage(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    sources = data.get("source_types") if isinstance(data.get("source_types"), dict) else {}
    surfaces = data.get("workspace_surfaces") if isinstance(data.get("workspace_surfaces"), dict) else {}
    checks = {
        f"{source_type}_organic_sample_count": _count(sources.get(source_type, {}).get("organic_sample_count")) >= 1
        for source_type in REQUIRED_SOURCE_TYPES
    }
    checks.update(
        {
            f"{surface}_workspace_surface_count": _count(surfaces.get(surface, {}).get("organic_sample_count")) >= 1
            for surface in REQUIRED_WORKSPACE_SURFACES
        }
    )
    checks.update(
        {
            "same_conclusion_across_chat_and_workspace": data.get("same_conclusion_across_chat_and_workspace") is True,
            "conflict_negative_proven": data.get("conflict_negative_proven") is True,
            "evidence_refs_present": _has_evidence_refs(data),
        }
    )
    return _section_result(
        checks,
        is_example=is_example,
        description="Organic workspace coverage includes docs, Sheets, Bitable, Wiki, same-conclusion, and conflict evidence.",
    )


def _check_discovery_and_cursoring(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "scheduler_enabled": data.get("scheduler_enabled") is True,
        "cursor_resume_proven": data.get("cursor_resume_proven") is True,
        "revision_skip_proven": data.get("revision_skip_proven") is True,
        "stale_marking_proven": data.get("stale_marking_proven") is True,
        "revocation_proven": data.get("revocation_proven") is True,
        "bounded_discovery_limits_present": _count(data.get("max_resources_per_run")) > 0
        and _count(data.get("max_pages_per_run")) > 0,
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Discovery proves scheduler, cursor resume, revision skip, stale marking, revocation, and bounds.",
    )


def _check_rate_limit_and_backoff(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "timeout_seconds_present": _count(data.get("timeout_seconds")) > 0,
        "backoff_policy_present": _real_value(data.get("backoff_policy")),
        "rate_limit_budget_present": _real_value(data.get("rate_limit_budget")),
        "throttling_or_retry_tested_at_is_iso": _is_iso_datetime(data.get("throttling_or_retry_tested_at")),
        "failed_fetch_audit_proven": data.get("failed_fetch_audit_proven") is True,
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Rate-limit evidence covers timeouts, backoff, retry/throttle tests, and failed-fetch audit.",
    )


def _check_governance(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "review_policy_enforced": data.get("review_policy_enforced") is True,
        "permission_fail_closed_negative_at_is_iso": _is_iso_datetime(data.get("permission_fail_closed_negative_at")),
        "no_raw_event_embedding": data.get("no_raw_event_embedding") is True,
        "curated_only_embedding": data.get("curated_only_embedding") is True,
        "audit_readback_proven": data.get("audit_readback_proven") is True,
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Governance proves review policy, fail-closed permission, curated-only embedding, and audit readback.",
    )


def _check_operations(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "single_listener_preflight_at_is_iso": _is_iso_datetime(data.get("single_listener_preflight_at")),
        "monitoring_alert_tested_at_is_iso": _is_iso_datetime(data.get("monitoring_alert_tested_at")),
        "rollback_stop_write_tested_at_is_iso": _is_iso_datetime(data.get("rollback_stop_write_tested_at")),
        "retention_policy_approved_at_is_iso": _is_iso_datetime(data.get("retention_policy_approved_at")),
        "dashboard_or_report_readback": data.get("dashboard_or_report_readback") is True,
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Operations proves single listener, monitoring, rollback, retention, and operator readback.",
    )


def _check_live_long_run(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "started_at_is_iso": _is_iso_datetime(data.get("started_at")),
        "ended_at_is_iso": _is_iso_datetime(data.get("ended_at")),
        "duration_hours_at_least_24": _count(data.get("duration_hours")) >= 24,
        "successful_runs_at_least_3": _count(data.get("successful_runs")) >= 3,
        "unresolved_failed_runs_zero": _count(data.get("unresolved_failed_runs")) == 0,
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Long-run evidence proves 24h+ productized workspace ingestion with successful runs and no unresolved failures.",
    )


def _section_result(checks: dict[str, bool], *, is_example: bool, description: str) -> dict[str, Any]:
    failed = sorted(name for name, passed in checks.items() if not passed)
    status = "pass" if not failed else ("warning" if is_example else "fail")
    return {
        "status": status,
        "description": description,
        "failed_subchecks": failed,
        "subchecks": checks,
    }


def _failure(
    *,
    manifest_path: Path,
    check_name: str,
    description: str,
    details: dict[str, Any],
    next_step: str,
) -> dict[str, Any]:
    check = {"status": "fail", "description": description, **details}
    return {
        "ok": False,
        "goal_complete": False,
        "status": "blocked",
        "example_manifest": False,
        "manifest_path": str(manifest_path),
        "boundary": BOUNDARY,
        "checks": {check_name: check},
        "failed_checks": [check_name],
        "warning_checks": [],
        "blockers": _blockers_for([check_name]),
        "next_step": next_step,
    }


def _blockers_for(names: list[str]) -> list[dict[str, str]]:
    descriptions = {
        "manifest_file": "No productized workspace ingestion evidence manifest was provided.",
        "manifest_json": "The evidence manifest is not valid JSON.",
        "manifest_shape": "The evidence manifest is missing schema or required sections.",
        "source_coverage": "Organic docs, Sheets, Bitable, Wiki, same-conclusion, or conflict evidence is incomplete.",
        "discovery_and_cursoring": "Scheduler, cursor, skip, stale, revocation, or bounded discovery evidence is incomplete.",
        "rate_limit_and_backoff": "Rate-limit, timeout, retry/backoff, or failed-fetch audit evidence is incomplete.",
        "governance": "Review policy, fail-closed permission, curated embedding, or audit evidence is incomplete.",
        "operations": "Single listener, monitoring, rollback, retention, or operator readback evidence is incomplete.",
        "live_long_run": "24h+ productized workspace ingestion long-run evidence is incomplete.",
        "secret_redaction": "The evidence manifest appears to contain secret-like values.",
    }
    return [{"check": name, "reason": descriptions.get(name, "Evidence is incomplete.")} for name in names]


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Productized Workspace Ingestion Readiness",
        f"status: {report['status']}",
        f"goal_complete: {str(report['goal_complete']).lower()}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(f"  {name}: {check['status']} - {check['description']}")
    if report["blockers"]:
        lines.append("")
        lines.append("blockers:")
        for blocker in report["blockers"]:
            lines.append(f"  - {blocker['check']}: {blocker['reason']}")
    if report.get("next_step"):
        lines.append("")
        lines.append(f"next_step: {report['next_step']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
