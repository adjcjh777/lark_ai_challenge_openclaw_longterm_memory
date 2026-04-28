from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Iterable, Literal

ListenerKind = Literal[
    "copilot-lark-cli",
    "legacy-lark-cli",
    "direct-lark-cli",
    "openclaw-websocket",
    "openclaw-gateway-unknown",
]

PlannedListener = Literal["copilot-lark-cli", "legacy-lark-cli", "openclaw-websocket", "none"]


@dataclass(frozen=True)
class FeishuListenerProcess:
    pid: int
    ppid: int
    kind: ListenerKind
    command: str


class FeishuListenerConflict(RuntimeError):
    def __init__(self, planned_listener: PlannedListener, processes: list[FeishuListenerProcess]):
        self.planned_listener = planned_listener
        self.processes = processes
        super().__init__(_format_conflict(planned_listener, processes))


def assert_single_feishu_listener(
    planned_listener: PlannedListener,
    *,
    current_pid: int | None = None,
    process_rows: Iterable[str] | None = None,
) -> list[FeishuListenerProcess]:
    """Fail fast when another Feishu event listener already owns the same bot."""

    active = discover_feishu_listeners(current_pid=current_pid, process_rows=process_rows)
    conflicts = conflicting_listeners(planned_listener, active)
    if conflicts and os.environ.get("FEISHU_SINGLE_LISTENER_ALLOW_CONFLICT") != "1":
        raise FeishuListenerConflict(planned_listener, conflicts)
    return active


def discover_feishu_listeners(
    *,
    current_pid: int | None = None,
    process_rows: Iterable[str] | None = None,
) -> list[FeishuListenerProcess]:
    rows = list(process_rows) if process_rows is not None else _ps_rows()
    current_pid = current_pid or os.getpid()
    listeners: list[FeishuListenerProcess] = []
    for row in rows:
        parsed = _parse_ps_row(row)
        if parsed is None:
            continue
        pid, ppid, command = parsed
        if pid == current_pid:
            continue
        kind = classify_listener_command(command)
        if kind is not None:
            listeners.append(FeishuListenerProcess(pid=pid, ppid=ppid, kind=kind, command=command))
    return listeners


def conflicting_listeners(
    planned_listener: PlannedListener,
    active: Iterable[FeishuListenerProcess],
) -> list[FeishuListenerProcess]:
    conflicts: list[FeishuListenerProcess] = []
    for process in active:
        if process.kind == "openclaw-gateway-unknown":
            continue
        if planned_listener == "none" or process.kind != planned_listener:
            conflicts.append(process)
    return conflicts


def classify_listener_command(command: str) -> ListenerKind | None:
    normalized = " ".join(command.lower().split())
    if _looks_like_search_command(normalized):
        return None
    if "lark-cli" in normalized and "event" in normalized and "+subscribe" in normalized:
        return "direct-lark-cli"
    if "memory_engine" in normalized and "copilot-feishu" in normalized and "listen" in normalized:
        return "copilot-lark-cli"
    if "memory_engine" in normalized and " feishu " in f" {normalized} " and "listen" in normalized:
        return "legacy-lark-cli"
    if "openclaw" in normalized and any(token in normalized for token in ("feishu", "lark", "websocket")):
        return "openclaw-websocket"
    if "openclaw-gateway" in normalized or "openclaw gateway" in normalized:
        return "openclaw-gateway-unknown"
    return None


def listener_report(active: Iterable[FeishuListenerProcess]) -> str:
    processes = list(active)
    if not processes:
        return "No Feishu listener process detected."
    return "\n".join(f"- pid={process.pid} kind={process.kind} command={process.command}" for process in processes)


def _ps_rows() -> list[str]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.splitlines()


def _parse_ps_row(row: str) -> tuple[int, int, str] | None:
    parts = row.strip().split(maxsplit=2)
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), parts[2]
    except ValueError:
        return None


def _looks_like_search_command(command: str) -> bool:
    return (
        " rg " in f" {command} "
        or "ripgrep" in command
        or "grep" in command
        or "check_feishu_listener_singleton.py" in command
    )


def _format_conflict(planned_listener: PlannedListener, processes: list[FeishuListenerProcess]) -> str:
    lines = [
        "Feishu listener singleton check failed.",
        f"Planned listener: {planned_listener}",
        "Only one listener may own the Feishu Memory Engine bot at a time.",
        "Stop the conflicting process or choose OpenClaw websocket as the only listener.",
        "Conflicts:",
    ]
    lines.extend(f"- pid={process.pid} kind={process.kind} command={process.command}" for process in processes)
    lines.append("Emergency override: FEISHU_SINGLE_LISTENER_ALLOW_CONFLICT=1, only for throwaway debugging.")
    return "\n".join(lines)
