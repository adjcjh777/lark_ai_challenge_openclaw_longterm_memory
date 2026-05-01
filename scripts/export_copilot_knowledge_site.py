#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.knowledge_site import export_knowledge_site
from memory_engine.db import db_path_from_env


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a static read-only LLM Wiki + knowledge graph site from the Copilot SQLite ledger."
    )
    parser.add_argument("--db-path", default=str(db_path_from_env()), help="SQLite database path.")
    parser.add_argument(
        "--output-dir",
        default="reports/copilot-knowledge-site",
        help="Output directory. The generated entrypoint is always index.html.",
    )
    parser.add_argument("--scope", default=None, help="Optional single scope to export.")
    parser.add_argument("--limit", type=int, default=120, help="Maximum Wiki cards and graph nodes to include.")
    parser.add_argument("--json", action="store_true", help="Print JSON result.")
    args = parser.parse_args()

    result = export_knowledge_site(
        db_path=args.db_path,
        output_dir=args.output_dir,
        scope=args.scope,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Static knowledge site exported: {result['entrypoint']}")
        print(f"Boundary: {result['manifest']['boundary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
