#!/usr/bin/env python3
"""Collect long-run evidence from workspace ingestion schedule reports."""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOUNDARY = (
    "workspace_ingestion_long_run_evidence_collector_only; normalizes existing schedule reports "
    "but does not run ingestion or prove productized full-workspace readiness by itself"
)
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect 24h+ workspace ingestion schedule evidence.")
    parser.add_argument("--schedule-report", type=Path, action="append", default=[])
    parser.add_argument("--schedule-report-glob", action="append", default=[])
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--min-window-hours", type=float, default=24.0)
    parser.add_argument("--min-successful-runs", type=int, default=3)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reports = _load_reports(args.schedule_report, args.schedule_report_glob)
    result = collect_workspace_ingestion_long_run_evidence(
        reports=reports,
        evidence_refs=args.evidence_ref,
        min_window_hours=args.min_window_hours,
        min_successful_runs=args.min_successful_runs,
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


def collect_workspace_ingestion_long_run_evidence(
    *,
    reports: list[dict[str, Any]],
    evidence_refs: list[str] | None = None,
    min_window_hours: float = 24.0,
    min_successful_runs: int = 3,
) -> dict[str, Any]:
    refs = list(evidence_refs or [])
    normalized = [_normalize_report(report) for report in reports]
    successful = [report for report in normalized if report["ok"]]
    unresolved_failed = [report for report in normalized if not report["ok"]]
    timestamps = [_parse_datetime(report["generated_at"]) for report in successful]
    timestamps = [item for item in timestamps if item is not None]
    window_hours = 0.0
    if len(timestamps) >= 2:
        window_hours = max(0.0, (max(timestamps) - min(timestamps)).total_seconds() / 3600.0)
    resource_counts = _merge_counts(report.get("resource_type_counts", {}) for report in successful)
    checks = {
        "successful_runs": _check(
            len(successful) >= min_successful_runs,
            "Enough successful schedule executions were collected.",
            successful_run_count=len(successful),
            min_successful_runs=min_successful_runs,
        ),
        "long_run_window": _check(
            window_hours >= min_window_hours,
            "Successful schedule executions cover the required long-run window.",
            window_hours=round(window_hours, 4),
            min_window_hours=min_window_hours,
        ),
        "no_unresolved_failed_runs": _check(
            not unresolved_failed,
            "No unresolved failed schedule executions are present in the evidence set.",
            unresolved_failed_runs=len(unresolved_failed),
        ),
        "evidence_refs_present": _check(
            _valid_evidence_refs(refs),
            "Evidence refs are present and do not contain secret-like values.",
            evidence_ref_count=len(refs),
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    started_at = min((item for item in timestamps), default=None)
    ended_at = max((item for item in timestamps), default=None)
    manifest_patch = {
        "live_long_run": {
            "started_at": started_at.isoformat() if started_at else "",
            "ended_at": ended_at.isoformat() if ended_at else "",
            "duration_hours": round(window_hours, 4),
            "successful_runs": len(successful),
            "unresolved_failed_runs": len(unresolved_failed),
            "evidence_refs": refs,
        },
        "discovery_and_cursoring": {
            "scheduler_enabled": bool(successful),
            "cursor_resume_proven": any(report.get("resume_cursor") for report in successful),
            "revision_skip_proven": any(report.get("skipped_unchanged_count", 0) > 0 for report in successful),
            "stale_marking_proven": any(report.get("stale_marked_count", 0) > 0 for report in successful),
            "revocation_proven": any(report.get("revocation_or_failed_fetch_seen") for report in successful),
            "max_resources_per_run": max((report.get("resource_count", 0) for report in successful), default=0),
            "max_pages_per_run": max((report.get("max_pages", 0) for report in successful), default=0),
            "evidence_refs": refs,
        },
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_checks": failed,
        "schedule_report_count": len(reports),
        "successful_run_count": len(successful),
        "unresolved_failed_run_count": len(unresolved_failed),
        "window_hours": round(window_hours, 4),
        "resource_type_counts": resource_counts,
        "production_manifest_patch": manifest_patch,
        "next_step": ""
        if not failed
        else "Collect more sanitized schedule reports across a 24h+ window and attach non-secret evidence refs.",
    }


def _normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    jobs = report.get("jobs") if isinstance(report.get("jobs"), list) else []
    pass_jobs = [job for job in jobs if isinstance(job, dict) and job.get("status") == "pass"]
    failed_jobs = report.get("failed_jobs") if isinstance(report.get("failed_jobs"), list) else []
    counts: dict[str, int] = {}
    resource_count = 0
    skipped_unchanged_count = 0
    stale_marked_count = 0
    revocation_or_failed_fetch_seen = False
    resume_cursor = False
    max_pages = 0
    for job in pass_jobs:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        counts = _merge_counts([counts, result.get("resource_type_counts") or _counts_from_resources(result)])
        resource_count += int(result.get("resource_count") or 0)
        skipped_unchanged_count += int(result.get("skipped_unchanged_count") or 0)
        stale_marked_count += int(result.get("stale_marked_count") or 0)
        revocation_or_failed_fetch_seen = revocation_or_failed_fetch_seen or int(result.get("failed_count") or 0) > 0
        resume_cursor = resume_cursor or "--resume-cursor" in job.get("command", [])
        max_pages = max(max_pages, _flag_int(job.get("command", []), "--max-pages"))
    return {
        "ok": bool(report.get("ok")) and report.get("mode") == "execute" and bool(pass_jobs) and not failed_jobs,
        "generated_at": str(report.get("generated_at") or ""),
        "resource_type_counts": counts,
        "resource_count": resource_count,
        "skipped_unchanged_count": skipped_unchanged_count,
        "stale_marked_count": stale_marked_count,
        "revocation_or_failed_fetch_seen": revocation_or_failed_fetch_seen,
        "resume_cursor": resume_cursor,
        "max_pages": max_pages,
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Long-run Evidence",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
        f"schedule_report_count: {result['schedule_report_count']}",
        f"successful_run_count: {result['successful_run_count']}",
        f"window_hours: {result['window_hours']}",
    ]
    if result["failed_checks"]:
        lines.append(f"failed_checks: {', '.join(result['failed_checks'])}")
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _load_reports(paths: list[Path], globs: list[str]) -> list[dict[str, Any]]:
    report_paths = [path.expanduser() for path in paths]
    for pattern in globs:
        report_paths.extend(sorted(Path(path).expanduser() for path in glob.glob(pattern)))
    reports = []
    for path in report_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path} must contain a JSON object")
        reports.append(payload)
    return reports


def _counts_from_resources(result: dict[str, Any]) -> dict[str, int]:
    resources = result.get("resources") if isinstance(result.get("resources"), list) else []
    counts: dict[str, int] = {}
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resource_type") or "unknown")
        counts[resource_type] = counts.get(resource_type, 0) + 1
    return counts


def _merge_counts(count_sets: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for counts in count_sets:
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            if isinstance(value, int):
                merged[str(key)] = merged.get(str(key), 0) + value
    return dict(sorted(merged.items()))


def _valid_evidence_refs(refs: list[str]) -> bool:
    return bool(refs) and all(isinstance(ref, str) and ref.strip() and not _contains_any(ref, SECRET_VALUE_MARKERS) for ref in refs)


def _flag_int(command: Any, flag: str) -> int:
    if not isinstance(command, list) or flag not in command:
        return 0
    index = command.index(flag) + 1
    if index >= len(command):
        return 0
    try:
        return int(command[index])
    except (TypeError, ValueError):
        return 0


def _check(ok: bool, description: str, **details: Any) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "description": description, **details}


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


if __name__ == "__main__":
    raise SystemExit(main())
