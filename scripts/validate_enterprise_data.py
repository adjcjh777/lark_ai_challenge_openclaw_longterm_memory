#!/usr/bin/env python3
"""Validate enterprise chat test data quality."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
errors = []


def err(msg):
    errors.append(msg)
    print(f"  [FAIL] {msg}")


def ok(msg):
    print(f"  [OK] {msg}")


def validate_jsonl():
    print("\n=== 1. JSONL 格式 ===")
    path = BASE / "datasets/enterprise_dialogues.jsonl"
    threads = []
    try:
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    threads.append(json.loads(line))
                except json.JSONDecodeError as e:
                    err(f"Line {i}: invalid JSON: {e}")
        ok(f"Parsed {len(threads)} threads")
    except FileNotFoundError:
        err(f"File not found: {path}")
    return threads


def validate_thread_count(threads):
    print("\n=== 2. Thread 数量 ===")
    if len(threads) != 60:
        err(f"Expected 60 threads, got {len(threads)}")
    else:
        ok("60 threads")


def validate_message_count(threads):
    print("\n=== 3. 消息数量 8-25 ===")
    for t in threads:
        n = len(t["messages"])
        if n < 8 or n > 25:
            err(f"{t['thread_id']}: {n} messages (need 8-25)")
    ok("All threads have 8-25 messages") if not errors else None


def validate_conflict_threads(threads):
    print("\n=== 4. Conflict threads >= 20 ===")
    count = sum(1 for t in threads if any(m["status"] == "superseded" for m in t["memory_labels"]))
    if count < 20:
        err(f"Only {count} conflict threads (need >= 20)")
    else:
        ok(f"{count} conflict threads")


def validate_noise_threads(threads):
    print("\n=== 5. Noise/temporary threads >= 15 ===")
    noise_keywords = ["只限今天", "临时", "不算最终结论", "别记成长期"]
    count = 0
    for t in threads:
        for m in t["messages"]:
            if any(kw in m["text"] for kw in noise_keywords):
                count += 1
                break
    if count < 15:
        err(f"Only {count} noise threads (need >= 15)")
    else:
        ok(f"{count} noise threads")


def validate_memory_types(threads):
    print("\n=== 6. Memory type 覆盖 10 类 ===")
    required = {
        "decision",
        "workflow",
        "preference",
        "deadline",
        "risk",
        "permission",
        "security",
        "demo",
        "benchmark",
        "document",
    }
    found = set()
    for t in threads:
        for ml in t["memory_labels"]:
            found.add(ml["type"])
    missing = required - found
    if missing:
        err(f"Missing types: {missing}")
    else:
        ok(f"All 10 types covered: {sorted(found)}")


def validate_current_value_length(threads):
    print("\n=== 7. current_value 长度 >= 3 ===")
    for t in threads:
        for ml in t["memory_labels"]:
            if len(ml["current_value"]) < 3:
                err(f"{t['thread_id']} {ml['memory_id']}: value too short: '{ml['current_value']}'")
    ok("All current_values >= 3 chars") if not errors else None


def validate_evidence_ids(threads):
    print("\n=== 8. evidence_message_ids 存在 ===")
    for t in threads:
        msg_ids = {m["message_id"] for m in t["messages"]}
        for ml in t["memory_labels"]:
            for eid in ml["evidence_message_ids"]:
                if eid not in msg_ids:
                    err(f"{t['thread_id']} {ml['memory_id']}: evidence {eid} not in messages")
    ok("All evidence IDs valid") if not errors else None


def validate_active_evidence_quality(threads):
    print("\n=== 9. Active label 证据不能只是确认句 ===")
    trivial = {
        "好",
        "收到",
        "可以",
        "行",
        "嗯",
        "同意",
        "确认",
        "好，确认。先这么定。",
        "可以，这个作为长期规则记下来。",
        "收到，记下来了。",
    }
    for t in threads:
        for ml in t["memory_labels"]:
            if ml["status"] != "active":
                continue
            for eid in ml["evidence_message_ids"]:
                msg = next((m for m in t["messages"] if m["message_id"] == eid), None)
                if msg and msg["text"].strip() in trivial:
                    err(f"{t['thread_id']} {ml['memory_id']}: evidence '{msg['text']}' is trivial")
    ok("Active evidence quality OK") if not errors else None


def validate_repeated_patterns(threads):
    print("\n=== 10. 重复句式不超过 3 次 ===")
    all_texts = []
    for t in threads:
        for m in t["messages"]:
            all_texts.append(m["text"])

    # Check for exact duplicates
    counts = Counter(all_texts)
    for text, count in counts.items():
        if count > 3:
            err(f"Repeated {count}x: '{text[:50]}...'")

    # Check for template patterns
    patterns = [
        r"以后都按这个来",
        r"好，确认。先这么定。",
        r"先这么定，后面再看。",
    ]
    for pat in patterns:
        matches = sum(1 for t in all_texts if re.search(pat, t))
        if matches > 3:
            err(f"Pattern '{pat}' appears {matches} times")

    ok("No excessive repetition") if not errors else None


def validate_noise_messages():
    print("\n=== 11. Noise messages >= 150 条不应沉淀 ===")
    path = BASE / "datasets/noise_messages.txt"
    try:
        with path.open(encoding="utf-8") as f:
            noise = [line.strip() for line in f if line.strip()]
        proj_noise = [
            n
            for n in noise
            if any(kw in n for kw in ["临时", "只限今天", "不算", "别记", "demo", "测试", "截图", "配置", "部署"])
        ]
        ok(f"{len(noise)} total noise, {len(proj_noise)} project-related (need >= 150)")
        if len(noise) < 150:
            err(f"Only {len(noise)} noise messages (need >= 150)")
    except FileNotFoundError:
        err(f"Noise file not found: {path}")


def validate_benchmarks():
    print("\n=== 12. Benchmark cases ===")
    path = BASE / "benchmarks/dialogue_memory_cases.json"
    try:
        with path.open(encoding="utf-8") as f:
            cases = json.load(f)
        types = {}
        for c in cases:
            types[c["type"]] = types.get(c["type"], 0) + 1
        ok(f"{len(cases)} cases: {dict(types)}")

        # Validate structure
        for c in cases:
            for field in [
                "case_id",
                "source_thread_id",
                "type",
                "query",
                "expected_active_value",
                "forbidden_value",
                "evidence_message_ids",
                "difficulty",
            ]:
                if field not in c:
                    err(f"Case {c.get('case_id', '?')}: missing field {field}")

        # Validate counts
        if types.get("recall", 0) < 90:
            err(f"Only {types.get('recall', 0)} recall cases (need 90)")
        if types.get("conflict_update", 0) < 40:
            err(f"Only {types.get('conflict_update', 0)} conflict cases (need 40)")
        if types.get("temporary_noise", 0) < 20:
            err(f"Only {types.get('temporary_noise', 0)} noise cases (need 20)")
    except FileNotFoundError:
        err(f"Benchmark file not found: {path}")
    except json.JSONDecodeError as e:
        err(f"Invalid JSON: {e}")


def validate_supersedes(threads):
    print("\n=== 13. supersedes 引用一致性 ===")
    for t in threads:
        mem_ids = {ml["memory_id"] for ml in t["memory_labels"]}
        for ml in t["memory_labels"]:
            for s in ml.get("supersedes", []):
                if s not in mem_ids:
                    err(f"{t['thread_id']} {ml['memory_id']}: supersedes {s} not found")
    ok("All supersedes references valid") if not errors else None


def main():
    print("=" * 60)
    print("Enterprise Data Validation")
    print("=" * 60)

    threads = validate_jsonl()
    if not threads:
        print("\nCannot continue without valid JSONL")
        sys.exit(1)

    validate_thread_count(threads)
    validate_message_count(threads)
    validate_conflict_threads(threads)
    validate_noise_threads(threads)
    validate_memory_types(threads)
    validate_current_value_length(threads)
    validate_evidence_ids(threads)
    validate_active_evidence_quality(threads)
    validate_repeated_patterns(threads)
    validate_noise_messages()
    validate_benchmarks()
    validate_supersedes(threads)

    print("\n" + "=" * 60)
    if errors:
        print(f"VALIDATION FAILED: {len(errors)} errors found")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
