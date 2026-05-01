#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import ADMIN_TOKEN_ENV_NAMES

BOUNDARY = (
    "productized_live_long_run_evidence_collector_only; does not create production DB, IdP, TLS, "
    "monitoring, rollback, or production readiness by itself"
)
REQUIRED_SAMPLE_PATHS = ("/healthz", "/api/health", "/api/launch-readiness", "/api/graph-quality", "/metrics")


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: str
    error: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Copilot Admin long-run health evidence from a running admin backend. "
            "This emits a production-evidence manifest patch, but does not claim production readiness."
        )
    )
    parser.add_argument("--base-url", required=True, help="Admin backend base URL, e.g. https://memory.example.com.")
    parser.add_argument(
        "--token",
        default=None,
        help="Admin or viewer bearer token. Defaults to FEISHU_MEMORY_COPILOT_ADMIN_TOKEN / COPILOT_ADMIN_TOKEN.",
    )
    parser.add_argument("--sample-count", type=int, default=3, help="Number of health samples to collect.")
    parser.add_argument(
        "--sample-interval-seconds",
        type=float,
        default=60.0,
        help="Delay between samples. Use 3600 with --sample-count 25 for a 24h window.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP timeout per endpoint.")
    parser.add_argument(
        "--min-window-hours",
        type=float,
        default=0.0,
        help="Minimum observed window for this collector to return ok. Use 24 for production evidence.",
    )
    parser.add_argument("--min-sample-count", type=int, default=3, help="Minimum successful sample count.")
    parser.add_argument("--service-unit", default="copilot-admin.service", help="Service unit or deployment id.")
    parser.add_argument("--oncall-owner", default="", help="On-call owner for the production evidence patch.")
    parser.add_argument(
        "--rollback-drill-at",
        default="",
        help="ISO-8601 rollback drill timestamp. Required for a production-ready manifest patch.",
    )
    parser.add_argument(
        "--evidence-ref",
        default="",
        help="Evidence reference to include in the manifest patch, such as an ops log or dashboard URL.",
    )
    parser.add_argument("--output", default="", help="Optional JSON output file path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = collect_long_run_evidence(
        base_url=args.base_url,
        token=args.token or _admin_token_from_env(),
        sample_count=args.sample_count,
        sample_interval_seconds=args.sample_interval_seconds,
        timeout_seconds=args.timeout_seconds,
        min_window_hours=args.min_window_hours,
        min_sample_count=args.min_sample_count,
        service_unit=args.service_unit,
        oncall_owner=args.oncall_owner,
        rollback_drill_at=args.rollback_drill_at,
        evidence_ref=args.evidence_ref,
    )
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


def collect_long_run_evidence(
    *,
    base_url: str,
    token: str | None,
    sample_count: int = 3,
    sample_interval_seconds: float = 60.0,
    timeout_seconds: float = 10.0,
    min_window_hours: float = 0.0,
    min_sample_count: int = 3,
    service_unit: str = "copilot-admin.service",
    oncall_owner: str = "",
    rollback_drill_at: str = "",
    evidence_ref: str = "",
    fetcher: Callable[[str, str | None, float], HttpResult] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    if sample_count < 1:
        raise ValueError("sample_count must be >= 1")
    if min_sample_count < 1:
        raise ValueError("min_sample_count must be >= 1")
    if sample_interval_seconds < 0:
        raise ValueError("sample_interval_seconds must be >= 0")
    fetch = fetcher or _http_get
    now = now_fn or _utc_now
    sleep = sleep_fn or time.sleep
    samples: list[dict[str, Any]] = []
    for index in range(sample_count):
        sampled_at = now()
        samples.append(
            _collect_sample(
                base_url=base_url,
                token=token,
                timeout_seconds=timeout_seconds,
                sampled_at=sampled_at,
                fetcher=fetch,
                sample_index=index,
            )
        )
        if index + 1 < sample_count and sample_interval_seconds:
            sleep(sample_interval_seconds)

    successful_samples = [sample for sample in samples if sample["status"] == "pass"]
    started_at = samples[0]["sampled_at"] if samples else _isoformat(now())
    ended_at = samples[-1]["sampled_at"] if samples else started_at
    evidence_window_hours = _hours_between(started_at, ended_at)
    manifest_patch = {
        "productized_live_long_run": {
            "service_unit": service_unit,
            "started_at": started_at,
            "evidence_window_hours": round(evidence_window_hours, 4),
            "healthcheck_sample_count": len(successful_samples),
            "oncall_owner": oncall_owner,
            "rollback_drill_at": rollback_drill_at,
            "evidence_refs": [evidence_ref] if evidence_ref else [],
        }
    }
    checks = {
        "samples_collected": _check(
            len(samples) >= sample_count,
            "Requested sample count was collected.",
            requested=sample_count,
            actual=len(samples),
        ),
        "successful_samples": _check(
            len(successful_samples) >= min_sample_count,
            "Enough samples had every required endpoint passing.",
            min_sample_count=min_sample_count,
            successful_sample_count=len(successful_samples),
        ),
        "evidence_window": _check(
            evidence_window_hours >= min_window_hours,
            "Observed evidence window meets the configured minimum.",
            min_window_hours=min_window_hours,
            evidence_window_hours=round(evidence_window_hours, 4),
        ),
        "manifest_patch_fields": _check(
            bool(service_unit and oncall_owner and rollback_drill_at and evidence_ref),
            "Manifest patch includes service unit, on-call owner, rollback drill timestamp, and evidence refs.",
            has_service_unit=bool(service_unit),
            has_oncall_owner=bool(oncall_owner),
            has_rollback_drill_at=bool(rollback_drill_at),
            has_evidence_ref=bool(evidence_ref),
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "base_url": _redact_url(base_url),
        "generated_at": _isoformat(now()),
        "started_at": started_at,
        "ended_at": ended_at,
        "evidence_window_hours": round(evidence_window_hours, 4),
        "sample_count": len(samples),
        "successful_sample_count": len(successful_samples),
        "required_sample_paths": list(REQUIRED_SAMPLE_PATHS),
        "checks": checks,
        "failed_checks": failed,
        "samples": samples,
        "production_manifest_patch": manifest_patch,
        "next_step": ""
        if not failed
        else "Run this collector against the production admin endpoint for the required window and fill missing ops evidence.",
    }


def _collect_sample(
    *,
    base_url: str,
    token: str | None,
    timeout_seconds: float,
    sampled_at: datetime,
    fetcher: Callable[[str, str | None, float], HttpResult],
    sample_index: int,
) -> dict[str, Any]:
    endpoint_checks: dict[str, dict[str, Any]] = {}
    for path in REQUIRED_SAMPLE_PATHS:
        result = fetcher(urljoin(_base_url(base_url), path), token, timeout_seconds)
        endpoint_checks[path] = _endpoint_check(path, result)
    status = "pass" if all(check["status"] == "pass" for check in endpoint_checks.values()) else "fail"
    launch = endpoint_checks["/api/launch-readiness"]
    graph_quality = endpoint_checks["/api/graph-quality"]
    return {
        "index": sample_index,
        "sampled_at": _isoformat(sampled_at),
        "status": status,
        "checks": endpoint_checks,
        "launch_staging_status": launch.get("staging_status"),
        "launch_production_status": launch.get("production_status"),
        "graph_quality_status": graph_quality.get("graph_quality_status"),
    }


def _endpoint_check(path: str, result: HttpResult) -> dict[str, Any]:
    base = {
        "status": "fail",
        "http_status": result.status,
        "description": f"{path} responds with expected health evidence.",
    }
    if result.error:
        return {**base, "error": result.error}
    if path == "/metrics":
        ok = result.status == 200 and "copilot_admin_" in result.body
        return {**base, "status": "pass" if ok else "fail", "metrics_present": "copilot_admin_" in result.body}
    payload = _json_payload(result.body)
    ok = result.status == 200 and payload.get("ok") is True
    if path == "/healthz":
        return {**base, "status": "pass" if ok else "fail", "ok": payload.get("ok")}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if path == "/api/health":
        ok = ok and data.get("database") == "readable" and bool(data.get("read_only_knowledge_surfaces"))
        return {
            **base,
            "status": "pass" if ok else "fail",
            "database": data.get("database"),
            "wiki_card_count": data.get("wiki_card_count"),
            "graph_quality_status": data.get("graph_quality_status"),
        }
    if path == "/api/launch-readiness":
        ok = ok and data.get("staging_status") in {"pass", "warning"}
        return {
            **base,
            "status": "pass" if ok else "fail",
            "staging_status": data.get("staging_status"),
            "production_status": data.get("production_status"),
        }
    if path == "/api/graph-quality":
        graph_status = data.get("status")
        ok = ok and graph_status in {"pass", "fail"}
        return {**base, "status": "pass" if ok else "fail", "graph_quality_status": graph_status}
    return {**base, "status": "pass" if ok else "fail"}


def _http_get(url: str, token: str | None, timeout_seconds: float) -> HttpResult:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout_seconds) as response:
            return HttpResult(status=response.status, body=response.read().decode("utf-8"))
    except HTTPError as exc:
        return HttpResult(status=exc.code, body=exc.read().decode("utf-8"), error=None)
    except (OSError, URLError) as exc:
        return HttpResult(status=0, body="", error=str(exc))


def _check(ok: bool, description: str, **extra: Any) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "description": description, **extra}


def _json_payload(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _base_url(base_url: str) -> str:
    value = base_url.strip()
    return value if value.endswith("/") else f"{value}/"


def _redact_url(value: str) -> str:
    return value.split("?", 1)[0]


def _hours_between(started_at: str, ended_at: str) -> float:
    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    return max(0.0, (end - start).total_seconds() / 3600)


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _admin_token_from_env() -> str | None:
    for name in ADMIN_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Admin Long-Run Evidence Collector")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"production_ready_claim: {str(result['production_ready_claim']).lower()}")
    print(f"boundary: {result['boundary']}")
    print(f"base_url: {result['base_url']}")
    print(f"samples: {result['successful_sample_count']}/{result['sample_count']}")
    print(f"evidence_window_hours: {result['evidence_window_hours']}")
    for name, check in result["checks"].items():
        print(f"- {name}: {check['status']} ({check['description']})")
    if result["failed_checks"]:
        print("failed_checks:")
        for name in result["failed_checks"]:
            print(f"- {name}")


if __name__ == "__main__":
    raise SystemExit(main())
