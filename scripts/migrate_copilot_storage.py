#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.db import connect
from memory_engine.storage_migration import apply_copilot_storage_migration, inspect_copilot_storage


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect or apply the local SQLite Copilot storage migration. This does not deploy production storage."
    )
    parser.add_argument("--db", help="SQLite database path. Defaults to MEMORY_DB_PATH or data/memory.sqlite.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect pending migration work without changing the database.")
    parser.add_argument("--apply", action="store_true", help="Apply idempotent local SQLite migration.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    if args.dry_run == args.apply:
        parser.error("Choose exactly one of --dry-run or --apply.")

    conn = connect(args.db)
    try:
        report = apply_copilot_storage_migration(conn) if args.apply else inspect_copilot_storage(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.apply:
        after = report["after"]
        print(f"applied: {str(report['applied']).lower()}")
        print(f"ready: {str(after['ready']).lower()}")
        print(f"schema_version: {after['current_schema_version']}/{after['target_schema_version']}")
        print(f"missing_indexes: {', '.join(after['missing_indexes']) or 'none'}")
        print(f"rollback: {report['rollback']['reason']}")
        return
    print(f"ready: {str(report['ready']).lower()}")
    print(f"schema_version: {report['current_schema_version']}/{report['target_schema_version']}")
    print(f"missing_tables: {', '.join(report['missing_tables']) or 'none'}")
    print(f"pending_column_additions: {json.dumps(report['pending_column_additions'], ensure_ascii=False, sort_keys=True)}")
    print(f"missing_indexes: {', '.join(report['missing_indexes']) or 'none'}")
    print(f"rollback: {report['rollback']['reason']}")


if __name__ == "__main__":
    main()
