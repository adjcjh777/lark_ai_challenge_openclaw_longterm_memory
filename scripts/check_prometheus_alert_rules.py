#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_PATH = ROOT / "deploy" / "monitoring" / "copilot-admin-alerts.yml"

REQUIRED_ALERTS: dict[str, tuple[str, ...]] = {
    "CopilotAdminMetricsDown": ("up",),
    "CopilotLaunchStagingNotReady": ("copilot_admin_launch_staging_ok",),
    "CopilotWikiCardsMissing": ("copilot_admin_wiki_card_count",),
    "CopilotGraphNodesMissing": ("copilot_admin_graph_workspace_node_count",),
    "CopilotTenantPolicyMissing": ("copilot_admin_tenant_policy_count",),
    "CopilotAuditLedgerEmpty": ("copilot_admin_audit_total",),
    "CopilotProductionStillBlocked": ("copilot_admin_launch_production_blocked",),
    "CopilotProductionMonitoringBlocker": (
        "copilot_admin_launch_production_blocker",
        'blocker="production_monitoring_alerts"',
    ),
}

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(token|secret|password|api[_-]?key|bearer)\b"),
    re.compile(r"(?i)xox[baprs]-[a-z0-9-]+"),
)


def check_alert_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    if not path.exists():
        checks["file_exists"] = {"status": "fail", "path": str(path)}
        return _report(path=path, checks=checks, alerts={})

    text = path.read_text(encoding="utf-8")
    alerts = _parse_alert_blocks(text)
    checks["file_exists"] = {"status": "pass", "path": str(path)}
    checks["group_shape"] = _group_shape_check(text)
    checks["required_alerts"] = _required_alerts_check(alerts)
    checks["required_metrics"] = _required_metrics_check(alerts)
    checks["labels_and_annotations"] = _labels_and_annotations_check(alerts)
    checks["no_secrets"] = _no_secrets_check(text)
    return _report(path=path, checks=checks, alerts=alerts)


def _parse_alert_blocks(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^(\s*)-\s+alert:\s*([A-Za-z0-9_]+)\s*$", text))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[match.group(2)] = text[start:end]
    return blocks


def _group_shape_check(text: str) -> dict[str, Any]:
    has_groups = bool(re.search(r"(?m)^groups:\s*$", text))
    has_named_group = bool(re.search(r"(?m)^\s*-\s+name:\s+feishu-memory-copilot-admin\s*$", text))
    return {
        "status": "pass" if has_groups and has_named_group else "fail",
        "has_groups": has_groups,
        "has_named_group": has_named_group,
    }


def _required_alerts_check(alerts: dict[str, str]) -> dict[str, Any]:
    missing = sorted(set(REQUIRED_ALERTS) - set(alerts))
    return {
        "status": "pass" if not missing else "fail",
        "missing": missing,
        "required": sorted(REQUIRED_ALERTS),
        "found": sorted(alerts),
    }


def _required_metrics_check(alerts: dict[str, str]) -> dict[str, Any]:
    missing: dict[str, list[str]] = {}
    for alert, required_fragments in REQUIRED_ALERTS.items():
        block = alerts.get(alert, "")
        missing_fragments = [fragment for fragment in required_fragments if fragment not in block]
        if missing_fragments:
            missing[alert] = missing_fragments
    return {
        "status": "pass" if not missing else "fail",
        "missing": missing,
    }


def _labels_and_annotations_check(alerts: dict[str, str]) -> dict[str, Any]:
    missing: dict[str, list[str]] = {}
    for alert in REQUIRED_ALERTS:
        block = alerts.get(alert, "")
        missing_fields: list[str] = []
        if not re.search(r"(?m)^\s+severity:\s+(info|warning|critical)\s*$", block):
            missing_fields.append("labels.severity")
        if not re.search(r"(?m)^\s+service:\s+feishu-memory-copilot\s*$", block):
            missing_fields.append("labels.service")
        if not re.search(r"(?m)^\s+summary:\s+", block):
            missing_fields.append("annotations.summary")
        if not re.search(r"(?m)^\s+description:\s+", block):
            missing_fields.append("annotations.description")
        if not re.search(r"(?m)^\s+runbook_url:\s+", block):
            missing_fields.append("annotations.runbook_url")
        if missing_fields:
            missing[alert] = missing_fields
    return {
        "status": "pass" if not missing else "fail",
        "missing": missing,
    }


def _no_secrets_check(text: str) -> dict[str, Any]:
    findings = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append({"line": line_no, "match": match.group(0)})
    return {
        "status": "pass" if not findings else "fail",
        "findings": findings,
    }


def _report(*, path: Path, checks: dict[str, dict[str, Any]], alerts: dict[str, str]) -> dict[str, Any]:
    status_counts = {"pass": 0, "warning": 0, "fail": 0}
    for check in checks.values():
        status = str(check.get("status") or "fail")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "ok": status_counts.get("fail", 0) == 0,
        "rules_path": str(path),
        "alert_count": len(alerts),
        "alerts": sorted(alerts),
        "checks": checks,
        "status_counts": status_counts,
        "boundary": "staging alert-rule artifact only; production Prometheus/Grafana deployment remains unverified.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Prometheus Alert Rules Check",
        f"ok: {str(report['ok']).lower()}",
        f"rules_path: {report['rules_path']}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    for name, check in report["checks"].items():
        lines.append(f"- {name}: {check.get('status')}")
    lines.append("")
    lines.append(f"alerts: {', '.join(report['alerts'])}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Copilot Prometheus alert-rule artifacts.")
    parser.add_argument("--rules-path", default=str(DEFAULT_RULES_PATH), help="Prometheus alert rules YAML path.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    report = check_alert_rules(Path(args.rules_path))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
