from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_local_env_files(*, root: Path = ROOT, override: bool = True) -> dict[str, str]:
    """Load repo-local env files, with .env.local taking precedence."""

    if os.environ.get("COPILOT_SKIP_LOCAL_ENV", "").lower() in {"1", "true", "yes"}:
        return {}

    loaded: dict[str, str] = {}
    for path in (root / ".env", root / ".env.local"):
        if not path.exists():
            continue
        for key, value in read_key_value_file(path).items():
            if override or key not in os.environ:
                os.environ[key] = value
            loaded[key] = value
    return loaded


def read_key_value_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_overrides_for_embedding_config() -> dict[str, str]:
    mapping = {
        "EMBEDDING_PROVIDER": "provider",
        "EMBEDDING_MODEL": "litellm_model",
        "EMBEDDING_ENDPOINT": "endpoint",
        "EMBEDDING_DIMENSIONS": "dimensions",
    }
    overrides: dict[str, str] = {}
    for env_key, config_key in mapping.items():
        value = os.environ.get(env_key)
        if value:
            overrides[config_key] = value
    return overrides
