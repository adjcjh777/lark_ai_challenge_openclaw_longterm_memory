"""Check the repo-level agent harness contracts.

This script intentionally checks structure, not business behavior. Business
behavior remains covered by Copilot unit tests, benchmarks, and healthchecks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

MAX_AGENTS_LINES = 180
REQUIRED_AGENTS_POINTERS = (
    "docs/harness/README.md",
    "docs/productization/agent-execution-contract.md",
    "docs/productization/full-copilot-next-execution-doc.md",
    "docs/productization/prd-completion-audit-and-gap-tasks.md",
)
REQUIRED_HARNESS_FILES = (
    "docs/harness/README.md",
    "docs/harness/QUALITY_SCORE.md",
    "docs/harness/TECH_DEBT_GARBAGE_COLLECTION.md",
    "docs/productization/agent-execution-contract.md",
)
REQUIRED_CONTRACT_TERMS = (
    "handle_tool_request()",
    "CopilotService",
    "current_context.permission",
    "fail closed",
    "candidate",
    "2026.4.24",
    "python3 scripts/check_openclaw_version.py",
    "python3 scripts/check_agent_harness.py",
)
COGNEE_ALLOWED_IMPORT_FILES = {
    Path("memory_engine/copilot/cognee_adapter.py"),
    Path("scripts/check_agent_harness.py"),
    Path("scripts/spike_cognee_local.py"),
    Path("tests/test_copilot_cognee_adapter.py"),
}


def main() -> int:
    failures: list[str] = []

    _check_agents_map(failures)
    _check_required_docs(failures)
    _check_execution_contract(failures)
    _check_openclaw_lock_consistency(failures)
    _check_cognee_adapter_boundary(failures)

    report: dict[str, Any] = {
        "ok": not failures,
        "checks": {
            "agents_map": "pass" if not any(item.startswith("AGENTS.md") for item in failures) else "fail",
            "required_docs": "pass" if not any(item.startswith("missing required") for item in failures) else "fail",
            "execution_contract": "pass" if not any(item.startswith("execution contract") for item in failures) else "fail",
            "openclaw_lock": "pass" if not any(item.startswith("OpenClaw") for item in failures) else "fail",
            "cognee_adapter_boundary": "pass" if not any(item.startswith("Cognee") for item in failures) else "fail",
        },
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def _check_agents_map(failures: list[str]) -> None:
    agents_path = ROOT / "AGENTS.md"
    if not agents_path.exists():
        failures.append("AGENTS.md is missing")
        return

    text = agents_path.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > MAX_AGENTS_LINES:
        failures.append(f"AGENTS.md has {line_count} lines; expected <= {MAX_AGENTS_LINES}")

    for pointer in REQUIRED_AGENTS_POINTERS:
        if pointer not in text:
            failures.append(f"AGENTS.md missing pointer: {pointer}")


def _check_required_docs(failures: list[str]) -> None:
    for relative in REQUIRED_HARNESS_FILES:
        if not (ROOT / relative).exists():
            failures.append(f"missing required harness artifact: {relative}")


def _check_execution_contract(failures: list[str]) -> None:
    path = ROOT / "docs" / "productization" / "agent-execution-contract.md"
    if not path.exists():
        failures.append("execution contract missing: docs/productization/agent-execution-contract.md")
        return

    text = path.read_text(encoding="utf-8")
    for term in REQUIRED_CONTRACT_TERMS:
        if term not in text:
            failures.append(f"execution contract missing required term: {term}")


def _check_openclaw_lock_consistency(failures: list[str]) -> None:
    lock_file = ROOT / "agent_adapters" / "openclaw" / "openclaw-version.lock"
    package_file = ROOT / "agent_adapters" / "openclaw" / "plugin" / "package.json"
    contract_file = ROOT / "docs" / "productization" / "agent-execution-contract.md"

    if not lock_file.exists():
        failures.append("OpenClaw lock missing: agent_adapters/openclaw/openclaw-version.lock")
        return
    locked = lock_file.read_text(encoding="utf-8").strip()
    if locked != "2026.4.24":
        failures.append(f"OpenClaw lock expected 2026.4.24, got {locked}")

    if package_file.exists():
        package = json.loads(package_file.read_text(encoding="utf-8"))
        package_version = package.get("engines", {}).get("openclaw")
        if package_version != locked:
            failures.append(f"OpenClaw plugin engine mismatch: package={package_version}, lock={locked}")
    else:
        failures.append("OpenClaw plugin package missing: agent_adapters/openclaw/plugin/package.json")

    if contract_file.exists() and locked not in contract_file.read_text(encoding="utf-8"):
        failures.append(f"OpenClaw lock {locked} missing from agent execution contract")


def _check_cognee_adapter_boundary(failures: list[str]) -> None:
    for path in _python_files(("memory_engine", "scripts", "tests")):
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        if "import cognee" not in text and "from cognee" not in text:
            continue
        if relative not in COGNEE_ALLOWED_IMPORT_FILES:
            failures.append(f"Cognee import must stay behind adapter boundary: {relative}")


def _python_files(directories: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        root = ROOT / directory
        if root.exists():
            files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


if __name__ == "__main__":
    raise SystemExit(main())
