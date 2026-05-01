#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.db import db_path_from_env
from memory_engine.storage_backup import create_sqlite_backup, restore_sqlite_backup, verify_sqlite_backup


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create, verify, or restore a local/staging Copilot SQLite storage backup."
    )
    parser.add_argument("--db-path", default=str(db_path_from_env()), help="SQLite database path to back up.")
    parser.add_argument("--backup-dir", default="data/backups", help="Directory for new backups.")
    parser.add_argument("--label", default=None, help="Optional backup filename label.")
    parser.add_argument("--verify-backup", default=None, help="Verify an existing backup file instead of creating one.")
    parser.add_argument("--restore-backup", default=None, help="Backup file to restore.")
    parser.add_argument("--restore-to", default=None, help="Restore target path. Required with --restore-backup.")
    parser.add_argument(
        "--force", action="store_true", help="Allow overwriting --restore-to after writers are stopped."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    try:
        if args.verify_backup:
            result = verify_sqlite_backup(args.verify_backup)
        elif args.restore_backup:
            if not args.restore_to:
                parser.error("--restore-to is required with --restore-backup")
            result = restore_sqlite_backup(
                backup_path=args.restore_backup,
                restore_to=args.restore_to,
                force=args.force,
            )
        else:
            result = create_sqlite_backup(
                db_path=args.db_path,
                backup_dir=args.backup_dir,
                label=args.label,
            )
    except (FileNotFoundError, OSError, ValueError) as exc:
        result = {"ok": False, "error": str(exc)}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_format_report(result))
    return 0 if result.get("ok") else 1


def _format_report(result: dict[str, object]) -> str:
    lines = [
        "Copilot Storage Backup Check",
        f"ok: {str(bool(result.get('ok'))).lower()}",
    ]
    for key in ("backup_path", "manifest_path", "restore_to", "integrity_check", "storage_ready", "boundary", "error"):
        if key in result:
            lines.append(f"{key}: {result[key]}")
    if "reason" in result:
        lines.append(f"reason: {result['reason']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
