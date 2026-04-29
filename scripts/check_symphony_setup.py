"""Validate repo-owned Symphony setup files.

The Symphony runtime lives outside this repository. This check only verifies
the repository contract Symphony will consume: WORKFLOW.md, env template, and
runbook pointers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LINEAR_PROJECT_SLUG = "feishu-ai-challenge-785b3bb0a19d"

WORKFLOW_REQUIRED_TERMS = (
    "tracker:",
    "kind: linear",
    "api_key: $LINEAR_API_KEY",
    f"project_slug: {LINEAR_PROJECT_SLUG}",
    "workspace:",
    "root: $SYMPHONY_WORKSPACE_ROOT",
    "git clone --depth 1 \"$SOURCE_REPO_URL\" .",
    "adjcjh777/lark_ai_challenge_openclaw_longterm_memory",
    "codex",
    "app-server",
    "handle_tool_request()",
    "CopilotService",
    "current_context.permission",
    "python3 scripts/check_openclaw_version.py",
    "python3 scripts/check_agent_harness.py",
    "python3 scripts/check_symphony_setup.py",
)

ENV_REQUIRED_TERMS = (
    "LINEAR_API_KEY=",
    "SYMPHONY_LINEAR_PROJECT_SLUG=",
    "SYMPHONY_WORKSPACE_ROOT=",
    "SOURCE_REPO_URL=",
    "CODEX_BIN=",
)

RUNBOOK_REQUIRED_TERMS = (
    "https://github.com/openai/symphony/blob/main/elixir/README.md",
    "https://github.com/openai/symphony/blob/main/SPEC.md",
    "mise exec -- ./bin/symphony",
    "WORKFLOW.md",
    "LINEAR_API_KEY",
    LINEAR_PROJECT_SLUG,
)


def main() -> int:
    failures: list[str] = []
    _check_required_files(failures)
    _check_workflow(failures)
    _check_env_example(failures)
    _check_runbook(failures)

    report: dict[str, Any] = {
        "ok": not failures,
        "checks": {
            "required_files": "pass" if not any(item.startswith("missing") for item in failures) else "fail",
            "workflow": "pass" if not any(item.startswith("WORKFLOW.md") for item in failures) else "fail",
            "env_example": "pass" if not any(item.startswith(".env.example") for item in failures) else "fail",
            "runbook": "pass" if not any(item.startswith("runbook") for item in failures) else "fail",
        },
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def _check_required_files(failures: list[str]) -> None:
    for relative in (
        "WORKFLOW.md",
        "docs/reference/symphony-setup.md",
        "scripts/check_symphony_setup.py",
        "tests/test_symphony_setup.py",
    ):
        if not (ROOT / relative).exists():
            failures.append(f"missing required Symphony setup file: {relative}")


def _check_workflow(failures: list[str]) -> None:
    workflow_path = ROOT / "WORKFLOW.md"
    if not workflow_path.exists():
        return
    text = workflow_path.read_text(encoding="utf-8")

    if not text.startswith("---\n"):
        failures.append("WORKFLOW.md must start with YAML front matter")
    if text.count("---") < 2:
        failures.append("WORKFLOW.md must include YAML front matter and prompt body")

    for term in WORKFLOW_REQUIRED_TERMS:
        if term not in text:
            failures.append(f"WORKFLOW.md missing required term: {term}")


def _check_env_example(failures: list[str]) -> None:
    env_path = ROOT / ".env.example"
    if not env_path.exists():
        failures.append("missing required Symphony setup file: .env.example")
        return
    text = env_path.read_text(encoding="utf-8")
    for term in ENV_REQUIRED_TERMS:
        if term not in text:
            failures.append(f".env.example missing required term: {term}")


def _check_runbook(failures: list[str]) -> None:
    runbook_path = ROOT / "docs" / "reference" / "symphony-setup.md"
    if not runbook_path.exists():
        return
    text = runbook_path.read_text(encoding="utf-8")
    for term in RUNBOOK_REQUIRED_TERMS:
        if term not in text:
            failures.append(f"runbook missing required term: {term}")


if __name__ == "__main__":
    raise SystemExit(main())
