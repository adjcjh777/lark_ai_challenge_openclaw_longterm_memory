from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ValidationRunner = Callable[[Path], dict[str, Any]]


@dataclass(frozen=True)
class EvidenceMergeConfig:
    boundary: str
    schema_version: str
    required_sections: tuple[str, ...]
    placeholder_markers: tuple[str, ...]
    secret_value_markers: tuple[str, ...]
    top_level_passthrough_keys: set[str]
    validation_runner: ValidationRunner
    ready_key: str
    claim_key: str
    default_output_name: str
    incomplete_next_step: str
    temp_prefix: str = "evidence_patch_merge_"
    extra_base_fields: dict[str, Any] = field(default_factory=dict)


def merge_evidence_patches(
    *,
    config: EvidenceMergeConfig,
    base_manifest: Path,
    patch_paths: list[Path],
    output_path: Path | None = None,
    keep_example: bool = False,
) -> dict[str, Any]:
    base_payload = load_json_file(base_manifest)
    if not base_payload["ok"]:
        return failed_result(config=config, errors=[base_payload], output_path=output_path, merged_sections=[])

    manifest = base_payload["data"]
    if not isinstance(manifest, dict):
        return failed_result(
            config=config,
            errors=[{"ok": False, "path": str(base_manifest), "error": "base_manifest_must_be_json_object"}],
            output_path=output_path,
            merged_sections=[],
        )

    merged = normalize_base_manifest(config=config, manifest=manifest, keep_example=keep_example)
    errors: list[dict[str, Any]] = []
    merged_sections: list[str] = []
    patch_summaries: list[dict[str, Any]] = []

    for patch_path in patch_paths:
        loaded = load_json_file(patch_path)
        if not loaded["ok"]:
            errors.append(loaded)
            continue
        patch = extract_patch(config=config, payload=loaded["data"], patch_path=patch_path)
        if not patch["ok"]:
            errors.append(patch)
            continue
        sections = sorted(patch["patch"].keys())
        merged_sections.extend(sections)
        patch_summaries.append({"path": str(patch_path.resolve()), "sections": sections})
        for section, values in patch["patch"].items():
            merged[section] = {**section_dict(merged.get(section)), **values}

    if errors:
        return failed_result(
            config=config,
            errors=errors,
            output_path=output_path,
            merged_sections=sorted(set(merged_sections)),
        )

    validation = validate_manifest_payload(config=config, manifest=merged)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        validation = config.validation_runner(output_path)

    return {
        "ok": True,
        config.claim_key: False,
        "boundary": config.boundary,
        "base_manifest": str(base_manifest.resolve()),
        "output_path": str(output_path.resolve()) if output_path else "",
        "merged_sections": sorted(set(merged_sections)),
        "patches": patch_summaries,
        "validation": validation,
        "manifest": merged,
        "next_step": "" if validation[config.ready_key] else config.incomplete_next_step,
    }


def format_merge_report(
    result: dict[str, Any],
    *,
    title: str,
    claim_key: str,
    ready_label: str,
    ready_key: str,
    blocker_key: str,
    blocker_name_key: str,
    blocker_reason_key: str,
) -> str:
    lines = [
        title,
        f"ok: {str(result['ok']).lower()}",
        f"{claim_key}: {str(result.get(claim_key, False)).lower()}",
        f"boundary: {result['boundary']}",
        f"merged_sections: {', '.join(result.get('merged_sections') or [])}",
    ]
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    if validation:
        lines.append(f"{ready_label}: {str(validation.get(ready_key)).lower()}")
        if validation.get(blocker_key):
            lines.append(f"{blocker_key}:")
            for blocker in validation[blocker_key]:
                lines.append(
                    f"- {blocker.get(blocker_name_key, '<unknown>')}: "
                    f"{blocker.get(blocker_reason_key, '<unknown>')}"
                )
    if result.get("errors"):
        lines.append("errors:")
        for error in result["errors"]:
            lines.append(f"- {error.get('path', '<unknown>')}: {error.get('error')}")
    if result.get("next_step"):
        lines.append(f"next_step: {result['next_step']}")
    return "\n".join(lines)


def normalize_base_manifest(
    *, config: EvidenceMergeConfig, manifest: dict[str, Any], keep_example: bool
) -> dict[str, Any]:
    merged = deepcopy(manifest)
    merged["schema_version"] = config.schema_version
    merged["example"] = bool(keep_example)
    merged["generated_at"] = datetime.now(timezone.utc).isoformat()
    merged["boundary"] = config.boundary
    for key, value in config.extra_base_fields.items():
        merged.setdefault(key, value)
    for section in config.required_sections:
        merged.setdefault(section, {})
    return merged


def extract_patch(*, config: EvidenceMergeConfig, payload: Any, patch_path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "path": str(patch_path), "error": "patch_file_must_be_json_object"}
    patch = payload.get("production_manifest_patch")
    if patch is None:
        patch = {
            key: value
            for key, value in payload.items()
            if key in config.required_sections or key not in config.top_level_passthrough_keys
        }
    if not isinstance(patch, dict) or not patch:
        return {"ok": False, "path": str(patch_path), "error": "production_manifest_patch_missing_or_empty"}
    unknown = sorted(key for key in patch if key not in config.required_sections)
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
    unsafe_values = sorted({value for value in flatten_strings(patch) if contains_unsafe_value(config, value)})
    if unsafe_values:
        return {
            "ok": False,
            "path": str(patch_path),
            "error": "patch_contains_placeholder_or_secret_like_value",
            "unsafe_value_count": len(unsafe_values),
        }
    return {"ok": True, "path": str(patch_path), "patch": deepcopy(patch)}


def validate_manifest_payload(*, config: EvidenceMergeConfig, manifest: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=config.temp_prefix) as temp_dir:
        manifest_path = Path(temp_dir) / config.default_output_name
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return config.validation_runner(manifest_path)


def load_json_file(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists():
        return {"ok": False, "path": str(resolved), "error": "file_missing"}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "path": str(resolved), "error": "invalid_json", "detail": str(exc)}
    return {"ok": True, "path": str(resolved), "data": payload}


def section_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(flatten_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(flatten_strings(item))
        return strings
    return []


def contains_unsafe_value(config: EvidenceMergeConfig, value: str) -> bool:
    return any(marker in value for marker in (*config.placeholder_markers, *config.secret_value_markers))


def contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def real_value(value: Any, placeholder_markers: tuple[str, ...]) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not contains_any(value, placeholder_markers)


def has_evidence_refs(data: dict[str, Any], placeholder_markers: tuple[str, ...]) -> bool:
    refs = data.get("evidence_refs")
    return isinstance(refs, list) and bool(refs) and all(real_value(item, placeholder_markers) for item in refs)


def count_number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def parse_iso_datetime(value: Any, placeholder_markers: tuple[str, ...] = ()) -> datetime | None:
    if not isinstance(value, str) or not value.strip() or contains_any(value, placeholder_markers):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def is_iso_datetime(value: Any, placeholder_markers: tuple[str, ...] = ()) -> bool:
    return parse_iso_datetime(value, placeholder_markers) is not None


def is_future_datetime(value: Any, placeholder_markers: tuple[str, ...] = ()) -> bool:
    parsed = parse_iso_datetime(value, placeholder_markers)
    if parsed is None:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > datetime.now(timezone.utc)


def failed_result(
    *,
    config: EvidenceMergeConfig,
    errors: list[dict[str, Any]],
    output_path: Path | None,
    merged_sections: list[str],
) -> dict[str, Any]:
    return {
        "ok": False,
        config.claim_key: False,
        "boundary": config.boundary,
        "output_path": str(output_path.resolve()) if output_path else "",
        "merged_sections": merged_sections,
        "errors": errors,
        "validation": None,
        "manifest": None,
        "next_step": "Fix patch JSON, remove placeholders/secrets, and rerun the merge.",
    }
