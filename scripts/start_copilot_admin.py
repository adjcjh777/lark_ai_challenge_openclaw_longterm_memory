#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import (
    ADMIN_TOKEN_ENV_NAMES,
    ADMIN_VIEWER_TOKEN_ENV_NAMES,
    DEFAULT_ADMIN_HOST,
    DEFAULT_ADMIN_PORT,
    admin_sso_config_from_env,
    create_admin_server,
)
from memory_engine.db import connect, db_path_from_env, init_db


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the local Feishu Memory Copilot admin backend with read-only knowledge views and admin-only tenant policy writes."
    )
    parser.add_argument("--host", default=DEFAULT_ADMIN_HOST, help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=DEFAULT_ADMIN_PORT, help="Bind port. Defaults to 8765.")
    parser.add_argument("--db-path", default=str(db_path_from_env()), help="SQLite database path.")
    parser.add_argument(
        "--admin-token",
        default=None,
        help=(
            "Admin bearer token for /api/* requests and Wiki export. "
            "Defaults to FEISHU_MEMORY_COPILOT_ADMIN_TOKEN or COPILOT_ADMIN_TOKEN."
        ),
    )
    parser.add_argument(
        "--viewer-token",
        default=None,
        help=(
            "Optional read-only bearer token for /api/* requests. Viewer tokens cannot export Wiki markdown "
            "or update tenant policies. "
            "Defaults to FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN or COPILOT_ADMIN_VIEWER_TOKEN."
        ),
    )
    parser.add_argument(
        "--allow-unauthenticated-remote",
        action="store_true",
        help="Allow binding to a non-loopback host without an admin token. Not recommended.",
    )
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

    auth_token = args.admin_token or _admin_token_from_env()
    viewer_token = args.viewer_token or _admin_viewer_token_from_env()
    sso_config = admin_sso_config_from_env()
    if auth_token and viewer_token and auth_token == viewer_token:
        print("Admin token and viewer token must be different.", file=sys.stderr)
        return 2
    if (
        _remote_bind_requires_token(args.host)
        and not (auth_token or viewer_token)
        and not args.allow_unauthenticated_remote
    ):
        print(
            "Refusing to bind the admin backend to a non-loopback host without an access token. "
            "Set FEISHU_MEMORY_COPILOT_ADMIN_TOKEN / FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN "
            "or pass --admin-token / --viewer-token. For SSO header auth, bind the backend to "
            "127.0.0.1 behind a reverse proxy instead of exposing it directly.",
            file=sys.stderr,
        )
        return 2

    server = create_admin_server(
        args.host,
        args.port,
        db_path,
        auth_token=auth_token,
        viewer_token=viewer_token,
        sso_config=sso_config,
    )
    url = f"http://{args.host}:{server.server_port}"
    print(f"Feishu Memory Copilot admin: {url}", flush=True)
    print(f"SQLite database: {db_path}", flush=True)
    print(
        f"Admin API auth: {'enabled' if auth_token or viewer_token or sso_config.enabled else 'disabled'}", flush=True
    )
    print(
        "Admin access policy: "
        f"admin_token={'configured' if auth_token else 'missing'}, "
        f"viewer_token={'configured' if viewer_token else 'missing'}, "
        f"sso={'enabled' if sso_config.enabled else 'disabled'}, "
        "viewer_export=disabled, tenant_policy_write=admin_only",
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping admin server.")
    finally:
        server.server_close()
    return 0


def _admin_token_from_env() -> str | None:
    for name in ADMIN_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _admin_viewer_token_from_env() -> str | None:
    for name in ADMIN_VIEWER_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _remote_bind_requires_token(host: str) -> bool:
    return host not in {"127.0.0.1", "localhost", "::1"}


if __name__ == "__main__":
    raise SystemExit(main())
