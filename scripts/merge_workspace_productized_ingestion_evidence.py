#!/usr/bin/env python3
"""Merge workspace ingestion evidence patches into a productized manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_workspace_productized_ingestion_readiness import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    PLACEHOLDER_MARKERS,
    REQUIRED_SECTIONS,
    SCHEMA_VERSION,
    SECRET_VALUE_MARKERS,
    run_productized_ingestion_check,
)
from scripts.evidence_patch_merge import EvidenceMergeConfig, format_merge_report, merge_evidence_patches  # noqa: E402

BOUNDARY = (
    "workspace_productized_ingestion_evidence_patch_merger_only; merges redacted evidence patches "
    "and runs the productized workspace ingestion gate, but does not create or prove production evidence"
)
TOP_LEVEL_PASSTHROUGH_KEYS = {
    "schema_version",
    "example",
    "generated_at",
    "boundary",
    "ok",
    "status",
    "production_ready_claim",
    "goal_complete",
    "next_step",
}
MERGE_CONFIG = EvidenceMergeConfig(
    boundary=BOUNDARY,
    schema_version=SCHEMA_VERSION,
    required_sections=REQUIRED_SECTIONS,
    placeholder_markers=PLACEHOLDER_MARKERS,
    secret_value_markers=SECRET_VALUE_MARKERS,
    top_level_passthrough_keys=TOP_LEVEL_PASSTHROUGH_KEYS,
    validation_runner=run_productized_ingestion_check,
    ready_key="goal_complete",
    claim_key="productized_ready_claim",
    default_output_name="workspace-productized-evidence.json",
    incomplete_next_step="Fill every real workspace evidence section, then rerun with --require-productized-ready.",
    temp_prefix="workspace_productized_merge_",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge production_manifest_patch JSON files into a workspace ingestion productized evidence "
            "manifest, then run check_workspace_productized_ingestion_readiness.py semantics."
        )
    )
    parser.add_argument("--base-manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--patch", action="append", default=[], required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--keep-example", action="store_true")
    parser.add_argument("--require-productized-ready", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = merge_workspace_productized_ingestion_evidence_patches(
        base_manifest=Path(args.base_manifest).expanduser(),
        patch_paths=[Path(path).expanduser() for path in args.patch],
        output_path=Path(args.output).expanduser() if args.output else None,
        keep_example=args.keep_example,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    if not result["ok"]:
        return 1
    if args.require_productized_ready and not result["validation"]["goal_complete"]:
        return 1
    return 0


def merge_workspace_productized_ingestion_evidence_patches(
    *,
    base_manifest: Path = DEFAULT_MANIFEST_PATH,
    patch_paths: list[Path],
    output_path: Path | None = None,
    keep_example: bool = False,
) -> dict[str, Any]:
    return merge_evidence_patches(
        config=MERGE_CONFIG,
        base_manifest=base_manifest,
        patch_paths=patch_paths,
        output_path=output_path,
        keep_example=keep_example,
    )


def format_report(result: dict[str, Any]) -> str:
    return format_merge_report(
        result,
        title="Workspace Productized Ingestion Evidence Patch Merge",
        claim_key="productized_ready_claim",
        ready_label="validation_goal_complete",
        ready_key="goal_complete",
        blocker_key="blockers",
        blocker_name_key="check",
        blocker_reason_key="reason",
    )


if __name__ == "__main__":
    raise SystemExit(main())
