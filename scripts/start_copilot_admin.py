#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import DEFAULT_ADMIN_HOST, DEFAULT_ADMIN_PORT, create_admin_server
from memory_engine.db import connect, db_path_from_env, init_db


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the local read-only Feishu Memory Copilot admin backend."
    )
    parser.add_argument("--host", default=DEFAULT_ADMIN_HOST, help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=DEFAULT_ADMIN_PORT, help="Bind port. Defaults to 8765.")
    parser.add_argument("--db-path", default=str(db_path_from_env()), help="SQLite database path.")
    parser.add_argument(
        "--init-db-if-missing",
        action="store_true",
        help="Initialize the SQLite schema if the database file does not exist.",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser()
    if not db_path.exists():
        if args.init_db_if_missing:
            conn = connect(db_path)
            try:
                init_db(conn)
            finally:
                conn.close()
        else:
            print(
                f"Database not found: {db_path}. Run `python3 -m memory_engine init-db` or pass --db-path.",
                file=sys.stderr,
            )
            return 1
    if not db_path.exists():
        print(
            f"Database not found: {db_path}. Run `python3 -m memory_engine init-db` or pass --db-path.",
            file=sys.stderr,
        )
        return 1

    server = create_admin_server(args.host, args.port, db_path)
    url = f"http://{args.host}:{server.server_port}"
    print(f"Feishu Memory Copilot read-only admin: {url}", flush=True)
    print(f"SQLite database: {db_path}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping admin server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
