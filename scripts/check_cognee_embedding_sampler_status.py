#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_cognee_embedding_long_run_evidence import (  # noqa: E402
    _normalize_embedding_sample,
    _read_embedding_samples,
    _sample_window_hours,
)

BOUNDARY = (
    "cognee_embedding_sampler_status_only; checks sampler liveness and sample-window progress, "
    "but does not create or prove long-run Cognee/embedding evidence by itself"
)

ProcessAlive = Callable[[int], bool]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether the Cognee embedding health sampler is still running and whether its sample log "
            "is ready for long-run evidence collection."
        )
    )
    parser.add_argument("--embedding-sample-log", required=True, type=Path)
    parser.add_argument("--pid-file", type=Path, default=None)
    parser.add_argument("--min-window-hours", type=float, default=24.0)
    parser.add_argument("--min-sample-count", type=int, default=3)
    parser.add_argument("--output", default="", help="Optional JSON status output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check_cognee_embedding_sampler_status(
        embedding_sample_log=args.embedding_sample_log,
        pid_file=args.pid_file,
        min_window_hours=args.min_window_hours,
        min_sample_count=args.min_sample_count,
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


def check_cognee_embedding_sampler_status(
    *,
    embedding_sample_log: Path,
    pid_file: Path | None = None,
    min_window_hours: float = 24.0,
    min_sample_count: int = 3,
    process_alive: ProcessAlive | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    now = (now_fn or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
    alive_fn = process_alive or _process_alive
    pid = _read_pid(pid_file)
    sampler_alive = bool(pid and alive_fn(pid))
    samples = _read_samples(embedding_sample_log)
    successful_samples = [_normalize_embedding_sample(sample) for sample in samples]
    successful_samples = [sample for sample in successful_samples if sample["ok"]]
    window_hours = _sample_window_hours(successful_samples)
    sample_count_ready = len(successful_samples) >= min_sample_count
    window_ready = window_hours >= min_window_hours
    completion_ready = sample_count_ready and window_ready
    first_sample_at = successful_samples[0]["sampled_at"] if successful_samples else ""
    last_sample_at = successful_samples[-1]["sampled_at"] if successful_samples else ""
    estimated_ready_at = _estimated_ready_at(first_sample_at, min_window_hours)
    checks = {
        "sampler_process_alive": _check(
            sampler_alive or completion_ready,
            "Sampler process is alive, or evidence already satisfies the requested sample window.",
            fail_when=not sampler_alive and not completion_ready,
            pid=pid,
            sampler_alive=sampler_alive,
        ),
        "embedding_successful_samples": _check(
            sample_count_ready,
            "Embedding sample log has enough successful provider checks.",
            fail_when=not sampler_alive and not sample_count_ready,
            min_sample_count=min_sample_count,
            successful_sample_count=len(successful_samples),
        ),
        "embedding_window": _check(
            window_ready,
            "Embedding sample log covers the requested evidence window.",
            fail_when=not sampler_alive and not window_ready,
            min_window_hours=min_window_hours,
            window_hours=round(window_hours, 4),
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] == "fail")
    warnings = sorted(name for name, check in checks.items() if check["status"] == "warning")
    return {
        "ok": not failed,
        "completion_ready": completion_ready,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": now.isoformat(),
        "embedding_sample_log": str(embedding_sample_log.expanduser()),
        "pid_file": str(pid_file.expanduser()) if pid_file else "",
        "pid": pid,
        "checks": checks,
        "failed_checks": failed,
        "warning_checks": warnings,
        "sample_count": len(samples),
        "successful_sample_count": len(successful_samples),
        "embedding_window_hours": round(window_hours, 4),
        "first_sample_at": first_sample_at,
        "last_sample_at": last_sample_at,
        "estimated_ready_at": estimated_ready_at,
        "collector_command_template": _collector_command_template(embedding_sample_log),
        "next_step": _next_step(
            completion_ready=completion_ready,
            sampler_alive=sampler_alive,
            sample_count_ready=sample_count_ready,
            window_ready=window_ready,
        ),
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Cognee Embedding Sampler Status",
        f"ok: {str(result['ok']).lower()}",
        f"completion_ready: {str(result['completion_ready']).lower()}",
        f"boundary: {result['boundary']}",
        f"sample_count: {result['sample_count']}",
        f"successful_sample_count: {result['successful_sample_count']}",
        f"embedding_window_hours: {result['embedding_window_hours']}",
        f"sampler_alive: {str(result['checks']['sampler_process_alive']['sampler_alive']).lower()}",
    ]
    if result["estimated_ready_at"]:
        lines.append(f"estimated_ready_at: {result['estimated_ready_at']}")
    if result["failed_checks"]:
        lines.append(f"failed_checks: {', '.join(result['failed_checks'])}")
    if result["warning_checks"]:
        lines.append(f"warning_checks: {', '.join(result['warning_checks'])}")
    if result["next_step"]:
        lines.append(f"next_step: {result['next_step']}")
    if result.get("collector_command_template"):
        lines.append(f"collector_command_template: {result['collector_command_template']}")
    return "\n".join(lines)


def _read_pid(pid_file: Path | None) -> int | None:
    if pid_file is None:
        return None
    try:
        value = pid_file.expanduser().read_text(encoding="utf-8").strip()
        return int(value)
    except (OSError, ValueError):
        return None


def _read_samples(path: Path) -> list[dict[str, Any]]:
    resolved = path.expanduser()
    if not resolved.exists():
        return []
    return list(_read_embedding_samples(resolved))


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _check(ok: bool, description: str, *, fail_when: bool, **details: Any) -> dict[str, Any]:
    if ok:
        status = "pass"
    elif fail_when:
        status = "fail"
    else:
        status = "warning"
    return {"status": status, "description": description, **details}


def _estimated_ready_at(first_sample_at: str, min_window_hours: float) -> str:
    parsed = _parse_datetime(first_sample_at)
    if parsed is None:
        return ""
    return (parsed + timedelta(hours=min_window_hours)).astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _next_step(
    *,
    completion_ready: bool,
    sampler_alive: bool,
    sample_count_ready: bool,
    window_ready: bool,
) -> str:
    if completion_ready:
        return "Run collect_cognee_embedding_long_run_evidence.py with this sample log and persistent readback proof."
    if sampler_alive:
        missing = []
        if not sample_count_ready:
            missing.append("more successful samples")
        if not window_ready:
            missing.append("the required time window")
        return f"Leave the sampler running until it collects {' and '.join(missing)}."
    return "Restart the embedding sampler before claiming long-run Cognee/embedding evidence."


def _collector_command_template(embedding_sample_log: Path) -> str:
    sample_arg = shlex.quote(str(embedding_sample_log.expanduser()))
    return (
        "python3 scripts/collect_cognee_embedding_long_run_evidence.py "
        "--curated-sync-report <cognee-curated-sync.json> "
        f"--embedding-sample-log {sample_arg} "
        "--persistent-readback-report <cognee-persistent-readback.json> "
        "--service-unit <service-or-supervisor-id> "
        "--oncall-owner <owner-or-team> "
        "--evidence-ref <non-secret-ops-log-or-path> "
        "--output <cognee-embedding-long-run-evidence.json> "
        "--json"
    )


if __name__ == "__main__":
    raise SystemExit(main())
