#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_cognee_embedding_sampler_status import check_cognee_embedding_sampler_status  # noqa: E402
from scripts.check_openclaw_feishu_productization_completion import build_completion_audit  # noqa: E402
from scripts.finalize_cognee_embedding_long_run import finalize_cognee_embedding_long_run  # noqa: E402

DEFAULT_RUN_DIR = ROOT / "logs/feishu-live-evidence-runs/20260502T052541Z-route-tools"
DEFAULT_COGNEE_DIR = ROOT / "logs/cognee-embedding-long-run/2026-05-02-sampler"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the current OpenClaw-native Feishu Memory Copilot productization finalization checks. "
            "This only marks ready when every underlying live and long-run evidence gate passes."
        )
    )
    parser.add_argument("--openclaw-log", type=Path, default=Path("/tmp/openclaw/openclaw-2026-05-02.log"))
    parser.add_argument("--routing-event-log", type=Path, default=DEFAULT_RUN_DIR / "02-first-class-routing.ndjson")
    parser.add_argument("--feishu-event-diagnostics", type=Path, default=DEFAULT_RUN_DIR / "00-feishu-event-diagnostics.json")
    parser.add_argument("--cognee-dir", type=Path, default=DEFAULT_COGNEE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = finalize_openclaw_feishu_productization(
        openclaw_log=args.openclaw_log,
        routing_event_log=args.routing_event_log,
        feishu_event_diagnostics=args.feishu_event_diagnostics,
        cognee_dir=args.cognee_dir,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["goal_complete"] else 1


def finalize_openclaw_feishu_productization(
    *,
    openclaw_log: Path,
    routing_event_log: Path,
    feishu_event_diagnostics: Path | None,
    cognee_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.expanduser().mkdir(parents=True, exist_ok=True)
    cognee_dir = cognee_dir.expanduser()
    sampler_status_path = output_dir / "00-cognee-sampler-status.json"
    cognee_evidence_path = cognee_dir / "cognee-long-run-evidence.json"

    sampler_status = check_cognee_embedding_sampler_status(
        embedding_sample_log=cognee_dir / "embedding-samples.ndjson",
        pid_file=cognee_dir / "sampler.pid",
    )
    sampler_status_path.write_text(json.dumps(sampler_status, ensure_ascii=False, indent=2), encoding="utf-8")

    cognee_finalizer = finalize_cognee_embedding_long_run(
        curated_sync_report_path=cognee_dir / "curated-sync-report.json",
        persistent_readback_report_path=cognee_dir / "persistent-readback-report.json",
        embedding_sample_log=cognee_dir / "embedding-samples.ndjson",
        pid_file=cognee_dir / "sampler.pid",
        service_unit="openclaw-local-cognee-sampler",
        oncall_owner="feishu-ai-challenge-local-owner",
        evidence_refs=[],
        output_path=cognee_evidence_path,
    )
    cognee_finalizer_path = output_dir / "00-cognee-finalizer.json"
    cognee_finalizer_path.write_text(json.dumps(cognee_finalizer, ensure_ascii=False, indent=2), encoding="utf-8")

    cognee_long_run_evidence = cognee_evidence_path if cognee_finalizer.get("ok") else None
    audit = build_completion_audit(
        passive_event_log=openclaw_log,
        permission_event_log=openclaw_log,
        review_event_log=openclaw_log,
        routing_event_log=routing_event_log,
        feishu_event_diagnostics=feishu_event_diagnostics,
        cognee_long_run_evidence=cognee_long_run_evidence,
        cognee_sampler_status=None if cognee_long_run_evidence else sampler_status_path,
    )
    audit_path = output_dir / "99-openclaw-feishu-productization-completion.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "ok": bool(audit.get("ok")),
        "goal_complete": bool(audit.get("goal_complete")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_path": str(audit_path),
        "cognee_sampler_status_path": str(sampler_status_path),
        "cognee_finalizer_path": str(cognee_finalizer_path),
        "cognee_long_run_evidence_path": str(cognee_evidence_path) if cognee_finalizer.get("ok") else "",
        "pass_count": len([item for item in audit.get("items", []) if item.get("status") == "pass"]),
        "blockers": audit.get("blockers") or [],
        "next_step": "" if audit.get("goal_complete") else audit.get("next_step"),
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "OpenClaw Feishu Productization Finalizer",
        f"goal_complete: {str(result['goal_complete']).lower()}",
        f"pass_count: {result['pass_count']}",
        f"audit_path: {result['audit_path']}",
    ]
    if result.get("cognee_long_run_evidence_path"):
        lines.append(f"cognee_long_run_evidence_path: {result['cognee_long_run_evidence_path']}")
    if result.get("blockers"):
        lines.append("blockers:")
        for blocker in result["blockers"]:
            lines.append(f"  {blocker['item']}. {blocker['name']}: {blocker['reason']}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
