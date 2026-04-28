from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_engine.copilot.tools import supported_tool_names


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "agent_adapters" / "openclaw" / "memory_tools.schema.json"
PLUGIN_DIR = ROOT / "agent_adapters" / "openclaw" / "plugin"


@dataclass(frozen=True)
class OpenClawToolRegistration:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    def to_manifest_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


def load_tool_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def native_tool_registrations(path: Path = SCHEMA_PATH) -> list[OpenClawToolRegistration]:
    schema = load_tool_schema(path)
    tools = schema.get("tools")
    if not isinstance(tools, list):
        raise ValueError("OpenClaw tool schema must contain a tools array")

    registrations: list[OpenClawToolRegistration] = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("OpenClaw tool entries must be objects")
        name = _require_string(tool, "name")
        registrations.append(
            OpenClawToolRegistration(
                name=name,
                description=_require_string(tool, "description"),
                input_schema=_require_object(tool, "input_schema"),
                output_schema=_require_object(tool, "output_schema"),
            )
        )

    schema_tools = sorted(registration.name for registration in registrations)
    supported = supported_tool_names()
    if schema_tools != supported:
        raise ValueError(f"schema tools do not match Copilot tool handlers: schema={schema_tools}, supported={supported}")
    return registrations


def openclaw_plugin_manifest(
    *,
    schema_path: Path = SCHEMA_PATH,
    plugin_dir: Path = PLUGIN_DIR,
) -> dict[str, Any]:
    schema = load_tool_schema(schema_path)
    registrations = native_tool_registrations(schema_path)
    return {
        "plugin_id": "feishu-memory-copilot",
        "plugin_name": "Feishu Memory Copilot",
        "openclaw_version": schema.get("openclaw_version"),
        "schema_version": schema.get("version"),
        "plugin_dir": str(plugin_dir.relative_to(ROOT)),
        "install_command": f"openclaw plugins install {plugin_dir.relative_to(ROOT)}",
        "enable_command": "openclaw plugins enable feishu-memory-copilot",
        "runtime_boundary": (
            "This registry artifact is ready for OpenClaw native plugin installation; "
            "live Agent tool-list evidence must be read back after the plugin is installed and enabled."
        ),
        "tools": [registration.to_manifest_entry() for registration in registrations],
    }


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value
