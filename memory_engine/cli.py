from __future__ import annotations

import argparse
import json
import os
import sys

from .bitable_sync import BitableTarget, collect_sync_payload, setup_commands, sync_payload, table_schema_spec
from .benchmark import run_benchmark, run_document_ingestion_benchmark
from .db import connect, db_path_from_env, init_db
from .document_ingestion import ingest_document_source
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

    if args.command == "ingest-doc":
        conn = connect(args.db_path)
        init_db(conn)
        result = ingest_document_source(
            MemoryRepository(conn),
            args.url_or_token,
            scope=args.scope,
            lark_cli=args.lark_cli,
            profile=args.profile,
            as_identity=args.as_identity,
            limit=args.limit,
        )
        print_json(result)
        return

    if args.command == "confirm":
        conn = connect(args.db_path)
        init_db(conn)
        result = MemoryRepository(conn).confirm_candidate(args.candidate_id)
        print_json(result or {"action": "not_found", "memory_id": args.candidate_id})
        if result is None:
            sys.exit(1)
        return

    if args.command == "reject":
        conn = connect(args.db_path)
        init_db(conn)
        result = MemoryRepository(conn).reject_candidate(args.candidate_id)
        print_json(result or {"action": "not_found", "memory_id": args.candidate_id})
        if result is None:
            sys.exit(1)
        return

    if args.command == "benchmark" and args.benchmark_command == "run":
        result = run_benchmark(args.cases_path, scope=args.scope)
        print_json(result)
        return

    if args.command == "benchmark" and args.benchmark_command == "ingest-doc":
        result = run_document_ingestion_benchmark(args.cases_path, scope=args.scope)
        print_json(result)
        return

    if args.command == "bitable" and args.bitable_command == "schema":
        print_json(table_schema_spec())
        return

    if args.command == "bitable" and args.bitable_command == "setup-commands":
        target = _bitable_target(args)
        print_json({"commands": setup_commands(target)})
        return

    if args.command == "bitable" and args.bitable_command == "sync":
        conn = connect(args.db_path)
        init_db(conn)
        payload = collect_sync_payload(
            conn,
            scope=args.scope,
            benchmark_json=args.benchmark_json,
            benchmark_cases=args.benchmark_cases,
            benchmark_name=args.benchmark_name,
        )
        result = sync_payload(
            payload,
            _bitable_target(args),
            dry_run=not args.write,
            retries=args.retries,
        )
        print_json(result)
        if not result["ok"]:
            sys.exit(1)
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

    ingest_parser = subparsers.add_parser("ingest-doc", help="Import candidate memories from a Feishu doc token/url or Markdown file")
    ingest_parser.add_argument("--scope", default=DEFAULT_SCOPE)
    ingest_parser.add_argument("--limit", type=int, default=12, help="Maximum candidate memories to extract")
    ingest_parser.add_argument("--lark-cli", default=os.environ.get("LARK_CLI", "lark-cli"), help="lark-cli executable path")
    ingest_parser.add_argument("--profile", default=os.environ.get("LARK_CLI_PROFILE"), help="Optional lark-cli profile")
    ingest_parser.add_argument("--as-identity", default=os.environ.get("LARK_CLI_AS"), help="Optional lark-cli identity, for example user or bot")
    ingest_parser.add_argument("url_or_token")

    confirm_parser = subparsers.add_parser("confirm", help="Promote a candidate memory to active")
    confirm_parser.add_argument("candidate_id")

    reject_parser = subparsers.add_parser("reject", help="Reject a candidate memory")
    reject_parser.add_argument("candidate_id")

    benchmark_parser = subparsers.add_parser("benchmark", help="Benchmark commands")
    benchmark_parser.add_argument("--scope", default=DEFAULT_SCOPE)
    benchmark_subparsers = benchmark_parser.add_subparsers(dest="benchmark_command")
    run_parser = benchmark_subparsers.add_parser("run", help="Run benchmark cases")
    run_parser.add_argument("cases_path")
    ingest_doc_benchmark_parser = benchmark_subparsers.add_parser("ingest-doc", help="Run document ingestion benchmark cases")
    ingest_doc_benchmark_parser.add_argument("cases_path")

    bitable_parser = subparsers.add_parser("bitable", help="Bitable ledger sync commands")
    bitable_subparsers = bitable_parser.add_subparsers(dest="bitable_command")
    bitable_subparsers.add_parser("schema", help="Print the Day 4 Bitable table schema")

    setup_parser = bitable_subparsers.add_parser("setup-commands", help="Print lark-cli commands to create Day 4 tables")
    add_bitable_target_args(setup_parser)

    sync_parser = bitable_subparsers.add_parser("sync", help="Sync local SQLite rows to Bitable")
    add_bitable_target_args(sync_parser)
    sync_parser.add_argument("--write", action="store_true", help="Actually write to Bitable. Omit for local dry-run")
    sync_parser.add_argument("--retries", type=int, default=2, help="Retry count for each lark-cli write batch")
    sync_parser.add_argument("--benchmark-json", help="Path to an existing benchmark JSON result to sync")
    sync_parser.add_argument("--benchmark-cases", help="Run benchmark cases and sync the summary row")
    sync_parser.add_argument("--benchmark-name", help="Display name for the benchmark run")
    sync_parser.add_argument("--scope", help="Only sync memories from this scope, for example project:day4_demo")

    feishu_parser = subparsers.add_parser("feishu", help="Feishu bot commands")
    feishu_subparsers = feishu_parser.add_subparsers(dest="feishu_command")
    replay_parser = feishu_subparsers.add_parser("replay", help="Replay a Feishu message event fixture")
    replay_parser.add_argument("event_path")
    listen_parser = feishu_subparsers.add_parser("listen", help="Listen for Feishu events with lark-cli")
    listen_parser.add_argument("--dry-run", action="store_true", help="Print replies without sending them to Feishu")

    return parser


def add_bitable_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-token", default=os.environ.get("BITABLE_BASE_TOKEN", "app_xxx"), help="Bitable/Base token. Required for non-dry-run sync")
    parser.add_argument("--ledger-table", default=os.environ.get("BITABLE_LEDGER_TABLE", "Memory Ledger"), help="Table ID or table name for current memory rows")
    parser.add_argument("--versions-table", default=os.environ.get("BITABLE_VERSIONS_TABLE", "Memory Versions"), help="Table ID or table name for version rows")
    parser.add_argument("--benchmark-table", default=os.environ.get("BITABLE_BENCHMARK_TABLE", "Benchmark Results"), help="Table ID or table name for benchmark rows")
    parser.add_argument("--lark-cli", default=os.environ.get("LARK_CLI", "lark-cli"), help="lark-cli executable path")
    parser.add_argument("--profile", default=os.environ.get("LARK_CLI_PROFILE"), help="Optional lark-cli profile")
    parser.add_argument("--as-identity", default=os.environ.get("LARK_CLI_AS"), help="Optional lark-cli identity, for example user or bot")


def _bitable_target(args) -> BitableTarget:
    return BitableTarget(
        base_token=args.base_token,
        ledger_table=args.ledger_table,
        versions_table=args.versions_table,
        benchmark_table=args.benchmark_table,
        lark_cli=args.lark_cli,
        profile=args.profile,
        as_identity=args.as_identity,
    )


def print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
