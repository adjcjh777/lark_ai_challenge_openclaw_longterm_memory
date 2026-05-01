#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_feishu_dm_routing import check_live_routing_events  # noqa: E402
from scripts.check_feishu_passive_message_event_gate import check_passive_message_events  # noqa: E402
from scripts.check_feishu_permission_negative_gate import check_permission_negative_events  # noqa: E402
from scripts.check_feishu_review_delivery_gate import check_review_delivery_log_events  # noqa: E402

DEFAULT_PASSIVE_EVENT_LOG = (
    ROOT / "logs/feishu-copilot-live/2026-05-01-any-group-test-isolated/feishu-listen-20260501_191825.ndjson"
)
DEFAULT_PERMISSION_EVENT_LOG = DEFAULT_PASSIVE_EVENT_LOG
DEFAULT_REVIEW_EVENT_LOG = ROOT / "logs/feishu-copilot-live-test/feishu-listen-20260429_202445.ndjson"
DEFAULT_ROUTING_EVENT_LOG = DEFAULT_REVIEW_EVENT_LOG
REQUIRED_ROUTING_TOOLS = ("fmc_memory_search", "fmc_memory_create_candidate", "fmc_memory_prefetch")

BOUNDARY = (
    "completion audit only; maps the nine unfinished OpenClaw-native Feishu Memory Copilot tasks "
    "to concrete evidence gates and refuses goal_complete when live or long-running evidence is missing"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the nine remaining OpenClaw-native Feishu Memory Copilot productization tasks against "
            "concrete repo artifacts and live evidence logs."
        )
    )
    parser.add_argument("--passive-event-log", type=Path, default=DEFAULT_PASSIVE_EVENT_LOG)
    parser.add_argument("--permission-event-log", type=Path, default=DEFAULT_PERMISSION_EVENT_LOG)
    parser.add_argument("--review-event-log", type=Path, default=DEFAULT_REVIEW_EVENT_LOG)
    parser.add_argument("--routing-event-log", type=Path, default=DEFAULT_ROUTING_EVENT_LOG)
    parser.add_argument(
        "--feishu-live-evidence-packet",
        type=Path,
        default=None,
        help=(
            "Optional sanitized packet from collect_feishu_live_evidence_packet.py. When present, items 1/3/4/5 "
            "are audited from the packet reports instead of raw logs."
        ),
    )
    parser.add_argument(
        "--feishu-event-diagnostics",
        type=Path,
        default=None,
        help=(
            "Optional JSON from check_feishu_event_subscription_diagnostics.py. When present, item 1 reports "
            "missing group-message scope as the preflight blocker before asking for another live send."
        ),
    )
    parser.add_argument(
        "--cognee-long-run-evidence",
        type=Path,
        default=None,
        help=(
            "Optional JSON evidence for Cognee/embedding long-running service. It must include "
            "cognee_sync.status=pass, persistence.store_reopened=true, embedding_service.window_hours>=24, "
            "and embedding_service.healthcheck_sample_count>=3."
        ),
    )
    parser.add_argument(
        "--cognee-sampler-status",
        type=Path,
        default=None,
        help=(
            "Optional JSON from check_cognee_embedding_sampler_status.py. Used only to explain item 8 progress "
            "when final long-run evidence is not ready."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = build_completion_audit(
        passive_event_log=args.passive_event_log,
        permission_event_log=args.permission_event_log,
        review_event_log=args.review_event_log,
        routing_event_log=args.routing_event_log,
        feishu_live_evidence_packet=args.feishu_live_evidence_packet,
        feishu_event_diagnostics=args.feishu_event_diagnostics,
        cognee_long_run_evidence=args.cognee_long_run_evidence,
        cognee_sampler_status=args.cognee_sampler_status,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["goal_complete"] else 1


def build_completion_audit(
    *,
    passive_event_log: Path | None = DEFAULT_PASSIVE_EVENT_LOG,
    permission_event_log: Path | None = DEFAULT_PERMISSION_EVENT_LOG,
    review_event_log: Path | None = DEFAULT_REVIEW_EVENT_LOG,
    routing_event_log: Path | None = DEFAULT_ROUTING_EVENT_LOG,
    feishu_live_evidence_packet: Path | None = None,
    feishu_event_diagnostics: Path | None = None,
    cognee_long_run_evidence: Path | None = None,
    cognee_sampler_status: Path | None = None,
) -> dict[str, Any]:
    live_packet = _load_live_packet(feishu_live_evidence_packet) if feishu_live_evidence_packet else None
    event_diagnostics = _load_event_diagnostics(feishu_event_diagnostics) if feishu_event_diagnostics else None
    items = [
        _passive_group_message_item(
            passive_event_log=passive_event_log,
            live_packet=live_packet,
            event_diagnostics=event_diagnostics,
        ),
        _single_listener_item(),
        _live_gate_item_or_packet(
            item_id="3",
            name="first_class_memory_tool_live_routing",
            requirement=(
                "真实 Feishu DM/群聊必须稳定路由到 first-class fmc_* bridge，并至少覆盖 search、"
                "create_candidate 和 prefetch 的成功结果。"
            ),
            evidence_path=routing_event_log,
            packet=live_packet,
            packet_key="first_class_routing",
            gate=lambda text: check_live_routing_events(text, required_tools=REQUIRED_ROUTING_TOOLS),
            pass_reason="first_class_live_routing_evidence_seen",
        ),
        _live_gate_item_or_packet(
            item_id="4",
            name="live_negative_permission_second_user",
            requirement="第二个真实非 reviewer 用户在受控群里执行 /enable_memory 必须被拒绝，并输出 live result。",
            evidence_path=permission_event_log,
            packet=live_packet,
            packet_key="permission_negative",
            gate=check_permission_negative_events,
            pass_reason="non_reviewer_enable_memory_denied",
        ),
        _live_gate_item_or_packet(
            item_id="5",
            name="review_dm_card_e2e",
            requirement="真实 /review 私聊 DM、interactive card 点击和 update_card 结果必须出现在同一类 live 日志证据中。",
            evidence_path=review_event_log,
            packet=live_packet,
            packet_key="review_delivery",
            gate=check_review_delivery_log_events,
            pass_reason="review_delivery_e2e_evidence_seen",
        ),
        _dashboard_access_control_item(),
        _clean_demo_db_item(),
        _cognee_long_term_item(cognee_long_run_evidence, sampler_status_path=cognee_sampler_status),
        _no_overclaim_item(),
    ]
    blockers = [
        {
            "item": item["item"],
            "name": item["name"],
            "reason": item["reason"],
            "next_step": item["next_step"],
        }
        for item in items
        if item["status"] != "pass"
    ]
    goal_complete = not blockers
    return {
        "ok": goal_complete,
        "goal_complete": goal_complete,
        "status": "complete" if goal_complete else "incomplete",
        "boundary": BOUNDARY,
        "required_routing_tools": list(REQUIRED_ROUTING_TOOLS),
        "items": items,
        "blockers": blockers,
        "next_step": ""
        if goal_complete
        else "Collect the missing real Feishu/OpenClaw live logs and Cognee/embedding long-run evidence, then rerun.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "OpenClaw Feishu Productization Completion Audit",
        f"goal_complete: {str(report['goal_complete']).lower()}",
        f"status: {report['status']}",
        f"boundary: {report['boundary']}",
        "",
        "items:",
    ]
    for item in report["items"]:
        lines.append(f"  {item['item']}. {item['name']}: {item['status']} ({item['reason']})")
    if report["blockers"]:
        lines.extend(["", "blockers:"])
        for blocker in report["blockers"]:
            lines.append(f"  {blocker['item']}. {blocker['name']}: {blocker['next_step']}")
    return "\n".join(lines)


def _live_gate_item(
    *,
    item_id: str,
    name: str,
    requirement: str,
    evidence_path: Path | None,
    gate: Callable[[str], dict[str, Any]],
    pass_reason: str,
) -> dict[str, Any]:
    if evidence_path is None:
        return _item(
            item_id=item_id,
            name=name,
            requirement=requirement,
            status="fail",
            reason="evidence_log_not_configured",
            evidence={"path": ""},
            next_step="Pass the captured live event/result log for this gate.",
        )
    resolved = evidence_path.expanduser()
    if not resolved.exists():
        return _item(
            item_id=item_id,
            name=name,
            requirement=requirement,
            status="fail",
            reason="evidence_log_missing",
            evidence={"path": str(resolved)},
            next_step=f"Capture the required live evidence and rerun with --{name.replace('_', '-')}-log.",
        )
    report = gate(resolved.read_text(encoding="utf-8"))
    ok = bool(report.get("ok")) and report.get("reason") == pass_reason
    return _item(
        item_id=item_id,
        name=name,
        requirement=requirement,
        status="pass" if ok else "fail",
        reason=str(report.get("reason") or ("gate_passed" if ok else "gate_failed")),
        evidence={
            "path": str(resolved),
            "gate": report.get("gate"),
            "summary": report.get("summary"),
            "missing_required_tools": report.get("missing_required_tools"),
            "failures": report.get("failures"),
        },
        next_step="" if ok else str(report.get("next_step") or "Collect live evidence that satisfies this gate."),
    )


def _live_gate_item_or_packet(
    *,
    item_id: str,
    name: str,
    requirement: str,
    evidence_path: Path | None,
    packet: dict[str, Any] | None,
    packet_key: str,
    gate: Callable[[str], dict[str, Any]],
    pass_reason: str,
) -> dict[str, Any]:
    if packet is None:
        return _live_gate_item(
            item_id=item_id,
            name=name,
            requirement=requirement,
            evidence_path=evidence_path,
            gate=gate,
            pass_reason=pass_reason,
        )
    if not packet.get("ok") and packet.get("reason"):
        return _item(
            item_id=item_id,
            name=name,
            requirement=requirement,
            status="fail",
            reason=str(packet.get("reason")),
            evidence={"packet": str(packet.get("path") or ""), "packet_ok": False},
            next_step="Fix the Feishu live evidence packet JSON or rerun the packet collector.",
        )
    reports = packet.get("reports") if isinstance(packet.get("reports"), dict) else {}
    report = reports.get(packet_key) if isinstance(reports.get(packet_key), dict) else None
    if report is None:
        return _item(
            item_id=item_id,
            name=name,
            requirement=requirement,
            status="fail",
            reason="live_evidence_packet_report_missing",
            evidence={"packet": str(packet.get("path") or ""), "packet_key": packet_key},
            next_step=f"Regenerate the Feishu live evidence packet with `{packet_key}` report included.",
        )
    ok = bool(report.get("ok")) and report.get("reason") == pass_reason
    return _item(
        item_id=item_id,
        name=name,
        requirement=requirement,
        status="pass" if ok else "fail",
        reason=str(report.get("reason") or ("gate_passed" if ok else "gate_failed")),
        evidence={
            "packet": str(packet.get("path") or ""),
            "packet_key": packet_key,
            "source_log": report.get("source_log"),
            "gate": report.get("gate"),
            "summary": report.get("summary"),
            "missing_required_tools": report.get("missing_required_tools"),
            "failures": report.get("failures"),
        },
        next_step="" if ok else str(report.get("next_step") or "Collect live evidence that satisfies this gate."),
    )


def _passive_group_message_item(
    *,
    passive_event_log: Path | None,
    live_packet: dict[str, Any] | None,
    event_diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    item = _live_gate_item_or_packet(
        item_id="1",
        name="non_at_group_message_live_delivery",
        requirement="普通非 @ 群文本消息必须真实进入当前单监听入口，并可触发 passive screening 前置判断。",
        evidence_path=passive_event_log,
        packet=live_packet,
        packet_key="passive_group_message",
        gate=check_passive_message_events,
        pass_reason="passive_group_message_seen",
    )
    if item["status"] == "pass" or not event_diagnostics or not _diagnostics_group_scope_missing(event_diagnostics):
        return item
    evidence = dict(item["evidence"])
    message_schema = event_diagnostics.get("message_event_schema")
    if not isinstance(message_schema, dict):
        message_schema = {}
    evidence["event_subscription_diagnostics"] = {
        "path": event_diagnostics.get("path"),
        "failed_checks": event_diagnostics.get("failed_checks"),
        "scopes": message_schema.get("scopes"),
        "has_group_message_scope": message_schema.get("has_group_message_scope"),
        "remediation": event_diagnostics.get("remediation"),
    }
    return _item(
        item_id="1",
        name="non_at_group_message_live_delivery",
        requirement=item["requirement"],
        status="fail",
        reason="message_schema_group_message_scope_missing",
        evidence=evidence,
        next_step=(
            "Feishu event diagnostics show the app schema lacks group-message readonly scope. "
            "Enable/verify im:message.group_msg:readonly or im:message:readonly for im.message.receive_v1, "
            "rerun diagnostics with --require-group-message-scope, then send a real non-@ group text."
        ),
    )


def _single_listener_item() -> dict[str, Any]:
    checks = {
        "guard_exists": (ROOT / "memory_engine/feishu_listener_guard.py").exists(),
        "singleton_script_exists": (ROOT / "scripts/check_feishu_listener_singleton.py").exists(),
        "guard_tests_exist": (ROOT / "tests/test_feishu_listener_guard.py").exists(),
        "runbook_mentions_three_modes": _any_file_contains(
            (
                ROOT / "docs/productization/feishu-staging-runbook.md",
                ROOT / "docs/productization/handoffs/feishu-staging-runbook.md",
            ),
            ("OpenClaw Feishu websocket", "Copilot lark-cli sandbox", "legacy", "三选一"),
        ),
        "generic_openclaw_fails_closed": _file_contains(
            ROOT / "memory_engine/feishu_listener_guard.py",
            "openclaw-gateway-unknown",
            "FeishuListenerConflict",
        ),
    }
    ok = all(checks.values())
    return _item(
        item_id="2",
        name="single_feishu_listener_entry",
        requirement="OpenClaw gateway、Copilot lark-cli sandbox 和 legacy listener 必须三选一，冲突时 fail closed。",
        status="pass" if ok else "fail",
        reason="single_listener_guard_present" if ok else "single_listener_guard_incomplete",
        evidence={"checks": checks},
        next_step="" if ok else "Complete listener guard, singleton CLI, tests, and staging runbook coverage.",
    )


def _dashboard_access_control_item() -> dict[str, Any]:
    checks = {
        "admin_readiness_gate": _file_contains(
            ROOT / "scripts/check_copilot_admin_readiness.py",
            "admin_token",
            "viewer_token",
            "strict",
            "remote_bind_auth",
            "access_policy",
        ),
        "sso_gate": (ROOT / "scripts/check_copilot_admin_sso_gate.py").exists(),
        "admin_tests": _file_contains(ROOT / "tests/test_copilot_admin.py", "viewer", "admin", "production_blockers"),
        "docs_keep_preproduction_boundary": _file_contains(
            ROOT / "README.md",
            "admin/viewer token",
            "SSO",
            "这仍不是生产",
        ),
    }
    ok = all(checks.values())
    return _item(
        item_id="6",
        name="dashboard_auth_preproduction_access_control",
        requirement="Dashboard 至少要有 admin/viewer token、SSO/minimal access-control gate，并继续标注 pre-production 边界。",
        status="pass" if ok else "fail",
        reason="preproduction_access_control_artifacts_present" if ok else "preproduction_access_control_incomplete",
        evidence={"checks": checks},
        next_step="" if ok else "Complete admin/viewer auth, SSO gate, tests, and no-production boundary docs.",
    )


def _clean_demo_db_item() -> dict[str, Any]:
    checks = {
        "script_exists": (ROOT / "scripts/prepare_clean_demo_db.py").exists(),
        "tests_exist": (ROOT / "tests/test_clean_demo_db.py").exists(),
        "does_not_modify_source": _file_contains(ROOT / "scripts/prepare_clean_demo_db.py", "source_db_modified", "False"),
        "blocks_group_policy_noise": _file_contains(
            ROOT / "scripts/prepare_clean_demo_db.py",
            "feishu_group_policy_total",
            "group_policies_carried_over",
        ),
        "manual_guide": _file_contains(ROOT / "docs/manual-testing-guide.md", "prepare_clean_demo_db.py", "output DB"),
    }
    ok = all(checks.values())
    return _item(
        item_id="7",
        name="clean_demo_db_isolation",
        requirement="Demo 前必须能生成隔离干净 DB，不能把 live 测试 memory/group policy/audit 噪声带给评委。",
        status="pass" if ok else "fail",
        reason="clean_demo_db_isolation_artifacts_present" if ok else "clean_demo_db_isolation_incomplete",
        evidence={"checks": checks},
        next_step="" if ok else "Complete clean demo DB generator, tests, and runbook evidence.",
    )


def _cognee_long_term_item(evidence_path: Path | None, *, sampler_status_path: Path | None = None) -> dict[str, Any]:
    local_sync_gate = _file_contains(
        ROOT / "scripts/check_cognee_curated_sync_gate.py",
        "CogneeMemoryAdapter",
        "CopilotService",
        "production_boundary",
    )
    if evidence_path is None:
        sampler_status = _load_sampler_status(sampler_status_path) if sampler_status_path else None
        if sampler_status is not None:
            return _cognee_sampler_status_item(local_sync_gate=local_sync_gate, sampler_status=sampler_status)
        return _item(
            item_id="8",
            name="cognee_embedding_long_term_service",
            requirement="Cognee curated sync 和 embedding provider 必须有真实持久 store、重启后读回和长时间运行证据。",
            status="fail",
            reason="long_term_cognee_embedding_evidence_missing",
            evidence={"local_curated_sync_gate_present": local_sync_gate, "long_run_evidence_path": ""},
            next_step=(
                "Run scripts/collect_cognee_embedding_long_run_evidence.py with a real curated-sync report, "
                "persistent-store reopen/readback proof, and >=24h embedding health samples; then pass "
                "--cognee-long-run-evidence."
            ),
        )
    loaded = _load_json(evidence_path)
    if not loaded["ok"]:
        return _item(
            item_id="8",
            name="cognee_embedding_long_term_service",
            requirement="Cognee curated sync 和 embedding provider 必须有真实持久 store、重启后读回和长时间运行证据。",
            status="fail",
            reason=loaded["reason"],
            evidence={"local_curated_sync_gate_present": local_sync_gate, "long_run_evidence_path": str(evidence_path)},
            next_step="Fix the Cognee/embedding long-run evidence JSON and rerun.",
        )
    payload = loaded["payload"]
    cognee_sync = payload.get("cognee_sync") if isinstance(payload, dict) else {}
    persistence = payload.get("persistence") if isinstance(payload, dict) else {}
    embedding_service = payload.get("embedding_service") if isinstance(payload, dict) else {}
    checks = {
        "local_curated_sync_gate_present": local_sync_gate,
        "cognee_sync_pass": isinstance(cognee_sync, dict) and cognee_sync.get("status") == "pass",
        "store_reopened": isinstance(persistence, dict) and persistence.get("store_reopened") is True,
        "reopened_search_pass": isinstance(persistence, dict) and persistence.get("reopened_search_ok") is True,
        "embedding_window_at_least_24h": _number(embedding_service.get("window_hours")) >= 24,
        "embedding_health_samples_at_least_3": _number(embedding_service.get("healthcheck_sample_count")) >= 3,
    }
    ok = all(checks.values())
    return _item(
        item_id="8",
        name="cognee_embedding_long_term_service",
        requirement="Cognee curated sync 和 embedding provider 必须有真实持久 store、重启后读回和长时间运行证据。",
        status="pass" if ok else "fail",
        reason="long_term_cognee_embedding_evidence_seen" if ok else "long_term_cognee_embedding_evidence_incomplete",
        evidence={"path": str(evidence_path), "checks": checks},
        next_step="" if ok else "Provide Cognee sync pass, reopened persistent-store readback, and >=24h embedding service samples.",
    )


def _cognee_sampler_status_item(*, local_sync_gate: bool, sampler_status: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "local_curated_sync_gate_present": local_sync_gate,
        "long_run_evidence_path": "",
        "sampler_status": {
            "path": sampler_status.get("path"),
            "ok": sampler_status.get("ok"),
            "completion_ready": sampler_status.get("completion_ready"),
            "sample_count": sampler_status.get("sample_count"),
            "successful_sample_count": sampler_status.get("successful_sample_count"),
            "embedding_window_hours": sampler_status.get("embedding_window_hours"),
            "estimated_ready_at": sampler_status.get("estimated_ready_at"),
            "failed_checks": sampler_status.get("failed_checks"),
            "warning_checks": sampler_status.get("warning_checks"),
        },
    }
    if sampler_status.get("completion_ready") is True:
        reason = "cognee_sampler_ready_but_long_run_evidence_missing"
        next_step = (
            "Sampler status is ready; run collect_cognee_embedding_long_run_evidence.py with curated-sync and "
            "persistent readback reports, then pass --cognee-long-run-evidence."
        )
    elif sampler_status.get("ok"):
        reason = "cognee_sampler_running_but_window_incomplete"
        next_step = str(
            sampler_status.get("next_step")
            or "Leave the sampler running until successful samples and the required time window are complete."
        )
    else:
        reason = "cognee_sampler_status_failed"
        next_step = str(sampler_status.get("next_step") or "Restart or repair the Cognee embedding sampler.")
    return _item(
        item_id="8",
        name="cognee_embedding_long_term_service",
        requirement="Cognee curated sync 和 embedding provider 必须有真实持久 store、重启后读回和长时间运行证据。",
        status="fail",
        reason=reason,
        evidence=evidence,
        next_step=next_step,
    )


def _no_overclaim_item() -> dict[str, Any]:
    docs = [
        ROOT / "README.md",
        ROOT / "docs/productization/agent-execution-contract.md",
        ROOT / "docs/productization/prd-completion-audit-and-gap-tasks.md",
    ]
    checks = {
        "production_not_claimed": all(_file_contains(path, "不能说") or _file_contains(path, "不是生产") for path in docs),
        "any_group_boundary_present": _file_contains(
            ROOT / "scripts/openclaw_feishu_remember_router.py",
            "passive_memory_enabled",
            "后续非 @ 群消息不会进入 passive candidate screening",
        ),
        "stable_routing_boundary_present": _file_contains(
            ROOT / "README.md",
            "不能写成稳定长期路由",
            "长期 embedding 服务仍未完成",
        ),
    }
    ok = all(checks.values())
    return _item(
        item_id="9",
        name="no_any_group_auto_memory_overclaim",
        requirement="只能说 bot 可发现/登记群并响应设置命令；不能说任意群默认开始记忆。",
        status="pass" if ok else "fail",
        reason="no_overclaim_boundary_present" if ok else "no_overclaim_boundary_incomplete",
        evidence={"checks": checks},
        next_step="" if ok else "Restore README/docs/router wording that passive memory requires explicit reviewer/admin enablement.",
    )


def _item(
    *,
    item_id: str,
    name: str,
    requirement: str,
    status: str,
    reason: str,
    evidence: dict[str, Any],
    next_step: str,
) -> dict[str, Any]:
    return {
        "item": item_id,
        "name": name,
        "requirement": requirement,
        "status": status,
        "reason": reason,
        "blocking": status != "pass",
        "evidence": evidence,
        "next_step": next_step,
    }


def _file_contains(path: Path, *needles: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def _any_file_contains(paths: tuple[Path, ...], needles: tuple[str, ...]) -> bool:
    return any(_file_contains(path, *needles) for path in paths)


def _load_json(path: Path) -> dict[str, Any]:
    resolved = path.expanduser()
    if not resolved.exists():
        return {"ok": False, "reason": "long_run_evidence_file_missing"}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError:
        return {"ok": False, "reason": "long_run_evidence_file_unreadable"}
    except json.JSONDecodeError:
        return {"ok": False, "reason": "long_run_evidence_invalid_json"}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "long_run_evidence_must_be_json_object"}
    return {"ok": True, "payload": payload}


def _load_live_packet(path: Path) -> dict[str, Any]:
    loaded = _load_json(path)
    if not loaded["ok"]:
        return {"ok": False, "path": str(path), "reason": loaded["reason"], "reports": {}}
    payload = loaded["payload"]
    payload["path"] = str(path)
    if not isinstance(payload.get("reports"), dict):
        return {"ok": False, "path": str(path), "reason": "live_evidence_packet_reports_missing", "reports": {}}
    return payload


def _load_event_diagnostics(path: Path) -> dict[str, Any]:
    loaded = _load_json(path)
    if not loaded["ok"]:
        return {"ok": False, "path": str(path), "reason": loaded["reason"]}
    payload = loaded["payload"]
    diagnostics = _extract_event_diagnostics(payload)
    diagnostics["path"] = str(path)
    return diagnostics


def _extract_event_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    event_subscription = checks.get("event_subscription") if isinstance(checks.get("event_subscription"), dict) else {}
    nested = event_subscription.get("diagnostics") if isinstance(event_subscription.get("diagnostics"), dict) else None
    return nested if nested is not None else payload


def _diagnostics_group_scope_missing(diagnostics: dict[str, Any]) -> bool:
    if not diagnostics.get("ok") and diagnostics.get("reason"):
        return False
    failed = diagnostics.get("failed_checks") if isinstance(diagnostics.get("failed_checks"), list) else []
    schema = diagnostics.get("message_event_schema") if isinstance(diagnostics.get("message_event_schema"), dict) else {}
    return "message_schema_group_message_scope" in failed or schema.get("has_group_message_scope") is False


def _load_sampler_status(path: Path) -> dict[str, Any]:
    loaded = _load_json(path)
    if not loaded["ok"]:
        return {"ok": False, "path": str(path), "reason": loaded["reason"]}
    payload = loaded["payload"]
    payload["path"] = str(path)
    return payload


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
