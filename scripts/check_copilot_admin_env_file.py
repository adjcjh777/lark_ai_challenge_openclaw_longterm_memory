#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLE_PATH = ROOT / "deploy" / "copilot-admin.env.example"
DEFAULT_RUNTIME_PATH = Path("/etc/feishu-memory-copilot/admin.env")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
PLACEHOLDER_TOKENS = {
    "__CHANGE_ME_ADMIN_TOKEN__",
    "__CHANGE_ME_VIEWER_TOKEN__",
    "<redacted-token>",
    "<redacted-viewer-token>",
}
SECRET_KEY_FRAGMENTS = ("SECRET", "ACCESS_TOKEN", "OPENAI_API_KEY", "RIGHTCODE", "LLM_API_KEY", "APP_SECRET")
REQUIRED_KEYS = (
    "MEMORY_DB_PATH",
    "FEISHU_MEMORY_COPILOT_ADMIN_HOST",
    "FEISHU_MEMORY_COPILOT_ADMIN_PORT",
    "FEISHU_MEMORY_COPILOT_ADMIN_TOKEN",
    "FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN",
)
SSO_KEYS = (
    "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED",
    "FEISHU_MEMORY_COPILOT_ADMIN_SSO_USER_HEADER",
    "FEISHU_MEMORY_COPILOT_ADMIN_SSO_EMAIL_HEADER",
    "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS",
    "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Copilot Admin admin.env file without printing secret values."
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_EXAMPLE_PATH),
        help="Path to admin.env. Defaults to deploy/copilot-admin.env.example.",
    )
    parser.add_argument(
        "--expect-example",
        action="store_true",
        help="Validate the committed example: placeholders must remain and backend must bind loopback.",
    )
    parser.add_argument(
        "--expect-runtime",
        action="store_true",
        help="Validate a real local runtime file: placeholders must be replaced and tokens must be usable.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser()
    expect_example = args.expect_example or (not args.expect_runtime and env_file.resolve() == DEFAULT_EXAMPLE_PATH)
    result = check_admin_env_file(env_file, expect_example=expect_example)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


def check_admin_env_file(path: Path, *, expect_example: bool = False) -> dict[str, Any]:
    env, parse_errors = _parse_env_file(path)
    checks = {
        "file_exists": {
            "status": "pass" if path.exists() else "fail",
            "description": "admin.env file exists.",
        },
        "parse": {
            "status": "pass" if not parse_errors else "fail",
            "description": "Environment file uses KEY=VALUE lines.",
            "errors": parse_errors,
        },
        "required_keys": _check_required_keys(env),
        "port": _check_port(env),
        "host": _check_host(env, expect_example=expect_example),
        "tokens": _check_tokens(env, expect_example=expect_example),
        "sso": _check_sso(env),
        "secret_hygiene": _check_secret_hygiene(env),
    }
    failed = {name: check for name, check in checks.items() if check["status"] == "fail"}
    return {
        "ok": not failed,
        "mode": "example" if expect_example else "runtime",
        "path": str(path),
        "checks": checks,
        "failed_checks": sorted(failed),
        "redacted_summary": _redacted_summary(env),
        "boundary": "env_lint_only; no token values printed; no production deployment or real IdP validation",
        "next_step": "" if not failed else "Fix failed admin.env checks before starting the systemd admin service.",
    }


def _parse_env_file(path: Path) -> tuple[dict[str, str], list[str]]:
    if not path.exists():
        return {}, [f"file not found: {path}"]
    env: dict[str, str] = {}
    errors: list[str] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"line {line_no}: missing '='")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            errors.append(f"line {line_no}: empty key")
            continue
        env[key] = value
    return env, errors


def _check_required_keys(env: dict[str, str]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_KEYS if not env.get(key)]
    return {
        "status": "pass" if not missing else "fail",
        "description": "Required runtime keys are present.",
        "missing": missing,
    }


def _check_port(env: dict[str, str]) -> dict[str, Any]:
    raw_port = env.get("FEISHU_MEMORY_COPILOT_ADMIN_PORT", "")
    try:
        port = int(raw_port)
    except ValueError:
        port = None
    ok = port is not None and 1 <= port <= 65535
    return {
        "status": "pass" if ok else "fail",
        "description": "Admin port is an integer in the valid TCP port range.",
        "configured": bool(raw_port),
    }


def _check_host(env: dict[str, str], *, expect_example: bool) -> dict[str, Any]:
    host = env.get("FEISHU_MEMORY_COPILOT_ADMIN_HOST", "")
    is_loopback = host in LOOPBACK_HOSTS
    ok = bool(host) and (is_loopback if expect_example else True)
    return {
        "status": "pass" if ok else "fail",
        "description": "Example binds loopback; runtime may bind remote only with admin token.",
        "host_class": "loopback" if is_loopback else "remote_or_unspecified",
        "requires_token_for_remote": not is_loopback,
    }


def _check_tokens(env: dict[str, str], *, expect_example: bool) -> dict[str, Any]:
    admin = env.get("FEISHU_MEMORY_COPILOT_ADMIN_TOKEN", "")
    viewer = env.get("FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN", "")
    host = env.get("FEISHU_MEMORY_COPILOT_ADMIN_HOST", "")
    admin_is_placeholder = _is_placeholder(admin)
    viewer_is_placeholder = _is_placeholder(viewer)
    if expect_example:
        ok = admin_is_placeholder and viewer_is_placeholder and admin != viewer
        reason = "example_placeholders_expected"
    else:
        ok = bool(admin) and bool(viewer) and not admin_is_placeholder and not viewer_is_placeholder and admin != viewer
        if host not in LOOPBACK_HOSTS:
            ok = ok and bool(admin)
        reason = "runtime_tokens_must_be_distinct_and_replaced"
    return {
        "status": "pass" if ok else "fail",
        "description": "Admin and viewer tokens are present, distinct, and in the expected placeholder/replaced state.",
        "reason": reason,
        "admin_token_state": _token_state(admin),
        "viewer_token_state": _token_state(viewer),
        "tokens_distinct": bool(admin and viewer and admin != viewer),
    }


def _check_sso(env: dict[str, str]) -> dict[str, Any]:
    enabled = _truthy(env.get("FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED", "0"))
    missing = [key for key in SSO_KEYS if key not in env]
    if enabled:
        for key in (
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_USER_HEADER",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_EMAIL_HEADER",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS",
            "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS",
        ):
            if not env.get(key):
                missing.append(key)
    return {
        "status": "pass" if not missing else "fail",
        "description": "SSO keys are present; enabled SSO has admin users and allowed domains configured.",
        "enabled": enabled,
        "missing": sorted(set(missing)),
    }


def _check_secret_hygiene(env: dict[str, str]) -> dict[str, Any]:
    unexpected_secret_keys = [
        key
        for key in env
        if any(fragment in key.upper() for fragment in SECRET_KEY_FRAGMENTS)
        and key
        not in {
            "FEISHU_MEMORY_COPILOT_ADMIN_TOKEN",
            "FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN",
        }
    ]
    return {
        "status": "pass" if not unexpected_secret_keys else "fail",
        "description": "admin.env should not carry unrelated API keys or IdP secrets.",
        "unexpected_secret_keys": unexpected_secret_keys,
    }


def _redacted_summary(env: dict[str, str]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key in sorted(env):
        value = env[key]
        if "TOKEN" in key.upper() or "SECRET" in key.upper() or "KEY" in key.upper():
            summary[key] = _token_state(value)
        elif key == "FEISHU_MEMORY_COPILOT_ADMIN_HOST":
            summary[key] = "loopback" if value in LOOPBACK_HOSTS else "remote_or_unspecified"
        else:
            summary[key] = "configured" if value else "empty"
    return summary


def _is_placeholder(value: str) -> bool:
    return value in PLACEHOLDER_TOKENS or value.startswith("__CHANGE_ME")


def _token_state(value: str) -> str:
    if not value:
        return "missing"
    if _is_placeholder(value):
        return "placeholder"
    return "configured_redacted"


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _print_text(result: dict[str, Any]) -> None:
    print("Copilot Admin Env File Check")
    print(f"ok: {str(result['ok']).lower()}")
    print(f"mode: {result['mode']}")
    print(f"path: {result['path']}")
    for name, check in result["checks"].items():
        print(f"- {name}: {check['status']} ({check['description']})")
    if result["failed_checks"]:
        print(f"failed_checks: {', '.join(result['failed_checks'])}")


if __name__ == "__main__":
    raise SystemExit(main())
