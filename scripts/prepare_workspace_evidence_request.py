#!/usr/bin/env python3
"""Prepare a redacted request packet for the remaining workspace evidence.

The packet is for a project owner/operator. It does not call Feishu, create
resources, read cells, or write the memory DB. It only turns the current
blockers into concrete inputs and command templates.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT_ROOT = ROOT / "logs/workspace-evidence-requests"
BOUNDARY = (
    "workspace_evidence_request_packet_only; no Feishu API calls, no resource creation, "
    "no cell reads, no memory DB writes, no full workspace ingestion claim"
)
SAMPLE_DURABLE_FACT = (
    "决定：Workspace ingestion readiness gate must include a reviewed normal Sheet sample "
    "before the goal can be marked complete."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a redacted packet for closing workspace ingestion evidence blockers."
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--create-dirs", action="store_true")
    parser.add_argument("--profile", default="feishu-ai-challenge")
    parser.add_argument("--scope", default="workspace:feishu")
    parser.add_argument("--roles", default="reviewer")
    parser.add_argument("--reviewer-open-id-placeholder", default="<reviewer_open_id>")
    parser.add_argument("--event-log-placeholder", default="<real_event_log.ndjson>")
    parser.add_argument("--sheet-token-placeholder", default="<sheet_token>")
    parser.add_argument("--sheet-title-placeholder", default="<reviewed_title>")
    parser.add_argument("--folder-token-placeholder", default="<folder_token>")
    parser.add_argument("--wiki-space-placeholder", default="<space_id_or_my_library>")
    parser.add_argument("--workspace-resource-placeholder", default="<reviewed_doc_or_sheet_or_bitable>")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    packet = prepare_workspace_evidence_request(
        output_dir=args.output_dir,
        profile=args.profile,
        scope=args.scope,
        roles=args.roles,
        reviewer_open_id_placeholder=args.reviewer_open_id_placeholder,
        event_log_placeholder=args.event_log_placeholder,
        sheet_token_placeholder=args.sheet_token_placeholder,
        sheet_title_placeholder=args.sheet_title_placeholder,
        folder_token_placeholder=args.folder_token_placeholder,
        wiki_space_placeholder=args.wiki_space_placeholder,
        workspace_resource_placeholder=args.workspace_resource_placeholder,
        create_dirs=args.create_dirs,
    )
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(packet))
    return 0


def prepare_workspace_evidence_request(
    *,
    output_dir: Path | None = None,
    profile: str = "feishu-ai-challenge",
    scope: str = "workspace:feishu",
    roles: str = "reviewer",
    reviewer_open_id_placeholder: str = "<reviewer_open_id>",
    event_log_placeholder: str = "<real_event_log.ndjson>",
    sheet_token_placeholder: str = "<sheet_token>",
    sheet_title_placeholder: str = "<reviewed_title>",
    folder_token_placeholder: str = "<folder_token>",
    wiki_space_placeholder: str = "<space_id_or_my_library>",
    workspace_resource_placeholder: str = "<reviewed_doc_or_sheet_or_bitable>",
    create_dirs: bool = False,
) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    packet_dir = (output_dir or DEFAULT_OUTPUT_ROOT / run_id).expanduser()
    paths = {
        "packet_json": str(packet_dir / "workspace-evidence-request.json"),
        "operator_markdown": str(packet_dir / "workspace-evidence-request.md"),
        "sheet_gate_json": str(packet_dir / "01-project-normal-sheet-gate.json"),
        "same_fact_finder_json": str(packet_dir / "02-same-fact-sample-finder.json"),
        "readiness_json": str(packet_dir / "03-workspace-readiness.json"),
    }
    packet = {
        "ok": True,
        "status": "ready_to_request_samples",
        "run_id": run_id,
        "boundary": BOUNDARY,
        "output_dir": str(packet_dir),
        "paths": paths,
        "required_inputs": _required_inputs(),
        "sample_durable_fact": SAMPLE_DURABLE_FACT,
        "commands": _commands(
            profile=profile,
            scope=scope,
            roles=roles,
            reviewer_open_id=reviewer_open_id_placeholder,
            event_log=event_log_placeholder,
            sheet_token=sheet_token_placeholder,
            sheet_title=sheet_title_placeholder,
            folder_token=folder_token_placeholder,
            wiki_space=wiki_space_placeholder,
            workspace_resource=workspace_resource_placeholder,
            paths=paths,
        ),
        "completion_criteria": {
            "project_normal_sheet": [
                "project Sheet gate returns ok=true",
                "eligible_project_normal_sheet_count >= 1",
                "inspection_failure_count == 0",
            ],
            "same_fact_corroboration": [
                "same_fact_match_count >= 1",
                "explicit_resource_fetch_failure_count == 0",
                "strict same-conclusion gate can add workspace evidence to the active memory version",
            ],
            "final_readiness": ["goal_complete=true", "status=pass", "failures=[]"],
        },
        "warnings": [
            "Do not paste raw tokens, chat ids, message ids, user ids, screenshots, or cell contents into Git.",
            "Do not create a controlled test Sheet unless the user explicitly approves it.",
            "If using the controlled sample, send the sample durable fact exactly; weaker process-only wording may be filtered as low memory signal.",
            "A sheet-backed Bitable tab is not a normal Sheet sample.",
            "This packet is a request/preflight artifact, not proof that workspace ingestion is complete.",
        ],
    }
    if create_dirs:
        packet_dir.mkdir(parents=True, exist_ok=True)
        Path(paths["packet_json"]).write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        Path(paths["operator_markdown"]).write_text(format_markdown(packet), encoding="utf-8")
    return packet


def format_report(packet: dict[str, Any]) -> str:
    lines = [
        "Workspace Evidence Request Packet",
        f"status: {packet['status']}",
        f"boundary: {packet['boundary']}",
        f"output_dir: {packet['output_dir']}",
        "",
        "required inputs:",
    ]
    for item in packet["required_inputs"]:
        lines.append(f"  - {item['id']}: {item['description']}")
    lines.append("")
    lines.append("next command:")
    lines.append(packet["commands"]["project_normal_sheet_explicit"])
    return "\n".join(lines)


def format_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Workspace Evidence Request",
        "",
        f"Run ID: `{packet['run_id']}`",
        "",
        "This packet asks for the two missing evidence samples. It does not create Feishu resources, "
        "read Sheet cells, write the memory DB, or prove full workspace ingestion.",
        "",
        "## Required Inputs",
        "",
    ]
    for item in packet["required_inputs"]:
        lines.append(f"- `{item['id']}`: {item['description']}")
    lines.extend(["", "## Commands", ""])
    lines.extend(
        [
            "## Controlled Same-Fact Sample",
            "",
            "If the owner approves a controlled test sample, put this exact durable fact in both the normal Sheet row and one real Feishu group message:",
            "",
            "```text",
            packet["sample_durable_fact"],
            "```",
            "",
        ]
    )
    for name, command in packet["commands"].items():
        lines.extend([f"### {name}", "", "```bash", command, "```", ""])
    lines.extend(["## Completion Criteria", ""])
    for name, criteria in packet["completion_criteria"].items():
        lines.append(f"### {name}")
        for criterion in criteria:
            lines.append(f"- {criterion}")
        lines.append("")
    lines.extend(["## Warnings", ""])
    for warning in packet["warnings"]:
        lines.append(f"- {warning}")
    lines.append("")
    return "\n".join(lines)


def _required_inputs() -> list[dict[str, str]]:
    return [
        {
            "id": "project_or_enterprise_normal_sheet",
            "description": "One normal Sheet token, or a Drive folder/Wiki space containing one. Sheet-backed Bitable is not enough.",
        },
        {
            "id": "real_same_fact_chat_sample",
            "description": "One real Feishu chat event log containing a durable fact repeated in a reviewed doc, Sheet, or Base source.",
        },
        {
            "id": "reviewer_actor",
            "description": "A reviewer/owner actor id allowed to run candidate-only gates.",
        },
    ]


def _commands(
    *,
    profile: str,
    scope: str,
    roles: str,
    reviewer_open_id: str,
    event_log: str,
    sheet_token: str,
    sheet_title: str,
    folder_token: str,
    wiki_space: str,
    workspace_resource: str,
    paths: dict[str, str],
) -> dict[str, str]:
    sheet_spec = f"sheet:{sheet_token}:{sheet_title}"
    return {
        "project_normal_sheet_explicit": " \\\n  ".join(
            [
                "python3 scripts/check_workspace_project_sheet_evidence_gate.py",
                "--json",
                f"--profile {profile}",
                f"--resource '{sheet_spec}'",
                f"> {paths['sheet_gate_json']}",
            ]
        ),
        "project_normal_sheet_folder_or_wiki": " \\\n  ".join(
            [
                "python3 scripts/check_workspace_project_sheet_evidence_gate.py",
                "--json",
                f"--profile {profile}",
                f"--folder-walk-tokens '{folder_token}'",
                f"--wiki-space-walk-ids '{wiki_space}'",
                "--walk-max-depth 2",
                "--limit 50",
                f"> {paths['sheet_gate_json']}",
            ]
        ),
        "same_fact_sample_finder": " \\\n  ".join(
            [
                "python3 scripts/check_workspace_real_same_conclusion_sample_finder.py",
                "--json",
                f"--event-log '{event_log}'",
                f"--resource '{workspace_resource}'",
                f"--resource '{sheet_spec}'",
                f"--actor-open-id '{reviewer_open_id}'",
                f"--roles {roles}",
                f"--scope {scope}",
                "--max-bitable-records 3",
                "--max-sheet-rows 20",
                f"> {paths['same_fact_finder_json']}",
            ]
        ),
        "final_readiness": " \\\n  ".join(
            [
                "python3 scripts/check_workspace_ingestion_goal_readiness.py",
                "--json",
                f"--event-log '{event_log}'",
                f"--resource '{workspace_resource}'",
                f"--resource '{sheet_spec}'",
                f"--actor-open-id '{reviewer_open_id}'",
                f"--roles {roles}",
                f"--scope {scope}",
                "--max-bitable-records 3",
                "--max-sheet-rows 20",
                f"> {paths['readiness_json']}",
            ]
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
