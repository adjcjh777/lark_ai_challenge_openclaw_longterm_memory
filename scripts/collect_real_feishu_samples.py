#!/usr/bin/env python3
"""收集真实飞书样本用于人工复核。

用法：
  python3 scripts/collect_real_feishu_samples.py --source tasks --limit 20
  python3 scripts/collect_real_feishu_samples.py --source meetings --limit 20
  python3 scripts/collect_real_feishu_samples.py --source bitable --app-token xxx --table-id yyy --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description="收集真实飞书样本用于人工复核")
    parser.add_argument(
        "--source",
        choices=["tasks", "meetings", "bitable"],
        required=True,
        help="数据来源类型",
    )
    parser.add_argument("--limit", type=int, default=20, help="最大拉取数量（默认 20）")
    parser.add_argument("--start-time", help="开始时间（Unix 时间戳，仅对 meetings 有效）")
    parser.add_argument("--end-time", help="结束时间（Unix 时间戳，仅对 meetings 有效）")
    parser.add_argument("--app-token", help="Bitable 应用 token（仅对 bitable 有效）")
    parser.add_argument("--table-id", help="Bitable 表格 ID（仅对 bitable 有效）")
    parser.add_argument("--profile", help="lark-cli profile 名称")
    parser.add_argument("--as-identity", help="身份切换（user/bot）")
    parser.add_argument("--output", help="输出文件路径（默认: benchmarks/real_feishu_samples.json）")

    args = parser.parse_args()

    output_path = args.output or "benchmarks/real_feishu_samples.json"

    if args.source == "tasks":
        samples = collect_task_samples(args)
    elif args.source == "meetings":
        samples = collect_meeting_samples(args)
    elif args.source == "bitable":
        samples = collect_bitable_samples(args)
    else:
        print(f"未知的数据来源: {args.source}", file=sys.stderr)
        sys.exit(1)

    # 保存样本
    save_samples(samples, output_path, args.source)
    print(f"\n已收集 {len(samples)} 个样本，保存到: {output_path}")
    print("请人工复核每个样本，然后运行以下命令更新状态:")
    print(f"  python3 scripts/review_feishu_samples.py --input {output_path}")


def collect_task_samples(args):
    """收集飞书任务样本。"""
    from memory_engine.feishu_task_fetcher import fetch_feishu_task_text, list_feishu_tasks

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

    samples = []
    for i, task in enumerate(tasks[: args.limit], 1):
        task_id = task.get("task_id")
        title = task.get("title", "无标题")

        print(f"\n[{i}/{min(len(tasks), args.limit)}] 拉取任务: {title}")

        try:
            source = fetch_feishu_task_text(
                task_id,
                profile=args.profile,
                as_identity=args.as_identity,
            )

            samples.append(
                {
                    "source_type": "feishu_task",
                    "source_id": task_id,
                    "title": source.title,
                    "text": source.text,
                    "actor_id": source.actor_id,
                    "source_url": source.source_url,
                    "metadata": source.metadata,
                    "review_status": "pending",  # pending, confirmed, rejected
                    "review_reason": "",
                    "reviewed_at": "",
                }
            )

            print(f"  成功: {len(source.text)} 字符")

        except ValueError as e:
            print(f"  跳过: {e}")
        except Exception as e:
            print(f"  错误: {e}")

    return samples


def collect_meeting_samples(args):
    """收集飞书会议样本。"""
    from memory_engine.feishu_meeting_fetcher import fetch_feishu_meeting_text, list_feishu_meetings

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

    samples = []
    for i, meeting in enumerate(meetings[: args.limit], 1):
        minute_token = meeting.get("minute_token")
        title = meeting.get("title", "无标题")

        print(f"\n[{i}/{min(len(meetings), args.limit)}] 拉取妙记: {title}")

        try:
            source = fetch_feishu_meeting_text(
                minute_token,
                profile=args.profile,
                as_identity=args.as_identity,
            )

            samples.append(
                {
                    "source_type": "feishu_meeting",
                    "source_id": minute_token,
                    "title": source.title,
                    "text": source.text,
                    "actor_id": source.actor_id,
                    "source_url": source.source_url,
                    "metadata": source.metadata,
                    "review_status": "pending",  # pending, confirmed, rejected
                    "review_reason": "",
                    "reviewed_at": "",
                }
            )

            print(f"  成功: {len(source.text)} 字符")

        except ValueError as e:
            print(f"  跳过: {e}")
        except Exception as e:
            print(f"  错误: {e}")

    return samples


def collect_bitable_samples(args):
    """收集 Bitable 样本。"""
    if not args.app_token or not args.table_id:
        print("错误: --app-token 和 --table-id 参数必须提供", file=sys.stderr)
        sys.exit(1)

    from memory_engine.feishu_bitable_fetcher import fetch_bitable_record_text, list_bitable_records

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

    samples = []
    for i, record in enumerate(records[: args.limit], 1):
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

            samples.append(
                {
                    "source_type": "lark_bitable",
                    "source_id": record_id,
                    "title": source.title,
                    "text": source.text,
                    "actor_id": source.actor_id,
                    "source_url": source.source_url,
                    "metadata": source.metadata,
                    "review_status": "pending",  # pending, confirmed, rejected
                    "review_reason": "",
                    "reviewed_at": "",
                }
            )

            print(f"  成功: {len(source.text)} 字符")

        except ValueError as e:
            print(f"  跳过: {e}")
        except Exception as e:
            print(f"  错误: {e}")

    return samples


def save_samples(samples, output_path, source_type):
    """保存样本到 JSON 文件。"""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 如果文件已存在，加载现有数据
    existing_data = {}
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            existing_data = {}

    # 更新数据
    if source_type not in existing_data:
        existing_data[source_type] = []

    # 合并样本（避免重复）
    existing_ids = {s["source_id"] for s in existing_data[source_type]}
    new_samples = [s for s in samples if s["source_id"] not in existing_ids]
    existing_data[source_type].extend(new_samples)

    # 添加元数据
    existing_data["_metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_samples": sum(len(v) for k, v in existing_data.items() if k != "_metadata"),
    }

    # 保存
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
