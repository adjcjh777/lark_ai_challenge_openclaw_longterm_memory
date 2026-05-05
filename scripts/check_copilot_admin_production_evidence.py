#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evidence_patch_merge import (  # noqa: E402
    contains_any,
    count_number,
    flatten_strings,
    has_evidence_refs,
    is_future_datetime,
    is_iso_datetime,
    real_value,
)

DEFAULT_MANIFEST_PATH = ROOT / "deploy" / "copilot-admin.production-evidence.example.json"
SCHEMA_VERSION = "copilot_admin_production_evidence/v1"
BOUNDARY = (
    "production_evidence_manifest_gate_only; does not create production DB, IdP, TLS, monitoring, "
    "or long-running live evidence"
)
REQUIRED_SECTIONS = (
    "production_db",
    "enterprise_idp_sso",
    "production_domain_tls",
    "production_monitoring",
    "productized_live_long_run",
)
PLACEHOLDER_MARKERS = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1")
SECRET_VALUE_MARKERS = (
    "app_secret=",
    "access_token=",
    "refresh_token=",
    "Bearer ",
    "sk-",
    "rightcode_",
)
_has_evidence_refs = partial(has_evidence_refs, placeholder_markers=PLACEHOLDER_MARKERS)
_real_value = partial(real_value, placeholder_markers=PLACEHOLDER_MARKERS)
_is_iso_datetime = partial(is_iso_datetime, placeholder_markers=PLACEHOLDER_MARKERS)
_is_future_datetime = partial(is_future_datetime, placeholder_markers=PLACEHOLDER_MARKERS)
_number = count_number


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Copilot Admin production evidence without claiming production readiness."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Production evidence manifest JSON. Defaults to the committed example template.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-production-ready",
        action="store_true",
        help="Return a failing exit code unless all production evidence checks pass on a non-example manifest.",
    )
    args = parser.parse_args()

    result = run_production_evidence_check(Path(args.manifest).expanduser())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    if not result["ok"]:
        return 1
    if args.require_production_ready and not result["production_ready"]:
        return 1
    return 0


def run_production_evidence_check(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        return {
            "ok": False,
            "production_ready": False,
            "manifest_path": str(manifest_path),
            "boundary": BOUNDARY,
            "checks": {
                "manifest_file": {
                    "status": "fail",
                    "description": "Production evidence manifest file exists.",
                    "missing": str(manifest_path),
                }
            },
            "failed_checks": ["manifest_file"],
            "warning_checks": [],
            "production_blockers": _blockers_for(["manifest_file"]),
            "next_step": "Create a production evidence manifest from deploy/copilot-admin.production-evidence.example.json.",
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "production_ready": False,
            "manifest_path": str(manifest_path),
            "boundary": BOUNDARY,
            "checks": {
                "manifest_json": {
                    "status": "fail",
                    "description": "Production evidence manifest is valid JSON.",
                    "error": str(exc),
                }
            },
            "failed_checks": ["manifest_json"],
            "warning_checks": [],
            "production_blockers": _blockers_for(["manifest_json"]),
            "next_step": "Fix manifest JSON syntax before running the production evidence gate.",
        }
    if not isinstance(manifest, dict):
        manifest = {}

    is_example = bool(manifest.get("example"))
    checks = {
        "manifest_shape": _check_manifest_shape(manifest),
        "secret_redaction": _check_secret_redaction(manifest),
        "production_db": _check_production_db(manifest.get("production_db"), is_example=is_example),
        "enterprise_idp_sso": _check_enterprise_idp_sso(manifest.get("enterprise_idp_sso"), is_example=is_example),
        "production_domain_tls": _check_production_domain_tls(
            manifest.get("production_domain_tls"), is_example=is_example
        ),
        "production_monitoring": _check_production_monitoring(
            manifest.get("production_monitoring"), is_example=is_example
        ),
        "productized_live_long_run": _check_productized_live_long_run(
            manifest.get("productized_live_long_run"), is_example=is_example
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] == "fail")
    warnings = sorted(name for name, check in checks.items() if check["status"] == "warning")
    production_ready = not is_example and not failed and not warnings
    return {
        "ok": not failed,
        "production_ready": production_ready,
        "example_manifest": is_example,
        "manifest_path": str(manifest_path),
        "boundary": BOUNDARY,
        "checks": checks,
        "failed_checks": failed,
        "warning_checks": warnings,
        "production_blockers": [] if production_ready else _blockers_for(failed + warnings),
        "next_step": ""
        if production_ready
        else "Replace placeholders with real production DB, SSO, TLS, monitoring, and long-run evidence.",
    }


def _check_manifest_shape(manifest: dict[str, Any]) -> dict[str, Any]:
    missing_sections = [section for section in REQUIRED_SECTIONS if not isinstance(manifest.get(section), dict)]
    ok = manifest.get("schema_version") == SCHEMA_VERSION and not missing_sections
    return {
        "status": "pass" if ok else "fail",
        "description": "Manifest uses the expected schema and contains every production evidence section.",
        "schema_version": manifest.get("schema_version"),
        "missing_sections": missing_sections,
    }


def _check_secret_redaction(manifest: dict[str, Any]) -> dict[str, Any]:
    leaked = sorted({value for value in flatten_strings(manifest) if contains_any(value, SECRET_VALUE_MARKERS)})
    return {
        "status": "pass" if not leaked else "fail",
        "description": "Manifest does not contain token or secret-like values.",
        "leaked_value_count": len(leaked),
    }


def _check_production_db(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "engine_is_postgresql_or_managed": _normalized(data.get("engine")) in {"postgresql", "managed_postgresql"},
        "migration_applied_at_is_iso": _is_iso_datetime(data.get("migration_applied_at")),
        "pitr_enabled": data.get("pitr_enabled") is True,
        "backup_restore_drill_at_is_iso": _is_iso_datetime(data.get("backup_restore_drill_at")),
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Production database evidence covers PostgreSQL/managed DB, migration, PITR, and restore drill.",
    )


def _check_enterprise_idp_sso(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    domains = data.get("allowed_domains") if isinstance(data.get("allowed_domains"), list) else []
    checks = {
        "provider_present": _real_value(data.get("provider")),
        "production_login_tested_at_is_iso": _is_iso_datetime(data.get("production_login_tested_at")),
        "admin_login_passed": data.get("admin_login_passed") is True,
        "viewer_export_denied": data.get("viewer_export_denied") is True,
        "allowed_domains_present": bool(domains) and all(_real_value(item) for item in domains),
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Enterprise IdP evidence covers real login, admin role, viewer denial, and allowed domains.",
    )


def _check_production_domain_tls(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "url_is_https_production_domain": _is_production_https_url(data.get("url")),
        "tls_validated_at_is_iso": _is_iso_datetime(data.get("tls_validated_at")),
        "certificate_subject_present": _real_value(data.get("certificate_subject")),
        "certificate_expires_in_future": _is_future_datetime(data.get("certificate_expires_at")),
        "hsts_enabled": data.get("hsts_enabled") is True,
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Domain/TLS evidence covers HTTPS production URL, certificate validity, HSTS, and proof refs.",
    )


def _check_production_monitoring(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "prometheus_scrape_proven": data.get("prometheus_scrape_proven") is True,
        "grafana_dashboard_url_present": _real_value(data.get("grafana_dashboard_url")),
        "alertmanager_route_present": _real_value(data.get("alertmanager_route")),
        "alert_delivery_tested_at_is_iso": _is_iso_datetime(data.get("alert_delivery_tested_at")),
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Monitoring evidence covers production scrape, dashboard, alert route, and alert delivery.",
    )


def _check_productized_live_long_run(section: Any, *, is_example: bool) -> dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    checks = {
        "service_unit_present": _real_value(data.get("service_unit")),
        "started_at_is_iso": _is_iso_datetime(data.get("started_at")),
        "evidence_window_hours_at_least_24": _number(data.get("evidence_window_hours")) >= 24,
        "healthcheck_sample_count_at_least_3": _number(data.get("healthcheck_sample_count")) >= 3,
        "oncall_owner_present": _real_value(data.get("oncall_owner")),
        "rollback_drill_at_is_iso": _is_iso_datetime(data.get("rollback_drill_at")),
        "evidence_refs_present": _has_evidence_refs(data),
    }
    return _section_result(
        checks,
        is_example=is_example,
        description="Long-run evidence covers service identity, 24h window, health samples, on-call, and rollback.",
    )


def _section_result(checks: dict[str, bool], *, is_example: bool, description: str) -> dict[str, Any]:
    missing = sorted(name for name, ok in checks.items() if not ok)
    if not missing:
        status = "pass"
    elif is_example:
        status = "warning"
    else:
        status = "fail"
    return {
        "status": status,
        "description": description,
        "passed": sorted(name for name, ok in checks.items() if ok),
        "missing_or_placeholder": missing,
    }


def _is_production_https_url(value: Any) -> bool:
    return _real_value(value) and str(value).startswith("https://")


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _blockers_for(check_names: list[str]) -> list[dict[str, str]]:
    blocker_map = {
        "manifest_file": "Production evidence manifest file is missing.",
        "manifest_json": "Production evidence manifest JSON is invalid.",
        "manifest_shape": "Production evidence manifest schema or sections are incomplete.",
        "secret_redaction": "Production evidence manifest contains secret-like values.",
        "production_db": "Production DB / PostgreSQL / PITR evidence is incomplete.",
        "enterprise_idp_sso": "Real enterprise IdP / Feishu SSO production evidence is incomplete.",
        "production_domain_tls": "Production domain, TLS, certificate, or HSTS evidence is incomplete.",
        "production_monitoring": "Production monitoring and alert delivery evidence is incomplete.",
        "productized_live_long_run": "Productized live long-running operations evidence is incomplete.",
    }
    return [
        {"id": name, "description": blocker_map.get(name, "Production evidence is incomplete.")} for name in check_names
    ]


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Admin Production Evidence Check")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"production_ready: {str(result['production_ready']).lower()}")
    print(f"manifest: {result['manifest_path']}")
    print(f"boundary: {result['boundary']}")
    for name, check in result["checks"].items():
        print(f"- {name}: {check['status']} ({check['description']})")
    if result["production_blockers"]:
        print("production_blockers:")
        for blocker in result["production_blockers"]:
            print(f"- {blocker['id']}: {blocker['description']}")


if __name__ == "__main__":
    raise SystemExit(main())
