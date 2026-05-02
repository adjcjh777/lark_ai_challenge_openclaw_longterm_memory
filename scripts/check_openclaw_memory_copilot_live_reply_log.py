#!/usr/bin/env python3
"""Check gateway.log for a post-fix Feishu Memory Copilot visible reply.

This script is a log verifier for the manual live step: send `/settings` in the
controlled Feishu test group, then run this checker with a timestamp taken just
before sending the message.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path.home() / ".openclaw/logs/gateway.log"
TIMESTAMP_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}) ")
JSON_RE = re.compile(r"(\{.*\})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH), help="OpenClaw gateway.log path.")
    parser.add_argument("--since", default="", help="Only inspect lines with timestamp >= this RFC3339-like value.")
    parser.add_argument("--expect-text", default="/settings", help="Expected Feishu message text fragment.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    report = check_live_reply_log(Path(args.log_path), since=args.since, expect_text=args.expect_text)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def check_live_reply_log(log_path: Path, *, since: str = "", expect_text: str = "/settings") -> dict[str, Any]:
    if not log_path.exists():
        return failure("log_missing", f"log_path does not exist: {log_path}")
    lines = [line for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if line_after_since(line, since)]
    message_index = find_index(lines, lambda line: "Feishu[default] message" in line and expect_text in line)
    if message_index is None:
        return failure("expected_message_missing", f"no Feishu message containing {expect_text!r} found after since={since!r}")

    inspected = lines[message_index:]
    card_delivery = first_json_log(inspected, "feishu-memory-copilot card delivery")
    if card_delivery and card_delivery.get("ok") is True:
        return success("card_delivery_ok", "interactive card delivery logged ok=true", card_delivery)

    route_result = first_json_log(inspected, "feishu-memory-copilot route result")
    router_failed = any("feishu-memory-copilot router failed" in line for line in inspected)
    fallback_dispatch = any("dispatch complete" in line and "replies=1" in line for line in inspected)
    if card_delivery and card_delivery.get("ok") is not True and fallback_dispatch:
        return {
            "ok": False,
            "status": "card_delivery_failed_visible_text_fallback",
            "message": "interactive card delivery failed and OpenClaw dispatched a visible text fallback",
            "card_delivery": card_delivery,
            "fallback_dispatch": True,
        }
    if router_failed and fallback_dispatch:
        return success(
            "router_failed_visible_fallback",
            "router failed but OpenClaw logged a visible fallback reply",
            {"router_failed": True},
        )

    return {
        "ok": False,
        "status": "visible_reply_unproven",
        "message": "expected message was received, but no successful interactive card delivery evidence was found",
        "route_result": route_result or {},
        "card_delivery": card_delivery or {},
        "fallback_dispatch": fallback_dispatch,
    }


def line_after_since(line: str, since: str) -> bool:
    if not since:
        return True
    match = TIMESTAMP_RE.match(line)
    if not match:
        return True
    return match.group("ts") >= since


def find_index(lines: list[str], predicate) -> int | None:
    for index, line in enumerate(lines):
        if predicate(line):
            return index
    return None


def first_json_log(lines: list[str], marker: str) -> dict[str, Any] | None:
    for line in lines:
        if marker not in line:
            continue
        match = JSON_RE.search(line)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def success(status: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "status": status, "message": message, "evidence": evidence}


def failure(status: str, message: str) -> dict[str, Any]:
    return {"ok": False, "status": status, "message": message}


def format_report(report: dict[str, Any]) -> str:
    return f"OpenClaw Memory Copilot live reply log: {'PASS' if report['ok'] else 'FAIL'}\n{report['status']}: {report['message']}"


if __name__ == "__main__":
    raise SystemExit(main())
