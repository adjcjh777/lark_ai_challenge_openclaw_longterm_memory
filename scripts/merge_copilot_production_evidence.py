#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_copilot_admin_production_evidence import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    REQUIRED_SECTIONS,
    SCHEMA_VERSION,
    run_production_evidence_check,
)

BOUNDARY = (
    "production_evidence_manifest_patch_merger_only; merges external evidence patches and runs the "
    "production evidence gate, but does not create or validate real production systems by itself"
)
PLACEHOLDER_MARKERS = ("__FILL", "__CHANGE_ME", "example.com", "localhost", "127.0.0.1")
SECRET_VALUE_MARKERS = ("app_secret=", "access_token=", "refresh_token=", "Bearer ", "sk-", "rightcode_")
TOP_LEVEL_PASSTHROUGH_KEYS = {
    "schema_version",
    "example",
    "generated_at",
    "environment",
    "owner",
    "boundary",
}


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
    errors: list[dict[str, Any]] = []
    base_payload = _load_json_file(base_manifest)
    if not base_payload["ok"]:
        return _failed_result(
            errors=[base_payload],
            output_path=output_path,
            merged_sections=[],
            validation=None,
            manifest=None,
        )
    manifest = base_payload["data"]
    if not isinstance(manifest, dict):
        return _failed_result(
            errors=[{"ok": False, "path": str(base_manifest), "error": "base_manifest_must_be_json_object"}],
            output_path=output_path,
            merged_sections=[],
            validation=None,
            manifest=None,
        )
    merged = _normalize_base_manifest(manifest, keep_example=keep_example)
    merged_sections: list[str] = []
    patch_summaries: list[dict[str, Any]] = []

    for patch_path in patch_paths:
        loaded = _load_json_file(patch_path)
        if not loaded["ok"]:
            errors.append(loaded)
            continue
        patch = _extract_patch(loaded["data"], patch_path)
        if not patch["ok"]:
            errors.append(patch)
            continue
        section_names = sorted(patch["patch"].keys())
        merged_sections.extend(section_names)
        patch_summaries.append({"path": str(patch_path.resolve()), "sections": section_names})
        for section, values in patch["patch"].items():
            merged[section] = {**_section_dict(merged.get(section)), **values}

    if errors:
        return _failed_result(
            errors=errors,
            output_path=output_path,
            merged_sections=sorted(set(merged_sections)),
            validation=None,
            manifest=None,
        )

    validation = _validate_manifest_payload(merged)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        validation = run_production_evidence_check(output_path)

    return {
        "ok": True,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "base_manifest": str(base_manifest.resolve()),
        "output_path": str(output_path.resolve()) if output_path else "",
        "merged_sections": sorted(set(merged_sections)),
        "patches": patch_summaries,
        "validation": validation,
        "manifest": merged,
        "next_step": ""
        if validation["production_ready"]
        else "Fill every real production evidence section, then rerun with --require-production-ready.",
    }


def _normalize_base_manifest(manifest: dict[str, Any], *, keep_example: bool) -> dict[str, Any]:
    merged = deepcopy(manifest)
    merged["schema_version"] = SCHEMA_VERSION
    merged["example"] = bool(keep_example)
    merged["generated_at"] = datetime.now(timezone.utc).isoformat()
    merged.setdefault("environment", "production")
    merged["boundary"] = BOUNDARY
    for section in REQUIRED_SECTIONS:
        merged.setdefault(section, {})
    return merged


def _extract_patch(payload: Any, patch_path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "path": str(patch_path), "error": "patch_file_must_be_json_object"}
    patch = payload.get("production_manifest_patch")
    if patch is None:
        patch = {
            key: value
            for key, value in payload.items()
            if key in REQUIRED_SECTIONS or key not in TOP_LEVEL_PASSTHROUGH_KEYS
        }
    if not isinstance(patch, dict) or not patch:
        return {"ok": False, "path": str(patch_path), "error": "production_manifest_patch_missing_or_empty"}
    unknown = sorted(key for key in patch if key not in REQUIRED_SECTIONS)
    if unknown:
        return {"ok": False, "path": str(patch_path), "error": "unknown_manifest_sections", "sections": unknown}
    non_object = sorted(key for key, value in patch.items() if not isinstance(value, dict))
    if non_object:
        return {
            "ok": False,
            "path": str(patch_path),
            "error": "section_patch_must_be_json_object",
            "sections": non_object,
        }
    unsafe_values = sorted({value for value in _flatten_strings(patch) if _contains_unsafe_value(value)})
    if unsafe_values:
        return {
            "ok": False,
            "path": str(patch_path),
            "error": "patch_contains_placeholder_or_secret_like_value",
            "unsafe_value_count": len(unsafe_values),
        }
    return {"ok": True, "path": str(patch_path), "patch": deepcopy(patch)}


def _validate_manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "production-evidence.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return run_production_evidence_check(manifest_path)


def _load_json_file(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists():
        return {"ok": False, "path": str(resolved), "error": "file_missing"}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "path": str(resolved), "error": "invalid_json", "detail": str(exc)}
    return {"ok": True, "path": str(resolved), "data": payload}


def _section_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_flatten_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_flatten_strings(item))
        return strings
    return []


def _contains_unsafe_value(value: str) -> bool:
    return any(marker in value for marker in (*PLACEHOLDER_MARKERS, *SECRET_VALUE_MARKERS))


def _failed_result(
    *,
    errors: list[dict[str, Any]],
    output_path: Path | None,
    merged_sections: list[str],
    validation: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "production_ready_claim": False,
        "boundary": BOUNDARY,
        "output_path": str(output_path.resolve()) if output_path else "",
        "merged_sections": merged_sections,
        "errors": errors,
        "validation": validation,
        "manifest": manifest,
        "next_step": "Fix patch JSON, remove placeholders/secrets, and rerun the merge.",
    }


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Production Evidence Patch Merge")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"production_ready_claim: {str(result['production_ready_claim']).lower()}")
    print(f"boundary: {result['boundary']}")
    print(f"merged_sections: {', '.join(result.get('merged_sections') or [])}")
    validation = result.get("validation") or {}
    if validation:
        print(f"validation_production_ready: {str(validation.get('production_ready')).lower()}")
        if validation.get("production_blockers"):
            print("production_blockers:")
            for blocker in validation["production_blockers"]:
                print(f"- {blocker['id']}: {blocker['description']}")
    if result.get("errors"):
        print("errors:")
        for error in result["errors"]:
            print(f"- {error.get('path', '<unknown>')}: {error.get('error')}")


if __name__ == "__main__":
    raise SystemExit(main())
