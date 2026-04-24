from __future__ import annotations

import argparse
import json
import sys

from .benchmark import run_benchmark
from .db import connect, db_path_from_env, init_db
from .feishu_runtime import listen, replay_event
from .models import DEFAULT_SCOPE
from .repository import MemoryRepository


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        conn = connect(args.db_path)
        init_db(conn)
        print_json({"ok": True, "db_path": str(args.db_path or db_path_from_env())})
        return

    if args.command == "remember":
        conn = connect(args.db_path)
        init_db(conn)
        result = MemoryRepository(conn).remember(args.scope, args.content)
        print_json(result)
        return

    if args.command == "recall":
        conn = connect(args.db_path)
        init_db(conn)
        result = MemoryRepository(conn).recall(args.scope, args.query)
        if result is None:
            print_json({"answer": None, "status": "not_found", "query": args.query})
            sys.exit(1)
        print_json(result)
        return

    if args.command == "versions":
        conn = connect(args.db_path)
        init_db(conn)
        result = MemoryRepository(conn).versions(args.memory_id)
        print_json({"memory_id": args.memory_id, "versions": result})
        return

    if args.command == "benchmark" and args.benchmark_command == "run":
        result = run_benchmark(args.cases_path, scope=args.scope)
        print_json(result)
        return

    if args.command == "feishu" and args.feishu_command == "replay":
        result = replay_event(args.event_path, db_path=args.db_path)
        print_json(result)
        return

    if args.command == "feishu" and args.feishu_command == "listen":
        listen(db_path=args.db_path, dry_run=args.dry_run)
        return

    parser.print_help()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory", description="Day 1 local Feishu Memory Engine CLI")
    parser.add_argument("--db-path", help="SQLite database path. Defaults to MEMORY_DB_PATH or data/memory.sqlite")

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-db", help="Initialize the SQLite schema")

    remember_parser = subparsers.add_parser("remember", help="Store a memory")
    remember_parser.add_argument("--scope", default=DEFAULT_SCOPE)
    remember_parser.add_argument("content")

    recall_parser = subparsers.add_parser("recall", help="Recall an active memory")
    recall_parser.add_argument("--scope", default=DEFAULT_SCOPE)
    recall_parser.add_argument("query")

    versions_parser = subparsers.add_parser("versions", help="List versions for a memory")
    versions_parser.add_argument("memory_id")

    benchmark_parser = subparsers.add_parser("benchmark", help="Benchmark commands")
    benchmark_parser.add_argument("--scope", default=DEFAULT_SCOPE)
    benchmark_subparsers = benchmark_parser.add_subparsers(dest="benchmark_command")
    run_parser = benchmark_subparsers.add_parser("run", help="Run benchmark cases")
    run_parser.add_argument("cases_path")

    feishu_parser = subparsers.add_parser("feishu", help="Feishu bot commands")
    feishu_subparsers = feishu_parser.add_subparsers(dest="feishu_command")
    replay_parser = feishu_subparsers.add_parser("replay", help="Replay a Feishu message event fixture")
    replay_parser.add_argument("event_path")
    listen_parser = feishu_subparsers.add_parser("listen", help="Listen for Feishu events with lark-cli")
    listen_parser.add_argument("--dry-run", action="store_true", help="Print replies without sending them to Feishu")

    return parser


def print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
