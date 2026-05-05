#!/usr/bin/env python3
"""Run a bounded Feishu workspace ingestion schedule.

This is a one-shot scheduler wrapper around scripts/feishu_workspace_ingest.py.
It is meant for cron/launchd/systemd timers and evidence collection. By
default it only returns the plan; pass --execute to run jobs sequentially.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evidence_patch_merge import contains_any, flatten_strings  # noqa: E402

DEFAULT_CONFIG_PATH = ROOT / "deploy" / "workspace-ingestion.schedule.example.json"
SCHEMA_VERSION = "workspace_ingestion_schedule/v1"
BOUNDARY = (
    "one_shot_workspace_ingestion_schedule_runner; plan mode has no external side effects; execute mode "
    "runs bounded feishu_workspace_ingest.py jobs sequentially and is not proof of productized long-run by itself"
)
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or run bounded Feishu workspace ingestion schedule jobs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--execute", action="store_true", help="Run enabled jobs. Default is plan-only.")
    parser.add_argument("--output", default="", help="Optional sanitized evidence report path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_schedule(Path(args.config).expanduser(), execute=args.execute)
    display_report = sanitize_report(report) if args.output else report
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(display_report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(display_report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(display_report))
    return 0 if report["ok"] else 1


def run_schedule(config_path: Path = DEFAULT_CONFIG_PATH, *, execute: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve()
    loaded = _load_config(config_path)
    if not loaded["ok"]:
        return loaded
    config = loaded["config"]
    jobs = config.get("jobs") if isinstance(config.get("jobs"), list) else []
    defaults = config.get("defaults") if isinstance(config.get("defaults"), dict) else {}

    planned_jobs = []
    for index, raw_job in enumerate(jobs):
        if not isinstance(raw_job, dict):
            planned_jobs.append(_job_failure(index=index, name=f"job_{index + 1}", reason="job_must_be_object"))
            continue
        planned_jobs.append(_build_job_plan(index=index, job=raw_job, defaults=defaults))

    enabled_jobs = [job for job in planned_jobs if job.get("enabled") and job.get("status") == "planned"]
    failed_jobs = [job for job in planned_jobs if job.get("status") == "invalid"]
    if execute:
        for job in enabled_jobs:
            _execute_job(job)
        failed_jobs = [job for job in planned_jobs if job.get("status") in {"invalid", "failed"}]

    ok = not failed_jobs
    return {
        "ok": ok,
        "mode": "execute" if execute else "plan",
        "status": "pass" if ok else "blocked",
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": config.get("schema_version"),
        "config_path": str(config_path),
        "job_count": len(planned_jobs),
        "enabled_job_count": len(enabled_jobs),
        "jobs": planned_jobs,
        "failed_jobs": [{"name": job["name"], "reason": job.get("reason", "failed")} for job in failed_jobs],
        "next_step": ""
        if ok
        else "Fix invalid or failed schedule jobs before using this as productized ingestion evidence.",
    }


def _load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {
            "ok": False,
            "status": "blocked",
            "mode": "plan",
            "boundary": BOUNDARY,
            "config_path": str(config_path),
            "jobs": [],
            "failed_jobs": [{"name": "config", "reason": "config_file_missing"}],
            "next_step": "Create a schedule config from deploy/workspace-ingestion.schedule.example.json.",
        }
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "status": "blocked",
            "mode": "plan",
            "boundary": BOUNDARY,
            "config_path": str(config_path),
            "jobs": [],
            "failed_jobs": [{"name": "config", "reason": "config_json_invalid", "error": str(exc)}],
            "next_step": "Fix schedule config JSON syntax.",
        }
    if not isinstance(config, dict):
        config = {}
    leaked = [value for value in flatten_strings(config) if contains_any(value, SECRET_VALUE_MARKERS)]
    if leaked:
        return {
            "ok": False,
            "status": "blocked",
            "mode": "plan",
            "boundary": BOUNDARY,
            "config_path": str(config_path),
            "jobs": [],
            "failed_jobs": [{"name": "config", "reason": "secret_like_value_present"}],
            "next_step": "Remove token or secret-like values from the schedule config.",
        }
    if config.get("schema_version") != SCHEMA_VERSION:
        return {
            "ok": False,
            "status": "blocked",
            "mode": "plan",
            "boundary": BOUNDARY,
            "config_path": str(config_path),
            "jobs": [],
            "failed_jobs": [{"name": "config", "reason": "schema_version_mismatch"}],
            "next_step": f"Set schema_version to {SCHEMA_VERSION}.",
        }
    return {"ok": True, "config": config}


def _build_job_plan(*, index: int, job: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    name = str(job.get("name") or f"job_{index + 1}")
    enabled = job.get("enabled", True) is True
    if not enabled:
        return {"name": name, "enabled": False, "status": "skipped", "command": []}

    merged = {**defaults, **job}
    validation_error = _validate_job(merged)
    if validation_error:
        return _job_failure(index=index, name=name, reason=validation_error)
    command = _build_ingest_command(merged)
    return {
        "name": name,
        "enabled": True,
        "status": "planned",
        "dry_run": merged.get("dry_run", True) is True,
        "timeout_seconds": int(merged.get("timeout_seconds") or 300),
        "retry_attempts": int(merged.get("retry_attempts") or 0),
        "retry_backoff_seconds": int(merged.get("retry_backoff_seconds") or 0),
        "command": command,
        "command_preview": _redact_command(command),
    }


def _validate_job(job: dict[str, Any]) -> str | None:
    if _int_value(job.get("limit")) <= 0:
        return "limit_must_be_positive"
    if _int_value(job.get("max_pages")) <= 0:
        return "max_pages_must_be_positive"
    if _int_value(job.get("timeout_seconds")) <= 0:
        return "timeout_seconds_must_be_positive"
    if _int_value(job.get("retry_attempts")) < 0:
        return "retry_attempts_must_be_non_negative"
    if _int_value(job.get("retry_backoff_seconds")) < 0:
        return "retry_backoff_seconds_must_be_non_negative"
    if not job.get("dry_run", True) and not (job.get("actor_user_id") or job.get("actor_open_id")):
        return "actor_required_for_non_dry_run_job"
    return None


def _build_ingest_command(job: dict[str, Any]) -> list[str]:
    command = [sys.executable, str(ROOT / "scripts" / "feishu_workspace_ingest.py"), "--json"]
    _append_value(command, "--query", job.get("query", ""))
    _append_csv(command, "--doc-types", job.get("doc_types", ["doc", "docx", "wiki", "sheet", "bitable"]))
    for key, flag in (
        ("edited_since", "--edited-since"),
        ("opened_since", "--opened-since"),
        ("created_since", "--created-since"),
        ("folder_tokens", "--folder-tokens"),
        ("space_ids", "--space-ids"),
        ("sort", "--sort"),
        ("scope", "--scope"),
        ("profile", "--profile"),
        ("as_identity", "--as-identity"),
        ("actor_user_id", "--actor-user-id"),
        ("actor_open_id", "--actor-open-id"),
        ("tenant_id", "--tenant-id"),
        ("organization_id", "--organization-id"),
        ("roles", "--roles"),
        ("folder_walk_tokens", "--folder-walk-tokens"),
        ("wiki_space_walk_ids", "--wiki-space-walk-ids"),
    ):
        _append_value(command, flag, job.get(key))
    for key, flag in (
        ("limit", "--limit"),
        ("max_pages", "--max-pages"),
        ("max_sheet_rows", "--max-sheet-rows"),
        ("max_bitable_records", "--max-bitable-records"),
        ("candidate_limit", "--candidate-limit"),
        ("walk_max_depth", "--walk-max-depth"),
        ("walk_page_size", "--walk-page-size"),
    ):
        _append_value(command, flag, job.get(key))
    for resource in job.get("resources") or []:
        _append_value(command, "--resource", resource)
    if job.get("mine") is True:
        command.append("--mine")
    if job.get("dry_run", True) is True:
        command.append("--dry-run")
    if job.get("resume_cursor") is True:
        command.append("--resume-cursor")
    if job.get("reset_cursor") is True:
        command.append("--reset-cursor")
    if job.get("mark_missing_stale") is True:
        command.append("--mark-missing-stale")
    if job.get("skip_discovery") is True:
        command.append("--skip-discovery")
    if job.get("folder_walk_root") is True:
        command.append("--folder-walk-root")
    return command


def _execute_job(job: dict[str, Any]) -> None:
    max_attempts = max(1, int(job.get("retry_attempts") or 0) + 1)
    attempts = []
    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        try:
            completed = subprocess.run(
                job["command"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=job["timeout_seconds"],
            )
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            attempt_result = _attempt_from_completed(attempt=attempt, completed=completed, elapsed_ms=elapsed_ms)
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            attempt_result = {
                "attempt": attempt,
                "returncode": None,
                "elapsed_ms": elapsed_ms,
                "ok": False,
                "reason": "ingestion_command_timeout",
                "stderr_preview": str(exc)[:1000],
            }
        attempts.append(attempt_result)
        if attempt_result["ok"]:
            job["status"] = "pass"
            job["returncode"] = attempt_result["returncode"]
            job["elapsed_ms"] = attempt_result["elapsed_ms"]
            job["result"] = attempt_result.get("result", {})
            job["attempt_count"] = attempt
            job["attempts"] = attempts
            return
        if attempt < max_attempts and int(job.get("retry_backoff_seconds") or 0) > 0:
            time.sleep(int(job["retry_backoff_seconds"]))
    last = attempts[-1]
    job["status"] = "failed"
    job["reason"] = last.get("reason", "ingestion_command_failed")
    job["returncode"] = last.get("returncode")
    job["elapsed_ms"] = last.get("elapsed_ms")
    job["attempt_count"] = len(attempts)
    job["attempts"] = attempts
    if last.get("stderr_preview"):
        job["stderr_preview"] = last["stderr_preview"]


def _attempt_from_completed(*, attempt: int, completed: subprocess.CompletedProcess[str], elapsed_ms: float) -> dict[str, Any]:
    try:
        result = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        result = {"stdout_preview": completed.stdout[:1000]}
    return {
        "attempt": attempt,
        "returncode": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "ok": completed.returncode == 0,
        "reason": "" if completed.returncode == 0 else "ingestion_command_failed",
        "result": result,
        "stderr_preview": completed.stderr[:1000] if completed.stderr else "",
    }


def sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a token-safe evidence report suitable for committing or archiving."""

    sanitized = copy.deepcopy(report)
    for job in sanitized.get("jobs", []):
        if isinstance(job, dict):
            job.pop("command", None)
            if "command_preview" in job:
                job["command"] = job.pop("command_preview")
            _sanitize_job_result(job)
            for attempt in job.get("attempts", []) or []:
                if isinstance(attempt, dict):
                    _sanitize_job_result(attempt)
    sanitized["sanitized"] = True
    return sanitized


def _sanitize_job_result(container: dict[str, Any]) -> None:
    result = container.get("result")
    if not isinstance(result, dict):
        return
    sensitive_values = _sensitive_values(result)
    _sanitize_discovery_cursor(result)
    resources = result.get("resources")
    if isinstance(resources, list):
        result["resource_type_counts"] = _resource_type_counts(resources)
        result["workspace_surface_counts"] = _workspace_surface_counts(resources)
        result["resources"] = [_sanitize_resource(resource) for resource in resources if isinstance(resource, dict)]
    results = result.get("results")
    if isinstance(results, list):
        result["resource_type_counts"] = _result_resource_type_counts(results)
        result["workspace_surface_counts"] = _result_workspace_surface_counts(results)
        result["source_type_counts"] = _source_type_counts(results)
        result["results"] = [
            _sanitize_ingestion_result(item, sensitive_values) for item in results if isinstance(item, dict)
        ]


def _sanitize_discovery_cursor(result: dict[str, Any]) -> None:
    discovery = result.get("discovery")
    if not isinstance(discovery, dict):
        return
    for key in ("start_page_token", "next_page_token"):
        if discovery.get(key):
            discovery[key] = "<redacted>"
    for key in ("cursor_before", "cursor_after"):
        cursor = discovery.get(key)
        if isinstance(cursor, dict) and cursor.get("page_token"):
            cursor["page_token"] = "<redacted>"


def _sanitize_ingestion_result(item: dict[str, Any], sensitive_values: set[str]) -> dict[str, Any]:
    sanitized = copy.deepcopy(item)
    resource = sanitized.get("resource")
    if isinstance(resource, dict):
        sanitized["resource"] = _sanitize_resource(resource)
    source = sanitized.get("source")
    if isinstance(source, dict):
        sanitized["source"] = {
            "source_type": source.get("source_type"),
            "source_id": "<redacted>" if source.get("source_id") else "",
            "title": source.get("title"),
        }
    for key in ("error", "reason", "error_code", "stderr_preview"):
        if isinstance(sanitized.get(key), str):
            sanitized[key] = _redact_known_values(sanitized[key], sensitive_values)
    return sanitized


def _sanitize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_type": resource.get("resource_type"),
        "route_type": resource.get("route_type"),
        "workspace_surface": _workspace_surface(resource),
        "title": resource.get("title"),
        "token": "<redacted>",
        "url": "<redacted>" if resource.get("url") else "",
    }


def _resource_type_counts(resources: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resource_type") or "unknown")
        counts[resource_type] = counts.get(resource_type, 0) + 1
    return dict(sorted(counts.items()))


def _workspace_surface_counts(resources: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        surface = _workspace_surface(resource)
        counts[surface] = counts.get(surface, 0) + 1
    return dict(sorted(counts.items()))


def _source_type_counts(results: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("ok") is False:
            continue
        source = item.get("source")
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("source_type") or "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1
    return dict(sorted(counts.items()))


def _result_workspace_surface_counts(results: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    seen_resources: set[tuple[str, str, str]] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        resource = item.get("resource")
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resource_type") or "unknown")
        route_type = str(resource.get("route_type") or "")
        token = str(resource.get("token") or "")
        key = (resource_type, route_type, token)
        if key in seen_resources:
            continue
        seen_resources.add(key)
        surface = _workspace_surface(resource)
        counts[surface] = counts.get(surface, 0) + 1
    return dict(sorted(counts.items()))


def _result_resource_type_counts(results: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    seen_resources: set[tuple[str, str, str]] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        resource = item.get("resource")
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resource_type") or "unknown")
        route_type = str(resource.get("route_type") or "")
        token = str(resource.get("token") or "")
        key = (resource_type, route_type, token)
        if key in seen_resources:
            continue
        seen_resources.add(key)
        counts[resource_type] = counts.get(resource_type, 0) + 1
    return dict(sorted(counts.items()))


def _workspace_surface(resource: dict[str, Any]) -> str:
    surface = str(resource.get("workspace_surface") or "").strip().lower()
    if surface:
        return surface
    resource_type = str(resource.get("resource_type") or "").strip().lower()
    route_type = str(resource.get("route_type") or "").strip().lower()
    if resource_type in {"doc", "docx", "document_feishu"}:
        return "document"
    if resource_type in {"sheet", "bitable", "wiki"}:
        return resource_type
    if route_type in {"document", "sheet", "bitable", "wiki"}:
        return route_type
    return resource_type or route_type or "unknown"


def _sensitive_values(value: Any) -> set[str]:
    values: set[str] = set()
    sensitive_keys = {"token", "url", "source_id", "page_token", "start_page_token", "next_page_token"}

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child_value in item.items():
                visit(child_value, str(child_key))
            return
        if isinstance(item, list):
            for child in item:
                visit(child, key)
            return
        if key in sensitive_keys and isinstance(item, str) and item.strip():
            values.add(item)

    visit(value)
    return values


def _redact_known_values(text: str, sensitive_values: set[str]) -> str:
    redacted = text
    for value in sorted(sensitive_values, key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


def _job_failure(*, index: int, name: str, reason: str) -> dict[str, Any]:
    return {"name": name or f"job_{index + 1}", "enabled": True, "status": "invalid", "reason": reason, "command": []}


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Workspace Ingestion Schedule",
        f"status: {report['status']}",
        f"mode: {report['mode']}",
        f"boundary: {report['boundary']}",
        "",
        "jobs:",
    ]
    for job in report["jobs"]:
        lines.append(f"  {job['name']}: {job['status']}")
    if report["failed_jobs"]:
        lines.append("")
        lines.append("failed_jobs:")
        for job in report["failed_jobs"]:
            lines.append(f"  - {job['name']}: {job['reason']}")
    return "\n".join(lines)


def _append_value(command: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    command.extend([flag, str(value)])


def _append_csv(command: list[str], flag: str, value: Any) -> None:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if items:
            command.extend([flag, ",".join(items)])
    elif value:
        command.extend([flag, str(value)])


def _redact_command(command: list[str]) -> list[str]:
    redacted = []
    redact_next_flags = {
        "--resource",
        "--folder-tokens",
        "--space-ids",
        "--folder-walk-tokens",
        "--wiki-space-walk-ids",
        "--actor-user-id",
        "--actor-open-id",
        "--creator-ids",
        "--sharer-ids",
        "--chat-ids",
    }
    redact_next = False
    for part in command:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        redacted.append(part)
        if part in redact_next_flags:
            redact_next = True
    return redacted


def _int_value(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
