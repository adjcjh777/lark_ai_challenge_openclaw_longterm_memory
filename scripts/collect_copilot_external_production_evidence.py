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

BOUNDARY = (
    "external_production_evidence_patch_collector_only; does not perform real IdP login, TLS issuance, "
    "Prometheus scrape, Grafana setup, Alertmanager delivery, or production readiness validation by itself"
)
PLACEHOLDER_MARKERS = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build enterprise IdP, production TLS, and monitoring sections for Copilot Admin production evidence. "
            "This normalizes external proof refs but does not perform production validation."
        )
    )
    parser.add_argument("--idp-provider", required=True, help="Real enterprise IdP provider, e.g. feishu_sso.")
    parser.add_argument("--idp-login-tested-at", required=True, help="ISO-8601 real login test timestamp.")
    parser.add_argument("--idp-admin-login-passed", action="store_true", help="Set when admin login was tested.")
    parser.add_argument("--idp-viewer-export-denied", action="store_true", help="Set when viewer export denial was tested.")
    parser.add_argument("--idp-allowed-domain", action="append", default=[], help="Allowed enterprise domain.")
    parser.add_argument("--idp-evidence-ref", action="append", default=[], help="Non-secret IdP evidence ref.")
    parser.add_argument("--tls-url", required=True, help="Production HTTPS URL.")
    parser.add_argument("--tls-validated-at", required=True, help="ISO-8601 TLS validation timestamp.")
    parser.add_argument("--tls-certificate-subject", required=True, help="Certificate subject.")
    parser.add_argument("--tls-certificate-expires-at", required=True, help="ISO-8601 certificate expiry timestamp.")
    parser.add_argument("--tls-hsts-enabled", action="store_true", help="Set when HSTS is enabled.")
    parser.add_argument("--tls-evidence-ref", action="append", default=[], help="Non-secret TLS evidence ref.")
    parser.add_argument("--prometheus-scrape-proven", action="store_true", help="Set when production scrape works.")
    parser.add_argument("--grafana-dashboard-url", required=True, help="Production Grafana dashboard URL.")
    parser.add_argument("--alertmanager-route", required=True, help="Production Alertmanager route name.")
    parser.add_argument("--alert-delivery-tested-at", required=True, help="ISO-8601 alert delivery test timestamp.")
    parser.add_argument("--monitoring-evidence-ref", action="append", default=[], help="Non-secret monitoring evidence ref.")
    parser.add_argument("--output", default="", help="Optional JSON output file path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = collect_external_production_evidence(
        idp_provider=args.idp_provider,
        idp_login_tested_at=args.idp_login_tested_at,
        idp_admin_login_passed=args.idp_admin_login_passed,
        idp_viewer_export_denied=args.idp_viewer_export_denied,
        idp_allowed_domains=args.idp_allowed_domain,
        idp_evidence_refs=args.idp_evidence_ref,
        tls_url=args.tls_url,
        tls_validated_at=args.tls_validated_at,
        tls_certificate_subject=args.tls_certificate_subject,
        tls_certificate_expires_at=args.tls_certificate_expires_at,
        tls_hsts_enabled=args.tls_hsts_enabled,
        tls_evidence_refs=args.tls_evidence_ref,
        prometheus_scrape_proven=args.prometheus_scrape_proven,
        grafana_dashboard_url=args.grafana_dashboard_url,
        alertmanager_route=args.alertmanager_route,
        alert_delivery_tested_at=args.alert_delivery_tested_at,
        monitoring_evidence_refs=args.monitoring_evidence_ref,
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


def collect_external_production_evidence(
    *,
    idp_provider: str,
    idp_login_tested_at: str,
    idp_admin_login_passed: bool,
    idp_viewer_export_denied: bool,
    idp_allowed_domains: list[str],
    idp_evidence_refs: list[str],
    tls_url: str,
    tls_validated_at: str,
    tls_certificate_subject: str,
    tls_certificate_expires_at: str,
    tls_hsts_enabled: bool,
    tls_evidence_refs: list[str],
    prometheus_scrape_proven: bool,
    grafana_dashboard_url: str,
    alertmanager_route: str,
    alert_delivery_tested_at: str,
    monitoring_evidence_refs: list[str],
) -> dict[str, Any]:
    checks = {
        "enterprise_idp_sso": _idp_check(
            provider=idp_provider,
            login_tested_at=idp_login_tested_at,
            admin_login_passed=idp_admin_login_passed,
            viewer_export_denied=idp_viewer_export_denied,
            allowed_domains=idp_allowed_domains,
            evidence_refs=idp_evidence_refs,
        ),
        "production_domain_tls": _tls_check(
            url=tls_url,
            validated_at=tls_validated_at,
            certificate_subject=tls_certificate_subject,
            certificate_expires_at=tls_certificate_expires_at,
            hsts_enabled=tls_hsts_enabled,
            evidence_refs=tls_evidence_refs,
        ),
        "production_monitoring": _monitoring_check(
            prometheus_scrape_proven=prometheus_scrape_proven,
            grafana_dashboard_url=grafana_dashboard_url,
            alertmanager_route=alertmanager_route,
            alert_delivery_tested_at=alert_delivery_tested_at,
            evidence_refs=monitoring_evidence_refs,
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    patch = {
        "enterprise_idp_sso": {
            "provider": idp_provider,
            "production_login_tested_at": idp_login_tested_at,
            "admin_login_passed": bool(idp_admin_login_passed),
            "viewer_export_denied": bool(idp_viewer_export_denied),
            "allowed_domains": list(idp_allowed_domains),
            "evidence_refs": list(idp_evidence_refs),
        },
        "production_domain_tls": {
            "url": tls_url,
            "tls_validated_at": tls_validated_at,
            "certificate_subject": tls_certificate_subject,
            "certificate_expires_at": tls_certificate_expires_at,
            "hsts_enabled": bool(tls_hsts_enabled),
            "evidence_refs": list(tls_evidence_refs),
        },
        "production_monitoring": {
            "prometheus_scrape_proven": bool(prometheus_scrape_proven),
            "grafana_dashboard_url": grafana_dashboard_url,
            "alertmanager_route": alertmanager_route,
            "alert_delivery_tested_at": alert_delivery_tested_at,
            "evidence_refs": list(monitoring_evidence_refs),
        },
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_checks": failed,
        "production_manifest_patch": patch,
        "next_step": ""
        if not failed
        else "Fill real IdP, TLS, and monitoring evidence before merging this patch into production evidence.",
    }


def _idp_check(
    *,
    provider: str,
    login_tested_at: str,
    admin_login_passed: bool,
    viewer_export_denied: bool,
    allowed_domains: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    checks = {
        "provider_present": _real_value(provider),
        "login_tested_at_is_iso": _is_iso_datetime(login_tested_at),
        "admin_login_passed": admin_login_passed is True,
        "viewer_export_denied": viewer_export_denied is True,
        "allowed_domains_present": bool(allowed_domains) and all(_real_domain(domain) for domain in allowed_domains),
        "evidence_refs_present": _valid_evidence_refs(evidence_refs),
    }
    return _section_result("Enterprise IdP evidence covers login, admin role, viewer denial, domains, and refs.", checks)


def _tls_check(
    *,
    url: str,
    validated_at: str,
    certificate_subject: str,
    certificate_expires_at: str,
    hsts_enabled: bool,
    evidence_refs: list[str],
) -> dict[str, Any]:
    checks = {
        "url_is_https_production_domain": _is_production_https_url(url),
        "tls_validated_at_is_iso": _is_iso_datetime(validated_at),
        "certificate_subject_present": _real_value(certificate_subject),
        "certificate_expires_in_future": _is_future_datetime(certificate_expires_at),
        "hsts_enabled": hsts_enabled is True,
        "evidence_refs_present": _valid_evidence_refs(evidence_refs),
    }
    return _section_result("Domain/TLS evidence covers HTTPS URL, cert validity, HSTS, and refs.", checks)


def _monitoring_check(
    *,
    prometheus_scrape_proven: bool,
    grafana_dashboard_url: str,
    alertmanager_route: str,
    alert_delivery_tested_at: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    checks = {
        "prometheus_scrape_proven": prometheus_scrape_proven is True,
        "grafana_dashboard_url_present": _is_production_https_url(grafana_dashboard_url),
        "alertmanager_route_present": _real_value(alertmanager_route),
        "alert_delivery_tested_at_is_iso": _is_iso_datetime(alert_delivery_tested_at),
        "evidence_refs_present": _valid_evidence_refs(evidence_refs),
    }
    return _section_result("Monitoring evidence covers scrape, dashboard, route, alert delivery, and refs.", checks)


def _section_result(description: str, checks: dict[str, bool]) -> dict[str, Any]:
    missing = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "pass" if not missing else "fail",
        "description": description,
        "passed": sorted(name for name, ok in checks.items() if ok),
        "missing_or_placeholder": missing,
    }


def _valid_evidence_refs(refs: list[str]) -> bool:
    return bool(refs) and all(_real_ref(ref) for ref in refs)


def _real_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _real_domain(value: Any) -> bool:
    return _real_value(value) and "@" not in str(value) and "://" not in str(value)


def _real_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _is_production_https_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://") and not _contains_secret_like(value)


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or _contains_placeholder(value):
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_future_datetime(value: Any) -> bool:
    if not _is_iso_datetime(value):
        return False
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > datetime.now(timezone.utc)


def _contains_placeholder(value: str) -> bool:
    return any(marker in value for marker in PLACEHOLDER_MARKERS)


def _contains_secret_like(value: str) -> bool:
    return _contains_placeholder(value) or any(marker in value for marker in SECRET_VALUE_MARKERS)


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot External Production Evidence Collector")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"production_ready_claim: {str(result['production_ready_claim']).lower()}")
    print(f"boundary: {result['boundary']}")
    for name, check in result["checks"].items():
        print(f"- {name}: {check['status']} ({check['description']})")
    if result["failed_checks"]:
        print("failed_checks:")
        for name in result["failed_checks"]:
            print(f"- {name}")


if __name__ == "__main__":
    raise SystemExit(main())
