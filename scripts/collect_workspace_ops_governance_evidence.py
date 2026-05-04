#!/usr/bin/env python3
"""Collect ops, governance, and rate-limit evidence for workspace ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_workspace_productized_ingestion_readiness import (  # noqa: E402
    PLACEHOLDER_MARKERS,
    SECRET_VALUE_MARKERS,
)

BOUNDARY = (
    "workspace_ops_governance_evidence_collector_only; normalizes operator-provided external evidence refs "
    "into rate_limit/governance/operations manifest patches, but does not run production ingestion"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build workspace ingestion rate-limit, governance, and operations evidence patch sections."
    )
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--backoff-policy", required=True)
    parser.add_argument("--rate-limit-budget", required=True)
    parser.add_argument("--throttling-or-retry-tested-at", required=True)
    parser.add_argument("--failed-fetch-audit-proven", action="store_true")
    parser.add_argument("--rate-limit-evidence-ref", action="append", default=[])
    parser.add_argument("--review-policy-enforced", action="store_true")
    parser.add_argument("--permission-fail-closed-negative-at", required=True)
    parser.add_argument("--no-raw-event-embedding", action="store_true")
    parser.add_argument("--curated-only-embedding", action="store_true")
    parser.add_argument("--audit-readback-proven", action="store_true")
    parser.add_argument("--governance-evidence-ref", action="append", default=[])
    parser.add_argument("--single-listener-preflight-at", required=True)
    parser.add_argument("--monitoring-alert-tested-at", required=True)
    parser.add_argument("--rollback-stop-write-tested-at", required=True)
    parser.add_argument("--retention-policy-approved-at", required=True)
    parser.add_argument("--dashboard-or-report-readback", action="store_true")
    parser.add_argument("--operations-evidence-ref", action="append", default=[])
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = collect_workspace_ops_governance_evidence(
        timeout_seconds=args.timeout_seconds,
        backoff_policy=args.backoff_policy,
        rate_limit_budget=args.rate_limit_budget,
        throttling_or_retry_tested_at=args.throttling_or_retry_tested_at,
        failed_fetch_audit_proven=args.failed_fetch_audit_proven,
        rate_limit_evidence_refs=args.rate_limit_evidence_ref,
        review_policy_enforced=args.review_policy_enforced,
        permission_fail_closed_negative_at=args.permission_fail_closed_negative_at,
        no_raw_event_embedding=args.no_raw_event_embedding,
        curated_only_embedding=args.curated_only_embedding,
        audit_readback_proven=args.audit_readback_proven,
        governance_evidence_refs=args.governance_evidence_ref,
        single_listener_preflight_at=args.single_listener_preflight_at,
        monitoring_alert_tested_at=args.monitoring_alert_tested_at,
        rollback_stop_write_tested_at=args.rollback_stop_write_tested_at,
        retention_policy_approved_at=args.retention_policy_approved_at,
        dashboard_or_report_readback=args.dashboard_or_report_readback,
        operations_evidence_refs=args.operations_evidence_ref,
    )
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def collect_workspace_ops_governance_evidence(
    *,
    timeout_seconds: int,
    backoff_policy: str,
    rate_limit_budget: str,
    throttling_or_retry_tested_at: str,
    failed_fetch_audit_proven: bool,
    rate_limit_evidence_refs: list[str],
    review_policy_enforced: bool,
    permission_fail_closed_negative_at: str,
    no_raw_event_embedding: bool,
    curated_only_embedding: bool,
    audit_readback_proven: bool,
    governance_evidence_refs: list[str],
    single_listener_preflight_at: str,
    monitoring_alert_tested_at: str,
    rollback_stop_write_tested_at: str,
    retention_policy_approved_at: str,
    dashboard_or_report_readback: bool,
    operations_evidence_refs: list[str],
) -> dict[str, Any]:
    checks = {
        "rate_limit_and_backoff": _rate_limit_check(
            timeout_seconds=timeout_seconds,
            backoff_policy=backoff_policy,
            rate_limit_budget=rate_limit_budget,
            throttling_or_retry_tested_at=throttling_or_retry_tested_at,
            failed_fetch_audit_proven=failed_fetch_audit_proven,
            evidence_refs=rate_limit_evidence_refs,
        ),
        "governance": _governance_check(
            review_policy_enforced=review_policy_enforced,
            permission_fail_closed_negative_at=permission_fail_closed_negative_at,
            no_raw_event_embedding=no_raw_event_embedding,
            curated_only_embedding=curated_only_embedding,
            audit_readback_proven=audit_readback_proven,
            evidence_refs=governance_evidence_refs,
        ),
        "operations": _operations_check(
            single_listener_preflight_at=single_listener_preflight_at,
            monitoring_alert_tested_at=monitoring_alert_tested_at,
            rollback_stop_write_tested_at=rollback_stop_write_tested_at,
            retention_policy_approved_at=retention_policy_approved_at,
            dashboard_or_report_readback=dashboard_or_report_readback,
            evidence_refs=operations_evidence_refs,
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    patch = {
        "rate_limit_and_backoff": {
            "timeout_seconds": timeout_seconds,
            "backoff_policy": backoff_policy,
            "rate_limit_budget": rate_limit_budget,
            "throttling_or_retry_tested_at": throttling_or_retry_tested_at,
            "failed_fetch_audit_proven": failed_fetch_audit_proven,
            "evidence_refs": list(rate_limit_evidence_refs),
        },
        "governance": {
            "review_policy_enforced": review_policy_enforced,
            "permission_fail_closed_negative_at": permission_fail_closed_negative_at,
            "no_raw_event_embedding": no_raw_event_embedding,
            "curated_only_embedding": curated_only_embedding,
            "audit_readback_proven": audit_readback_proven,
            "evidence_refs": list(governance_evidence_refs),
        },
        "operations": {
            "single_listener_preflight_at": single_listener_preflight_at,
            "monitoring_alert_tested_at": monitoring_alert_tested_at,
            "rollback_stop_write_tested_at": rollback_stop_write_tested_at,
            "retention_policy_approved_at": retention_policy_approved_at,
            "dashboard_or_report_readback": dashboard_or_report_readback,
            "evidence_refs": list(operations_evidence_refs),
        },
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_checks": failed,
        "production_manifest_patch": patch,
        "next_step": "" if not failed else "Fill real non-secret evidence refs and timestamps before merging.",
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Ops/Governance Evidence",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
    ]
    for section, check in result["checks"].items():
        lines.append(f"{section}: {check['status']}")
    if result["failed_checks"]:
        lines.append(f"failed_checks: {', '.join(result['failed_checks'])}")
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _rate_limit_check(
    *,
    timeout_seconds: int,
    backoff_policy: str,
    rate_limit_budget: str,
    throttling_or_retry_tested_at: str,
    failed_fetch_audit_proven: bool,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return _section_result(
        "Rate-limit evidence covers timeout, backoff, budget, retry/throttle test, failed-fetch audit, and refs.",
        {
            "timeout_seconds_present": timeout_seconds > 0,
            "backoff_policy_present": _real_value(backoff_policy),
            "rate_limit_budget_present": _real_value(rate_limit_budget),
            "throttling_or_retry_tested_at_is_iso": _is_iso_datetime(throttling_or_retry_tested_at),
            "failed_fetch_audit_proven": failed_fetch_audit_proven is True,
            "evidence_refs_present": _valid_evidence_refs(evidence_refs),
        },
    )


def _governance_check(
    *,
    review_policy_enforced: bool,
    permission_fail_closed_negative_at: str,
    no_raw_event_embedding: bool,
    curated_only_embedding: bool,
    audit_readback_proven: bool,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return _section_result(
        "Governance evidence covers review policy, permission negative, curated-only embedding, audit, and refs.",
        {
            "review_policy_enforced": review_policy_enforced is True,
            "permission_fail_closed_negative_at_is_iso": _is_iso_datetime(permission_fail_closed_negative_at),
            "no_raw_event_embedding": no_raw_event_embedding is True,
            "curated_only_embedding": curated_only_embedding is True,
            "audit_readback_proven": audit_readback_proven is True,
            "evidence_refs_present": _valid_evidence_refs(evidence_refs),
        },
    )


def _operations_check(
    *,
    single_listener_preflight_at: str,
    monitoring_alert_tested_at: str,
    rollback_stop_write_tested_at: str,
    retention_policy_approved_at: str,
    dashboard_or_report_readback: bool,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return _section_result(
        "Operations evidence covers single listener, monitoring, rollback, retention, readback, and refs.",
        {
            "single_listener_preflight_at_is_iso": _is_iso_datetime(single_listener_preflight_at),
            "monitoring_alert_tested_at_is_iso": _is_iso_datetime(monitoring_alert_tested_at),
            "rollback_stop_write_tested_at_is_iso": _is_iso_datetime(rollback_stop_write_tested_at),
            "retention_policy_approved_at_is_iso": _is_iso_datetime(retention_policy_approved_at),
            "dashboard_or_report_readback": dashboard_or_report_readback is True,
            "evidence_refs_present": _valid_evidence_refs(evidence_refs),
        },
    )


def _section_result(description: str, checks: dict[str, bool]) -> dict[str, Any]:
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "pass" if not failed else "fail",
        "description": description,
        "failed_subchecks": failed,
        "subchecks": checks,
    }


def _valid_evidence_refs(refs: list[str]) -> bool:
    unsafe_markers = (*PLACEHOLDER_MARKERS, *SECRET_VALUE_MARKERS)
    return bool(refs) and all(isinstance(ref, str) and ref.strip() and not _contains_any(ref, unsafe_markers) for ref in refs)


def _real_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_any(value, (*PLACEHOLDER_MARKERS, *SECRET_VALUE_MARKERS))


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if _contains_any(value, (*PLACEHOLDER_MARKERS, *SECRET_VALUE_MARKERS)):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


if __name__ == "__main__":
    raise SystemExit(main())
