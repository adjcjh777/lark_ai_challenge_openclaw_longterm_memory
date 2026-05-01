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
    "production_db_evidence_patch_collector_only; does not create, migrate, connect to, back up, "
    "restore, or validate a production PostgreSQL database by itself"
)
ALLOWED_ENGINES = {"postgresql", "managed_postgresql"}
PLACEHOLDER_MARKERS = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_", "://")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build and validate the production_db section for Copilot Admin production evidence. "
            "This does not deploy or verify a production database."
        )
    )
    parser.add_argument(
        "--engine",
        required=True,
        choices=sorted(ALLOWED_ENGINES),
        help="Production DB engine, usually postgresql or managed_postgresql.",
    )
    parser.add_argument("--migration-applied-at", required=True, help="ISO-8601 production migration timestamp.")
    parser.add_argument("--pitr-enabled", action="store_true", help="Set when production PITR is actually enabled.")
    parser.add_argument("--backup-restore-drill-at", required=True, help="ISO-8601 restore drill timestamp.")
    parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Non-secret ops evidence reference. Pass multiple times for migration, PITR, and restore proof.",
    )
    parser.add_argument("--migration-report", default="", help="Optional JSON migration report path to summarize.")
    parser.add_argument("--restore-report", default="", help="Optional JSON backup/restore report path to summarize.")
    parser.add_argument("--output", default="", help="Optional JSON output file path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = collect_production_db_evidence(
        engine=args.engine,
        migration_applied_at=args.migration_applied_at,
        pitr_enabled=args.pitr_enabled,
        backup_restore_drill_at=args.backup_restore_drill_at,
        evidence_refs=args.evidence_ref,
        migration_report=Path(args.migration_report).expanduser() if args.migration_report else None,
        restore_report=Path(args.restore_report).expanduser() if args.restore_report else None,
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


def collect_production_db_evidence(
    *,
    engine: str,
    migration_applied_at: str,
    pitr_enabled: bool,
    backup_restore_drill_at: str,
    evidence_refs: list[str],
    migration_report: Path | None = None,
    restore_report: Path | None = None,
) -> dict[str, Any]:
    reports = {
        "migration_report": _report_summary(migration_report) if migration_report else None,
        "restore_report": _report_summary(restore_report) if restore_report else None,
    }
    checks = {
        "engine": _check(_normalized(engine) in ALLOWED_ENGINES, "Engine is PostgreSQL or managed PostgreSQL."),
        "migration_timestamp": _check(
            _is_iso_datetime(migration_applied_at), "Migration applied timestamp is valid ISO-8601."
        ),
        "pitr_enabled": _check(pitr_enabled is True, "Production PITR is explicitly enabled."),
        "backup_restore_timestamp": _check(
            _is_iso_datetime(backup_restore_drill_at), "Backup restore drill timestamp is valid ISO-8601."
        ),
        "evidence_refs": _check(
            _valid_evidence_refs(evidence_refs),
            "Evidence refs are present and do not contain placeholders, URLs, DSNs, or secret-like values.",
            evidence_ref_count=len(evidence_refs),
        ),
        "attached_reports": _check(
            _reports_are_safe(reports),
            "Attached report summaries are readable and do not contain secret-like values.",
            attached=[name for name, report in reports.items() if report],
        ),
    }
    failed = sorted(name for name, check in checks.items() if check["status"] != "pass")
    patch = {
        "production_db": {
            "engine": _normalized(engine),
            "migration_applied_at": migration_applied_at,
            "pitr_enabled": bool(pitr_enabled),
            "backup_restore_drill_at": backup_restore_drill_at,
            "evidence_refs": list(evidence_refs),
        }
    }
    return {
        "ok": not failed,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_checks": failed,
        "report_summaries": reports,
        "production_manifest_patch": patch,
        "next_step": ""
        if not failed
        else "Fill real PostgreSQL/PITR/restore evidence before merging this patch into production evidence.",
    }


def _report_summary(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists():
        return {"path": str(resolved), "status": "missing"}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"path": str(resolved), "status": "invalid_json", "error": str(exc)}
    if not isinstance(payload, dict):
        payload = {}
    summary = {
        "path": str(resolved),
        "status": "readable",
        "ok": payload.get("ok"),
        "ready": payload.get("ready") or (payload.get("after") or {}).get("ready"),
        "boundary": payload.get("boundary") or (payload.get("manifest") or {}).get("boundary"),
    }
    if "integrity_check" in payload:
        summary["integrity_check"] = payload.get("integrity_check")
    if "storage_ready" in payload:
        summary["storage_ready"] = payload.get("storage_ready")
    return summary


def _reports_are_safe(reports: dict[str, Any]) -> bool:
    for report in reports.values():
        if report is None:
            continue
        if report.get("status") != "readable":
            return False
        if _contains_secret_like(json.dumps(report, ensure_ascii=False)):
            return False
    return True


def _valid_evidence_refs(refs: list[str]) -> bool:
    return bool(refs) and all(_real_ref(ref) for ref in refs)


def _real_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _contains_secret_like(value)


def _contains_secret_like(value: str) -> bool:
    return any(marker in value for marker in (*PLACEHOLDER_MARKERS, *SECRET_VALUE_MARKERS))


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or _contains_secret_like(value):
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _check(ok: bool, description: str, **extra: Any) -> dict[str, Any]:
    return {"status": "pass" if ok else "fail", "description": description, **extra}


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Production DB Evidence Collector")
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
