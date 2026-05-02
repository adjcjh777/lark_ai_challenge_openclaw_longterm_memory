#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ARTIFACTS = {
    "admin": Path("memory_engine/copilot/admin.py"),
    "static_site": Path("memory_engine/copilot/knowledge_site.py"),
}

REQUIRED_PATTERNS = {
    "admin": (
        'data-design-system="copilot-admin-ui/v1"',
        "--surface-muted",
        "--surface-tint",
        "--radius-control",
        "--radius-panel",
        "--space-2",
        "--space-3",
        "--space-4",
        "--warning-surface",
        "--info-surface",
    ),
    "static_site": (
        'data-design-system="copilot-static-knowledge-site/v1"',
        "--panel-muted",
        "--radius-control",
        "--radius-panel",
        "--space-2",
        "--space-3",
        "--space-4",
        "--warning-surface",
        "--info-surface",
    ),
}

RETIRED_PALETTE_VALUES = (
    "#fffdf8",
    "#fffaf0",
    "#fbfaf5",
    "#f4f0e8",
    "#f0eadf",
    "#f6f4ed",
    "#eef1ed",
    "#17201d",
    "#18201d",
    "#355c4b",
    "#9d5d3f",
    "#2f5f89",
    "#b2872d",
    "#d8c8aa",
    "#d7c7af",
    "#bfb5a4",
)


@dataclass(frozen=True)
class ArtifactCheck:
    name: str
    path: Path
    status: str
    missing_patterns: list[str]
    retired_palette_hits: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": str(self.path),
            "missing_patterns": self.missing_patterns,
            "retired_palette_hits": self.retired_palette_hits,
        }


def run_design_system_check(*, root: Path = ROOT) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failed: list[str] = []
    for name, relative_path in ARTIFACTS.items():
        check = _check_artifact(name, root / relative_path)
        checks[name] = check.to_dict()
        if check.status != "pass":
            failed.append(name)
    return {
        "ok": not failed,
        "boundary": (
            "local/staging admin UI design-system token check only; "
            "not production deployment or human-approved visual baseline evidence"
        ),
        "checks": checks,
        "failed_checks": failed,
        "retired_palette_values": list(RETIRED_PALETTE_VALUES),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin Design System Check",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        "checks:",
    ]
    for name, check in sorted(report["checks"].items()):
        lines.append(f"- {name}: {check['status']}")
        if check["missing_patterns"]:
            lines.append(f"  missing: {', '.join(check['missing_patterns'])}")
        if check["retired_palette_hits"]:
            lines.append(f"  retired_palette_hits: {', '.join(check['retired_palette_hits'])}")
    return "\n".join(lines)


def _check_artifact(name: str, path: Path) -> ArtifactCheck:
    if not path.exists():
        return ArtifactCheck(
            name=name,
            path=path,
            status="fail",
            missing_patterns=["file_exists"],
            retired_palette_hits=[],
        )
    text = path.read_text(encoding="utf-8")
    missing = [pattern for pattern in REQUIRED_PATTERNS[name] if pattern not in text]
    retired_hits = [value for value in RETIRED_PALETTE_VALUES if value.lower() in text.lower()]
    return ArtifactCheck(
        name=name,
        path=path,
        status="pass" if not missing and not retired_hits else "fail",
        missing_patterns=missing,
        retired_palette_hits=retired_hits,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Copilot Admin and static site design-system tokens.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()
    report = run_design_system_check()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
