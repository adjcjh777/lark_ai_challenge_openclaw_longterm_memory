#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_copilot_admin_production_evidence import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    PLACEHOLDER_MARKERS,
    REQUIRED_SECTIONS,
    SCHEMA_VERSION,
    SECRET_VALUE_MARKERS,
    run_production_evidence_check,
)
from scripts.evidence_patch_merge import EvidenceMergeConfig, format_merge_report, merge_evidence_patches  # noqa: E402

BOUNDARY = (
    "production_evidence_manifest_patch_merger_only; merges external evidence patches and runs the "
    "production evidence gate, but does not create or validate real production systems by itself"
)
TOP_LEVEL_PASSTHROUGH_KEYS = {
    "schema_version",
    "example",
    "generated_at",
    "environment",
    "owner",
    "boundary",
}
MERGE_CONFIG = EvidenceMergeConfig(
    boundary=BOUNDARY,
    schema_version=SCHEMA_VERSION,
    required_sections=REQUIRED_SECTIONS,
    placeholder_markers=PLACEHOLDER_MARKERS,
    secret_value_markers=SECRET_VALUE_MARKERS,
    top_level_passthrough_keys=TOP_LEVEL_PASSTHROUGH_KEYS,
    validation_runner=run_production_evidence_check,
    ready_key="production_ready",
    claim_key="production_ready_claim",
    default_output_name="production-evidence.json",
    incomplete_next_step="Fill every real production evidence section, then rerun with --require-production-ready.",
    extra_base_fields={"environment": "production"},
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge collector production_manifest_patch JSON files into a Copilot Admin production evidence "
            "manifest, then run the existing production evidence gate."
        )
    )
    parser.add_argument(
        "--base-manifest",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Base manifest JSON. Defaults to deploy/copilot-admin.production-evidence.example.json.",
    )
    parser.add_argument(
        "--patch",
        action="append",
        default=[],
        required=True,
        help="Collector output JSON containing production_manifest_patch. Pass multiple times.",
    )
    parser.add_argument("--output", default="", help="Optional merged manifest output path.")
    parser.add_argument(
        "--keep-example",
        action="store_true",
        help="Keep example=true. By default merged manifests are marked example=false.",
    )
    parser.add_argument(
        "--require-production-ready",
        action="store_true",
        help="Return a failing exit code unless the merged manifest passes the production-ready gate.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = merge_production_evidence_patches(
        base_manifest=Path(args.base_manifest).expanduser(),
        patch_paths=[Path(path).expanduser() for path in args.patch],
        output_path=Path(args.output).expanduser() if args.output else None,
        keep_example=args.keep_example,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    if not result["ok"]:
        return 1
    if args.require_production_ready and not result["validation"]["production_ready"]:
        return 1
    return 0


def merge_production_evidence_patches(
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


def _print_text(result: dict[str, Any]) -> None:
    print(
        format_merge_report(
            result,
            title="Copilot Production Evidence Patch Merge",
            claim_key="production_ready_claim",
            ready_label="validation_production_ready",
            ready_key="production_ready",
            blocker_key="production_blockers",
            blocker_name_key="id",
            blocker_reason_key="description",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
