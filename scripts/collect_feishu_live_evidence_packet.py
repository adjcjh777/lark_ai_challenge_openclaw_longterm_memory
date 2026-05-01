#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_feishu_dm_routing import check_live_routing_events  # noqa: E402
from scripts.check_feishu_passive_message_event_gate import check_passive_message_events  # noqa: E402
from scripts.check_feishu_permission_negative_gate import check_permission_negative_events  # noqa: E402
from scripts.check_feishu_review_delivery_gate import check_review_delivery_log_events  # noqa: E402

REQUIRED_ROUTING_TOOLS = ("fmc_memory_search", "fmc_memory_create_candidate", "fmc_memory_prefetch")
BOUNDARY = (
    "feishu_live_evidence_packet_collector_only; stores sanitized gate reports and source log paths, "
    "not raw Feishu message content, and does not prove production long-running ingestion by itself"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect sanitized Feishu/OpenClaw live evidence reports for the productization completion audit. "
            "Each input should be an already captured listener/OpenClaw JSON or NDJSON log."
        )
    )
    parser.add_argument("--passive-event-log", required=True, type=Path)
    parser.add_argument("--routing-event-log", required=True, type=Path)
    parser.add_argument("--permission-event-log", required=True, type=Path)
    parser.add_argument("--review-event-log", required=True, type=Path)
    parser.add_argument("--output", default="", help="Optional JSON packet output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = collect_feishu_live_evidence_packet(
        passive_event_log=args.passive_event_log,
        routing_event_log=args.routing_event_log,
        permission_event_log=args.permission_event_log,
        review_event_log=args.review_event_log,
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


def collect_feishu_live_evidence_packet(
    *,
    passive_event_log: Path,
    routing_event_log: Path,
    permission_event_log: Path,
    review_event_log: Path,
) -> dict[str, Any]:
    reports = {
        "passive_group_message": _run_log_gate(passive_event_log, check_passive_message_events),
        "first_class_routing": _run_log_gate(
            routing_event_log,
            lambda text: check_live_routing_events(text, required_tools=REQUIRED_ROUTING_TOOLS),
        ),
        "permission_negative": _run_log_gate(permission_event_log, check_permission_negative_events),
        "review_delivery": _run_log_gate(review_event_log, check_review_delivery_log_events),
    }
    failed = sorted(name for name, report in reports.items() if not report.get("ok"))
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "required_routing_tools": list(REQUIRED_ROUTING_TOOLS),
        "reports": reports,
        "failed_reports": failed,
        "next_step": ""
        if not failed
        else "Collect fresh real Feishu/OpenClaw logs for the failed reports and rerun this packet collector.",
    }


def format_report(packet: dict[str, Any]) -> str:
    lines = [
        "Feishu/OpenClaw Live Evidence Packet",
        f"ok: {str(packet['ok']).lower()}",
        f"boundary: {packet['boundary']}",
    ]
    for name, report in packet["reports"].items():
        lines.append(f"  {name}: ok={str(bool(report.get('ok'))).lower()} reason={report.get('reason')}")
    if packet.get("failed_reports"):
        lines.append(f"failed_reports: {', '.join(packet['failed_reports'])}")
        lines.append(f"next_step: {packet['next_step']}")
    return "\n".join(lines)


def _run_log_gate(path: Path, gate: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    resolved = path.expanduser()
    if not resolved.exists():
        return {
            "ok": False,
            "gate": "missing_log",
            "source_log": str(resolved),
            "reason": "evidence_log_missing",
            "summary": {},
            "next_step": "Capture this live evidence log and rerun.",
        }
    report = gate(resolved.read_text(encoding="utf-8"))
    return {
        "ok": bool(report.get("ok")),
        "gate": report.get("gate"),
        "source_log": str(resolved),
        "reason": report.get("reason"),
        "summary": report.get("summary"),
        "missing_required_tools": report.get("missing_required_tools"),
        "failures": report.get("failures"),
        "next_step": report.get("next_step"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
