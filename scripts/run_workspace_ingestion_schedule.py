#!/usr/bin/env python3
"""Run a bounded Feishu workspace ingestion schedule.

This is a one-shot scheduler wrapper around scripts/feishu_workspace_ingest.py.
It is meant for cron/launchd/systemd timers and evidence collection. By
default it only returns the plan; pass --execute to run jobs sequentially.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_schedule(Path(args.config).expanduser(), execute=args.execute)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
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
    leaked = [value for value in _flatten_strings(config) if _contains_any(value, SECRET_VALUE_MARKERS)]
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
    started = time.monotonic()
    completed = subprocess.run(
        job["command"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=job["timeout_seconds"],
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    job["elapsed_ms"] = elapsed_ms
    job["returncode"] = completed.returncode
    try:
        job["result"] = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        job["result"] = {"stdout_preview": completed.stdout[:1000]}
    if completed.returncode == 0:
        job["status"] = "pass"
    else:
        job["status"] = "failed"
        job["reason"] = "ingestion_command_failed"
        job["stderr_preview"] = completed.stderr[:1000]


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
    redact_next_flags = {"--resource", "--folder-tokens", "--space-ids", "--folder-walk-tokens", "--wiki-space-walk-ids"}
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


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_flatten_strings(item))
        return result
    return []


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


if __name__ == "__main__":
    raise SystemExit(main())
