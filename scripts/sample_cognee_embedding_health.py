#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "logs/cognee-embedding-long-run"
BOUNDARY = (
    "embedding_health_sample_collector_only; appends timestamped check_embedding_provider results for later "
    "long-run evidence collection, but does not prove a 24h service by itself"
)

Checker = Callable[[list[str], float], dict[str, Any]]
Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Append timestamped embedding provider health samples for Cognee/embedding long-run evidence. "
            "Use the output NDJSON as --embedding-sample-log for collect_cognee_embedding_long_run_evidence.py."
        )
    )
    parser.add_argument("--output", type=Path, default=None, help="NDJSON output path.")
    parser.add_argument("--summary-output", type=Path, default=None, help="Optional JSON summary output path.")
    parser.add_argument("--sample-count", type=int, default=1)
    parser.add_argument("--sample-interval-seconds", type=float, default=0.0)
    parser.add_argument("--text", default="生产部署参数")
    parser.add_argument("--model", default="")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--dimensions", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = sample_embedding_health(
        output=args.output,
        sample_count=args.sample_count,
        sample_interval_seconds=args.sample_interval_seconds,
        text=args.text,
        model=args.model,
        endpoint=args.endpoint,
        dimensions=args.dimensions,
        timeout=args.timeout,
    )
    if args.summary_output:
        args.summary_output.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.expanduser().write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def sample_embedding_health(
    *,
    output: Path | None = None,
    sample_count: int = 1,
    sample_interval_seconds: float = 0.0,
    text: str = "生产部署参数",
    model: str = "",
    endpoint: str = "",
    dimensions: int = 0,
    timeout: float = 60.0,
    checker: Checker | None = None,
    now_fn: Clock | None = None,
    sleep_fn: Sleeper | None = None,
) -> dict[str, Any]:
    if sample_count < 1:
        raise ValueError("sample_count must be >= 1")
    if sample_interval_seconds < 0:
        raise ValueError("sample_interval_seconds must be >= 0")
    out_path = (output or _default_output_path()).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_checker = checker or _run_embedding_check
    clock = now_fn or (lambda: datetime.now(timezone.utc))
    sleeper = sleep_fn or time.sleep
    command = _embedding_check_command(
        text=text, model=model, endpoint=endpoint, dimensions=dimensions, timeout=timeout
    )
    samples: list[dict[str, Any]] = []
    for index in range(sample_count):
        sampled_at = clock().astimezone(timezone.utc).isoformat()
        payload = run_checker(command, timeout)
        sample = _normalize_sample(payload, sampled_at=sampled_at, sample_index=index + 1)
        samples.append(sample)
        _append_ndjson(out_path, sample)
        if index < sample_count - 1 and sample_interval_seconds:
            sleeper(sample_interval_seconds)
    successful = [sample for sample in samples if sample.get("ok")]
    result = {
        "ok": len(successful) == len(samples),
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": clock().astimezone(timezone.utc).isoformat(),
        "output": str(out_path),
        "sample_count": len(samples),
        "successful_sample_count": len(successful),
        "failed_sample_count": len(samples) - len(successful),
        "first_sample_at": samples[0]["sampled_at"] if samples else "",
        "last_sample_at": samples[-1]["sampled_at"] if samples else "",
        "next_step": (
            "After the NDJSON covers >=24h and Cognee store reopen/readback is verified, pass it to "
            "scripts/collect_cognee_embedding_long_run_evidence.py as --embedding-sample-log."
        ),
        "collector_command_hint": (
            "python3 scripts/collect_cognee_embedding_long_run_evidence.py "
            "--curated-sync-report <curated-sync-report.json> "
            f"--embedding-sample-log {out_path} "
            "--store-reopened --reopened-search-ok "
            "--service-unit <service-unit> --oncall-owner <owner> "
            "--evidence-ref <non-secret-ref> --json"
        ),
    }
    return result


def format_report(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Cognee/Embedding Health Samples",
            f"ok: {str(result['ok']).lower()}",
            f"boundary: {result['boundary']}",
            f"output: {result['output']}",
            f"sample_count: {result['sample_count']}",
            f"successful_sample_count: {result['successful_sample_count']}",
            f"failed_sample_count: {result['failed_sample_count']}",
            f"next_step: {result['next_step']}",
        ]
    )


def _embedding_check_command(
    *,
    text: str,
    model: str,
    endpoint: str,
    dimensions: int,
    timeout: float,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts/check_embedding_provider.py"),
        "--text",
        text,
        "--timeout",
        str(timeout),
    ]
    if model:
        command.extend(["--model", model])
    if endpoint:
        command.extend(["--endpoint", endpoint])
    if dimensions:
        command.extend(["--dimensions", str(dimensions)])
    return command


def _run_embedding_check(command: list[str], timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout + 5,
        check=False,
    )
    payload = _parse_json(completed.stdout)
    if not isinstance(payload, dict):
        payload = {
            "ok": False,
            "status": "invalid_output",
            "stdout": completed.stdout[-1000:],
            "stderr": completed.stderr[-1000:],
        }
    payload["process_returncode"] = completed.returncode
    if completed.returncode != 0:
        payload["ok"] = False
    return payload


def _normalize_sample(payload: dict[str, Any], *, sampled_at: str, sample_index: int) -> dict[str, Any]:
    sample = dict(payload)
    sample["sampled_at"] = sampled_at
    sample["sample_index"] = sample_index
    sample["boundary"] = BOUNDARY
    if "endpoint" in sample:
        sample["endpoint"] = _redact_endpoint(str(sample["endpoint"]))
    return sample


def _append_ndjson(path: Path, sample: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_OUTPUT_ROOT / f"embedding-samples-{stamp}.ndjson"


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _redact_endpoint(endpoint: str) -> str:
    return endpoint.split("?", 1)[0].rstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
