#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = (
    "enterprise_idp_entrypoint_probe_only; validates HTTPS Admin entrypoint guard and external IdP evidence refs; "
    "does not perform interactive IdP login, issue SSO config, prove DB, TLS, monitoring, or productized live readiness"
)
PLACEHOLDER_HOSTS = {"example.com", "localhost", "127.0.0.1", "::1"}
PLACEHOLDER_SUFFIXES = (".example.com", ".localhost")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")
AUTH_GUARD_STATUSES = {301, 302, 303, 307, 308, 401, 403}

HttpFetcher = Callable[[str, float], dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Copilot Admin enterprise IdP production evidence.")
    parser.add_argument("--base-url", required=True, help="Production Admin base URL, e.g. https://memory.company/")
    parser.add_argument("--provider", required=True, help="Enterprise IdP provider, e.g. feishu_sso or oauth2_proxy.")
    parser.add_argument("--login-tested-at", required=True, help="ISO-8601 real login test timestamp.")
    parser.add_argument("--admin-login-passed", action="store_true", help="Set when admin login was externally tested.")
    parser.add_argument("--viewer-export-denied", action="store_true", help="Set when viewer export denial was tested.")
    parser.add_argument("--allowed-domain", action="append", default=[], help="Allowed enterprise email domain.")
    parser.add_argument("--idp-evidence-ref", action="append", default=[], help="Non-secret IdP evidence ref.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Network timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_idp_probe(
        base_url=args.base_url,
        provider=args.provider,
        login_tested_at=args.login_tested_at,
        admin_login_passed=args.admin_login_passed,
        viewer_export_denied=args.viewer_export_denied,
        allowed_domains=args.allowed_domain,
        evidence_refs=args.idp_evidence_ref,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def run_idp_probe(
    *,
    base_url: str,
    provider: str,
    login_tested_at: str,
    admin_login_passed: bool,
    viewer_export_denied: bool,
    allowed_domains: list[str],
    evidence_refs: list[str],
    timeout: float = 10.0,
    http_fetcher: HttpFetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    checks: dict[str, dict[str, Any]] = {
        "admin_url": _url_check(base_url, description="Admin base URL is a non-placeholder production HTTPS endpoint."),
        "idp_evidence": _idp_evidence_check(
            provider=provider,
            login_tested_at=login_tested_at,
            admin_login_passed=admin_login_passed,
            viewer_export_denied=viewer_export_denied,
            allowed_domains=allowed_domains,
            evidence_refs=evidence_refs,
        ),
    }
    probe_url = urljoin(base_url.rstrip("/") + "/", "api/summary")
    if checks["admin_url"]["status"] == "pass":
        try:
            response = (http_fetcher or _fetch_without_credentials)(probe_url, timeout)
            checks["unauthenticated_guard"] = _unauthenticated_guard_check(response)
        except Exception as exc:  # pragma: no cover - network errors vary by platform.
            checks["unauthenticated_guard"] = _fail(
                "Unauthenticated request to Admin API is denied or redirected to IdP.",
                error=str(exc),
            )

    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    host = urlparse(base_url).hostname or ""
    patched_refs = list(evidence_refs)
    if not failed:
        patched_refs.append(f"idp_entrypoint_probe:{host}:{now.isoformat()}")
    patch = {
        "enterprise_idp_sso": {
            "provider": provider,
            "production_login_tested_at": login_tested_at,
            "admin_login_passed": bool(admin_login_passed),
            "viewer_export_denied": bool(viewer_export_denied),
            "allowed_domains": list(allowed_domains),
            "evidence_refs": patched_refs if not failed else [],
        }
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "base_url": base_url,
        "probe_url": probe_url,
        "checks": checks,
        "failed_checks": failed,
        "production_manifest_patch": patch,
        "next_step": ""
        if not failed
        else "Fix Admin unauthenticated guard or attach real IdP login/admin/viewer denial evidence refs.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin Enterprise IdP Probe",
        f"ok: {str(report['ok']).lower()}",
        f"production_ready_claim: {str(report['production_ready_claim']).lower()}",
        f"boundary: {report['boundary']}",
        f"probe_url: {report['probe_url']}",
        "checks:",
    ]
    for name, check in sorted(report["checks"].items()):
        lines.append(f"- {name}: {check['status']} {check.get('description', '')}".rstrip())
        if check.get("missing_or_placeholder"):
            lines.append(f"  missing: {', '.join(check['missing_or_placeholder'])}")
        if check.get("error"):
            lines.append(f"  error: {check['error']}")
    return "\n".join(lines)


def _fetch_without_credentials(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status": int(response.status), "headers": dict(response.headers.items()), "body": body}
    except HTTPError as exc:
        return {
            "status": int(exc.code),
            "headers": dict(exc.headers.items()),
            "body": exc.read().decode("utf-8", errors="replace"),
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


def _idp_evidence_check(
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
    return _section_result("Enterprise IdP evidence covers real login, admin role, viewer denial, domains, and refs.", checks)


def _unauthenticated_guard_check(response: dict[str, Any]) -> dict[str, Any]:
    status = int(response.get("status") or 0)
    headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
    location = str(headers.get("Location") or headers.get("location") or "")
    checks = {
        "status_is_auth_guard": status in AUTH_GUARD_STATUSES,
        "not_publicly_readable": status != 200,
        "redirect_or_denial_has_no_secret_like_value": not _contains_secret_like(location),
    }
    result = _section_result("Unauthenticated request to Admin API is denied or redirected to IdP.", checks)
    result["actual_http_status"] = status
    result["redirect_location_host"] = urlparse(location).hostname or ""
    return result


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


def _valid_evidence_refs(refs: list[str]) -> bool:
    return bool(refs) and all(_real_ref(ref) for ref in refs)


def _real_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _real_domain(value: Any) -> bool:
    return _real_value(value) and "@" not in str(value) and "://" not in str(value)


def _real_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _is_production_host(host: str) -> bool:
    normalized = host.strip().lower()
    return (
        bool(normalized)
        and normalized not in PLACEHOLDER_HOSTS
        and not any(normalized.endswith(suffix) for suffix in PLACEHOLDER_SUFFIXES)
    )


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or _contains_secret_like(value):
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _contains_secret_like(value: str) -> bool:
    markers = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1", *SECRET_VALUE_MARKERS)
    return any(marker in value for marker in markers)


if __name__ == "__main__":
    raise SystemExit(main())
