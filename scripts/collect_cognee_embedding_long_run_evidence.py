#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BOUNDARY = (
    "cognee_embedding_long_run_evidence_collector_only; normalizes existing curated-sync, persistent-store, "
    "and embedding health evidence, but does not create or prove a long-running service by itself"
)
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Cognee/embedding long-run evidence for the OpenClaw Feishu productization completion audit. "
            "Feed it a real check_cognee_curated_sync_gate JSON report and embedding sample log."
        )
    )
    parser.add_argument("--curated-sync-report", required=True, type=Path, help="JSON from check_cognee_curated_sync_gate.")
    parser.add_argument(
        "--embedding-sample-log",
        required=True,
        type=Path,
        help="JSON/NDJSON embedding sample log, usually repeated check_embedding_provider outputs.",
    )
    parser.add_argument("--store-reopened", action="store_true", help="Set only after reopening the persistent store.")
    parser.add_argument("--reopened-search-ok", action="store_true", help="Set only after search/readback passes post-reopen.")
    parser.add_argument("--service-unit", default="", help="Embedding/Cognee service unit or deployment id.")
    parser.add_argument("--oncall-owner", default="", help="Human owner for the long-run window.")
    parser.add_argument("--evidence-ref", action="append", default=[], help="Non-secret evidence ref, e.g. ops log URL/path.")
    parser.add_argument("--min-window-hours", type=float, default=24.0)
    parser.add_argument("--min-sample-count", type=int, default=3)
    parser.add_argument("--output", default="", help="Optional output JSON path for completion audit.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = collect_cognee_embedding_long_run_evidence(
        curated_sync_report=_read_json_object(args.curated_sync_report),
        embedding_samples=list(_read_embedding_samples(args.embedding_sample_log)),
        store_reopened=args.store_reopened,
        reopened_search_ok=args.reopened_search_ok,
        service_unit=args.service_unit,
        oncall_owner=args.oncall_owner,
        evidence_refs=args.evidence_ref,
        min_window_hours=args.min_window_hours,
        min_sample_count=args.min_sample_count,
    )
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result["completion_audit_evidence"], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def collect_cognee_embedding_long_run_evidence(
    *,
    curated_sync_report: dict[str, Any],
    embedding_samples: list[dict[str, Any]],
    store_reopened: bool,
    reopened_search_ok: bool,
    service_unit: str = "",
    oncall_owner: str = "",
    evidence_refs: list[str] | None = None,
    min_window_hours: float = 24.0,
    min_sample_count: int = 3,
) -> dict[str, Any]:
    refs = list(evidence_refs or [])
    successful_samples = [_normalize_embedding_sample(sample) for sample in embedding_samples]
    successful_samples = [sample for sample in successful_samples if sample["ok"]]
    window_hours = _sample_window_hours(successful_samples)
    cognee_sync = curated_sync_report.get("cognee_sync") if isinstance(curated_sync_report, dict) else {}
    cognee_sync_pass = isinstance(cognee_sync, dict) and cognee_sync.get("status") == "pass" and not cognee_sync.get(
        "fallback"
    )
    checks = {
        "curated_sync_pass": _check(
            cognee_sync_pass,
            "Curated memory confirm synced through Cognee without repository fallback.",
            status=cognee_sync.get("status") if isinstance(cognee_sync, dict) else None,
            fallback=cognee_sync.get("fallback") if isinstance(cognee_sync, dict) else None,
        ),
        "persistent_store_reopened": _check(
            bool(store_reopened),
            "Persistent Cognee store was reopened after the initial sync.",
        ),
        "reopened_search_ok": _check(
            bool(reopened_search_ok),
            "Post-reopen search/readback found the synced curated memory.",
        ),
        "embedding_successful_samples": _check(
            len(successful_samples) >= min_sample_count,
            "Enough embedding health samples returned expected dimensions.",
            min_sample_count=min_sample_count,
            successful_sample_count=len(successful_samples),
        ),
        "embedding_window": _check(
            window_hours >= min_window_hours,
            "Embedding health samples cover the required evidence window.",
            min_window_hours=min_window_hours,
            window_hours=round(window_hours, 4),
        ),
        "ops_metadata_present": _check(
            bool(service_unit and oncall_owner and _valid_evidence_refs(refs)),
            "Long-run evidence includes service identity, owner, and non-secret evidence refs.",
            has_service_unit=bool(service_unit),
            has_oncall_owner=bool(oncall_owner),
            evidence_ref_count=len(refs),
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    evidence = {
        "cognee_sync": {
            "status": cognee_sync.get("status") if isinstance(cognee_sync, dict) else None,
            "fallback": cognee_sync.get("fallback") if isinstance(cognee_sync, dict) else None,
            "dataset_name": curated_sync_report.get("dataset_name"),
            "memory_id": curated_sync_report.get("memory_id"),
        },
        "persistence": {
            "store_reopened": bool(store_reopened),
            "reopened_search_ok": bool(reopened_search_ok),
            "data_root": curated_sync_report.get("data_root"),
            "system_root": curated_sync_report.get("system_root"),
        },
        "embedding_service": {
            "service_unit": service_unit,
            "oncall_owner": oncall_owner,
            "window_hours": round(window_hours, 4),
            "healthcheck_sample_count": len(successful_samples),
            "first_sample_at": successful_samples[0]["sampled_at"] if successful_samples else "",
            "last_sample_at": successful_samples[-1]["sampled_at"] if successful_samples else "",
            "model": _first_non_empty(sample.get("model") for sample in successful_samples),
            "expected_dimensions": _first_non_empty(sample.get("expected_dimensions") for sample in successful_samples),
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
        "sample_count": len(embedding_samples),
        "successful_sample_count": len(successful_samples),
        "embedding_window_hours": round(window_hours, 4),
        "completion_audit_evidence": evidence,
        "next_step": ""
        if not failed
        else "Collect real Cognee sync, persistent-store reopen/readback, and long-running embedding samples.",
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Cognee/Embedding Long-run Evidence",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
        f"sample_count: {result['sample_count']}",
        f"successful_sample_count: {result['successful_sample_count']}",
        f"embedding_window_hours: {result['embedding_window_hours']}",
    ]
    if result["failed_checks"]:
        lines.append("failed_checks:")
        lines.extend(f"  - {name}" for name in result["failed_checks"])
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _normalize_embedding_sample(sample: dict[str, Any]) -> dict[str, Any]:
    expected = _number(sample.get("expected_dimensions"))
    actual = _number(sample.get("actual_dimensions"))
    status = str(sample.get("status") or "")
    return {
        "ok": bool(sample.get("ok")) and status in {"ready", "pass", "live_embedding_verified"} and actual == expected,
        "sampled_at": str(sample.get("sampled_at") or sample.get("generated_at") or sample.get("timestamp") or ""),
        "model": sample.get("model"),
        "expected_dimensions": expected,
        "actual_dimensions": actual,
    }


def _sample_window_hours(samples: list[dict[str, Any]]) -> float:
    parsed = [_parse_datetime(sample.get("sampled_at")) for sample in samples]
    parsed = [item for item in parsed if item is not None]
    if len(parsed) < 2:
        return 0.0
    return max(0.0, (max(parsed) - min(parsed)).total_seconds() / 3600.0)


def _check(ok: bool, description: str, **details: Any) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "description": description, **details}


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_embedding_samples(path: Path) -> Iterable[dict[str, Any]]:
    text = path.expanduser().read_text(encoding="utf-8").strip()
    if not text:
        return []
    parsed = _parse_json(text)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        samples = parsed.get("samples")
        if isinstance(samples, list):
            return [item for item in samples if isinstance(item, dict)]
        return [parsed]
    samples: list[dict[str, Any]] = []
    for line in text.splitlines():
        parsed_line = _parse_json(line.strip())
        if isinstance(parsed_line, dict):
            samples.append(parsed_line)
    return samples


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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


def _valid_evidence_refs(refs: list[str]) -> bool:
    return bool(refs) and all(isinstance(ref, str) and ref.strip() and not _contains_secret_like(ref) for ref in refs)


def _contains_secret_like(value: str) -> bool:
    return any(marker in value for marker in SECRET_VALUE_MARKERS)


def _number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _first_non_empty(values: Iterable[Any]) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
