from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from memory_engine.db import init_db
from memory_engine.repository import MemoryRepository

from .permissions import demo_permission_context
from .service import CopilotService
from .tools import handle_tool_request


ROOT = Path(__file__).resolve().parents[2]
OPENCLAW_LOCK_FILE = ROOT / "agent_adapters" / "openclaw" / "openclaw-version.lock"
OPENCLAW_SCHEMA_FILE = ROOT / "agent_adapters" / "openclaw" / "memory_tools.schema.json"
EMBEDDING_LOCK_FILE = ROOT / "memory_engine" / "copilot" / "embedding-provider.lock"

STATUS_ORDER = ("pass", "fail", "warning", "skipped", "not_configured", "fallback_used")
PHASE_NAME = "Phase 6 Deployability + Healthcheck"
SCOPE = "project:feishu_ai_challenge"

OpenClawVersionReader = Callable[[], tuple[str, str]]


def run_copilot_healthcheck(
    *,
    openclaw_version_reader: OpenClawVersionReader | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Run non-live deployability checks for the Phase 6 handoff.

    The default path avoids real Feishu pushes, production deployment, and live
    embedding calls. Provider checks inspect configuration and local import
    readiness, then report fallback/not_configured states instead of crashing.
    """

    repo_root = root or ROOT
    checks = {
        "openclaw_version": _check_openclaw_version(openclaw_version_reader),
        "copilot_service": _check_copilot_service(),
        "openclaw_schema": _check_openclaw_schema(repo_root / OPENCLAW_SCHEMA_FILE.relative_to(ROOT)),
        "storage_schema": _check_storage_schema(),
        "permission_contract": _check_permission_contract(),
        "cognee_adapter": _check_cognee_adapter(),
        "embedding_provider": _check_embedding_provider(repo_root / EMBEDDING_LOCK_FILE.relative_to(ROOT)),
        "smoke_tests": _check_smoke_tests(),
    }
    status_counts = _status_counts(checks)
    return {
        "ok": status_counts["fail"] == 0,
        "phase": PHASE_NAME,
        "scope": "deployability_and_healthcheck_only",
        "boundary": "可检查、可初始化、可诊断；不做生产部署、不做真实飞书推送、不宣称 productized live。",
        "checks": checks,
        "status_counts": status_counts,
    }


def format_healthcheck_text(report: dict[str, Any]) -> str:
    lines = [
        f"{report['phase']}",
        f"ok: {str(report['ok']).lower()}",
        f"scope: {report['scope']}",
        f"boundary: {report['boundary']}",
        "",
        "checks:",
    ]
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    for name, check in checks.items():
        if not isinstance(check, dict):
            continue
        detail = _summary_for_check(name, check)
        lines.append(f"- {name}: {check.get('status')}{detail}")
    lines.append("")
    lines.append(f"status_counts: {json.dumps(report.get('status_counts', {}), ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines)


def _check_openclaw_version(openclaw_version_reader: OpenClawVersionReader | None) -> dict[str, Any]:
    try:
        locked, local = (openclaw_version_reader or _read_openclaw_versions)()
    except Exception as exc:
        return {
            "status": "fail",
            "command": "python3 scripts/check_openclaw_version.py",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "next_step": "确认 openclaw CLI 在 PATH 上，并且不要升级；需要重装时仅用 npm i -g openclaw@2026.4.24 --no-fund --no-audit。",
        }
    return {
        "status": "pass" if local == locked else "fail",
        "locked_version": locked,
        "local_version": local,
        "command": "python3 scripts/check_openclaw_version.py",
        "next_step": "" if local == locked else f"Reinstall exact locked version: npm i -g openclaw@{locked} --no-fund --no-audit",
    }


def _read_openclaw_versions() -> tuple[str, str]:
    locked = OPENCLAW_LOCK_FILE.read_text(encoding="utf-8").strip()
    completed = subprocess.run(
        ["openclaw", "--version"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    match = re.search(r"OpenClaw\s+([0-9]{4}\.[0-9]+\.[0-9]+)", completed.stdout)
    if not match:
        raise RuntimeError(f"Could not parse OpenClaw version from: {completed.stdout.strip()}")
    return locked, match.group(1)


def _check_copilot_service() -> dict[str, Any]:
    try:
        service = CopilotService()
        return {
            "status": "pass",
            "import": "ok",
            "initialization": "ok",
            "service_class": service.__class__.__name__,
        }
    except Exception as exc:
        return {
            "status": "fail",
            "import": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "next_step": "检查 memory_engine/copilot/service.py 的 import 和初始化依赖。",
        }


def _check_openclaw_schema(path: Path) -> dict[str, Any]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        tools = [str(tool.get("name")) for tool in schema.get("tools", []) if isinstance(tool, dict)]
        version = str(schema.get("version") or "")
        openclaw_version = str(schema.get("openclaw_version") or "")
        missing_versions = not version or not openclaw_version
        return {
            "status": "warning" if missing_versions else "pass",
            "schema_file": str(path.relative_to(ROOT)),
            "schema_version": version,
            "openclaw_version": openclaw_version,
            "tool_count": len(tools),
            "tools": sorted(tools),
            "next_step": "补齐 schema version / openclaw_version。" if missing_versions else "",
        }
    except Exception as exc:
        return {
            "status": "fail",
            "schema_file": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "next_step": "修复 OpenClaw tool schema JSON 后再运行 healthcheck。",
        }


def _check_storage_schema() -> dict[str, Any]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        tables = _sqlite_tables(conn)
        memory_columns = _sqlite_columns(conn, "memories")
        has_core_tables = {"raw_events", "memories", "memory_versions", "memory_evidence"}.issubset(tables)
        tenant_visibility_columns = {"tenant_id", "organization_id", "visibility_policy"}.issubset(memory_columns)
        audit_table_available = "memory_audit_events" in tables
        status = "pass" if has_core_tables and tenant_visibility_columns and audit_table_available else "warning"
        return {
            "status": status,
            "schema_checkable": has_core_tables,
            "schema_version": "legacy_scope_v1" if has_core_tables else "unknown",
            "tables": sorted(tables),
            "tenant_visibility_columns": tenant_visibility_columns,
            "audit_table_available": audit_table_available,
            "boundary": "storage schema is checkable; this is not a full audit migration or tenant visibility migration.",
            "next_step": (
                ""
                if status == "pass"
                else "后续 migration 阶段再加入 tenant_id / organization_id / visibility_policy 和 audit table。"
            ),
        }
    except Exception as exc:
        return {
            "status": "fail",
            "schema_checkable": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "next_step": "修复 memory_engine/db.py 的 init_db schema。",
        }
    finally:
        conn.close()


def _check_permission_contract() -> dict[str, Any]:
    deny = _permission_deny_check()
    return {
        "status": "pass" if deny["passed"] else "fail",
        "loaded": True,
        "fail_closed": deny["passed"],
        "payload_shape": "current_context.permission",
        "missing_reason_code": deny["missing_reason_code"],
        "malformed_reason_code": deny["malformed_reason_code"],
        "request_id": deny["request_id"],
        "trace_id": deny["trace_id"],
        "next_step": "" if deny["passed"] else "修复 missing/malformed current_context.permission 的 fail-closed 行为。",
    }


def _check_cognee_adapter() -> dict[str, Any]:
    try:
        from .cognee_adapter import CogneeMemoryAdapter

        adapter = CogneeMemoryAdapter()
        sdk_available = importlib.util.find_spec("cognee") is not None
        return {
            "status": "pass" if sdk_available and adapter.is_configured else "fallback_used",
            "adapter_import": "ok",
            "configured": adapter.is_configured,
            "sdk_available": sdk_available,
            "fallback_available": True,
            "fallback": "repository_retrieval",
            "next_step": (
                ""
                if adapter.is_configured
                else "需要真实 Cognee 验证时注入本地 SDK client；当前 healthcheck 只确认 adapter 可 import，并使用 repository fallback。"
            ),
        }
    except Exception as exc:
        return {
            "status": "fail",
            "adapter_import": "failed",
            "fallback_available": True,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "next_step": "修复 memory_engine/copilot/cognee_adapter.py 的 adapter 边界。",
        }


def _check_embedding_provider(path: Path) -> dict[str, Any]:
    try:
        lock = _read_key_value_file(path)
    except Exception as exc:
        return {
            "status": "fail",
            "lock_file": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "next_step": "补齐 memory_engine/copilot/embedding-provider.lock。",
        }
    provider = lock.get("provider") or "unknown"
    model = lock.get("model") or lock.get("litellm_model") or "unknown"
    litellm_available = importlib.util.find_spec("litellm") is not None
    status = "warning" if litellm_available else "not_configured"
    return {
        "status": status,
        "check_mode": "configuration_only",
        "provider": provider,
        "model": model,
        "litellm_model": lock.get("litellm_model"),
        "endpoint": lock.get("endpoint"),
        "expected_dimensions": _int_or_none(lock.get("dimensions")),
        "litellm_available": litellm_available,
        "live_available": None,
        "fallback_available": True,
        "fallback": "DeterministicEmbeddingProvider",
        "next_step": (
            "当前 healthcheck 只做配置可检查；需要真实 embedding 可用性验证时运行 python3 scripts/check_embedding_provider.py。"
            if litellm_available
            else "需要真实 embedding 验证时运行 python3 scripts/check_embedding_provider.py；结束后执行 ollama ps 并清理本项目模型。"
        ),
    }


def _check_smoke_tests() -> dict[str, Any]:
    search = _smoke_search()
    permission_deny = _smoke_permission_deny()
    candidate_review = _smoke_candidate_review()
    passed = all(item.get("status") == "pass" for item in (search, permission_deny, candidate_review))
    return {
        "status": "pass" if passed else "fail",
        "search": search,
        "permission_deny": permission_deny,
        "candidate_review": candidate_review,
    }


def _smoke_search() -> dict[str, Any]:
    with _seeded_service() as service:
        result = handle_tool_request(
            "memory.search",
            {
                "query": "生产部署参数",
                "scope": SCOPE,
                "current_context": demo_permission_context("memory.search", SCOPE, entrypoint="healthcheck"),
            },
            service=service,
        )
    returned_count = len(result.get("results") or []) if isinstance(result.get("results"), list) else 0
    return {
        "status": "pass" if result.get("ok") and returned_count >= 1 else "fail",
        "entrypoint": "handle_tool_request",
        "tool": "memory.search",
        "returned_count": returned_count,
        "trace_backend": (result.get("trace") or {}).get("backend") if isinstance(result.get("trace"), dict) else None,
        "fallback_used": (result.get("trace") or {}).get("fallback_used") if isinstance(result.get("trace"), dict) else None,
    }


def _smoke_permission_deny() -> dict[str, Any]:
    deny = _permission_deny_check()
    return {
        "status": "pass" if deny["passed"] else "fail",
        "entrypoint": "handle_tool_request",
        "tool": "memory.search",
        "error_code": deny["error_code"],
        "missing_reason_code": deny["missing_reason_code"],
        "malformed_reason_code": deny["malformed_reason_code"],
        "request_id": deny["request_id"],
        "trace_id": deny["trace_id"],
    }


def _permission_deny_check() -> dict[str, Any]:
    missing = handle_tool_request("memory.search", {"query": "部署", "scope": SCOPE})
    malformed = handle_tool_request("memory.search", _malformed_permission_search_payload())
    missing_details = _error_details(missing)
    malformed_details = _error_details(malformed)
    passed = (
        _error_code(missing) == "permission_denied"
        and missing_details.get("reason_code") == "missing_permission_context"
        and _error_code(malformed) == "permission_denied"
        and malformed_details.get("reason_code") == "malformed_permission_context"
        and malformed_details.get("request_id") == "req_health_bad"
        and malformed_details.get("trace_id") == "trace_health_bad"
    )
    return {
        "passed": passed,
        "error_code": _error_code(malformed),
        "missing_reason_code": missing_details.get("reason_code"),
        "malformed_reason_code": malformed_details.get("reason_code"),
        "request_id": malformed_details.get("request_id"),
        "trace_id": malformed_details.get("trace_id"),
    }


def _malformed_permission_search_payload() -> dict[str, Any]:
    return {
        "query": "部署",
        "scope": SCOPE,
        "current_context": {
            "scope": SCOPE,
            "permission": {
                "request_id": "req_health_bad",
                "trace_id": "trace_health_bad",
                "actor": {
                    "user_id": "u_health",
                    "tenant_id": "tenant:demo",
                    "organization_id": "org:demo",
                    "roles": "reviewer",
                },
                "source_context": {"entrypoint": "openclaw", "workspace_id": SCOPE},
                "requested_action": "memory.search",
                "requested_visibility": "team",
                "timestamp": "2026-05-07T00:00:00+08:00",
            },
        },
    }


def _smoke_candidate_review() -> dict[str, Any]:
    with _temp_service() as service:
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：生产部署必须加 --canary --region cn-shanghai。",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "health_candidate_1",
                    "actor_id": "u_health",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
                },
                "current_context": demo_permission_context("memory.create_candidate", SCOPE, actor_id="u_health", entrypoint="healthcheck"),
            },
            service=service,
        )
        candidate = created.get("candidate") if isinstance(created.get("candidate"), dict) else {}
        candidate_id = created.get("candidate_id")
        confirmed: dict[str, Any] = {"ok": False}
        if isinstance(candidate_id, str):
            confirmed = handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": candidate_id,
                    "scope": SCOPE,
                    "reason": "healthcheck smoke confirm",
                    "current_context": demo_permission_context("memory.confirm", SCOPE, actor_id="u_health", entrypoint="healthcheck"),
                },
                service=service,
            )
    memory = confirmed.get("memory") if isinstance(confirmed.get("memory"), dict) else {}
    passed = created.get("ok") and candidate.get("status") == "candidate" and confirmed.get("ok") and memory.get("status") == "active"
    return {
        "status": "pass" if passed else "fail",
        "entrypoint": "handle_tool_request",
        "tools": ["memory.create_candidate", "memory.confirm"],
        "created_status": candidate.get("status"),
        "confirmed_status": memory.get("status"),
        "state_boundary": "temp_db_only",
    }


class _temp_service:
    def __enter__(self) -> CopilotService:
        self.tmp = tempfile.NamedTemporaryFile(prefix="copilot_health_", suffix=".sqlite")
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.service = CopilotService(repository=MemoryRepository(self.conn))
        return self.service

    def __exit__(self, *_exc: object) -> None:
        self.conn.close()
        self.tmp.close()


class _seeded_service(_temp_service):
    def __enter__(self) -> CopilotService:
        service = super().__enter__()
        service.repository.remember(SCOPE, "生产部署必须加 --canary --region cn-shanghai", source_type="healthcheck")
        return service


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _read_key_value_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _status_counts(checks: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in STATUS_ORDER}
    for check in checks.values():
        status = str(check.get("status") or "fail")
        counts.setdefault(status, 0)
        counts[status] += 1
    return counts


def _error_code(response: dict[str, Any]) -> str | None:
    error = response.get("error")
    return str(error.get("code")) if isinstance(error, dict) and error.get("code") else None


def _error_details(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if not isinstance(error, dict):
        return {}
    details = error.get("details")
    return dict(details) if isinstance(details, dict) else {}


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _summary_for_check(name: str, check: dict[str, Any]) -> str:
    if name == "openclaw_version":
        return f" locked={check.get('locked_version')} local={check.get('local_version')}"
    if name == "openclaw_schema":
        return f" schema_version={check.get('schema_version')} openclaw={check.get('openclaw_version')} tools={check.get('tool_count')}"
    if name == "storage_schema":
        return (
            f" schema_version={check.get('schema_version')}"
            f" tenant_visibility_columns={check.get('tenant_visibility_columns')}"
            f" audit_table_available={check.get('audit_table_available')}"
        )
    if name == "embedding_provider":
        return f" provider={check.get('provider')} model={check.get('model')} mode={check.get('check_mode')}"
    if name == "cognee_adapter":
        return f" configured={check.get('configured')} fallback={check.get('fallback')}"
    if name == "smoke_tests":
        return (
            f" search={check.get('search', {}).get('status')}"
            f" permission_deny={check.get('permission_deny', {}).get('status')}"
            f" candidate_review={check.get('candidate_review', {}).get('status')}"
        )
    return ""
