#!/usr/bin/env python3
"""Collect source-coverage evidence for productized workspace ingestion."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_workspace_productized_ingestion_readiness import (
    PLACEHOLDER_MARKERS,
    REQUIRED_SOURCE_TYPES,
    SECRET_VALUE_MARKERS,
)

BOUNDARY = (
    "workspace_source_coverage_evidence_collector_only; normalizes existing redacted evidence reports "
    "into a source_coverage manifest patch, but does not run ingestion or prove full workspace readiness"
)
WORKSPACE_SOURCE_TYPES = {"document_feishu", "lark_doc", "lark_sheet", "lark_bitable", "wiki"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect workspace source-coverage evidence.")
    parser.add_argument("--evidence-report", type=Path, action="append", default=[])
    parser.add_argument("--evidence-report-glob", action="append", default=[])
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--min-organic-samples", type=int, default=1)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reports = _load_reports(args.evidence_report, args.evidence_report_glob)
    result = collect_workspace_source_coverage_evidence(
        reports=reports,
        evidence_refs=args.evidence_ref,
        min_organic_samples=args.min_organic_samples,
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


def collect_workspace_source_coverage_evidence(
    *,
    reports: list[dict[str, Any]],
    evidence_refs: list[str] | None = None,
    min_organic_samples: int = 1,
) -> dict[str, Any]:
    refs = list(evidence_refs or [])
    source_counts: dict[str, int] = {}
    report_summaries: list[dict[str, Any]] = []
    same_conclusion = False
    conflict_negative = False
    usable_report_count = 0

    for index, report in enumerate(reports):
        normalized = _normalize_report(report)
        report_summaries.append(
            {
                "index": index,
                "usable": normalized["usable"],
                "mode": normalized["mode"],
                "source_type_counts": normalized["source_type_counts"],
                "same_conclusion": normalized["same_conclusion"],
                "conflict_negative": normalized["conflict_negative"],
            }
        )
        if not normalized["usable"]:
            continue
        usable_report_count += 1
        source_counts = _merge_counts([source_counts, normalized["source_type_counts"]])
        same_conclusion = same_conclusion or normalized["same_conclusion"]
        conflict_negative = conflict_negative or normalized["conflict_negative"]

    checks = {
        f"{source_type}_organic_sample_count": _check(
            source_counts.get(source_type, 0) >= min_organic_samples,
            "Required organic source type has enough usable samples.",
            actual=source_counts.get(source_type, 0),
            threshold=min_organic_samples,
        )
        for source_type in REQUIRED_SOURCE_TYPES
    }
    checks.update(
        {
            "same_conclusion_across_chat_and_workspace": _check(
                same_conclusion,
                "At least one report proves a chat fact is corroborated by a workspace source.",
            ),
            "conflict_negative_proven": _check(
                conflict_negative,
                "At least one report proves conflicting workspace evidence does not overwrite active memory.",
            ),
            "evidence_refs_present": _check(
                _valid_evidence_refs(refs),
                "Evidence refs are present and do not contain placeholder or secret-like values.",
                evidence_ref_count=len(refs),
            ),
        }
    )
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    manifest_patch = {
        "source_coverage": {
            "source_types": {
                source_type: {"organic_sample_count": int(source_counts.get(source_type, 0))}
                for source_type in REQUIRED_SOURCE_TYPES
            },
            "same_conclusion_across_chat_and_workspace": same_conclusion,
            "conflict_negative_proven": conflict_negative,
            "evidence_refs": refs,
        }
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_report_count": len(reports),
        "usable_report_count": usable_report_count,
        "source_type_counts": dict(sorted(source_counts.items())),
        "checks": checks,
        "failed_checks": failed,
        "reports": report_summaries,
        "production_manifest_patch": manifest_patch,
        "next_step": ""
        if not failed
        else "Attach redacted passing reports for every required source type plus same-conclusion and conflict-negative evidence.",
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Workspace Source Coverage Evidence",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
        f"evidence_report_count: {result['evidence_report_count']}",
        f"usable_report_count: {result['usable_report_count']}",
        f"source_type_counts: {json.dumps(result['source_type_counts'], ensure_ascii=False, sort_keys=True)}",
    ]
    if result["failed_checks"]:
        lines.append(f"failed_checks: {', '.join(result['failed_checks'])}")
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    usable = _report_passed(report)
    source_counts = _source_counts_from_report(report)
    return {
        "usable": usable,
        "mode": str(report.get("mode") or report.get("boundary") or ""),
        "source_type_counts": source_counts,
        "same_conclusion": usable and _proves_same_conclusion(report),
        "conflict_negative": usable and _proves_conflict_negative(report),
    }


def _report_passed(report: dict[str, Any]) -> bool:
    if report.get("ok") is not True:
        return False
    if report.get("status") and report.get("status") != "pass":
        return False
    failures = report.get("failures") or report.get("failed_checks") or []
    return not failures


def _source_counts_from_report(report: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    counts = _merge_counts([counts, _known_source_counts(report.get("source_type_counts"))])
    counts = _merge_counts([counts, _source_counts_from_results(report.get("results"))])
    counts = _merge_counts([counts, _source_counts_from_resource_results(report.get("resource_results"))])
    counts = _merge_counts([counts, _source_counts_from_manifest_patch(report)])

    jobs = report.get("jobs") if isinstance(report.get("jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict) or job.get("status") != "pass":
            continue
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        counts = _merge_counts([counts, _source_counts_from_report(result)])
    return dict(sorted(counts.items()))


def _source_counts_from_results(results: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(results, list):
        return counts
    for item in results:
        if not isinstance(item, dict) or item.get("ok") is False:
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_type = source.get("source_type")
        if source_type in WORKSPACE_SOURCE_TYPES:
            counts[str(source_type)] = counts.get(str(source_type), 0) + 1
        resource = item.get("resource") if isinstance(item.get("resource"), dict) else {}
        if item.get("source") and resource.get("resource_type") == "wiki":
            counts["wiki"] = counts.get("wiki", 0) + 1
    return counts


def _source_counts_from_resource_results(resource_results: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(resource_results, list):
        return counts
    for item in resource_results:
        if not isinstance(item, dict) or item.get("ok") is False:
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_type = source.get("source_type")
        if source_type in WORKSPACE_SOURCE_TYPES:
            counts[str(source_type)] = counts.get(str(source_type), 0) + 1
    return counts


def _source_counts_from_manifest_patch(report: dict[str, Any]) -> dict[str, int]:
    patch = report.get("production_manifest_patch")
    if not isinstance(patch, dict):
        return {}
    source_coverage = patch.get("source_coverage")
    if not isinstance(source_coverage, dict):
        return {}
    source_types = source_coverage.get("source_types")
    if not isinstance(source_types, dict):
        return {}
    counts: dict[str, int] = {}
    for source_type, payload in source_types.items():
        if source_type not in WORKSPACE_SOURCE_TYPES or not isinstance(payload, dict):
            continue
        count = payload.get("organic_sample_count")
        if isinstance(count, int) and count > 0:
            counts[str(source_type)] = count
    return counts


def _known_source_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        if key in WORKSPACE_SOURCE_TYPES and isinstance(count, int) and count > 0:
            counts[str(key)] = count
    return counts


def _proves_same_conclusion(report: dict[str, Any]) -> bool:
    if report.get("strict_same_conclusion_gate_passed") is True:
        return True
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if int(summary.get("same_fact_match_count") or 0) >= 1:
        return True
    if int(summary.get("matching_resource_source_count") or 0) >= 1:
        source_types = set(report.get("active_evidence_source_types") or [])
        return "feishu_message" in source_types and bool(source_types & WORKSPACE_SOURCE_TYPES)
    patch = report.get("production_manifest_patch")
    source_coverage = patch.get("source_coverage") if isinstance(patch, dict) else {}
    return isinstance(source_coverage, dict) and source_coverage.get("same_conclusion_across_chat_and_workspace") is True


def _proves_conflict_negative(report: dict[str, Any]) -> bool:
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    if checks.get("bitable_conflict_candidate_created") is True:
        return True
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    conflict_sources = evidence.get("conflict_evidence_source_types")
    if isinstance(conflict_sources, list) and bool(set(conflict_sources) & WORKSPACE_SOURCE_TYPES):
        return True
    patch = report.get("production_manifest_patch")
    source_coverage = patch.get("source_coverage") if isinstance(patch, dict) else {}
    return isinstance(source_coverage, dict) and source_coverage.get("conflict_negative_proven") is True


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


def _valid_evidence_refs(refs: list[str]) -> bool:
    unsafe_markers = (*PLACEHOLDER_MARKERS, *SECRET_VALUE_MARKERS)
    return bool(refs) and all(isinstance(ref, str) and ref.strip() and not _contains_any(ref, unsafe_markers) for ref in refs)


def _merge_counts(count_sets: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for counts in count_sets:
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            if isinstance(value, int):
                merged[str(key)] = merged.get(str(key), 0) + value
    return dict(sorted(merged.items()))


def _check(ok: bool, description: str, **details: Any) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "description": description, **details}


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


if __name__ == "__main__":
    raise SystemExit(main())
