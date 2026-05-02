#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_cognee_embedding_sampler_status import check_cognee_embedding_sampler_status  # noqa: E402
from scripts.collect_cognee_embedding_long_run_evidence import (  # noqa: E402
    _read_embedding_samples,
    _read_json_object,
    collect_cognee_embedding_long_run_evidence,
)

DEFAULT_EVIDENCE_DIR = ROOT / "logs/cognee-embedding-long-run/2026-05-02-sampler"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize Cognee/embedding long-run evidence once the sampler covers the required time window. "
            "If the sampler is not ready, this exits non-zero with the estimated ready time."
        )
    )
    parser.add_argument("--curated-sync-report", type=Path, default=DEFAULT_EVIDENCE_DIR / "curated-sync-report.json")
    parser.add_argument(
        "--persistent-readback-report", type=Path, default=DEFAULT_EVIDENCE_DIR / "persistent-readback-report.json"
    )
    parser.add_argument("--embedding-sample-log", type=Path, default=DEFAULT_EVIDENCE_DIR / "embedding-samples.ndjson")
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_EVIDENCE_DIR / "sampler.pid")
    parser.add_argument("--service-unit", default="openclaw-local-cognee-sampler")
    parser.add_argument("--oncall-owner", default="feishu-ai-challenge-local-owner")
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--min-window-hours", type=float, default=24.0)
    parser.add_argument("--min-sample-count", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_EVIDENCE_DIR / "cognee-long-run-evidence.json",
        help="Completion-audit evidence JSON path.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = finalize_cognee_embedding_long_run(
        curated_sync_report_path=args.curated_sync_report,
        persistent_readback_report_path=args.persistent_readback_report,
        embedding_sample_log=args.embedding_sample_log,
        pid_file=args.pid_file,
        service_unit=args.service_unit,
        oncall_owner=args.oncall_owner,
        evidence_refs=args.evidence_ref,
        output_path=args.output,
        min_window_hours=args.min_window_hours,
        min_sample_count=args.min_sample_count,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def finalize_cognee_embedding_long_run(
    *,
    curated_sync_report_path: Path,
    persistent_readback_report_path: Path,
    embedding_sample_log: Path,
    pid_file: Path | None,
    service_unit: str,
    oncall_owner: str,
    evidence_refs: list[str] | None,
    output_path: Path,
    min_window_hours: float = 24.0,
    min_sample_count: int = 3,
) -> dict[str, Any]:
    sampler_status = check_cognee_embedding_sampler_status(
        embedding_sample_log=embedding_sample_log,
        pid_file=pid_file,
        min_window_hours=min_window_hours,
        min_sample_count=min_sample_count,
    )
    if not sampler_status.get("completion_ready"):
        return {
            "ok": False,
            "reason": "cognee_sampler_not_ready",
            "completion_ready": False,
            "sampler_status": _sampler_summary(sampler_status),
            "output": str(output_path),
            "next_step": str(sampler_status.get("next_step") or "Leave the sampler running until it is ready."),
        }

    refs = list(evidence_refs or [])
    for path in (embedding_sample_log, curated_sync_report_path, persistent_readback_report_path):
        if str(path) not in refs:
            refs.append(str(path))
    collector = collect_cognee_embedding_long_run_evidence(
        curated_sync_report=_read_json_object(curated_sync_report_path),
        persistent_readback_report=_read_json_object(persistent_readback_report_path),
        embedding_samples=list(_read_embedding_samples(embedding_sample_log)),
        store_reopened=False,
        reopened_search_ok=False,
        service_unit=service_unit,
        oncall_owner=oncall_owner,
        evidence_refs=refs,
        min_window_hours=min_window_hours,
        min_sample_count=min_sample_count,
    )
    if collector.get("ok"):
        output_path.expanduser().parent.mkdir(parents=True, exist_ok=True)
        output_path.expanduser().write_text(
            json.dumps(collector["completion_audit_evidence"], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return {
        "ok": bool(collector.get("ok")),
        "reason": "cognee_long_run_evidence_ready" if collector.get("ok") else "cognee_long_run_evidence_incomplete",
        "completion_ready": True,
        "output": str(output_path),
        "sampler_status": _sampler_summary(sampler_status),
        "collector": {
            "ok": collector.get("ok"),
            "failed_checks": collector.get("failed_checks"),
            "embedding_window_hours": collector.get("embedding_window_hours"),
            "successful_sample_count": collector.get("successful_sample_count"),
        },
        "next_step": ""
        if collector.get("ok")
        else str(collector.get("next_step") or "Fix collector inputs and rerun."),
    }


def format_report(result: dict[str, Any]) -> str:
    sampler = result.get("sampler_status") if isinstance(result.get("sampler_status"), dict) else {}
    lines = [
        "Cognee Embedding Long-run Finalizer",
        f"ok: {str(result['ok']).lower()}",
        f"reason: {result['reason']}",
        f"completion_ready: {str(result.get('completion_ready')).lower()}",
        f"embedding_window_hours: {sampler.get('embedding_window_hours')}",
        f"successful_sample_count: {sampler.get('successful_sample_count')}",
        f"output: {result.get('output')}",
    ]
    if sampler.get("estimated_ready_at"):
        lines.append(f"estimated_ready_at: {sampler['estimated_ready_at']}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def _sampler_summary(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": status.get("ok"),
        "completion_ready": status.get("completion_ready"),
        "sample_count": status.get("sample_count"),
        "successful_sample_count": status.get("successful_sample_count"),
        "embedding_window_hours": status.get("embedding_window_hours"),
        "estimated_ready_at": status.get("estimated_ready_at"),
        "next_expected_sample_at": status.get("next_expected_sample_at"),
        "final_scheduled_sample_at": status.get("final_scheduled_sample_at"),
        "failed_checks": status.get("failed_checks"),
        "warning_checks": status.get("warning_checks"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
