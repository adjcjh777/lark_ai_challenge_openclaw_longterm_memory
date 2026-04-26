"""Verify that the local OpenClaw CLI matches the project lock file."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / "agent_adapters" / "openclaw" / "openclaw-version.lock"


def read_locked_version() -> str:
    try:
        return LOCK_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print(f"OpenClaw lock file not found: {LOCK_FILE}", file=sys.stderr)
        sys.exit(2)


def read_local_version() -> str:
    try:
        completed = subprocess.run(
            ["openclaw", "--version"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print("openclaw CLI not found on PATH", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or exc.stdout.strip(), file=sys.stderr)
        sys.exit(exc.returncode or 2)

    match = re.search(r"OpenClaw\s+([0-9]{4}\.[0-9]+\.[0-9]+)", completed.stdout)
    if not match:
        print(f"Could not parse OpenClaw version from: {completed.stdout.strip()}", file=sys.stderr)
        sys.exit(2)
    return match.group(1)


def main() -> int:
    locked = read_locked_version()
    local = read_local_version()
    if local != locked:
        print(
            f"OpenClaw version mismatch: local={local}, locked={locked}. "
            f"Reinstall with: npm i -g openclaw@{locked} --no-fund --no-audit",
            file=sys.stderr,
        )
        return 1

    print(f"OpenClaw version OK: {local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
