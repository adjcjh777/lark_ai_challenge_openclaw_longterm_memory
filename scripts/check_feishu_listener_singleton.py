#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory_engine.feishu_listener_guard import (  # noqa: E402
    FeishuListenerConflict,
    assert_single_feishu_listener,
    listener_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that only one Feishu listener owns the Feishu Memory Engine bot."
    )
    parser.add_argument(
        "--planned-listener",
        choices=("copilot-lark-cli", "legacy-lark-cli", "openclaw-websocket", "none"),
        default="none",
        help="Listener you are about to start, or openclaw-websocket when OpenClaw owns Feishu events.",
    )
    args = parser.parse_args()

    try:
        active = assert_single_feishu_listener(args.planned_listener)
    except FeishuListenerConflict as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Feishu listener singleton check OK.")
    print(f"Planned listener: {args.planned_listener}")
    print(listener_report(active))
    if any(process.kind == "openclaw-gateway-unknown" for process in active):
        print(
            "Note: openclaw-gateway is running, but this process list cannot prove whether its Feishu websocket "
            "channel is active. If OpenClaw owns this bot, do not start lark-cli event +subscribe.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
