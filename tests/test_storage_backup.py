from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_engine.db import init_db
from memory_engine.repository import MemoryRepository
from memory_engine.storage_backup import create_sqlite_backup, restore_sqlite_backup, verify_sqlite_backup


class StorageBackupTest(unittest.TestCase):
    def test_create_verify_and_restore_sqlite_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="copilot_backup_") as tmp:
            root = Path(tmp)
            db_path = root / "memory.sqlite"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:backup_demo",
                "备份演练必须保留 audit 和 tenant/org schema。",
                source_type="unit_test",
            )
            conn.close()

            result = create_sqlite_backup(db_path=db_path, backup_dir=root / "backups", label="staging")

            self.assertTrue(result["ok"], result)
            backup_path = Path(result["backup_path"])
            manifest_path = Path(result["manifest_path"])
            self.assertTrue(backup_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(result["storage_ready"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("not a production PostgreSQL deployment", manifest["boundary"])

            verification = verify_sqlite_backup(backup_path)
            self.assertTrue(verification["ok"], verification)
            self.assertEqual("ok", verification["integrity_check"])

            restore_path = root / "restored.sqlite"
            restored = restore_sqlite_backup(backup_path=backup_path, restore_to=restore_path)
            self.assertTrue(restored["ok"], restored)
            self.assertTrue(restore_path.exists())

            restored_conn = sqlite3.connect(restore_path)
            try:
                count = restored_conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE scope_id = 'backup_demo'"
                ).fetchone()[0]
            finally:
                restored_conn.close()
            self.assertEqual(1, count)

    def test_restore_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="copilot_backup_") as tmp:
            root = Path(tmp)
            db_path = root / "memory.sqlite"
            conn = sqlite3.connect(db_path)
            init_db(conn)
            conn.close()
            result = create_sqlite_backup(db_path=db_path, backup_dir=root / "backups")
            target = root / "target.sqlite"
            target.write_text("existing", encoding="utf-8")

            restored = restore_sqlite_backup(backup_path=result["backup_path"], restore_to=target)

            self.assertFalse(restored["ok"])
            self.assertFalse(restored["restored"])
            self.assertIn("target exists", restored["reason"])
            self.assertEqual("existing", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
