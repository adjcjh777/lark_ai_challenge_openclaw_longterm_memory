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
from scripts.check_cognee_embedding_sampler_status import (  # noqa: E402
    check_cognee_embedding_sampler_status,
)
from scripts.check_feishu_event_subscription_diagnostics import (  # noqa: E402
    DEFAULT_OPENCLAW_CONFIG,
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
    parser.add_argument(
        "--openclaw-config",
        type=Path,
        default=DEFAULT_OPENCLAW_CONFIG,
        help="OpenClaw config path for the read-only Feishu group policy safety preflight.",
    )
    parser.add_argument(
        "--event-diagnostics-file",
        type=Path,
        default=None,
        help="Use an existing check_feishu_event_subscription_diagnostics.py JSON file instead of probing live.",
    )
    parser.add_argument(
        "--skip-event-diagnostics",
        action="store_true",
        help="Generate the checklist without probing Feishu/OpenClaw diagnostics; live capture remains blocked.",
    )
    parser.add_argument("--create-dirs", action="store_true")
    parser.add_argument("--output", default="", help="Optional JSON manifest output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        event_subscription_diagnostics = event_subscription_diagnostics_from_cli(
            args.event_diagnostics_file,
            skip=args.skip_event_diagnostics,
        )
    except ValueError as exc:
        parser.error(str(exc))

    result = prepare_live_evidence_run(
        planned_listener=args.planned_listener,
        output_dir=args.output_dir,
        controlled_chat_id=args.controlled_chat_id,
        non_reviewer_open_id=args.non_reviewer_open_id,
        reviewer_open_id=args.reviewer_open_id,
        cognee_long_run_evidence=args.cognee_long_run_evidence,
        embedding_sample_log=args.embedding_sample_log,
        embedding_sampler_pid_file=args.embedding_sampler_pid_file,
        openclaw_config_path=args.openclaw_config,
        create_dirs=args.create_dirs,
        event_subscription_diagnostics=event_subscription_diagnostics,
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


def event_subscription_diagnostics_from_cli(path: Path | None, *, skip: bool) -> dict[str, Any] | None:
    if path is not None and skip:
        raise ValueError("--event-diagnostics-file and --skip-event-diagnostics cannot be used together")
    if path is not None:
        return _load_event_diagnostics_file(path)
    if skip:
        return _skipped_event_diagnostics()
    return None


def _load_event_diagnostics_file(path: Path) -> dict[str, Any]:
    resolved = path.expanduser()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"unable to read --event-diagnostics-file {resolved}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"--event-diagnostics-file must be valid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"--event-diagnostics-file must contain a JSON object: {resolved}")
    return payload


def _skipped_event_diagnostics() -> dict[str, Any]:
    return {
        "ok": False,
        "skipped": True,
        "failed_checks": ["event_subscription_diagnostics_skipped"],
        "warnings": [
            {
                "id": "event_subscription_diagnostics_skipped",
                "detail": "Checklist was generated without probing live Feishu/OpenClaw event diagnostics.",
            }
        ],
        "checks": {
            "event_subscription_diagnostics": {
                "status": "fail",
                "detail": "skipped by --skip-event-diagnostics",
            }
        },
        "remediation": {
            "steps": [
                "Run scripts/check_feishu_event_subscription_diagnostics.py before sending real live test messages.",
                "Keep ready_to_capture_live_logs=false until event diagnostics pass.",
            ]
        },
    }


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
    openclaw_config_path: Path | None = DEFAULT_OPENCLAW_CONFIG,
    create_dirs: bool = False,
    process_rows: Iterable[str] | None = None,
    event_subscription_diagnostics: dict[str, Any] | None = None,
    cognee_sampler_status: dict[str, Any] | None = None,
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
        controlled_chat_id=controlled_chat_id,
        openclaw_config_path=openclaw_config_path,
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
    blocking_failures = [name for name in ("single_listener", "event_subscription") if checks[name]["status"] == "fail"]
    blocking_resolution_steps = _blocking_resolution_steps(checks)
    warnings = [name for name, check in checks.items() if check["status"] == "warning"]
    diagnostic_paths = _diagnostic_paths(evidence_dir)
    diagnostic_write_results = _write_diagnostic_inputs(
        create_dirs=create_dirs,
        diagnostic_paths=diagnostic_paths,
        event_subscription=event_subscription,
        embedding_sample_log=embedding_sample_log,
        embedding_sampler_pid_file=embedding_sampler_pid_file,
        cognee_sampler_status=cognee_sampler_status,
    )
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
        reviewer_open_id=reviewer_open_id,
        planned_listener=planned_listener,
        openclaw_config_path=openclaw_config_path,
    )
    evidence_checklist = _evidence_checklist(
        log_paths=log_paths,
        diagnostic_paths=diagnostic_paths,
        packet_output=packet_output,
        completion_output=completion_output,
        cognee_long_run_evidence=cognee_long_run_evidence,
        embedding_sample_log=embedding_sample_log,
        controlled_chat_id=controlled_chat_id,
        non_reviewer_open_id=non_reviewer_open_id,
        reviewer_open_id=reviewer_open_id,
    )
    operator_checklist_path = evidence_dir / "operator-checklist.md"
    result = {
        "ok": not blocking_failures,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "evidence_dir": str(evidence_dir),
        "create_dirs": bool(create_dirs),
        "checks": checks,
        "ready_to_capture_live_logs": not blocking_failures,
        "blocking_failures": blocking_failures,
        "blocking_resolution_steps": blocking_resolution_steps,
        "warnings": warnings,
        "log_paths": {name: str(path) for name, path in log_paths.items()},
        "diagnostic_paths": {name: str(path) for name, path in diagnostic_paths.items()},
        "diagnostic_write_results": diagnostic_write_results,
        "operator_checklist_path": str(operator_checklist_path),
        "operator_checklist_write_result": {},
        "manual_steps": steps,
        "evidence_checklist": evidence_checklist,
        "next_step": "Follow manual_steps and rerun packet/completion audit after real Feishu/OpenClaw logs are captured.",
    }
    if create_dirs:
        result["operator_checklist_write_result"] = _write_text_file(
            operator_checklist_path,
            format_operator_checklist(result),
        )
    return result


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "Feishu Live Evidence Run Preflight",
        f"ok: {str(result['ok']).lower()}",
        f"boundary: {result['boundary']}",
        f"evidence_dir: {result['evidence_dir']}",
        f"single_listener: {result['checks']['single_listener']['status']}",
        f"event_subscription: {result['checks']['event_subscription']['status']}",
        f"ready_to_capture_live_logs: {str(result['ready_to_capture_live_logs']).lower()}",
    ]
    if result["warnings"]:
        lines.append(f"warnings: {', '.join(result['warnings'])}")
    if result["blocking_failures"]:
        lines.append(f"blocking_failures: {', '.join(result['blocking_failures'])}")
    if result.get("blocking_resolution_steps"):
        lines.append("blocking_resolution_steps:")
        for step in result["blocking_resolution_steps"]:
            lines.append(f"  - {step}")
    lines.append("manual_steps:")
    for step in result["manual_steps"]:
        ready_marker = " requires_ready" if step.get("requires_ready_to_capture_live_logs") else ""
        phase = f" [{step.get('phase')}]" if step.get("phase") else ""
        lines.append(f"  {step['id']}. {step['title']}{phase}{ready_marker}")
        lines.append(f"     {step['instruction']}")
    lines.append("evidence_checklist:")
    for item in result.get("evidence_checklist", []):
        lines.append(f"  - {item['id']}: {item['status']} -> {item['evidence_path']}")
    if result.get("operator_checklist_path"):
        lines.append(f"operator_checklist: {result['operator_checklist_path']}")
    return "\n".join(lines)


def format_operator_checklist(result: dict[str, Any]) -> str:
    lines = [
        "# Feishu Live Evidence Operator Checklist",
        "",
        f"- Run ID: `{result['run_id']}`",
        f"- Evidence dir: `{result['evidence_dir']}`",
        f"- Ready to capture live logs: `{str(result['ready_to_capture_live_logs']).lower()}`",
        f"- Boundary: `{result['boundary']}`",
        "- Do not claim productized live from this checklist, preflight, or packet alone.",
        "",
    ]
    if result.get("blocking_failures"):
        lines.extend(["## Blocking Preconditions", ""])
        for failure in result["blocking_failures"]:
            lines.append(f"- `{failure}`")
        for step in result.get("blocking_resolution_steps", []):
            lines.append(f"- {step}")
        lines.append("")
    lines.extend(["## Manual Steps", ""])
    for step in result["manual_steps"]:
        lines.extend(
            [
                f"### {step['id']}. {step['title']}",
                "",
                f"- Phase: `{step.get('phase', '')}`",
                f"- Requires live readiness: `{str(step.get('requires_ready_to_capture_live_logs', False)).lower()}`",
                "",
                "```text",
                step["instruction"],
                "```",
                "",
            ]
        )
    lines.extend(["## Evidence Checklist", ""])
    for item in result.get("evidence_checklist", []):
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Completion item: `{item['completion_item']}`",
                f"- Status: `{item['status']}`",
                f"- Requirement: {item['requirement']}",
                f"- Evidence path: `{item['evidence_path']}`",
                f"- Proxy signal warning: {item['proxy_signal_warning']}",
                "",
                "```bash",
                item["gate_command"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Completion Rule",
            "",
            "Only rerun the completion audit after the real Feishu/OpenClaw logs and Cognee long-run evidence exist.",
            "A saved `completion-audit.json` with `goal_complete=false` is an audit artifact, not a success proof.",
            "",
        ]
    )
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


def _blocking_resolution_steps(checks: dict[str, dict[str, Any]]) -> list[str]:
    steps: list[str] = []
    singleton = checks.get("single_listener") or {}
    if singleton.get("status") == "fail":
        report = str(singleton.get("report") or "Stop the conflicting Feishu listener before collecting live logs.")
        steps.append(report)
    event_subscription = checks.get("event_subscription") or {}
    if event_subscription.get("status") == "fail":
        diagnostics = event_subscription.get("diagnostics")
        remediation = diagnostics.get("remediation") if isinstance(diagnostics, dict) else None
        remediation_steps = remediation.get("steps") if isinstance(remediation, dict) else None
        if isinstance(remediation_steps, list) and remediation_steps:
            steps.extend(str(step) for step in remediation_steps)
        else:
            steps.append(str(event_subscription.get("detail") or "Fix Feishu event diagnostics before live capture."))
    return steps


def _write_diagnostic_inputs(
    *,
    create_dirs: bool,
    diagnostic_paths: dict[str, Path],
    event_subscription: dict[str, Any],
    embedding_sample_log: Path | None,
    embedding_sampler_pid_file: Path | None,
    cognee_sampler_status: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    if not create_dirs:
        return {}

    results: dict[str, dict[str, str]] = {}
    event_diagnostics = event_subscription.get("diagnostics")
    if isinstance(event_diagnostics, dict):
        results["feishu_event_diagnostics"] = _write_json_file(
            diagnostic_paths["feishu_event_diagnostics"],
            event_diagnostics,
        )
    else:
        results["feishu_event_diagnostics"] = {
            "status": "warning",
            "path": str(diagnostic_paths["feishu_event_diagnostics"]),
            "detail": "Event subscription diagnostics were unavailable; rerun the manual diagnostics command.",
        }

    if embedding_sample_log:
        sampler_status = cognee_sampler_status
        if sampler_status is None:
            try:
                sampler_status = check_cognee_embedding_sampler_status(
                    embedding_sample_log=embedding_sample_log,
                    pid_file=embedding_sampler_pid_file,
                )
            except Exception as exc:  # pragma: no cover - defensive local process/file boundary.
                results["cognee_sampler_status"] = {
                    "status": "warning",
                    "path": str(diagnostic_paths["cognee_sampler_status"]),
                    "detail": f"Unable to check Cognee sampler status: {exc}",
                }
                return results
        results["cognee_sampler_status"] = _write_json_file(
            diagnostic_paths["cognee_sampler_status"],
            sampler_status,
        )
    return results


def _write_json_file(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        return {"status": "warning", "path": str(path), "detail": f"Unable to write diagnostic JSON: {exc}"}
    return {"status": "pass", "path": str(path), "detail": "written"}


def _write_text_file(path: Path, content: str) -> dict[str, str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"status": "warning", "path": str(path), "detail": f"Unable to write text file: {exc}"}
    return {"status": "pass", "path": str(path), "detail": "written"}


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
    reviewer_open_id: str,
    planned_listener: PlannedListener,
    openclaw_config_path: Path | None,
) -> list[dict[str, Any]]:
    chat_filter = f" --expected-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    target_chat_probe = f" --target-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    actor_filter = f" --expected-actor-id {non_reviewer_open_id}" if non_reviewer_open_id else ""
    cognee_arg = f" --cognee-long-run-evidence {cognee_long_run_evidence}" if cognee_long_run_evidence else ""
    event_diagnostics_arg = f" --feishu-event-diagnostics {diagnostic_paths['feishu_event_diagnostics']}"
    packet_chat_filter = f" --expected-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    packet_actor_filter = (
        f" --expected-non-reviewer-open-id {non_reviewer_open_id}" if non_reviewer_open_id else ""
    )
    packet_reviewer_filter = f" --expected-reviewer-open-id {reviewer_open_id}" if reviewer_open_id else ""
    sampler_status_arg = (
        f" --cognee-sampler-status {diagnostic_paths['cognee_sampler_status']}" if embedding_sample_log else ""
    )
    openclaw_config_arg = f" --openclaw-config {openclaw_config_path}" if openclaw_config_path else ""
    steps = [
        {
            "id": "1",
            "title": "Run read-only event subscription diagnostics",
            "phase": "preflight",
            "requires_ready_to_capture_live_logs": False,
            "instruction": (
                "python3 scripts/check_feishu_event_subscription_diagnostics.py "
                f"--planned-listener {planned_listener} --require-group-message-scope"
                f"{target_chat_probe}{openclaw_config_arg} --json "
                f"> {diagnostic_paths['feishu_event_diagnostics']}"
            ),
        },
        {
            "id": "2",
            "title": "Send non-@ group text",
            "phase": "live_capture",
            "requires_ready_to_capture_live_logs": True,
            "instruction": (
                "In the controlled enabled group, send exactly this as a normal user without mentioning the bot: "
                "决定：非 @ 群消息 live gate 测试，今天只验证事件投递。 Save the listener/OpenClaw log to "
                f"{log_paths['passive_event_log']}."
            ),
        },
        {
            "id": "3",
            "title": "Trigger first-class fmc tools",
            "phase": "live_capture",
            "requires_ready_to_capture_live_logs": True,
            "instruction": (
                "In Feishu DM or the controlled group, ask OpenClaw to run fmc_memory_search and fmc_memory_prefetch "
                "through the Feishu path. Save successful bridge result logs to "
                f"{log_paths['routing_event_log']}."
            ),
        },
        {
            "id": "4",
            "title": "Ask second non-reviewer to enable memory",
            "phase": "live_capture",
            "requires_ready_to_capture_live_logs": True,
            "instruction": (
                "From the second real non-reviewer account, send @Bot /enable_memory in the controlled group. "
                f"Save the live result log to {log_paths['permission_event_log']}."
            ),
        },
        {
            "id": "5",
            "title": "Run review DM/card E2E",
            "phase": "live_capture",
            "requires_ready_to_capture_live_logs": True,
            "instruction": (
                "Create a fresh candidate, send /review as reviewer, click one card action, and preserve private DM "
                f"delivery plus update_card result logs in {log_paths['review_event_log']}."
            ),
        },
        {
            "id": "6",
            "title": "Build sanitized Feishu live packet",
            "phase": "post_capture",
            "requires_ready_to_capture_live_logs": True,
            "instruction": (
                "python3 scripts/collect_feishu_live_evidence_packet.py "
                f"--passive-event-log {log_paths['passive_event_log']} "
                f"--routing-event-log {log_paths['routing_event_log']} "
                f"--permission-event-log {log_paths['permission_event_log']} "
                f"--review-event-log {log_paths['review_event_log']}{event_diagnostics_arg}"
                f"{packet_chat_filter}{packet_actor_filter}{packet_reviewer_filter} "
                f"--output {packet_output} --json"
            ),
        },
        {
            "id": "7",
            "title": "Run focused gates with filters",
            "phase": "post_capture",
            "requires_ready_to_capture_live_logs": True,
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
                "phase": "cognee",
                "requires_ready_to_capture_live_logs": False,
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
            "phase": "audit",
            "requires_ready_to_capture_live_logs": False,
            "instruction": (
                "python3 scripts/check_openclaw_feishu_productization_completion.py "
                f"--feishu-live-evidence-packet {packet_output}{event_diagnostics_arg}{sampler_status_arg}{cognee_arg} "
                f"--output {completion_output} --json"
            ),
        },
    )
    return steps


def _evidence_checklist(
    *,
    log_paths: dict[str, Path],
    diagnostic_paths: dict[str, Path],
    packet_output: Path,
    completion_output: Path,
    cognee_long_run_evidence: Path | None,
    embedding_sample_log: Path | None,
    controlled_chat_id: str,
    non_reviewer_open_id: str,
    reviewer_open_id: str,
) -> list[dict[str, Any]]:
    chat_filter = f" --target-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    passive_chat_filter = f" --expected-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    permission_actor_filter = f" --expected-actor-id {non_reviewer_open_id}" if non_reviewer_open_id else ""
    packet_chat_filter = f" --expected-chat-id {controlled_chat_id}" if controlled_chat_id else ""
    packet_actor_filter = (
        f" --expected-non-reviewer-open-id {non_reviewer_open_id}" if non_reviewer_open_id else ""
    )
    packet_reviewer_filter = f" --expected-reviewer-open-id {reviewer_open_id}" if reviewer_open_id else ""
    reviewer_filter = f" --expected-reviewer-open-id {reviewer_open_id}" if reviewer_open_id else ""
    cognee_evidence = cognee_long_run_evidence or Path("<pending-cognee-long-run-evidence.json>")
    return [
        {
            "id": "event_subscription_preflight",
            "completion_item": "1",
            "requirement": "Feishu app event subscription and group-message scope are readable before live capture.",
            "evidence_path": str(diagnostic_paths["feishu_event_diagnostics"]),
            "gate_command": (
                "python3 scripts/check_feishu_event_subscription_diagnostics.py "
                f"--require-group-message-scope{chat_filter} --json"
            ),
            "manual_step_ids": ["1"],
            "status": "preflight_required",
            "proxy_signal_warning": "Read-only diagnostics do not prove non-@ group message delivery.",
        },
        {
            "id": "non_at_group_message_live_delivery",
            "completion_item": "1",
            "requirement": "A real non-@ group text message reaches the current single listener.",
            "evidence_path": str(log_paths["passive_event_log"]),
            "gate_command": (
                "python3 scripts/check_feishu_passive_message_event_gate.py "
                f"--event-log {log_paths['passive_event_log']}{passive_chat_filter} --json"
            ),
            "manual_step_ids": ["2", "7"],
            "status": "requires_real_feishu_message",
            "proxy_signal_warning": "At-mention messages, reaction events, and unit tests are insufficient.",
        },
        {
            "id": "first_class_memory_tool_live_routing",
            "completion_item": "3",
            "requirement": "Real Feishu/OpenClaw path emits fmc_memory_search, fmc_memory_create_candidate, and fmc_memory_prefetch results.",
            "evidence_path": str(log_paths["routing_event_log"]),
            "gate_command": (
                "python3 scripts/collect_feishu_live_evidence_packet.py "
                f"--passive-event-log {log_paths['passive_event_log']} "
                f"--routing-event-log {log_paths['routing_event_log']} "
                f"--permission-event-log {log_paths['permission_event_log']} "
                f"--review-event-log {log_paths['review_event_log']} "
                f"--feishu-event-diagnostics {diagnostic_paths['feishu_event_diagnostics']}"
                f"{packet_chat_filter}{packet_actor_filter}{packet_reviewer_filter} "
                f"--output {packet_output} --json"
            ),
            "manual_step_ids": ["3", "6"],
            "status": "requires_real_feishu_openclaw_result",
            "proxy_signal_warning": "Local fmc tool registry and dry-run bridge results are insufficient.",
        },
        {
            "id": "live_negative_permission_second_user",
            "completion_item": "4",
            "requirement": "A second real non-reviewer user is denied when sending @Bot /enable_memory.",
            "evidence_path": str(log_paths["permission_event_log"]),
            "gate_command": (
                "python3 scripts/check_feishu_permission_negative_gate.py "
                f"--event-log {log_paths['permission_event_log']}{passive_chat_filter}{permission_actor_filter} --json"
            ),
            "manual_step_ids": ["4", "7"],
            "status": "requires_second_real_user",
            "proxy_signal_warning": "Reviewer/admin allow-path logs do not cover the negative permission requirement.",
        },
        {
            "id": "review_dm_card_e2e",
            "completion_item": "5",
            "requirement": "Real /review produces private DM/card delivery and card action update result.",
            "evidence_path": str(log_paths["review_event_log"]),
            "gate_command": (
                "python3 scripts/check_feishu_review_delivery_gate.py "
                f"--event-log {log_paths['review_event_log']}{reviewer_filter} --json"
            ),
            "manual_step_ids": ["5", "6"],
            "status": "requires_real_review_dm_and_click",
            "proxy_signal_warning": "Candidate review card creation alone is insufficient.",
        },
        {
            "id": "cognee_embedding_long_term_service",
            "completion_item": "8",
            "requirement": "Cognee curated sync has persistent-store readback and >=24h embedding health evidence.",
            "evidence_path": str(cognee_evidence),
            "gate_command": (
                "python3 scripts/check_openclaw_feishu_productization_completion.py "
                f"--feishu-live-evidence-packet {packet_output} "
                f"--cognee-long-run-evidence {cognee_evidence} --output {completion_output} --json"
            ),
            "manual_step_ids": ["8", "9"] if embedding_sample_log else ["8"],
            "status": "requires_24h_long_run_evidence",
            "proxy_signal_warning": "Live embedding dimension checks and Cognee dry-run are insufficient.",
        },
    ]


def _event_subscription_check(
    *,
    planned_listener: PlannedListener,
    controlled_chat_id: str,
    openclaw_config_path: Path | None,
    diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        report = diagnostics or run_feishu_event_subscription_diagnostics(
            planned_listener=planned_listener,
            require_group_message_scope=True,
            target_chat_id=controlled_chat_id or None,
            openclaw_config_path=openclaw_config_path,
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
