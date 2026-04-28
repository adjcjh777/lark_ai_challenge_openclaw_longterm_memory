#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.healthcheck import format_healthcheck_text, run_copilot_healthcheck


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase 6 deployability and healthcheck diagnostics without production deployment or real Feishu push."
    )
    parser.add_argument("--json", action="store_true", help="Print the full healthcheck report as JSON.")
    args = parser.parse_args()

    report = run_copilot_healthcheck()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_healthcheck_text(report))
        print("")
        print("JSON: python3 scripts/check_copilot_health.py --json")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
