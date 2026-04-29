from __future__ import annotations

import json
import os
import sys
from typing import Any

from .local_env import load_local_env_files
from .service import CopilotService
from .tools import handle_tool_request


def run_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    load_local_env_files(override=True)

    tool_name = envelope.get("tool")
    payload = envelope.get("payload")
    if not isinstance(tool_name, str) or not tool_name:
        return {
            "ok": False,
            "error": {
                "code": "validation_error",
                "message": "tool must be a non-empty string",
                "retryable": False,
                "details": {"envelope": "openclaw_tool_runner"},
            },
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": {
                "code": "validation_error",
                "message": "payload must be an object",
                "retryable": False,
                "details": {"tool": tool_name},
            },
        }

    payload = _normalize_openclaw_payload(payload)
    db_path = envelope.get("db_path") or os.getenv("FEISHU_MEMORY_COPILOT_DB")
    service = CopilotService(db_path=db_path if isinstance(db_path, str) and db_path else None)
    return handle_tool_request(tool_name, payload, service=service)


def _normalize_openclaw_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["current_context"] = _json_object_string_to_dict(normalized.get("current_context"))
    return normalized


def _json_object_string_to_dict(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return value
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    return parsed if isinstance(parsed, dict) else value


def main() -> int:
    try:
        raw = sys.stdin.read()
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise ValueError("stdin JSON must be an object")
        response = run_envelope(envelope)
    except Exception as exc:
        response = {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": str(exc),
                "retryable": False,
                "details": {"runner": "memory_engine.copilot.openclaw_tool_runner"},
            },
        }
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") is not False or response.get("error", {}).get("code") != "internal_error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
