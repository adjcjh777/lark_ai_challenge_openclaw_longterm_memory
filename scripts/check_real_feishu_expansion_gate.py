#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory_engine.feishu_listener_guard import (  # noqa: E402
    FeishuListenerConflict,
    assert_single_feishu_listener,
    listener_report,
)


@dataclass(frozen=True)
class GateCheck:
    name: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "reason": self.reason}


def evaluate_gate(
    *,
    env: Mapping[str, str],
    planned_listener: str,
    task_id: str | None = None,
    minute_token: str | None = None,
    bitable_app_token: str | None = None,
    bitable_table_id: str | None = None,
    bitable_record_id: str | None = None,
    listener_singleton_ok: bool = True,
    listener_singleton_reason: str = "single listener check passed",
) -> dict[str, object]:
    checks = [
        _env_present(env, "COPILOT_FEISHU_ALLOWED_CHAT_IDS", "受控 allowlist 群 ID 必须已配置。"),
        _env_present(env, "COPILOT_FEISHU_REVIEWER_OPEN_IDS", "受控 reviewer / owner open_id 必须已配置。"),
        GateCheck(
            "listener_singleton",
            "pass" if listener_singleton_ok else "block",
            listener_singleton_reason,
        ),
        GateCheck(
            "planned_listener",
            "pass" if planned_listener != "none" else "block",
            "planned listener selected" if planned_listener != "none" else "必须明确本轮使用哪个 Feishu listener。",
        ),
        _resource_check(
            task_id=task_id,
            minute_token=minute_token,
            bitable_app_token=bitable_app_token,
            bitable_table_id=bitable_table_id,
            bitable_record_id=bitable_record_id,
        ),
    ]
    blocked = [item for item in checks if item.status != "pass"]
    return {
        "ok": not blocked,
        "status": "pass" if not blocked else "blocked",
        "planned_listener": planned_listener,
        "checks": [item.to_dict() for item in checks],
        "blocked_count": len(blocked),
        "blocked_checks": [item.name for item in blocked],
        "redaction_policy": "environment values and resource ids are not printed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check readiness for the controlled real Feishu expansion smoke gate."
    )
    parser.add_argument(
        "--planned-listener",
        choices=("copilot-lark-cli", "legacy-lark-cli", "openclaw-websocket", "none"),
        default="none",
    )
    parser.add_argument("--task-id", help="Controlled Feishu task id for task fetcher smoke.")
    parser.add_argument("--minute-token", help="Controlled Feishu minute token for meeting fetcher smoke.")
    parser.add_argument("--bitable-app-token", help="Controlled Bitable app token.")
    parser.add_argument("--bitable-table-id", help="Controlled Bitable table id.")
    parser.add_argument("--bitable-record-id", help="Controlled Bitable record id.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    listener_ok = True
    listener_reason = "single listener check passed"
    try:
        active = assert_single_feishu_listener(args.planned_listener)
        if active:
            listener_reason = listener_report(active)
    except FeishuListenerConflict as exc:
        listener_ok = False
        listener_reason = str(exc)
    except OSError as exc:
        listener_ok = False
        listener_reason = f"unable_to_check_listener_singleton:{exc.__class__.__name__}"

    result = evaluate_gate(
        env=os.environ,
        planned_listener=args.planned_listener,
        task_id=args.task_id,
        minute_token=args.minute_token,
        bitable_app_token=args.bitable_app_token,
        bitable_table_id=args.bitable_table_id,
        bitable_record_id=args.bitable_record_id,
        listener_singleton_ok=listener_ok,
        listener_singleton_reason=listener_reason,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 2


def _env_present(env: Mapping[str, str], name: str, missing_reason: str) -> GateCheck:
    value = str(env.get(name) or "").strip()
    return GateCheck(
        name=name,
        status="pass" if value else "block",
        reason="configured" if value else missing_reason,
    )


def _resource_check(
    *,
    task_id: str | None,
    minute_token: str | None,
    bitable_app_token: str | None,
    bitable_table_id: str | None,
    bitable_record_id: str | None,
) -> GateCheck:
    has_task = bool(task_id)
    has_meeting = bool(minute_token)
    has_bitable = bool(bitable_app_token and bitable_table_id and bitable_record_id)
    if has_task or has_meeting or has_bitable:
        selected = []
        if has_task:
            selected.append("task")
        if has_meeting:
            selected.append("meeting")
        if has_bitable:
            selected.append("bitable")
        return GateCheck("controlled_resource", "pass", f"controlled resource selected: {', '.join(selected)}")
    return GateCheck(
        "controlled_resource",
        "block",
        "至少提供一个受控 Task、Meeting 或完整 Bitable 资源 ID 组合。",
    )


def _print_text(result: dict[str, object]) -> None:
    print(f"Real Feishu controlled expansion gate: {result['status']}")
    print(f"Planned listener: {result['planned_listener']}")
    for item in result["checks"]:
        assert isinstance(item, dict)
        print(f"- {item['name']}: {item['status']} ({item['reason']})")
    print(f"Redaction: {result['redaction_policy']}")


if __name__ == "__main__":
    raise SystemExit(main())
