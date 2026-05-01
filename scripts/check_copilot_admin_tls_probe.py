#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = (
    "live_tls_probe_only; validates an already-running HTTPS endpoint and HSTS header; "
    "does not issue certificates, configure DNS, prove IdP, monitoring, DB, or productized live readiness"
)
PLACEHOLDER_HOSTS = {"example.com", "localhost", "127.0.0.1", "::1"}
PLACEHOLDER_SUFFIXES = (".example.com", ".localhost")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")

CertificateFetcher = Callable[[str, int, float], dict[str, Any]]
HstsFetcher = Callable[[str, float], dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a Copilot Admin production HTTPS URL for TLS and HSTS.")
    parser.add_argument("--url", required=True, help="Production HTTPS URL to probe.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Network timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_tls_probe(url=args.url, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def run_tls_probe(
    *,
    url: str,
    timeout: float = 10.0,
    certificate_fetcher: CertificateFetcher | None = None,
    hsts_fetcher: HstsFetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 443
    checks: dict[str, dict[str, Any]] = {
        "url": _url_check(parsed),
    }
    cert: dict[str, Any] = {}
    hsts: dict[str, Any] = {}
    if checks["url"]["status"] == "pass":
        try:
            cert = (certificate_fetcher or _fetch_certificate)(host, port, timeout)
            checks["certificate"] = _certificate_check(cert, host=host, now=now)
        except Exception as exc:  # pragma: no cover - network errors vary by platform.
            checks["certificate"] = _fail("TLS certificate could be fetched and parsed.", error=str(exc))
        try:
            hsts = (hsts_fetcher or _fetch_hsts)(url, timeout)
            checks["hsts"] = _hsts_check(hsts)
        except Exception as exc:  # pragma: no cover - network errors vary by platform.
            checks["hsts"] = _fail("HTTPS endpoint responds with a valid Strict-Transport-Security header.", error=str(exc))
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    cert_subject = _certificate_subject(cert)
    cert_expiry = _certificate_expiry_iso(cert)
    patch = {
        "production_domain_tls": {
            "url": url,
            "tls_validated_at": now.isoformat(),
            "certificate_subject": cert_subject,
            "certificate_expires_at": cert_expiry,
            "hsts_enabled": checks.get("hsts", {}).get("status") == "pass",
            "evidence_refs": [f"tls_probe:{host}:{now.isoformat()}"] if not failed else [],
        }
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "url": url,
        "host": host,
        "port": port,
        "checks": checks,
        "failed_checks": failed,
        "production_manifest_patch": patch,
        "next_step": ""
        if not failed
        else "Fix production HTTPS, certificate hostname/expiry, or HSTS before merging this TLS patch.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin TLS Probe",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        f"url: {report['url']}",
        "checks:",
    ]
    for name, check in sorted(report["checks"].items()):
        lines.append(f"- {name}: {check['status']} {check.get('description', '')}".rstrip())
        if check.get("error"):
            lines.append(f"  error: {check['error']}")
        if check.get("missing_or_placeholder"):
            lines.append(f"  missing: {', '.join(check['missing_or_placeholder'])}")
    return "\n".join(lines)


def _url_check(parsed: Any) -> dict[str, Any]:
    host = parsed.hostname or ""
    checks = {
        "scheme_is_https": parsed.scheme == "https",
        "host_is_present": bool(host),
        "host_is_not_placeholder": bool(host) and _is_production_host(host),
        "url_has_no_secret_like_value": not _contains_secret_like(parsed.geturl()),
    }
    return _section_result("URL is a non-placeholder production HTTPS endpoint.", checks)


def _certificate_check(cert: dict[str, Any], *, host: str, now: datetime) -> dict[str, Any]:
    checks = {
        "certificate_present": bool(cert),
        "hostname_matches_certificate": _hostname_matches(cert, host),
        "certificate_expires_in_future": _certificate_expires_in_future(cert, now=now),
        "certificate_subject_present": bool(_certificate_subject(cert)),
    }
    return _section_result("Certificate matches host, has a subject, and has not expired.", checks)


def _hsts_check(hsts: dict[str, Any]) -> dict[str, Any]:
    header = str(hsts.get("strict_transport_security") or "")
    checks = {
        "endpoint_responded": int(hsts.get("status") or 0) > 0,
        "hsts_header_present": bool(header.strip()),
        "hsts_has_max_age": "max-age=" in header.lower(),
    }
    return _section_result("HTTPS endpoint responds with a Strict-Transport-Security max-age header.", checks)


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


def _fetch_certificate(host: str, port: int, timeout: float) -> dict[str, Any]:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as raw_sock:
        with context.wrap_socket(raw_sock, server_hostname=host) as tls_sock:
            return dict(tls_sock.getpeercert())


def _fetch_hsts(url: str, timeout: float) -> dict[str, Any]:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout)
    try:
        conn.request("HEAD", path)
        response = conn.getresponse()
        if response.status == 405:
            conn.close()
            conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout)
            conn.request("GET", path, headers={"Range": "bytes=0-0"})
            response = conn.getresponse()
        return {
            "status": response.status,
            "strict_transport_security": response.getheader("Strict-Transport-Security", ""),
        }
    finally:
        conn.close()


def _hostname_matches(cert: dict[str, Any], host: str) -> bool:
    if not cert or not host:
        return False
    try:
        ssl.match_hostname(cert, host)
    except Exception:
        return False
    return True


def _certificate_expires_in_future(cert: dict[str, Any], *, now: datetime) -> bool:
    expires_at = _certificate_expiry_datetime(cert)
    return expires_at is not None and expires_at > now


def _certificate_expiry_datetime(cert: dict[str, Any]) -> datetime | None:
    not_after = cert.get("notAfter")
    if not isinstance(not_after, str) or not not_after.strip():
        return None
    try:
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=timezone.utc)
    except (OSError, ValueError):
        return None


def _certificate_expiry_iso(cert: dict[str, Any]) -> str:
    expires_at = _certificate_expiry_datetime(cert)
    return expires_at.isoformat() if expires_at else ""


def _certificate_subject(cert: dict[str, Any]) -> str:
    subject_parts: list[str] = []
    for group in cert.get("subject") or []:
        for key, value in group:
            if key and value:
                subject_parts.append(f"{key}={value}")
    if subject_parts:
        return ", ".join(subject_parts)
    san = cert.get("subjectAltName") or []
    dns_names = [value for key, value in san if key == "DNS" and value]
    return f"DNS={dns_names[0]}" if dns_names else ""


def _is_production_host(host: str) -> bool:
    normalized = host.strip().lower()
    return (
        bool(normalized)
        and normalized not in PLACEHOLDER_HOSTS
        and not any(normalized.endswith(suffix) for suffix in PLACEHOLDER_SUFFIXES)
    )


def _contains_secret_like(value: str) -> bool:
    return any(marker in value for marker in SECRET_VALUE_MARKERS)


if __name__ == "__main__":
    raise SystemExit(main())
