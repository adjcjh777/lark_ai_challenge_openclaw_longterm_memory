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

from memory_engine.feishu_listener_guard import (  # noqa: E402
    FeishuListenerConflict,
    PlannedListener,
    assert_single_feishu_listener,
    listener_report,
)
from scripts.check_feishu_event_subscription_diagnostics import (  # noqa: E402
    run_feishu_event_subscription_diagnostics,
)

BOUNDARY = (
    "feishu_live_evidence_run_preflight_only; validates single-listener state and emits manual test steps, "
    "but does not send Feishu messages, click cards, or prove live evidence by itself"
)
DEFAULT_OUTPUT_ROOT = ROOT / "logs/feishu-live-evidence-runs"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a deterministic manual Feishu/OpenClaw live evidence run. This does not send messages; "
            "it writes/prints the paths and commands needed for the next real test."
        )
    )
    parser.add_argument(
        "--planned-listener",
        choices=("openclaw-websocket", "copilot-lark-cli", "legacy-lark-cli", "none"),
        default="openclaw-websocket",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--controlled-chat-id", default="", help="Optional redacted/local-only controlled group id.")
    parser.add_argument("--non-reviewer-open-id", default="", help="Optional redacted/local-only second user open_id.")
    parser.add_argument("--reviewer-open-id", default="", help="Optional redacted/local-only reviewer open_id.")
    parser.add_argument("--cognee-long-run-evidence", type=Path, default=None)
    parser.add_argument("--embedding-sample-log", type=Path, default=None)
    parser.add_argument("--embedding-sampler-pid-file", type=Path, default=None)
    parser.add_argument("--create-dirs", action="store_true")
    parser.add_argument("--output", default="", help="Optional JSON manifest output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = prepare_live_evidence_run(
        planned_listener=args.planned_listener,
        output_dir=args.output_dir,
        controlled_chat_id=args.controlled_chat_id,
        non_reviewer_open_id=args.non_reviewer_open_id,
        reviewer_open_id=args.reviewer_open_id,
        cognee_long_run_evidence=args.cognee_long_run_evidence,
        embedding_sample_log=args.embedding_sample_log,
        embedding_sampler_pid_file=args.embedding_sampler_pid_file,
        create_dirs=args.create_dirs,
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


def prepare_live_evidence_run(
    *,
    planned_listener: PlannedListener = "openclaw-websocket",
    output_dir: Path | None = None,
    controlled_chat_id: str = "",
    non_reviewer_open_id: str = "",
    reviewer_open_id: str = "",
    cognee_long_run_evidence: Path | None = None,
    embedding_sample_log: Path | None = None,
    embedding_sampler_pid_file: Path | None = None,
    create_dirs: bool = False,
    process_rows: Iterable[str] | None = None,
    event_subscription_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = (output_dir or DEFAULT_OUTPUT_ROOT / run_id).expanduser()
    if create_dirs:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    log_paths = _log_paths(evidence_dir)
    try:
        active = assert_single_feishu_listener(planned_listener, process_rows=process_rows)
        singleton = {
            "status": "pass",
            "planned_listener": planned_listener,
            "active": [
                {"pid": process.pid, "ppid": process.ppid, "kind": process.kind, "command": process.command}
                for process in active
            ],
            "report": listener_report(active),
        }
    except FeishuListenerConflict as exc:
        singleton = {
            "status": "fail",
            "planned_listener": planned_listener,
            "active": [
                {"pid": process.pid, "ppid": process.ppid, "kind": process.kind, "command": process.command}
                for process in exc.processes
            ],
            "report": str(exc),
        }
    event_subscription = _event_subscription_check(
        planned_listener=planned_listener,
        diagnostics=event_subscription_diagnostics,
    )
    checks = {
        "single_listener": singleton,
        "event_subscription": event_subscription,
        "controlled_chat_id": _presence_check(controlled_chat_id, "Required for expected-chat-id filters."),
        "non_reviewer_open_id": _presence_check(non_reviewer_open_id, "Required for expected-actor-id filter."),
        "reviewer_open_id": _presence_check(reviewer_open_id, "Useful for /review DM target readback."),
        "cognee_long_run_evidence": _file_check(cognee_long_run_evidence),
    }
    blocking_failures = [
        name for name in ("single_listener", "event_subscription") if checks[name]["status"] == "fail"
    ]
    warnings = [name for name, check in checks.items() if check["status"] == "warning"]
    diagnostic_paths = _diagnostic_paths(evidence_dir)
    packet_output = evidence_dir / "feishu-live-evidence-packet.json"
    completion_output = evidence_dir / "completion-audit.json"
    steps = _manual_steps(
        log_paths=log_paths,
        diagnostic_paths=diagnostic_paths,
        packet_output=packet_output,
        completion_output=completion_output,
        cognee_long_run_evidence=cognee_long_run_evidence,
        embedding_sample_log=embedding_sample_log,
        embedding_sampler_pid_file=embedding_sampler_pid_file,
        controlled_chat_id=controlled_chat_id,
        non_reviewer_open_id=non_reviewer_open_id,
        planned_listener=planned_listener,
    )
    return {
        "ok": not blocking_failures,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "evidence_dir": str(evidence_dir),
        "create_dirs": bool(create_dirs),
        "checks": checks,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "log_paths": {name: str(path) for name, path in log_paths.items()},
        "diagnostic_paths": {name: str(path) for name, path in diagnostic_paths.items()},
        "manual_steps": steps,
        "next_step": "Follow manual_steps and rerun packet/completion audit after real Feishu/OpenClaw logs are captured.",
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Feishu Live Evidence Run Preflight",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
        f"evidence_dir: {result['evidence_dir']}",
        f"single_listener: {result['checks']['single_listener']['status']}",
        f"event_subscription: {result['checks']['event_subscription']['status']}",
    ]
    if result["warnings"]:
        lines.append(f"warnings: {', '.join(result['warnings'])}")
    if result["blocking_failures"]:
        lines.append(f"blocking_failures: {', '.join(result['blocking_failures'])}")
    lines.append("manual_steps:")
    for step in result["manual_steps"]:
        lines.append(f"  {step['id']}. {step['title']}")
        lines.append(f"     {step['instruction']}")
    return "\n".join(lines)


def _log_paths(evidence_dir: Path) -> dict[str, Path]:
    return {
        "passive_event_log": evidence_dir / "01-passive-non-at-message.ndjson",
        "routing_event_log": evidence_dir / "02-first-class-routing.ndjson",
        "permission_event_log": evidence_dir / "03-non-reviewer-deny.ndjson",
        "review_event_log": evidence_dir / "04-review-dm-card.ndjson",
    }


def _diagnostic_paths(evidence_dir: Path) -> dict[str, Path]:
    return {
        "feishu_event_diagnostics": evidence_dir / "00-feishu-event-diagnostics.json",
        "cognee_sampler_status": evidence_dir / "00-cognee-sampler-status.json",
    }


def _manual_steps(
    *,
    log_paths: dict[str, Path],
    diagnostic_paths: dict[str, Path],
    packet_output: Path,
    completion_output: Path,
    cognee_long_run_evidence: Path | None,
    embedding_sample_log: Path | None,
    embedding_sampler_pid_file: Path | None,
    controlled_chat_id: str,
    non_reviewer_open_id: str,
    planned_listener: PlannedListener,
) -> list[dict[str, str]]:
    chat_filter = f" --expected-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    actor_filter = f" --expected-actor-id {non_reviewer_open_id}" if non_reviewer_open_id else ""
    cognee_arg = f" --cognee-long-run-evidence {cognee_long_run_evidence}" if cognee_long_run_evidence else ""
    event_diagnostics_arg = f" --feishu-event-diagnostics {diagnostic_paths['feishu_event_diagnostics']}"
    sampler_status_arg = (
        f" --cognee-sampler-status {diagnostic_paths['cognee_sampler_status']}"
        if embedding_sample_log
        else ""
    )
    steps = [
        {
            "id": "1",
            "title": "Run read-only event subscription diagnostics",
            "instruction": (
                "python3 scripts/check_feishu_event_subscription_diagnostics.py "
                f"--planned-listener {planned_listener} --require-group-message-scope --json "
                f"> {diagnostic_paths['feishu_event_diagnostics']}"
            ),
        },
        {
            "id": "2",
            "title": "Send non-@ group text",
            "instruction": (
                "In the controlled enabled group, send exactly this as a normal user without mentioning the bot: "
                "决定：非 @ 群消息 live gate 测试，今天只验证事件投递。 Save the listener/OpenClaw log to "
                f"{log_paths['passive_event_log']}."
            ),
        },
        {
            "id": "3",
            "title": "Trigger first-class fmc tools",
            "instruction": (
                "In Feishu DM or the controlled group, ask OpenClaw to run fmc_memory_search and fmc_memory_prefetch "
                "through the Feishu path. Save successful bridge result logs to "
                f"{log_paths['routing_event_log']}."
            ),
        },
        {
            "id": "4",
            "title": "Ask second non-reviewer to enable memory",
            "instruction": (
                "From the second real non-reviewer account, send @Bot /enable_memory in the controlled group. "
                f"Save the live result log to {log_paths['permission_event_log']}."
            ),
        },
        {
            "id": "5",
            "title": "Run review DM/card E2E",
            "instruction": (
                "Create a fresh candidate, send /review as reviewer, click one card action, and preserve private DM "
                f"delivery plus update_card result logs in {log_paths['review_event_log']}."
            ),
        },
        {
            "id": "6",
            "title": "Build sanitized Feishu live packet",
            "instruction": (
                "python3 scripts/collect_feishu_live_evidence_packet.py "
                f"--passive-event-log {log_paths['passive_event_log']} "
                f"--routing-event-log {log_paths['routing_event_log']} "
                f"--permission-event-log {log_paths['permission_event_log']} "
                f"--review-event-log {log_paths['review_event_log']} "
                f"--output {packet_output} --json"
            ),
        },
        {
            "id": "7",
            "title": "Run focused gates with filters",
            "instruction": (
                f"python3 scripts/check_feishu_passive_message_event_gate.py --event-log {log_paths['passive_event_log']}{chat_filter} --json && "
                f"python3 scripts/check_feishu_permission_negative_gate.py --event-log {log_paths['permission_event_log']}{chat_filter}{actor_filter} --json"
            ),
        },
    ]
    next_id = 8
    if embedding_sample_log:
        pid_arg = f" --pid-file {embedding_sampler_pid_file}" if embedding_sampler_pid_file else ""
        steps.append(
            {
                "id": str(next_id),
                "title": "Check Cognee embedding sampler status",
                "instruction": (
                    "python3 scripts/check_cognee_embedding_sampler_status.py "
                    f"--embedding-sample-log {embedding_sample_log}{pid_arg} --json "
                    f"> {diagnostic_paths['cognee_sampler_status']}"
                ),
            }
        )
        next_id += 1
    steps.append(
        {
            "id": str(next_id),
            "title": "Run completion audit",
            "instruction": (
                "python3 scripts/check_openclaw_feishu_productization_completion.py "
                f"--feishu-live-evidence-packet {packet_output}{event_diagnostics_arg}{sampler_status_arg}{cognee_arg} "
                f"--json > {completion_output}"
            ),
        },
    )
    return steps


def _event_subscription_check(
    *,
    planned_listener: PlannedListener,
    diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        report = diagnostics or run_feishu_event_subscription_diagnostics(
            planned_listener=planned_listener,
            require_group_message_scope=True,
        )
    except Exception as exc:  # pragma: no cover - defensive shell/environment boundary.
        return {
            "status": "fail",
            "detail": f"Unable to run read-only Feishu event subscription diagnostics: {exc}",
            "diagnostics": None,
        }
    failed = report.get("failed_checks") if isinstance(report.get("failed_checks"), list) else []
    warning_items = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if not report.get("ok"):
        status = "fail"
    elif warning_items:
        status = "warning"
    else:
        status = "pass"
    return {
        "status": status,
        "detail": (
            "read-only event diagnostics passed"
            if status == "pass"
            else f"failed_checks={failed}; warnings={[item.get('id') for item in warning_items if isinstance(item, dict)]}"
        ),
        "diagnostics": report,
    }


def _presence_check(value: str, detail: str) -> dict[str, str]:
    return {"status": "pass" if value else "warning", "detail": detail if not value else "configured"}


def _file_check(path: Path | None) -> dict[str, str]:
    if path is None:
        return {
            "status": "warning",
            "detail": "Optional for Feishu-only run; required for full goal completion audit.",
        }
    resolved = path.expanduser()
    return {
        "status": "pass" if resolved.exists() else "warning",
        "detail": str(resolved) if resolved.exists() else f"File not found yet: {resolved}",
    }


if __name__ == "__main__":
    raise SystemExit(main())
