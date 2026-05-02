#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = (
    "live_monitoring_probe_only; validates an already-running Admin /metrics endpoint and external monitoring refs; "
    "does not configure Prometheus, Grafana, Alertmanager, IdP, DB, TLS, or productized live readiness"
)
REQUIRED_METRICS = (
    "copilot_admin_memory_total",
    "copilot_admin_wiki_card_count",
    "copilot_admin_graph_workspace_node_count",
    "copilot_admin_launch_production_blocked",
)
PLACEHOLDER_HOSTS = {"example.com", "localhost", "127.0.0.1", "::1"}
PLACEHOLDER_SUFFIXES = (".example.com", ".localhost")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")

MetricsFetcher = Callable[[str, Optional[str], float], dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Copilot Admin production monitoring evidence.")
    parser.add_argument(
        "--base-url", required=True, help="Production Admin base URL, e.g. https://memory.company/admin/"
    )
    parser.add_argument("--token", default=None, help="Optional viewer/admin token for /metrics.")
    parser.add_argument("--grafana-dashboard-url", required=True, help="Production Grafana dashboard URL.")
    parser.add_argument("--alertmanager-route", required=True, help="Production Alertmanager route name.")
    parser.add_argument("--alert-delivery-tested-at", required=True, help="ISO-8601 alert delivery test timestamp.")
    parser.add_argument(
        "--monitoring-evidence-ref", action="append", default=[], help="Non-secret monitoring proof ref."
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Network timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_monitoring_probe(
        base_url=args.base_url,
        token=args.token,
        grafana_dashboard_url=args.grafana_dashboard_url,
        alertmanager_route=args.alertmanager_route,
        alert_delivery_tested_at=args.alert_delivery_tested_at,
        monitoring_evidence_refs=args.monitoring_evidence_ref,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def run_monitoring_probe(
    *,
    base_url: str,
    token: str | None,
    grafana_dashboard_url: str,
    alertmanager_route: str,
    alert_delivery_tested_at: str,
    monitoring_evidence_refs: list[str],
    timeout: float = 10.0,
    metrics_fetcher: MetricsFetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    checks: dict[str, dict[str, Any]] = {
        "admin_url": _url_check(base_url, description="Admin base URL is a non-placeholder production HTTPS endpoint."),
        "grafana_url": _url_check(
            grafana_dashboard_url,
            description="Grafana dashboard URL is a non-placeholder production HTTPS endpoint.",
        ),
        "alerting": _alerting_check(alertmanager_route, alert_delivery_tested_at, monitoring_evidence_refs),
    }
    metrics_payload = ""
    metrics_url = urljoin(base_url.rstrip("/") + "/", "metrics")
    if checks["admin_url"]["status"] == "pass":
        try:
            metrics_result = (metrics_fetcher or _fetch_metrics)(metrics_url, token, timeout)
            metrics_payload = str(metrics_result.get("body") or "")
            checks["metrics"] = _metrics_check(metrics_result)
        except Exception as exc:  # pragma: no cover - network errors vary by platform.
            checks["metrics"] = _fail("Admin /metrics endpoint can be fetched and parsed.", error=str(exc))
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    host = urlparse(base_url).hostname or ""
    evidence_refs = list(monitoring_evidence_refs)
    if not failed:
        evidence_refs.append(f"metrics_probe:{host}:{now.isoformat()}")
    patch = {
        "production_monitoring": {
            "prometheus_scrape_proven": checks.get("metrics", {}).get("status") == "pass",
            "grafana_dashboard_url": grafana_dashboard_url,
            "alertmanager_route": alertmanager_route,
            "alert_delivery_tested_at": alert_delivery_tested_at,
            "evidence_refs": evidence_refs if not failed else [],
        }
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "base_url": base_url,
        "metrics_url": metrics_url,
        "checks": checks,
        "failed_checks": failed,
        "metric_names_seen": _metric_names(metrics_payload),
        "production_manifest_patch": patch,
        "next_step": ""
        if not failed
        else "Fix Admin /metrics, Grafana URL, alert route, delivery timestamp, or evidence refs before merging.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin Monitoring Probe",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        f"metrics_url: {report['metrics_url']}",
        "checks:",
    ]
    for name, check in sorted(report["checks"].items()):
        lines.append(f"- {name}: {check['status']} {check.get('description', '')}".rstrip())
        if check.get("missing_or_placeholder"):
            lines.append(f"  missing: {', '.join(check['missing_or_placeholder'])}")
        if check.get("error"):
            lines.append(f"  error: {check['error']}")
    return "\n".join(lines)


def _fetch_metrics(metrics_url: str, token: str | None, timeout: float) -> dict[str, Any]:
    headers = {"Accept": "text/plain"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(metrics_url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return {
            "status": int(response.status),
            "content_type": response.headers.get("Content-Type", ""),
            "body": response.read().decode("utf-8", errors="replace"),
        }


def _url_check(value: str, *, description: str) -> dict[str, Any]:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    checks = {
        "scheme_is_https": parsed.scheme == "https",
        "host_is_present": bool(host),
        "host_is_not_placeholder": bool(host) and _is_production_host(host),
        "url_has_no_secret_like_value": not _contains_secret_like(value),
    }
    return _section_result(description, checks)


def _metrics_check(metrics_result: dict[str, Any]) -> dict[str, Any]:
    body = str(metrics_result.get("body") or "")
    names = set(_metric_names(body))
    checks = {
        "http_status_ok": 200 <= int(metrics_result.get("status") or 0) < 300,
        "content_type_text": "text" in str(metrics_result.get("content_type") or "").lower()
        or "openmetrics" in str(metrics_result.get("content_type") or "").lower(),
        "required_metrics_present": all(name in names for name in REQUIRED_METRICS),
    }
    result = _section_result("Admin /metrics exposes required Copilot production-monitoring metrics.", checks)
    result["required_metrics"] = list(REQUIRED_METRICS)
    result["metric_names_seen"] = sorted(names)
    return result


def _alerting_check(route: str, tested_at: str, refs: list[str]) -> dict[str, Any]:
    checks = {
        "alertmanager_route_present": _real_value(route),
        "alert_delivery_tested_at_is_iso": _is_iso_datetime(tested_at),
        "evidence_refs_present": bool(refs) and all(_real_value(ref) for ref in refs),
    }
    return _section_result("Alertmanager route, delivery test timestamp, and evidence refs are present.", checks)


def _section_result(description: str, checks: dict[str, bool]) -> dict[str, Any]:
    missing = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "pass" if not missing else "fail",
        "description": description,
        "passed": sorted(name for name, ok in checks.items() if ok),
        "missing_or_placeholder": missing,
    }


def _fail(description: str, *, error: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "description": description,
        "passed": [],
        "missing_or_placeholder": ["probe_error"],
        "error": error,
    }


def _metric_names(metrics_text: str) -> list[str]:
    names: set[str] = set()
    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0].strip()
        if name:
            names.add(name)
    return sorted(names)


def _is_production_host(host: str) -> bool:
    normalized = host.strip().lower()
    return (
        bool(normalized)
        and normalized not in PLACEHOLDER_HOSTS
        and not any(normalized.endswith(suffix) for suffix in PLACEHOLDER_SUFFIXES)
    )


def _is_iso_datetime(value: str) -> bool:
    if not isinstance(value, str) or not value.strip() or _contains_secret_like(value):
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _real_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _contains_secret_like(value: str) -> bool:
    return any(marker in value for marker in SECRET_VALUE_MARKERS)


if __name__ == "__main__":
    raise SystemExit(main())
