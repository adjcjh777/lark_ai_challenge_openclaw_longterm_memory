#!/usr/bin/env python3
"""批量从飞书来源拉取数据进入 candidate pipeline。

用法：
  python3 scripts/feishu_batch_ingest.py --source tasks --limit 50
  python3 scripts/feishu_batch_ingest.py --source meetings --start-time 2026-04-01
  python3 scripts/feishu_batch_ingest.py --source bitable --app-token xxx --table-id yyy
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from memory_engine.db import connect, db_path_from_env, init_db
from memory_engine.document_ingestion import ingest_feishu_source
from memory_engine.repository import MemoryRepository


def main():
    parser = argparse.ArgumentParser(description="批量从飞书来源拉取数据进入 candidate pipeline")
    parser.add_argument(
        "--source",
        choices=["tasks", "meetings", "bitable"],
        required=True,
        help="数据来源类型",
    )
    parser.add_argument("--limit", type=int, default=50, help="最大拉取数量（默认 50）")
    parser.add_argument("--scope", default="project:feishu_ai_challenge", help="作用域")
    parser.add_argument("--dry-run", action="store_true", help="只显示将要拉取的内容，不实际写入")
    parser.add_argument("--start-time", help="开始时间（Unix 时间戳，仅对 meetings 有效）")
    parser.add_argument("--end-time", help="结束时间（Unix 时间戳，仅对 meetings 有效）")
    parser.add_argument("--app-token", help="Bitable 应用 token（仅对 bitable 有效）")
    parser.add_argument("--table-id", help="Bitable 表格 ID（仅对 bitable 有效）")
    parser.add_argument("--profile", help="lark-cli profile 名称")
    parser.add_argument("--as-identity", help="身份切换（user/bot）")

    args = parser.parse_args()

    if args.source == "tasks":
        batch_ingest_tasks(args)
    elif args.source == "meetings":
        batch_ingest_meetings(args)
    elif args.source == "bitable":
        batch_ingest_bitable(args)


def batch_ingest_tasks(args):
    """批量拉取飞书任务。"""
    from memory_engine.feishu_task_fetcher import list_feishu_tasks, fetch_feishu_task_text

    print(f"正在获取任务列表（最多 {args.limit} 条）...")
    try:
        tasks = list_feishu_tasks(
            page_size=args.limit,
            profile=args.profile,
            as_identity=args.as_identity,
        )
    except ValueError as e:
        print(f"获取任务列表失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(tasks)} 个任务")

    if args.dry_run:
        print("\n[Dry Run] 将要拉取的任务:")
        for i, task in enumerate(tasks[:args.limit], 1):
            print(f"{i}. {task.get('title', '无标题')} (ID: {task.get('task_id', '-')})")
        return

    # 初始化数据库
    conn = connect(db_path_from_env())
    init_db(conn)
    repo = MemoryRepository(conn)

    success_count = 0
    error_count = 0

    for i, task in enumerate(tasks[:args.limit], 1):
        task_id = task.get("task_id")
        title = task.get("title", "无标题")

        print(f"\n[{i}/{min(len(tasks), args.limit)}] 拉取任务: {title}")

        try:
            source = fetch_feishu_task_text(
                task_id,
                profile=args.profile,
                as_identity=args.as_identity,
            )

            result = ingest_feishu_source(repo, source, scope=args.scope)

            if result.get("ok"):
                candidate_count = result.get("candidate_count", 0)
                duplicate_count = result.get("duplicate_count", 0)
                print(f"  成功: {candidate_count} 个候选, {duplicate_count} 个重复")
                success_count += 1
            else:
                print(f"  失败: {result.get('error', {}).get('message', '未知错误')}")
                error_count += 1

        except ValueError as e:
            print(f"  跳过: {e}")
            error_count += 1
        except Exception as e:
            print(f"  错误: {e}")
            error_count += 1

    conn.close()
    print(f"\n完成: {success_count} 成功, {error_count} 失败")


def batch_ingest_meetings(args):
    """批量拉取飞书会议。"""
    from memory_engine.feishu_meeting_fetcher import list_feishu_meetings, fetch_feishu_meeting_text

    print(f"正在获取妙记列表（最多 {args.limit} 条）...")
    try:
        meetings = list_feishu_meetings(
            start_time=args.start_time,
            end_time=args.end_time,
            page_size=args.limit,
            profile=args.profile,
            as_identity=args.as_identity,
        )
    except ValueError as e:
        print(f"获取妙记列表失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(meetings)} 个妙记")

    if args.dry_run:
        print("\n[Dry Run] 将要拉取的妙记:")
        for i, meeting in enumerate(meetings[:args.limit], 1):
            print(f"{i}. {meeting.get('title', '无标题')} (Token: {meeting.get('minute_token', '-')})")
        return

    # 初始化数据库
    conn = connect(db_path_from_env())
    init_db(conn)
    repo = MemoryRepository(conn)

    success_count = 0
    error_count = 0

    for i, meeting in enumerate(meetings[:args.limit], 1):
        minute_token = meeting.get("minute_token")
        title = meeting.get("title", "无标题")

        print(f"\n[{i}/{min(len(meetings), args.limit)}] 拉取妙记: {title}")

        try:
            source = fetch_feishu_meeting_text(
                minute_token,
                profile=args.profile,
                as_identity=args.as_identity,
            )

            result = ingest_feishu_source(repo, source, scope=args.scope)

            if result.get("ok"):
                candidate_count = result.get("candidate_count", 0)
                duplicate_count = result.get("duplicate_count", 0)
                print(f"  成功: {candidate_count} 个候选, {duplicate_count} 个重复")
                success_count += 1
            else:
                print(f"  失败: {result.get('error', {}).get('message', '未知错误')}")
                error_count += 1

        except ValueError as e:
            print(f"  跳过: {e}")
            error_count += 1
        except Exception as e:
            print(f"  错误: {e}")
            error_count += 1

    conn.close()
    print(f"\n完成: {success_count} 成功, {error_count} 失败")


def batch_ingest_bitable(args):
    """批量拉取 Bitable 记录。"""
    if not args.app_token or not args.table_id:
        print("错误: --app-token 和 --table-id 参数必须提供", file=sys.stderr)
        sys.exit(1)

    from memory_engine.feishu_bitable_fetcher import list_bitable_records, fetch_bitable_record_text

    print(f"正在获取 Bitable 记录列表（最多 {args.limit} 条）...")
    try:
        records = list_bitable_records(
            args.app_token,
            args.table_id,
            limit=args.limit,
            profile=args.profile,
            as_identity=args.as_identity,
        )
    except ValueError as e:
        print(f"获取 Bitable 记录列表失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(records)} 条记录")

    if args.dry_run:
        print("\n[Dry Run] 将要拉取的记录:")
        for i, record in enumerate(records[:args.limit], 1):
            print(f"{i}. {record.get('summary', '无摘要')} (ID: {record.get('record_id', '-')})")
        return

    # 初始化数据库
    conn = connect(db_path_from_env())
    init_db(conn)
    repo = MemoryRepository(conn)

    success_count = 0
    error_count = 0

    for i, record in enumerate(records[:args.limit], 1):
        record_id = record.get("record_id")
        summary = record.get("summary", "无摘要")

        print(f"\n[{i}/{min(len(records), args.limit)}] 拉取记录: {summary[:50]}...")

        try:
            source = fetch_bitable_record_text(
                args.app_token,
                args.table_id,
                record_id,
                profile=args.profile,
                as_identity=args.as_identity,
            )

            result = ingest_feishu_source(repo, source, scope=args.scope)

            if result.get("ok"):
                candidate_count = result.get("candidate_count", 0)
                duplicate_count = result.get("duplicate_count", 0)
                print(f"  成功: {candidate_count} 个候选, {duplicate_count} 个重复")
                success_count += 1
            else:
                print(f"  失败: {result.get('error', {}).get('message', '未知错误')}")
                error_count += 1

        except ValueError as e:
            print(f"  跳过: {e}")
            error_count += 1
        except Exception as e:
            print(f"  错误: {e}")
            error_count += 1

    conn.close()
    print(f"\n完成: {success_count} 成功, {error_count} 失败")


if __name__ == "__main__":
    main()
