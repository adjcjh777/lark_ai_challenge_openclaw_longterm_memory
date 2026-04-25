from __future__ import annotations

import shutil
import uuid
from pathlib import Path


class WorkspaceTempDir:
    def __init__(self, prefix: str = "test") -> None:
        root = Path("data") / ".test_dbs"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{prefix}_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=False)
        self.name = str(self.path)

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()
