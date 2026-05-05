#!/usr/bin/env python3
"""Check whether this checkout is ready for cross-platform quick deployment.

The check is intentionally local and conservative: it verifies that a macOS,
Linux, or Windows host can run the demo/pre-production path from this checkout.
It does not prove production deployment, full Feishu workspace ingestion, or
long-running productized live service readiness.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / "agent_adapters" / "openclaw" / "openclaw-version.lock"
BOUNDARY = (
    "cross_platform_quick_deploy_preflight_only; validates demo/pre-production host readiness "
    "for macOS/Linux/Windows; does not prove production deployment, full Feishu workspace ingestion, "
    "stable long-running Feishu routing, or productized live completion"
)
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:0.6b-fp16"
SUPPORTED_PLATFORMS = {"darwin": "macOS", "linux": "Linux", "win32": "Windows", "cygwin": "Windows", "msys": "Windows"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--profile",
        choices=("local-demo", "openclaw-staging", "embedding"),
        default="local-demo",
        help=(
            "local-demo checks the fastest local replay path; openclaw-staging requires the locked OpenClaw CLI; "
            "embedding additionally requires Ollama to be installed."
        ),
    )
    args = parser.parse_args()

    report = run_preflight(profile=args.profile)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


def run_preflight(
    *,
    profile: str = "local-demo",
    sys_platform: str | None = None,
    python_version: tuple[int, int, int] | None = None,
    command_runner: Callable[[list[str]], dict[str, Any]] | None = None,
    command_exists: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    sys_platform = sys_platform or sys.platform
    python_version = python_version or (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    command_runner = command_runner or run_command
    command_exists = command_exists or command_available

    locked_openclaw = read_locked_openclaw_version()
    checks = [
        check_supported_platform(sys_platform),
        check_python_version(python_version),
        check_python_modules(),
        check_command("git", command_exists=command_exists, required=True),
        check_repo_layout(),
        check_pip(command_runner=command_runner),
        check_openclaw(
            locked_openclaw,
            command_runner=command_runner,
            command_exists=command_exists,
            required=profile in {"openclaw-staging", "embedding"},
        ),
        check_node_for_openclaw(command_exists=command_exists, required=profile in {"openclaw-staging", "embedding"}),
        check_ollama(command_exists=command_exists, command_runner=command_runner, required=profile == "embedding"),
    ]

    failures = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warning"]
    return {
        "ok": not failures,
        "profile": profile,
        "platform": platform_label(sys_platform),
        "boundary": BOUNDARY,
        "locked_openclaw_version": locked_openclaw,
        "checks": checks,
        "summary": {"fail": len(failures), "warning": len(warnings), "pass": count_status(checks, "pass")},
        "next_commands": build_next_commands(sys_platform, locked_openclaw),
    }


def check_supported_platform(sys_platform: str) -> dict[str, Any]:
    label = platform_label(sys_platform)
    if label == "unsupported":
        return {
            "name": "supported_platform",
            "status": "fail",
            "detail": f"unsupported platform: {sys_platform}; expected macOS, Linux, or Windows",
        }
    return {"name": "supported_platform", "status": "pass", "detail": label}


def check_python_version(version: tuple[int, int, int]) -> dict[str, Any]:
    major, minor, micro = version
    if (major, minor) >= (3, 11):
        return {"name": "python_version", "status": "pass", "detail": f"{major}.{minor}.{micro}"}
    if major == 3 and minor >= 9:
        return {
            "name": "python_version",
            "status": "warning",
            "detail": f"{major}.{minor}.{micro}; pyproject allows >=3.9, but quick deploy recommends Python 3.11+",
        }
    return {"name": "python_version", "status": "fail", "detail": f"{major}.{minor}.{micro}; Python 3.9+ required"}


def check_python_modules() -> dict[str, Any]:
    missing = []
    for module_name in ("venv", "sqlite3"):
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)
    if missing:
        return {"name": "python_stdlib_modules", "status": "fail", "detail": {"missing": missing}}
    return {"name": "python_stdlib_modules", "status": "pass", "detail": {"required": ["venv", "sqlite3"]}}


def check_command(name: str, *, command_exists: Callable[[str], bool], required: bool) -> dict[str, Any]:
    exists = command_exists(name)
    if exists:
        return {"name": f"{name}_command", "status": "pass", "detail": "available"}
    return {
        "name": f"{name}_command",
        "status": "fail" if required else "warning",
        "detail": f"{name} is not available on PATH",
    }


def check_repo_layout() -> dict[str, Any]:
    required_paths = [
        "pyproject.toml",
        ".env.example",
        "README.md",
        "memory_engine/copilot/service.py",
        "agent_adapters/openclaw/memory_tools.schema.json",
        "scripts/check_demo_readiness.py",
    ]
    missing = [path for path in required_paths if not (ROOT / path).exists()]
    if missing:
        return {"name": "repo_layout", "status": "fail", "detail": {"missing": missing}}
    return {"name": "repo_layout", "status": "pass", "detail": {"required_paths": required_paths}}


def check_pip(*, command_runner: Callable[[list[str]], dict[str, Any]]) -> dict[str, Any]:
    result = command_runner([sys.executable, "-m", "pip", "--version"])
    if result["returncode"] != 0:
        return {"name": "pip", "status": "fail", "detail": command_failure_detail(result)}
    return {"name": "pip", "status": "pass", "detail": result["stdout"].splitlines()[0] if result["stdout"] else "available"}


def check_openclaw(
    locked_version: str,
    *,
    command_runner: Callable[[list[str]], dict[str, Any]],
    command_exists: Callable[[str], bool],
    required: bool,
) -> dict[str, Any]:
    if not command_exists("openclaw"):
        return {
            "name": "openclaw_locked_version",
            "status": "fail" if required else "warning",
            "detail": f"openclaw CLI not found; install with: npm i -g openclaw@{locked_version} --no-fund --no-audit",
        }
    result = command_runner(["openclaw", "--version"])
    if result["returncode"] != 0:
        return {"name": "openclaw_locked_version", "status": "fail", "detail": command_failure_detail(result)}
    local_version = parse_openclaw_version(result["stdout"])
    if local_version != locked_version:
        return {
            "name": "openclaw_locked_version",
            "status": "fail",
            "detail": f"local={local_version or 'unparsed'}, locked={locked_version}",
        }
    return {"name": "openclaw_locked_version", "status": "pass", "detail": f"OpenClaw {local_version}"}


def check_node_for_openclaw(*, command_exists: Callable[[str], bool], required: bool) -> dict[str, Any]:
    missing = [name for name in ("node", "npm") if not command_exists(name)]
    if not missing:
        return {"name": "node_npm", "status": "pass", "detail": "node and npm available"}
    return {
        "name": "node_npm",
        "status": "fail" if required else "warning",
        "detail": {"missing": missing, "why": "required to install and run the OpenClaw plugin path"},
    }


def check_ollama(
    *,
    command_exists: Callable[[str], bool],
    command_runner: Callable[[list[str]], dict[str, Any]],
    required: bool,
) -> dict[str, Any]:
    if command_exists("ollama"):
        if not required:
            return {"name": "ollama", "status": "pass", "detail": "available"}
        result = command_runner(["ollama", "list"])
        if result["returncode"] != 0:
            return {"name": "ollama", "status": "fail", "detail": command_failure_detail(result)}
        if DEFAULT_EMBEDDING_MODEL not in result["stdout"]:
            return {
                "name": "ollama",
                "status": "fail",
                "detail": f"ollama is installed, but {DEFAULT_EMBEDDING_MODEL} is not present; run the platform setup script",
            }
        return {"name": "ollama", "status": "pass", "detail": f"{DEFAULT_EMBEDDING_MODEL} available"}
    return {
        "name": "ollama",
        "status": "fail" if required else "warning",
        "detail": "ollama is optional for local-demo; required only for real embedding gate",
    }


def read_locked_openclaw_version() -> str:
    try:
        return LOCK_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "2026.4.24"


def parse_openclaw_version(output: str) -> str | None:
    match = re.search(r"OpenClaw\s+([0-9]{4}\.[0-9]+\.[0-9]+)", output)
    return match.group(1) if match else None


def platform_label(sys_platform: str) -> str:
    if sys_platform.startswith("linux"):
        return "Linux"
    return SUPPORTED_PLATFORMS.get(sys_platform, "unsupported")


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
    except Exception as exc:  # pragma: no cover - production diagnostic path
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def command_failure_detail(result: dict[str, Any]) -> str:
    return str(result.get("stderr") or result.get("stdout") or f"returncode={result.get('returncode')}")


def count_status(checks: list[dict[str, Any]], status: str) -> int:
    return sum(1 for check in checks if check["status"] == status)


def build_next_commands(sys_platform: str, locked_openclaw: str) -> dict[str, list[str]]:
    if platform_label(sys_platform) == "Windows":
        return {
            "install_prerequisites": [
                "winget install --id Python.Python.3.11 --exact",
                "winget install --id Git.Git --exact",
                "winget install --id OpenJS.NodeJS --exact",
                f"npm i -g openclaw@{locked_openclaw} --no-fund --no-audit",
            ],
            "setup_repo": [
                "py -3.11 -m venv .venv",
                ".\\.venv\\Scripts\\Activate.ps1",
                "python -m pip install -U pip",
                "pip install -e .",
                "python -m memory_engine init-db",
            ],
            "verify": [
                "python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json",
                "python scripts/check_demo_readiness.py --json",
            ],
        }
    python_cmd = "python3"
    return {
        "install_prerequisites": [
            "Install Python 3.11+, Git, Node.js/npm, and OpenClaw without changing the project lock.",
            f"npm i -g openclaw@{locked_openclaw} --no-fund --no-audit",
        ],
        "setup_repo": [
            f"{python_cmd} -m venv .venv",
            "source .venv/bin/activate",
            "python -m pip install -U pip",
            "pip install -e .",
            "python -m memory_engine init-db",
        ],
        "verify": [
            "python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json",
            "python scripts/check_demo_readiness.py --json",
        ],
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"Cross-platform quick deploy preflight: {'PASS' if report['ok'] else 'FAIL'}",
        f"Profile: {report['profile']}",
        f"Platform: {report['platform']}",
        f"Boundary: {report['boundary']}",
    ]
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status'].upper()} ({check['detail']})")
    lines.append("Next verify commands:")
    for command in report["next_commands"]["verify"]:
        lines.append(f"  {command}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
