#!/usr/bin/env python3
"""Latency gate for controlled real lark-cli workspace fetches.

This gate intentionally invokes the existing workspace ingestion entrypoint
against a temporary SQLite DB. It measures the full subprocess path, including
lark-cli network fetch, source rendering, candidate routing, and registry writes.
It is not a production SLO and does not prove full workspace ingestion.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

BOUNDARY = (
    "controlled real lark-cli workspace fetch latency gate; temp SQLite only; "
    "no production SLO proof, no full workspace ingestion claim"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure controlled real lark-cli workspace fetch latency through the existing ingestion path."
    )
    parser.add_argument(
        "--resource",
        action="append",
        required=True,
        help="Explicit resource spec type:token[:title]. Resource identifiers are not echoed in the report.",
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
    parser.add_argument("--max-bitable-records", type=int, default=20)
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--elapsed-ms-max", type=float, default=45000.0)
    parser.add_argument("--per-resource-ms-max", type=float, default=45000.0)
    parser.add_argument("--min-source-count", type=int, default=1)
    parser.add_argument("--min-candidate-count", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not (args.actor_user_id or args.actor_open_id):
        parser.error("--actor-user-id or --actor-open-id is required")

    temp_db = tempfile.NamedTemporaryFile(prefix="fmc-real-fetch-latency-", suffix=".sqlite", delete=False)
    temp_db_path = temp_db.name
    temp_db.close()
    command = _build_ingest_command(args)
    env = os.environ.copy()
    env["MEMORY_DB_PATH"] = temp_db_path
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=max(60, int(args.elapsed_ms_max / 1000) + 30),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    ingest_output = _parse_json_output(completed.stdout)
    report = build_real_fetch_latency_report(
        ingest_output=ingest_output,
        returncode=completed.returncode,
        elapsed_ms=elapsed_ms,
        resource_count=len(args.resource),
        elapsed_ms_max=args.elapsed_ms_max,
        per_resource_ms_max=args.per_resource_ms_max,
        min_source_count=args.min_source_count,
        min_candidate_count=args.min_candidate_count,
    )
    if completed.returncode != 0:
        report["stderr_excerpt"] = completed.stderr[-1000:]
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def build_real_fetch_latency_report(
    *,
    ingest_output: dict[str, Any],
    returncode: int,
    elapsed_ms: float,
    resource_count: int,
    elapsed_ms_max: float,
    per_resource_ms_max: float,
    min_source_count: int,
    min_candidate_count: int,
) -> dict[str, Any]:
    source_count = int(ingest_output.get("source_count") or 0)
    candidate_count = int(ingest_output.get("candidate_count") or 0)
    failed_count = int(ingest_output.get("failed_count") or 0)
    fetched_count = int(ingest_output.get("fetched_count") or 0)
    result_count = int(ingest_output.get("result_count") or 0)
    per_resource_ms = elapsed_ms / max(1, resource_count)
    checks = {
        "ingest_command_ok": _equals_check(returncode, 0),
        "ingest_output_ok": _equals_check(bool(ingest_output.get("ok")), True),
        "no_failed_fetch": _equals_check(failed_count, 0),
        "min_source_count": _min_check(source_count, min_source_count),
        "min_candidate_count": _min_check(candidate_count, min_candidate_count),
        "elapsed_ms": _max_check(elapsed_ms, elapsed_ms_max),
        "per_resource_ms": _max_check(per_resource_ms, per_resource_ms_max),
    }
    failures = [name for name, check in checks.items() if check["status"] != "pass"]
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "boundary": BOUNDARY,
        "mode": "real_lark_cli_fetch_temp_db",
        "summary": {
            "elapsed_ms": round(elapsed_ms, 3),
            "per_resource_ms": round(per_resource_ms, 3),
            "resource_count": resource_count,
            "fetched_count": fetched_count,
            "source_count": source_count,
            "candidate_count": candidate_count,
            "failed_count": failed_count,
            "result_count": result_count,
            "run_status": ingest_output.get("mode"),
            "ingestion_boundary": ingest_output.get("boundary"),
        },
        "thresholds": {
            "elapsed_ms_max": elapsed_ms_max,
            "per_resource_ms_max": per_resource_ms_max,
            "min_source_count": min_source_count,
            "min_candidate_count": min_candidate_count,
        },
        "checks": checks,
        "route_counts": _route_counts(ingest_output),
        "source_type_counts": _source_type_counts(ingest_output),
        "failures": failures,
        "next_step": ""
        if not failures
        else "Investigate lark-cli fetch failures or latency before using this as workspace fetch evidence.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Real Fetch Latency Gate",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        f"elapsed_ms: {report['summary']['elapsed_ms']}",
        f"source_count: {report['summary']['source_count']}",
        f"candidate_count: {report['summary']['candidate_count']}",
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


def _build_ingest_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "feishu_workspace_ingest.py"),
        "--json",
        "--skip-discovery",
        "--scope",
        args.scope,
        "--tenant-id",
        args.tenant_id,
        "--organization-id",
        args.organization_id,
        "--roles",
        args.roles,
        "--as-identity",
        args.as_identity,
        "--max-sheet-rows",
        str(args.max_sheet_rows),
        "--max-bitable-records",
        str(args.max_bitable_records),
        "--candidate-limit",
        str(args.candidate_limit),
    ]
    if args.actor_user_id:
        command.extend(["--actor-user-id", args.actor_user_id])
    if args.actor_open_id:
        command.extend(["--actor-open-id", args.actor_open_id])
    if args.profile:
        command.extend(["--profile", args.profile])
    for resource in args.resource:
        command.extend(["--resource", resource])
    return command


def _parse_json_output(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _route_counts(ingest_output: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _result_items(ingest_output):
        resource = item.get("resource") if isinstance(item.get("resource"), dict) else {}
        route_type = str(resource.get("route_type") or "unknown")
        counts[route_type] = counts.get(route_type, 0) + 1
    return counts


def _source_type_counts(ingest_output: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _result_items(ingest_output):
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_type = source.get("source_type")
        if source_type:
            key = str(source_type)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _result_items(ingest_output: dict[str, Any]) -> list[dict[str, Any]]:
    results = ingest_output.get("results")
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


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


def _max_check(actual: int | float, threshold: int | float) -> dict[str, Any]:
    rounded = round(float(actual), 3)
    return {
        "status": "pass" if rounded <= threshold else "fail",
        "actual": rounded,
        "threshold": threshold,
        "operator": "<=",
    }


if __name__ == "__main__":
    raise SystemExit(main())
