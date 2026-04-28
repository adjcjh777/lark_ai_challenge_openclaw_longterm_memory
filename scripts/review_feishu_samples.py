#!/usr/bin/env python3
"""人工复核飞书样本。

用法：
  python3 scripts/review_feishu_samples.py --input benchmarks/real_feishu_samples.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description="人工复核飞书样本")
    parser.add_argument(
        "--input",
        default="benchmarks/real_feishu_samples.json",
        help="输入文件路径（默认: benchmarks/real_feishu_samples.json）",
    )
    parser.add_argument("--source", help="只复核指定来源类型（tasks, meetings, bitable）")
    parser.add_argument("--auto-confirm", action="store_true", help="自动确认所有待复核样本（用于测试）")

    args = parser.parse_args()

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"错误: 输入文件不存在: {input_file}", file=sys.stderr)
        sys.exit(1)

    # 加载样本
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 确定要复核的来源类型
    source_types = []
    if args.source:
        if args.source in data:
            source_types = [args.source]
        else:
            print(f"错误: 来源类型 '{args.source}' 不存在于数据中", file=sys.stderr)
            sys.exit(1)
    else:
        source_types = [k for k in data.keys() if k != "_metadata"]

    # 复核样本
    total_reviewed = 0
    for source_type in source_types:
        samples = data.get(source_type, [])
        pending_samples = [s for s in samples if s.get("review_status") == "pending"]

        if not pending_samples:
            print(f"\n{source_type}: 没有待复核的样本")
            continue

        print(f"\n{source_type}: 有 {len(pending_samples)} 个待复核样本")

        if args.auto_confirm:
            # 自动确认所有样本
            for sample in pending_samples:
                sample["review_status"] = "confirmed"
                sample["review_reason"] = "auto-confirmed for testing"
                sample["reviewed_at"] = datetime.now().isoformat()
                total_reviewed += 1
            print(f"  已自动确认 {len(pending_samples)} 个样本")
        else:
            # 交互式复核
            for i, sample in enumerate(pending_samples, 1):
                print(f"\n--- 样本 {i}/{len(pending_samples)} ---")
                print(f"来源类型: {sample.get('source_type')}")
                print(f"来源 ID: {sample.get('source_id')}")
                print(f"标题: {sample.get('title')}")
                print(f"文本预览: {sample.get('text', '')[:200]}...")
                print(f"元数据: {json.dumps(sample.get('metadata', {}), ensure_ascii=False)}")

                while True:
                    action = input("\n请输入操作 (c=确认, r=拒绝, s=跳过, q=退出): ").strip().lower()
                    if action in ("c", "r", "s", "q"):
                        break
                    print("无效输入，请重新输入")

                if action == "q":
                    print("退出复核")
                    break
                elif action == "s":
                    print("跳过此样本")
                    continue
                elif action == "c":
                    reason = input("请输入确认理由（可选）: ").strip()
                    sample["review_status"] = "confirmed"
                    sample["review_reason"] = reason or "confirmed by human"
                    sample["reviewed_at"] = datetime.now().isoformat()
                    total_reviewed += 1
                    print("已确认")
                elif action == "r":
                    reason = input("请输入拒绝理由: ").strip()
                    if not reason:
                        print("拒绝必须提供理由，请重新操作")
                        continue
                    sample["review_status"] = "rejected"
                    sample["review_reason"] = reason
                    sample["reviewed_at"] = datetime.now().isoformat()
                    total_reviewed += 1
                    print("已拒绝")

    # 保存更新后的数据
    data["_metadata"] = {
        "last_updated": datetime.now().isoformat(),
        "total_samples": sum(len(v) for k, v in data.items() if k != "_metadata"),
        "confirmed_samples": sum(
            len([s for s in v if s.get("review_status") == "confirmed"])
            for k, v in data.items()
            if k != "_metadata"
        ),
        "rejected_samples": sum(
            len([s for s in v if s.get("review_status") == "rejected"])
            for k, v in data.items()
            if k != "_metadata"
        ),
    }

    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n复核完成，共复核 {total_reviewed} 个样本")
    print(f"已保存到: {input_file}")

    # 显示统计信息
    print("\n统计信息:")
    for source_type in source_types:
        samples = data.get(source_type, [])
        confirmed = len([s for s in samples if s.get("review_status") == "confirmed"])
        rejected = len([s for s in samples if s.get("review_status") == "rejected"])
        pending = len([s for s in samples if s.get("review_status") == "pending"])
        print(f"  {source_type}: {confirmed} 确认, {rejected} 拒绝, {pending} 待复核")


if __name__ == "__main__":
    main()
