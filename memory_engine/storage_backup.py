from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage_migration import inspect_copilot_storage

BACKUP_BOUNDARY = (
    "SQLite staging backup/restore drill only; not a production PostgreSQL deployment, PITR, or productized live proof."
)


@dataclass(frozen=True)
class BackupResult:
    ok: bool
    backup_path: str
    manifest_path: str
    source_path: str
    integrity_check: str
    storage_ready: bool
    boundary: str = BACKUP_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "backup_path": self.backup_path,
            "manifest_path": self.manifest_path,
            "source_path": self.source_path,
            "integrity_check": self.integrity_check,
            "storage_ready": self.storage_ready,
            "boundary": self.boundary,
        }


def create_sqlite_backup(
    *,
    db_path: str | Path,
    backup_dir: str | Path,
    label: str | None = None,
) -> dict[str, Any]:
    source = Path(db_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"database not found: {source}")
    target_dir = Path(backup_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = _safe_label(label or source.stem)
    backup_path = target_dir / f"{safe_label}.{timestamp}.sqlite"
    manifest_path = backup_path.with_suffix(".manifest.json")

    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
        with sqlite3.connect(backup_path) as dst:
            src.backup(dst)

    verification = verify_sqlite_backup(backup_path)
    manifest = {
        "ok": bool(verification["ok"]),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "source_path": str(source),
        "backup_path": str(backup_path),
        "integrity_check": verification["integrity_check"],
        "storage_ready": verification["storage"]["ready"],
        "storage_schema_version": verification["storage"]["current_schema_version"],
        "boundary": BACKUP_BOUNDARY,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = BackupResult(
        ok=bool(verification["ok"]),
        backup_path=str(backup_path),
        manifest_path=str(manifest_path),
        source_path=str(source),
        integrity_check=str(verification["integrity_check"]),
        storage_ready=bool(verification["storage"]["ready"]),
    )
    payload = result.to_dict()
    payload["manifest"] = manifest
    return payload


def verify_sqlite_backup(backup_path: str | Path) -> dict[str, Any]:
    path = Path(backup_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"backup not found: {path}")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        integrity_check = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        storage = inspect_copilot_storage(conn)
    return {
        "ok": integrity_check == "ok" and bool(storage["ready"]),
        "backup_path": str(path),
        "integrity_check": integrity_check,
        "storage": storage,
        "boundary": BACKUP_BOUNDARY,
    }


def restore_sqlite_backup(
    *,
    backup_path: str | Path,
    restore_to: str | Path,
    force: bool = False,
) -> dict[str, Any]:
    source = Path(backup_path).expanduser().resolve()
    target = Path(restore_to).expanduser().resolve()
    verification = verify_sqlite_backup(source)
    if not verification["ok"]:
        return {
            "ok": False,
            "restored": False,
            "backup_path": str(source),
            "restore_to": str(target),
            "verification": verification,
            "boundary": BACKUP_BOUNDARY,
        }
    if target.exists() and not force:
        return {
            "ok": False,
            "restored": False,
            "backup_path": str(source),
            "restore_to": str(target),
            "reason": "restore target exists; pass --force to overwrite after stopping writers",
            "verification": verification,
            "boundary": BACKUP_BOUNDARY,
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    restored_verification = verify_sqlite_backup(target)
    return {
        "ok": bool(restored_verification["ok"]),
        "restored": bool(restored_verification["ok"]),
        "backup_path": str(source),
        "restore_to": str(target),
        "verification": restored_verification,
        "boundary": BACKUP_BOUNDARY,
    }


def _safe_label(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value.strip())
    return safe.strip("._") or "memory"
