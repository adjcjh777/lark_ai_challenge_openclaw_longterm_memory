#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = (
    "production_db_live_probe_only; validates an already-running PostgreSQL endpoint through a DSN env var; "
    "does not create, migrate, enable PITR, back up, restore, or prove productized live readiness"
)
ALLOWED_ENGINES = {"postgresql", "managed_postgresql"}
PLACEHOLDER_HOSTS = {"example.com", "localhost", "127.0.0.1", "::1"}
PLACEHOLDER_SUFFIXES = (".example.com", ".localhost")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_", "://")
ENV_NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")

CommandRunner = Callable[[list[str], dict[str, str], float], dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Copilot production PostgreSQL evidence without printing DSNs.")
    parser.add_argument(
        "--dsn-env",
        default="DATABASE_URL",
        help="Environment variable containing the production PostgreSQL DSN. The value is never printed.",
    )
    parser.add_argument(
        "--engine",
        default="managed_postgresql",
        choices=sorted(ALLOWED_ENGINES),
        help="Production DB engine to emit in the manifest patch.",
    )
    parser.add_argument("--migration-applied-at", required=True, help="ISO-8601 production migration timestamp.")
    parser.add_argument("--pitr-enabled", action="store_true", help="Set when production PITR is actually enabled.")
    parser.add_argument("--backup-restore-drill-at", required=True, help="ISO-8601 restore drill timestamp.")
    parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Non-secret ops evidence reference. Pass migration, PITR, restore, and probe refs.",
    )
    parser.add_argument(
        "--min-server-version-num",
        type=int,
        default=150000,
        help="Minimum accepted PostgreSQL server_version_num. Default requires PostgreSQL 15+.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Command timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_production_db_probe(
        dsn_env=args.dsn_env,
        engine=args.engine,
        migration_applied_at=args.migration_applied_at,
        pitr_enabled=args.pitr_enabled,
        backup_restore_drill_at=args.backup_restore_drill_at,
        evidence_refs=args.evidence_ref,
        min_server_version_num=args.min_server_version_num,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0 if result["ok"] else 1


def run_production_db_probe(
    *,
    dsn_env: str,
    engine: str,
    migration_applied_at: str,
    pitr_enabled: bool,
    backup_restore_drill_at: str,
    evidence_refs: list[str],
    min_server_version_num: int = 150000,
    timeout: float = 10.0,
    environ: dict[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    now = now or datetime.now(timezone.utc)
    checks: dict[str, dict[str, Any]] = {
        "dsn_env": _dsn_env_check(dsn_env),
        "engine": _section_result(
            "Engine is PostgreSQL or managed PostgreSQL.",
            {"engine_is_supported": _normalized(engine) in ALLOWED_ENGINES},
        ),
        "migration_timestamp": _section_result(
            "Migration applied timestamp is valid ISO-8601.",
            {"migration_applied_at_is_iso": _is_iso_datetime(migration_applied_at)},
        ),
        "pitr": _section_result("Production PITR is explicitly enabled.", {"pitr_enabled": pitr_enabled is True}),
        "backup_restore": _section_result(
            "Backup restore drill timestamp is valid ISO-8601.",
            {"backup_restore_drill_at_is_iso": _is_iso_datetime(backup_restore_drill_at)},
        ),
        "evidence_refs": _section_result(
            "Evidence refs are present and do not contain placeholders, URLs, DSNs, or secret-like values.",
            {"evidence_refs_present": _valid_evidence_refs(evidence_refs)},
            evidence_ref_count=len(evidence_refs),
        ),
    }
    dsn = env.get(dsn_env, "") if checks["dsn_env"]["status"] == "pass" else ""
    dsn_summary = _dsn_summary(dsn)
    checks["dsn"] = dsn_summary["check"]

    server_version_num = 0
    if checks["dsn"]["status"] == "pass":
        command_env = dict(env)
        command_env["PGDATABASE"] = dsn
        runner = command_runner or _run_command
        checks["pg_isready"] = _pg_isready_check(runner, command_env, timeout, dsn)
        if checks["pg_isready"]["status"] == "pass":
            psql_check = _psql_query_check(runner, command_env, timeout, dsn, min_server_version_num)
            checks["psql_readonly_query"] = psql_check
            server_version_num = int(psql_check.get("server_version_num") or 0)

    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    patched_refs = list(evidence_refs)
    if not failed:
        host = dsn_summary.get("host") or "postgresql"
        patched_refs.append(f"db_live_probe:{host}:{now.isoformat()}")
    patch = {
        "production_db": {
            "engine": _normalized(engine),
            "migration_applied_at": migration_applied_at,
            "pitr_enabled": bool(pitr_enabled),
            "backup_restore_drill_at": backup_restore_drill_at,
            "evidence_refs": patched_refs if not failed else [],
        }
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "dsn_env": dsn_env,
        "dsn_summary": {key: value for key, value in dsn_summary.items() if key != "check"},
        "checks": checks,
        "failed_checks": failed,
        "server_version_num": server_version_num,
        "min_server_version_num": min_server_version_num,
        "production_manifest_patch": patch,
        "next_step": ""
        if not failed
        else "Fix PostgreSQL DSN reachability, read-only query access, PITR/restore evidence, or evidence refs.",
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Production DB Live Probe",
        f"ok: {str(report['ok']).lower()}",
        f"production_ready_claim: {str(report['production_ready_claim']).lower()}",
        f"boundary: {report['boundary']}",
        f"dsn_env: {report['dsn_env']}",
        "checks:",
    ]
    for name, check in sorted(report["checks"].items()):
        lines.append(f"- {name}: {check['status']} {check.get('description', '')}".rstrip())
        if check.get("missing_or_placeholder"):
            lines.append(f"  missing: {', '.join(check['missing_or_placeholder'])}")
        if check.get("error"):
            lines.append(f"  error: {check['error']}")
    return "\n".join(lines)


def _run_command(command: list[str], env: dict[str, str], timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            env=env,
            timeout=timeout,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": 124, "stdout": exc.stdout or "", "stderr": "command timed out"}
    return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _pg_isready_check(runner: CommandRunner, env: dict[str, str], timeout: float, dsn: str) -> dict[str, Any]:
    result = runner(["pg_isready", "--timeout", str(max(1, int(timeout)))], env, timeout)
    stdout = _redact(str(result.get("stdout") or ""), dsn)
    stderr = _redact(str(result.get("stderr") or ""), dsn)
    checks = {
        "pg_isready_exit_zero": int(result.get("returncode") or 0) == 0,
        "pg_isready_no_secret_output": not _contains_secret_like(stdout + stderr),
    }
    section = _section_result("pg_isready can reach the production PostgreSQL endpoint.", checks)
    section["stdout_tail"] = stdout.strip()[-160:]
    section["stderr_tail"] = stderr.strip()[-160:]
    return section


def _psql_query_check(
    runner: CommandRunner,
    env: dict[str, str],
    timeout: float,
    dsn: str,
    min_server_version_num: int,
) -> dict[str, Any]:
    result = runner(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", "select current_setting('server_version_num')"],
        env,
        timeout,
    )
    stdout = _redact(str(result.get("stdout") or ""), dsn).strip()
    stderr = _redact(str(result.get("stderr") or ""), dsn)
    version = _parse_server_version_num(stdout)
    checks = {
        "psql_exit_zero": int(result.get("returncode") or 0) == 0,
        "server_version_present": version > 0,
        "server_version_at_least_minimum": version >= int(min_server_version_num),
        "psql_no_secret_output": not _contains_secret_like(stdout + stderr),
    }
    section = _section_result(
        "psql authenticated read-only query returns PostgreSQL server_version_num.",
        checks,
    )
    section["server_version_num"] = version
    section["stderr_tail"] = stderr.strip()[-160:]
    return section


def _dsn_env_check(value: str) -> dict[str, Any]:
    return _section_result(
        "DSN env var name is explicit and shell-safe.",
        {
            "dsn_env_name_present": bool(value),
            "dsn_env_name_safe": bool(ENV_NAME_PATTERN.match(value or "")),
        },
    )


def _dsn_summary(dsn: str) -> dict[str, Any]:
    parsed = urlparse(dsn or "")
    host = parsed.hostname or ""
    scheme = parsed.scheme
    checks = {
        "dsn_is_present": bool(dsn),
        "scheme_is_postgresql": scheme in {"postgresql", "postgres"},
        "host_is_present": bool(host),
        "host_is_not_placeholder": bool(host) and _is_production_host(host),
    }
    return {
        "scheme": scheme,
        "host": host,
        "port": parsed.port,
        "database_present": bool((parsed.path or "").strip("/")),
        "username_present": bool(parsed.username),
        "check": _section_result(
            "Production PostgreSQL DSN is present in env and points at a non-placeholder host.",
            checks,
        ),
    }


def _section_result(description: str, checks: dict[str, bool], **extra: Any) -> dict[str, Any]:
    missing = sorted(name for name, ok in checks.items() if not ok)
    return {
        "status": "pass" if not missing else "fail",
        "description": description,
        "passed": sorted(name for name, ok in checks.items() if ok),
        "missing_or_placeholder": missing,
        **extra,
    }


def _valid_evidence_refs(refs: list[str]) -> bool:
    return bool(refs) and all(_real_ref(ref) for ref in refs)


def _real_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _contains_secret_like(value: str) -> bool:
    markers = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1", *SECRET_VALUE_MARKERS)
    return any(marker in value for marker in markers)


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


def _parse_server_version_num(value: str) -> int:
    first_line = value.splitlines()[0].strip() if value.splitlines() else value.strip()
    return int(first_line) if first_line.isdigit() else 0


def _redact(value: str, secret: str) -> str:
    if secret:
        value = value.replace(secret, "<redacted-dsn>")
    return value


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


if __name__ == "__main__":
    raise SystemExit(main())
