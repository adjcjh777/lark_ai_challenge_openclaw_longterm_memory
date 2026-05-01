from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from memory_engine.copilot.knowledge_pages import compile_project_memory_cards
from memory_engine.db import db_path_from_env, init_db
from memory_engine.repository import MemoryRepository, now_ms
from scripts.check_copilot_admin_production_evidence import (
    DEFAULT_MANIFEST_PATH as DEFAULT_PRODUCTION_EVIDENCE_MANIFEST_PATH,
)
from scripts.check_copilot_admin_production_evidence import (
    run_production_evidence_check,
)

DEFAULT_ADMIN_HOST = "127.0.0.1"
DEFAULT_ADMIN_PORT = 8765
ADMIN_TOKEN_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_TOKEN", "COPILOT_ADMIN_TOKEN")
ADMIN_VIEWER_TOKEN_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN", "COPILOT_ADMIN_VIEWER_TOKEN")
ADMIN_SSO_ENABLED_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED", "COPILOT_ADMIN_SSO_ENABLED")
ADMIN_SSO_USER_HEADER_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_SSO_USER_HEADER", "COPILOT_ADMIN_SSO_USER_HEADER")
ADMIN_SSO_EMAIL_HEADER_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_SSO_EMAIL_HEADER", "COPILOT_ADMIN_SSO_EMAIL_HEADER")
ADMIN_SSO_ADMIN_USERS_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS", "COPILOT_ADMIN_SSO_ADMIN_USERS")
ADMIN_SSO_VIEWER_USERS_ENV_NAMES = ("FEISHU_MEMORY_COPILOT_ADMIN_SSO_VIEWER_USERS", "COPILOT_ADMIN_SSO_VIEWER_USERS")
ADMIN_SSO_ALLOWED_DOMAINS_ENV_NAMES = (
    "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS",
    "COPILOT_ADMIN_SSO_ALLOWED_DOMAINS",
)
ADMIN_PRODUCTION_EVIDENCE_MANIFEST_ENV_NAMES = (
    "FEISHU_MEMORY_COPILOT_ADMIN_PRODUCTION_EVIDENCE_MANIFEST",
    "COPILOT_ADMIN_PRODUCTION_EVIDENCE_MANIFEST",
)
MAX_LIMIT = 200


@dataclass(frozen=True)
class AdminSsoConfig:
    enabled: bool = False
    user_header: str = "X-Forwarded-User"
    email_header: str = "X-Forwarded-Email"
    admin_users: frozenset[str] = frozenset()
    viewer_users: frozenset[str] = frozenset()
    allowed_domains: frozenset[str] = frozenset()

    def role_for(self, *, user: str | None, email: str | None) -> str | None:
        if not self.enabled:
            return None
        identities = {value.strip().lower() for value in (user, email) if value and value.strip()}
        if not identities:
            return None
        if identities & self.admin_users:
            return "admin"
        if identities & self.viewer_users:
            return "viewer"
        for identity in identities:
            if "@" in identity and identity.rsplit("@", 1)[1] in self.allowed_domains:
                return "viewer"
        return None


@dataclass
class EmbeddedAdminRuntime:
    enabled: bool
    url: str | None = None
    reason: str | None = None
    server: CopilotAdminServer | None = None
    thread: threading.Thread | None = None

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)

    def to_log_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "url": self.url,
            "reason": self.reason,
        }


def start_embedded_admin(
    *,
    host: str = DEFAULT_ADMIN_HOST,
    port: int = DEFAULT_ADMIN_PORT,
    db_path: str | Path | None = None,
    enabled: bool = True,
    auth_token: str | None = None,
    viewer_token: str | None = None,
    sso_config: AdminSsoConfig | None = None,
    production_evidence_manifest: str | Path | None = None,
) -> EmbeddedAdminRuntime:
    if not enabled:
        return EmbeddedAdminRuntime(enabled=False, reason="disabled")
    try:
        server = create_admin_server(
            host,
            port,
            db_path,
            auth_token=auth_token,
            viewer_token=viewer_token,
            sso_config=sso_config,
            production_evidence_manifest=production_evidence_manifest,
        )
    except OSError as exc:
        return EmbeddedAdminRuntime(enabled=False, reason=f"bind_failed: {exc}")

    thread = threading.Thread(target=server.serve_forever, name="copilot-admin-dashboard", daemon=True)
    thread.start()
    url = f"http://{host}:{server.server_port}"
    return EmbeddedAdminRuntime(enabled=True, url=url, server=server, thread=thread)


class AdminQueryService:
    """Read-only query helpers for the local Copilot admin surface."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def summary(self) -> dict[str, Any]:
        return {
            "memory_total": self._count("memories"),
            "memory_by_status": self._count_by("memories", "status"),
            "raw_event_total": self._count("raw_events"),
            "version_total": self._count("memory_versions"),
            "evidence_total": self._count("memory_evidence"),
            "audit_total": self._count("memory_audit_events"),
            "audit_by_event_type": self._count_by("memory_audit_events", "event_type"),
            "audit_by_permission_decision": self._count_by("memory_audit_events", "permission_decision"),
        }

    def live_overview(self) -> dict[str, Any]:
        recent_raw_events = self._recent_raw_events(limit=20)
        recent_audit = self.list_audit(limit=15)["items"]
        graph = self._knowledge_graph_overview(limit=12)
        wiki = self.wiki_overview(limit=8)
        return {
            "bot_activity": {
                "latest_raw_event_at": recent_raw_events[0]["event_time_iso"] if recent_raw_events else None,
                "latest_audit_at": recent_audit[0]["created_at_iso"] if recent_audit else None,
                "latest_graph_seen_at": graph["recent_nodes"][0]["last_seen_at_iso"] if graph["recent_nodes"] else None,
            },
            "recent_raw_events": recent_raw_events,
            "recent_audit": recent_audit,
            "knowledge_graph": graph,
            "wiki": wiki,
            "knowledge_cards": wiki["cards"],
        }

    def launch_readiness(self) -> dict[str, Any]:
        summary = self.summary()
        wiki = self.wiki_overview(limit=20)
        graph = self.graph_workspace(limit=80)
        tenants = self.tenant_overview(limit=80)
        policies = self.tenant_policies(limit=80)
        checks = [
            _launch_check(
                "llm_wiki",
                "LLM Wiki cards",
                "pass" if int(wiki.get("card_count") or 0) > 0 else "fail",
                f"{int(wiki.get('card_count') or 0)} active evidence-backed cards",
                "Confirm active memories with evidence before sharing the knowledge site.",
            ),
            _launch_check(
                "knowledge_graph",
                "Knowledge graph",
                "pass" if int(graph.get("workspace_node_count") or 0) > 0 else "fail",
                f"{int(graph.get('workspace_node_count') or 0)} nodes / {int(graph.get('workspace_edge_count') or 0)} edges",
                "Ingest graph context or confirm evidence-backed memories.",
            ),
            _launch_check(
                "tenant_inventory",
                "Tenant inventory",
                "pass" if int(tenants.get("tenant_count") or 0) > 0 else "fail",
                f"{int(tenants.get('tenant_count') or 0)} tenants / {int(tenants.get('organization_count') or 0)} orgs",
                "Create tenant/org scoped ledger rows before staging review.",
            ),
            _launch_check(
                "tenant_policy_editor",
                "Tenant policy editor",
                "pass"
                if bool(policies.get("available")) and int(policies.get("total") or 0) > 0
                else "warning"
                if bool(policies.get("available"))
                else "fail",
                f"{int(policies.get('total') or 0)} configured policies",
                "Save at least one tenant policy for the staging tenant.",
            ),
            _launch_check(
                "audit_ledger",
                "Audit ledger",
                "pass" if int(summary.get("audit_total") or 0) > 0 else "warning",
                f"{int(summary.get('audit_total') or 0)} audit events",
                "Run a candidate/review or tenant policy action to prove audit writeback.",
            ),
        ]
        staging_status = _rollup_status(checks)
        production_blockers = [
            {
                "id": "enterprise_idp_sso_validation",
                "label": "Real enterprise IdP / Feishu SSO validation",
                "status": "blocker",
            },
            {
                "id": "production_db_operations",
                "label": "Production database operations",
                "status": "blocker",
            },
            {
                "id": "production_monitoring_alerts",
                "label": "Production monitoring and alerting",
                "status": "blocker",
            },
            {
                "id": "productized_live_long_run",
                "label": "Productized live long-run evidence",
                "status": "blocker",
            },
        ]
        return {
            "staging_status": staging_status,
            "production_status": "blocked",
            "checks": checks,
            "production_blockers": production_blockers,
            "summary": {
                "memory_total": summary.get("memory_total"),
                "audit_total": summary.get("audit_total"),
                "wiki_card_count": wiki.get("card_count"),
                "graph_node_count": graph.get("workspace_node_count"),
                "graph_edge_count": graph.get("workspace_edge_count"),
                "tenant_count": tenants.get("tenant_count"),
                "tenant_policy_count": policies.get("total"),
            },
            "boundary": (
                "staging launch readiness only; production remains blocked until real IdP, "
                "production DB ops, monitoring, and long-run live evidence are complete."
            ),
        }

    def prometheus_metrics(self) -> str:
        summary = self.summary()
        wiki = self.wiki_overview(limit=1)
        graph = self.graph_workspace(limit=10)
        tenants = self.tenant_overview(limit=80)
        policies = self.tenant_policies(limit=1)
        launch = self.launch_readiness()
        lines = [
            "# HELP copilot_admin_memory_total Total memories in the local ledger.",
            "# TYPE copilot_admin_memory_total gauge",
            f"copilot_admin_memory_total {int(summary.get('memory_total') or 0)}",
            "# HELP copilot_admin_audit_total Total audit events in the local ledger.",
            "# TYPE copilot_admin_audit_total gauge",
            f"copilot_admin_audit_total {int(summary.get('audit_total') or 0)}",
            "# HELP copilot_admin_wiki_card_count Active evidence-backed LLM Wiki cards.",
            "# TYPE copilot_admin_wiki_card_count gauge",
            f"copilot_admin_wiki_card_count {int(wiki.get('card_count') or 0)}",
            "# HELP copilot_admin_graph_workspace_node_count Visible admin graph workspace nodes.",
            "# TYPE copilot_admin_graph_workspace_node_count gauge",
            f"copilot_admin_graph_workspace_node_count {int(graph.get('workspace_node_count') or 0)}",
            "# HELP copilot_admin_tenant_count Tenant count visible to the admin inventory.",
            "# TYPE copilot_admin_tenant_count gauge",
            f"copilot_admin_tenant_count {int(tenants.get('tenant_count') or 0)}",
            "# HELP copilot_admin_tenant_policy_count Tenant policies configured in the local admin backend.",
            "# TYPE copilot_admin_tenant_policy_count gauge",
            f"copilot_admin_tenant_policy_count {int(policies.get('total') or 0)}",
            "# HELP copilot_admin_launch_staging_ok Staging launch readiness rollup, 1 when pass.",
            "# TYPE copilot_admin_launch_staging_ok gauge",
            f"copilot_admin_launch_staging_ok {1 if launch.get('staging_status') == 'pass' else 0}",
            "# HELP copilot_admin_launch_production_blocked Production launch blocker rollup, 1 when blocked.",
            "# TYPE copilot_admin_launch_production_blocked gauge",
            f"copilot_admin_launch_production_blocked {1 if launch.get('production_status') == 'blocked' else 0}",
        ]
        for status, count in sorted((summary.get("memory_by_status") or {}).items()):
            lines.append(f'copilot_admin_memory_by_status{{status="{_metric_label_value(status)}"}} {int(count or 0)}')
        for blocker in launch.get("production_blockers") or []:
            if not isinstance(blocker, dict):
                continue
            lines.append(
                f'copilot_admin_launch_production_blocker{{blocker="{_metric_label_value(blocker.get("id"))}"}} 1'
            )
        lines.append("")
        return "\n".join(lines)

    def tenant_overview(
        self,
        *,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        limit = _clamp_limit(limit)
        conditions: list[str] = ["tenant_id IS NOT NULL", "tenant_id != ''"]
        params: list[Any] = []
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if organization_id:
            conditions.append("organization_id = ?")
            params.append(organization_id)
        where = "WHERE " + " AND ".join(conditions)
        tenant_sources = [
            "SELECT tenant_id, organization_id FROM memories",
            "SELECT tenant_id, organization_id FROM raw_events",
            "SELECT tenant_id, organization_id FROM memory_audit_events",
            "SELECT tenant_id, organization_id FROM knowledge_graph_nodes",
            "SELECT tenant_id, organization_id FROM knowledge_graph_edges",
        ]
        if _table_exists(self.conn, "tenant_admin_policies"):
            tenant_sources.append("SELECT tenant_id, organization_id FROM tenant_admin_policies")
        rows = self.conn.execute(
            f"""
            SELECT tenant_id, COALESCE(organization_id, '-') AS organization_id
            FROM (
              {" UNION ".join(tenant_sources)}
            )
            {where}
            ORDER BY tenant_id ASC, organization_id ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        policy_available = _table_exists(self.conn, "tenant_admin_policies")
        items = [self._tenant_org_overview(str(row["tenant_id"]), str(row["organization_id"])) for row in rows]
        missing_capabilities = [
            "enterprise_idp_sso_validation",
            "production_db_operations",
            "productized_live_long_run",
        ]
        if not policy_available:
            missing_capabilities.extend(["tenant_config_editor", "role_policy_editor"])
        return {
            "tenant_count": len({item["tenant_id"] for item in items}),
            "organization_count": len(items),
            "items": items,
            "read_only": False,
            "tenant_policy_editor_available": policy_available,
            "source": "ledger_and_tenant_policy_inventory",
            "boundary": (
                "tenant inventory plus local/pre-production tenant policy write API; "
                "not real enterprise IdP validation, production DB operations, or productized live."
            ),
            "missing_capabilities": missing_capabilities,
        }

    def tenant_policies(
        self,
        *,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        if not _table_exists(self.conn, "tenant_admin_policies"):
            return {"available": False, "items": [], "total": 0, "limit": _clamp_limit(limit)}
        limit = _clamp_limit(limit)
        conditions: list[str] = []
        params: list[Any] = []
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if organization_id:
            conditions.append("organization_id = ?")
            params.append(organization_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(self.conn.execute(f"SELECT COUNT(*) FROM tenant_admin_policies {where}", params).fetchone()[0])
        rows = self.conn.execute(
            f"""
            SELECT id, tenant_id, organization_id, status, default_visibility_policy,
                   auto_confirm_low_risk, require_review_for_conflicts,
                   reviewer_roles, admin_users, sso_allowed_domains, notes,
                   created_by, updated_by, created_at, updated_at
            FROM tenant_admin_policies
            {where}
            ORDER BY updated_at DESC, tenant_id ASC, organization_id ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return {
            "available": True,
            "total": total,
            "limit": limit,
            "items": [_tenant_policy_row_to_dict(row) for row in rows],
        }

    def upsert_tenant_policy(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        policy = _validate_tenant_policy_payload(payload)
        now = now_ms()
        policy_id = _tenant_policy_id(policy["tenant_id"], policy["organization_id"])
        existing = self.conn.execute(
            """
            SELECT id, created_at, created_by
            FROM tenant_admin_policies
            WHERE tenant_id = ? AND organization_id = ?
            """,
            (policy["tenant_id"], policy["organization_id"]),
        ).fetchone()
        created_at = int(existing["created_at"]) if existing else now
        created_by = str(existing["created_by"]) if existing else actor_id
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO tenant_admin_policies (
                  id, tenant_id, organization_id, status, default_visibility_policy,
                  auto_confirm_low_risk, require_review_for_conflicts,
                  reviewer_roles, admin_users, sso_allowed_domains, notes,
                  created_by, updated_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, organization_id) DO UPDATE SET
                  status = excluded.status,
                  default_visibility_policy = excluded.default_visibility_policy,
                  auto_confirm_low_risk = excluded.auto_confirm_low_risk,
                  require_review_for_conflicts = excluded.require_review_for_conflicts,
                  reviewer_roles = excluded.reviewer_roles,
                  admin_users = excluded.admin_users,
                  sso_allowed_domains = excluded.sso_allowed_domains,
                  notes = excluded.notes,
                  updated_by = excluded.updated_by,
                  updated_at = excluded.updated_at
                """,
                (
                    policy_id,
                    policy["tenant_id"],
                    policy["organization_id"],
                    policy["status"],
                    policy["default_visibility_policy"],
                    int(policy["auto_confirm_low_risk"]),
                    int(policy["require_review_for_conflicts"]),
                    json.dumps(policy["reviewer_roles"], ensure_ascii=False),
                    json.dumps(policy["admin_users"], ensure_ascii=False),
                    json.dumps(policy["sso_allowed_domains"], ensure_ascii=False),
                    policy["notes"],
                    created_by,
                    actor_id,
                    created_at,
                    now,
                ),
            )
            MemoryRepository(self.conn).record_audit_event(
                event_type="tenant_policy_upserted",
                action="admin.tenant_policy.upsert",
                tool_name="admin.tenant_policy.upsert",
                target_type="tenant_policy",
                target_id=policy_id,
                actor_id=actor_id,
                actor_roles=["admin"],
                tenant_id=policy["tenant_id"],
                organization_id=policy["organization_id"],
                permission_decision="allow",
                reason_code="admin_policy_updated",
                request_id=f"req_{policy_id}_{now}",
                trace_id=f"trace_{policy_id}_{now}",
                visible_fields=[
                    "tenant_id",
                    "organization_id",
                    "status",
                    "default_visibility_policy",
                    "reviewer_roles",
                    "admin_users",
                    "sso_allowed_domains",
                ],
                source_context={
                    "surface": "copilot_admin",
                    "boundary": "local_preproduction_tenant_policy_editor",
                },
                created_at=now,
            )
        row = self.conn.execute(
            "SELECT * FROM tenant_admin_policies WHERE tenant_id = ? AND organization_id = ?",
            (policy["tenant_id"], policy["organization_id"]),
        ).fetchone()
        return {"created": existing is None, "policy": _tenant_policy_row_to_dict(row)}

    def wiki_overview(
        self,
        *,
        scope: str | None = None,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        limit = _clamp_limit(limit)
        conditions = ["m.status = 'active'", "e.quote IS NOT NULL", "TRIM(e.quote) != ''"]
        params: list[Any] = []
        if scope:
            conditions.append("(m.scope_type || ':' || m.scope_id) = ?")
            params.append(scope)
        if tenant_id:
            conditions.append("m.tenant_id = ?")
            params.append(tenant_id)
        if organization_id:
            conditions.append("m.organization_id = ?")
            params.append(organization_id)
        if query:
            like = f"%{query}%"
            conditions.append(
                "(m.id LIKE ? OR m.subject LIKE ? OR m.current_value LIKE ? OR COALESCE(m.summary, '') LIKE ? OR e.quote LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        where = "WHERE " + " AND ".join(conditions)
        rows = self.conn.execute(
            f"""
            SELECT
              m.id, m.tenant_id, m.organization_id, m.visibility_policy,
              m.scope_type, m.scope_id, m.type, m.subject, m.current_value,
              m.summary, m.confidence, m.importance, m.owner_id,
              m.updated_at, m.active_version_id,
              v.version_no,
              e.source_type AS evidence_source_type,
              e.source_url AS evidence_source_url,
              e.source_event_id AS evidence_source_event_id,
              e.quote AS evidence_quote,
              e.actor_display AS evidence_actor_display,
              e.event_time AS evidence_event_time,
              r.source_id AS raw_source_id,
              r.raw_json AS raw_json,
              (
                SELECT COUNT(*)
                FROM memory_versions old_v
                WHERE old_v.memory_id = m.id
                  AND old_v.status = 'superseded'
              ) AS superseded_version_count
            FROM memories m
            LEFT JOIN memory_versions v ON v.id = m.active_version_id
            LEFT JOIN memory_evidence e
              ON e.id = (
                SELECT latest_e.id
                FROM memory_evidence latest_e
                WHERE latest_e.memory_id = m.id
                  AND latest_e.version_id = m.active_version_id
                ORDER BY latest_e.created_at DESC
                LIMIT 1
              )
            LEFT JOIN raw_events r ON r.id = e.source_event_id
            {where}
            ORDER BY m.importance DESC, m.updated_at DESC, m.subject ASC, m.id ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        cards = [_wiki_card_row_to_dict(row) for row in rows]
        tenancy_where, tenancy_params = _tenancy_where(alias=None, tenant_id=tenant_id, organization_id=organization_id)
        scopes = self.conn.execute(
            f"""
            SELECT scope_type || ':' || scope_id AS scope, COUNT(*) AS count
            FROM memories
            WHERE status = 'active'
            {tenancy_where}
            GROUP BY scope_type, scope_id
            ORDER BY count DESC, scope ASC
            LIMIT 20
            """,
            tenancy_params,
        ).fetchall()
        open_questions = self.conn.execute(
            f"""
            SELECT scope_type || ':' || scope_id AS scope, COUNT(*) AS count
            FROM memories
            WHERE status IN ('candidate', 'needs_evidence')
            {tenancy_where}
            GROUP BY scope_type, scope_id
            ORDER BY count DESC, scope ASC
            LIMIT 20
            """,
            tenancy_params,
        ).fetchall()
        return {
            "card_count": len(cards),
            "cards": cards,
            "scopes": [{"scope": str(row["scope"]), "count": int(row["count"])} for row in scopes],
            "open_questions_by_scope": [
                {"scope": str(row["scope"]), "count": int(row["count"])} for row in open_questions
            ],
            "generation_policy": {
                "source": "active_curated_memory_only",
                "raw_events_included": False,
                "requires_evidence": True,
                "writes_feishu": False,
            },
        }

    def wiki_export_markdown(self, *, scope: str) -> str:
        scope = scope.strip()
        if not scope:
            raise ValueError("scope is required for wiki export")
        compiled = compile_project_memory_cards(MemoryRepository(self.conn), scope=scope)
        return _redact_sensitive_text(str(compiled["markdown"]))

    def graph_workspace(
        self,
        *,
        node_type: str | None = None,
        status: str | None = None,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        query: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        limit = _clamp_limit(limit)
        conditions: list[str] = []
        params: list[Any] = []
        if node_type:
            conditions.append("node_type = ?")
            params.append(node_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if organization_id:
            conditions.append("organization_id = ?")
            params.append(organization_id)
        if query:
            like = f"%{query}%"
            conditions.append("(id LIKE ? OR node_key LIKE ? OR label LIKE ? OR metadata_json LIKE ?)")
            params.extend([like, like, like, like])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        node_rows = self.conn.execute(
            f"""
            SELECT id, tenant_id, organization_id, node_type, node_key, label,
                   visibility_policy, status, metadata_json, first_seen_at,
                   last_seen_at, observation_count
            FROM knowledge_graph_nodes
            {where}
            ORDER BY observation_count DESC, last_seen_at DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        node_ids = [str(row["id"]) for row in node_rows]
        edge_rows: list[sqlite3.Row] = []
        if node_ids:
            placeholders = ", ".join("?" for _ in node_ids)
            edge_conditions = [
                f"(e.source_node_id IN ({placeholders}) OR e.target_node_id IN ({placeholders}))",
            ]
            edge_params: list[Any] = [*node_ids, *node_ids]
            if tenant_id:
                edge_conditions.append("e.tenant_id = ?")
                edge_params.append(tenant_id)
            if organization_id:
                edge_conditions.append("e.organization_id = ?")
                edge_params.append(organization_id)
            edge_rows = self.conn.execute(
                f"""
                SELECT e.id, e.tenant_id, e.organization_id, e.edge_type,
                       e.metadata_json, e.first_seen_at, e.last_seen_at,
                       e.observation_count, e.source_node_id, e.target_node_id,
                       source.label AS source_label, target.label AS target_label,
                       source.node_type AS source_type, target.node_type AS target_type
                FROM knowledge_graph_edges e
                LEFT JOIN knowledge_graph_nodes source ON source.id = e.source_node_id
                LEFT JOIN knowledge_graph_nodes target ON target.id = e.target_node_id
                WHERE {" AND ".join(edge_conditions)}
                ORDER BY e.observation_count DESC, e.last_seen_at DESC, e.id DESC
                LIMIT ?
                """,
                [*edge_params, limit],
            ).fetchall()
        nodes = [_graph_node_row_to_dict(row) for row in node_rows]
        edges = [_graph_edge_row_to_dict(row) for row in edge_rows]
        self._append_compiled_memory_graph(
            nodes,
            edges,
            query=query,
            tenant_id=tenant_id,
            organization_id=organization_id,
            status=status,
            limit=limit,
        )
        return {
            "node_total": self._count("knowledge_graph_nodes"),
            "edge_total": self._count("knowledge_graph_edges"),
            "workspace_node_count": len(nodes),
            "workspace_edge_count": len(edges),
            "nodes_by_type": _count_items_by(nodes, "node_type"),
            "edges_by_type": _count_items_by(edges, "edge_type"),
            "filters": {
                "node_type": node_type,
                "status": status,
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "query": query,
            },
            "nodes": nodes,
            "edges": edges,
        }

    def _append_compiled_memory_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        *,
        query: str | None,
        tenant_id: str | None,
        organization_id: str | None,
        status: str | None,
        limit: int,
    ) -> None:
        if status and status != "active":
            return
        existing_node_ids = {str(node["id"]) for node in nodes}
        existing_node_keys = {str(node.get("node_key")) for node in nodes if node.get("node_key")}
        cards = self.wiki_overview(
            query=query,
            tenant_id=tenant_id,
            organization_id=organization_id,
            limit=max(1, min(30, limit)),
        )["cards"]
        for card in cards:
            memory_node_id = f"memory:{card['id']}"
            if memory_node_id not in existing_node_ids:
                nodes.append(
                    {
                        "id": memory_node_id,
                        "tenant_id": card["tenant_id"],
                        "organization_id": card["organization_id"],
                        "node_type": "memory",
                        "node_key": card["id"],
                        "label": card["subject"],
                        "visibility_policy": card["visibility_policy"],
                        "status": "active",
                        "metadata": {
                            "scope": card["scope"],
                            "type": card["type"],
                            "current_value": card["current_value"],
                            "version": card["version"],
                            "compiled": True,
                        },
                        "first_seen_at": card["updated_at"],
                        "last_seen_at": card["updated_at"],
                        "first_seen_at_iso": card["updated_at_iso"],
                        "last_seen_at_iso": card["updated_at_iso"],
                        "observation_count": max(1, int(card["superseded_version_count"] or 0) + 1),
                    }
                )
                existing_node_ids.add(memory_node_id)
            evidence = card.get("evidence") or {}
            evidence_source_id = evidence.get("source_id")
            if not evidence_source_id:
                continue
            evidence_node_id = f"evidence:{evidence_source_id}"
            if evidence_source_id not in existing_node_keys and evidence_node_id not in existing_node_ids:
                nodes.append(
                    {
                        "id": evidence_node_id,
                        "tenant_id": card["tenant_id"],
                        "organization_id": card["organization_id"],
                        "node_type": "evidence_source",
                        "node_key": evidence_source_id,
                        "label": evidence_source_id,
                        "visibility_policy": card["visibility_policy"],
                        "status": "active",
                        "metadata": {
                            "source_type": evidence.get("source_type"),
                            "document_title": evidence.get("document_title"),
                            "compiled": True,
                        },
                        "first_seen_at": card["updated_at"],
                        "last_seen_at": card["updated_at"],
                        "first_seen_at_iso": card["updated_at_iso"],
                        "last_seen_at_iso": card["updated_at_iso"],
                        "observation_count": 1,
                    }
                )
                existing_node_ids.add(evidence_node_id)
                existing_node_keys.add(str(evidence_source_id))
            target = next(
                (node for node in nodes if node.get("node_key") == evidence_source_id),
                {"id": evidence_node_id, "label": evidence_source_id, "node_type": "evidence_source"},
            )
            edges.append(
                {
                    "id": f"compiled:{card['id']}:{evidence_source_id}",
                    "tenant_id": card["tenant_id"],
                    "organization_id": card["organization_id"],
                    "source_node_id": memory_node_id,
                    "target_node_id": target["id"],
                    "source_label": card["subject"],
                    "target_label": target.get("label"),
                    "source_type": "memory",
                    "target_type": target.get("node_type"),
                    "edge_type": "grounded_by",
                    "metadata": {"compiled": True, "source_type": evidence.get("source_type")},
                    "first_seen_at_iso": card["updated_at_iso"],
                    "last_seen_at_iso": card["updated_at_iso"],
                    "observation_count": 1,
                }
            )

    def list_memories(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = _clamp_limit(limit)
        offset = max(0, offset)
        where, params = self._memory_filters(
            status=status,
            scope=scope,
            tenant_id=tenant_id,
            organization_id=organization_id,
            query=query,
        )
        total = int(self.conn.execute(f"SELECT COUNT(*) FROM memories {where}", params).fetchone()[0])
        rows = self.conn.execute(
            f"""
            SELECT id, tenant_id, organization_id, visibility_policy,
                   scope_type, scope_id, type, subject, current_value, summary,
                   status, confidence, importance, owner_id, created_by, updated_by,
                   source_event_id, active_version_id, created_at, updated_at,
                   expires_at, last_recalled_at, recall_count, source_visibility_revoked_at
            FROM memories
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [_memory_row_to_dict(row) for row in rows]
        evidence_by_memory = self._latest_evidence_by_memory([str(item["id"]) for item in items])
        for item in items:
            item["evidence"] = evidence_by_memory.get(str(item["id"]), [])
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def memory_detail(self, memory_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT id, tenant_id, organization_id, visibility_policy,
                   scope_type, scope_id, type, subject, current_value, summary,
                   reason, status, confidence, importance, owner_id, created_by, updated_by,
                   source_event_id, active_version_id, created_at, updated_at,
                   expires_at, last_recalled_at, recall_count, source_visibility_revoked_at
            FROM memories
            WHERE id = ?
            """,
            (memory_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"memory not found: {memory_id}")
        versions = self.conn.execute(
            """
            SELECT id, memory_id, version_no, value, reason, decision_reason, status,
                   source_event_id, created_by, created_at, supersedes_version_id
            FROM memory_versions
            WHERE memory_id = ?
            ORDER BY version_no DESC
            """,
            (memory_id,),
        ).fetchall()
        evidence = self.conn.execute(
            """
            SELECT e.id, e.memory_id, e.version_id, e.tenant_id, e.organization_id,
                   e.visibility_policy, e.source_type, e.source_url, e.source_event_id,
                   e.quote, e.actor_id, e.actor_display, e.event_time, e.ingested_at,
                   e.source_deleted_at, e.redaction_state, e.created_at,
                   r.source_id, r.raw_json
            FROM memory_evidence e
            LEFT JOIN raw_events r ON r.id = e.source_event_id
            WHERE e.memory_id = ?
            ORDER BY e.created_at DESC, e.id DESC
            """,
            (memory_id,),
        ).fetchall()
        audit = self.conn.execute(
            """
            SELECT audit_id, event_type, action, tool_name, target_type, target_id,
                   memory_id, candidate_id, actor_id, actor_roles, tenant_id,
                   organization_id, scope, permission_decision, reason_code,
                   request_id, trace_id, visible_fields, redacted_fields,
                   source_context, created_at
            FROM memory_audit_events
            WHERE memory_id = ? OR candidate_id = ? OR target_id = ?
            ORDER BY created_at DESC, audit_id DESC
            LIMIT 50
            """,
            (memory_id, memory_id, memory_id),
        ).fetchall()
        return {
            "memory": _memory_row_to_dict(row),
            "versions": [_version_row_to_dict(version) for version in versions],
            "evidence": [_evidence_row_to_dict(item) for item in evidence],
            "audit": [_audit_row_to_dict(item) for item in audit],
        }

    def list_audit(
        self,
        *,
        event_type: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        permission_decision: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = _clamp_limit(limit)
        offset = max(0, offset)
        conditions: list[str] = []
        params: list[Any] = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if actor_id:
            conditions.append("actor_id = ?")
            params.append(actor_id)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if organization_id:
            conditions.append("organization_id = ?")
            params.append(organization_id)
        if permission_decision:
            conditions.append("permission_decision = ?")
            params.append(permission_decision)
        if query:
            like = f"%{query}%"
            conditions.append(
                "(audit_id LIKE ? OR request_id LIKE ? OR trace_id LIKE ? OR target_id LIKE ? OR reason_code LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(self.conn.execute(f"SELECT COUNT(*) FROM memory_audit_events {where}", params).fetchone()[0])
        rows = self.conn.execute(
            f"""
            SELECT audit_id, event_type, action, tool_name, target_type, target_id,
                   memory_id, candidate_id, actor_id, actor_roles, tenant_id,
                   organization_id, scope, permission_decision, reason_code,
                   request_id, trace_id, visible_fields, redacted_fields,
                   source_context, created_at
            FROM memory_audit_events
            {where}
            ORDER BY created_at DESC, audit_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "items": [_audit_row_to_dict(row) for row in rows]}

    def list_tables(self) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        tables = []
        for row in rows:
            table = str(row["name"])
            columns = self.conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
            tables.append(
                {
                    "name": table,
                    "row_count": self._count(table),
                    "columns": [
                        {
                            "name": str(column["name"]),
                            "type": str(column["type"]),
                            "notnull": bool(column["notnull"]),
                            "primary_key": bool(column["pk"]),
                        }
                        for column in columns
                    ],
                }
            )
        user_version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        return {"user_version": user_version, "tables": tables}

    def _memory_filters(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        tenant_id: str | None = None,
        organization_id: str | None = None,
        query: str | None = None,
    ) -> tuple[str, list[Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if scope:
            conditions.append("(scope_type || ':' || scope_id) = ?")
            params.append(scope)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if organization_id:
            conditions.append("organization_id = ?")
            params.append(organization_id)
        if query:
            like = f"%{query}%"
            conditions.append("(id LIKE ? OR subject LIKE ? OR current_value LIKE ? OR COALESCE(summary, '') LIKE ?)")
            params.extend([like, like, like, like])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return where, params

    def _latest_evidence_by_memory(self, memory_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not memory_ids:
            return {}
        placeholders = ", ".join("?" for _ in memory_ids)
        rows = self.conn.execute(
            f"""
            SELECT e.id, e.memory_id, e.version_id, e.tenant_id, e.organization_id,
                   e.visibility_policy, e.source_type, e.source_url, e.source_event_id,
                   e.quote, e.actor_id, e.actor_display, e.event_time, e.ingested_at,
                   e.source_deleted_at, e.redaction_state, e.created_at,
                   r.source_id, r.raw_json
            FROM memory_evidence e
            LEFT JOIN raw_events r ON r.id = e.source_event_id
            WHERE e.memory_id IN ({placeholders})
            ORDER BY e.created_at DESC, e.id DESC
            """,
            memory_ids,
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            bucket = grouped.setdefault(str(row["memory_id"]), [])
            if len(bucket) < 3:
                bucket.append(_evidence_row_to_dict(row))
        return grouped

    def _count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0])

    def _count_by(self, table: str, column: str) -> dict[str, int]:
        rows = self.conn.execute(
            f"""
            SELECT {_quote_identifier(column)} AS group_key, COUNT(*) AS count
            FROM {_quote_identifier(table)}
            GROUP BY {_quote_identifier(column)}
            ORDER BY count DESC, group_key ASC
            """
        ).fetchall()
        return {str(row["group_key"]): int(row["count"]) for row in rows}

    def _count_tenant_rows(
        self,
        table: str,
        *,
        tenant_id: str,
        organization_id: str,
        extra_where: str = "",
        extra_params: list[Any] | None = None,
    ) -> int:
        return int(
            self.conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {_quote_identifier(table)}
                WHERE tenant_id = ?
                  AND COALESCE(organization_id, '-') = ?
                {extra_where}
                """,
                [tenant_id, organization_id, *(extra_params or [])],
            ).fetchone()[0]
        )

    def _tenant_org_overview(self, tenant_id: str, organization_id: str) -> dict[str, Any]:
        policy = self._tenant_policy_for(tenant_id, organization_id)
        active_memory_count = self._count_tenant_rows(
            "memories",
            tenant_id=tenant_id,
            organization_id=organization_id,
            extra_where="AND status = ?",
            extra_params=["active"],
        )
        candidate_memory_count = self._count_tenant_rows(
            "memories",
            tenant_id=tenant_id,
            organization_id=organization_id,
            extra_where="AND status = ?",
            extra_params=["candidate"],
        )
        needs_evidence_memory_count = self._count_tenant_rows(
            "memories",
            tenant_id=tenant_id,
            organization_id=organization_id,
            extra_where="AND status = ?",
            extra_params=["needs_evidence"],
        )
        denied_audit_count = self._count_tenant_rows(
            "memory_audit_events",
            tenant_id=tenant_id,
            organization_id=organization_id,
            extra_where="AND permission_decision = ?",
            extra_params=["deny"],
        )
        scopes = self.conn.execute(
            """
            SELECT scope_type || ':' || scope_id AS scope, COUNT(*) AS count
            FROM memories
            WHERE tenant_id = ?
              AND COALESCE(organization_id, '-') = ?
            GROUP BY scope_type, scope_id
            ORDER BY count DESC, scope ASC
            LIMIT 8
            """,
            (tenant_id, organization_id),
        ).fetchall()
        latest_activity = self.conn.execute(
            """
            SELECT MAX(activity_at) AS latest_activity
            FROM (
              SELECT updated_at AS activity_at
              FROM memories
              WHERE tenant_id = ? AND COALESCE(organization_id, '-') = ?
              UNION ALL
              SELECT event_time AS activity_at
              FROM raw_events
              WHERE tenant_id = ? AND COALESCE(organization_id, '-') = ?
              UNION ALL
              SELECT created_at AS activity_at
              FROM memory_audit_events
              WHERE tenant_id = ? AND COALESCE(organization_id, '-') = ?
              UNION ALL
              SELECT last_seen_at AS activity_at
              FROM knowledge_graph_nodes
              WHERE tenant_id = ? AND COALESCE(organization_id, '-') = ?
            )
            """,
            (
                tenant_id,
                organization_id,
                tenant_id,
                organization_id,
                tenant_id,
                organization_id,
                tenant_id,
                organization_id,
            ),
        ).fetchone()["latest_activity"]
        if latest_activity is None and policy:
            latest_activity = policy.get("updated_at")
        return {
            "tenant_id": tenant_id,
            "organization_id": None if organization_id == "-" else organization_id,
            "memory_total": self._count_tenant_rows("memories", tenant_id=tenant_id, organization_id=organization_id),
            "active_memory_count": active_memory_count,
            "candidate_memory_count": candidate_memory_count,
            "needs_evidence_memory_count": needs_evidence_memory_count,
            "open_review_count": candidate_memory_count + needs_evidence_memory_count,
            "raw_event_count": self._count_tenant_rows(
                "raw_events", tenant_id=tenant_id, organization_id=organization_id
            ),
            "graph_node_count": self._count_tenant_rows(
                "knowledge_graph_nodes",
                tenant_id=tenant_id,
                organization_id=organization_id,
            ),
            "graph_edge_count": self._count_tenant_rows(
                "knowledge_graph_edges",
                tenant_id=tenant_id,
                organization_id=organization_id,
            ),
            "audit_total": self._count_tenant_rows(
                "memory_audit_events",
                tenant_id=tenant_id,
                organization_id=organization_id,
            ),
            "denied_audit_count": denied_audit_count,
            "scopes": [{"scope": str(row["scope"]), "count": int(row["count"])} for row in scopes],
            "latest_activity_at": latest_activity,
            "latest_activity_at_iso": _ms_to_iso(latest_activity),
            "tenant_policy": policy,
            "readiness": {
                "data_isolation": "derived_from_tenant_org_columns",
                "access_gate": "admin_viewer_token_or_loopback_sso_header",
                "sso": "header_gate_available_not_idp_validated",
                "policy_editor": "configured" if policy else "available_unconfigured",
                "config_write_api": "admin_only_tenant_policy_upsert",
                "production_db": "not_verified",
            },
        }

    def _tenant_policy_for(self, tenant_id: str, organization_id: str) -> dict[str, Any] | None:
        if not _table_exists(self.conn, "tenant_admin_policies"):
            return None
        row = self.conn.execute(
            """
            SELECT id, tenant_id, organization_id, status, default_visibility_policy,
                   auto_confirm_low_risk, require_review_for_conflicts,
                   reviewer_roles, admin_users, sso_allowed_domains, notes,
                   created_by, updated_by, created_at, updated_at
            FROM tenant_admin_policies
            WHERE tenant_id = ? AND COALESCE(organization_id, '-') = ?
            """,
            (tenant_id, organization_id),
        ).fetchone()
        return _tenant_policy_row_to_dict(row) if row else None

    def _recent_raw_events(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, tenant_id, organization_id, visibility_policy, source_type,
                   source_id, source_url, ingestion_status, scope_type, scope_id,
                   sender_id, event_time, content, raw_json, created_at
            FROM raw_events
            ORDER BY event_time DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (_clamp_limit(limit),),
        ).fetchall()
        return [_raw_event_row_to_dict(row) for row in rows]

    def _knowledge_graph_overview(self, *, limit: int) -> dict[str, Any]:
        recent_nodes = self.conn.execute(
            """
            SELECT id, tenant_id, organization_id, node_type, node_key, label,
                   visibility_policy, status, metadata_json, first_seen_at,
                   last_seen_at, observation_count
            FROM knowledge_graph_nodes
            ORDER BY last_seen_at DESC, observation_count DESC, id DESC
            LIMIT ?
            """,
            (_clamp_limit(limit),),
        ).fetchall()
        recent_edges = self.conn.execute(
            """
            SELECT e.id, e.tenant_id, e.organization_id, e.edge_type,
                   e.metadata_json, e.first_seen_at, e.last_seen_at,
                   e.observation_count, source.label AS source_label,
                   target.label AS target_label
            FROM knowledge_graph_edges e
            LEFT JOIN knowledge_graph_nodes source ON source.id = e.source_node_id
            LEFT JOIN knowledge_graph_nodes target ON target.id = e.target_node_id
            ORDER BY e.last_seen_at DESC, e.observation_count DESC, e.id DESC
            LIMIT ?
            """,
            (_clamp_limit(limit),),
        ).fetchall()
        return {
            "node_total": self._count("knowledge_graph_nodes"),
            "edge_total": self._count("knowledge_graph_edges"),
            "nodes_by_type": self._count_by("knowledge_graph_nodes", "node_type"),
            "edges_by_type": self._count_by("knowledge_graph_edges", "edge_type"),
            "recent_nodes": [_graph_node_row_to_dict(row) for row in recent_nodes],
            "recent_edges": [_graph_edge_row_to_dict(row) for row in recent_edges],
        }


class CopilotAdminServer(ThreadingHTTPServer):
    db_path: str
    auth_token: str | None
    viewer_token: str | None
    sso_config: AdminSsoConfig
    production_evidence_manifest: str


def create_admin_server(
    host: str,
    port: int,
    db_path: str | Path | None = None,
    *,
    auth_token: str | None = None,
    viewer_token: str | None = None,
    sso_config: AdminSsoConfig | None = None,
    production_evidence_manifest: str | Path | None = None,
) -> CopilotAdminServer:
    resolved_db_path = str(db_path or db_path_from_env())
    resolved_auth_token = auth_token if auth_token is not None else _admin_token_from_env()
    resolved_viewer_token = viewer_token if viewer_token is not None else _admin_viewer_token_from_env()
    resolved_sso_config = sso_config or admin_sso_config_from_env()
    resolved_production_evidence_manifest = str(
        production_evidence_manifest or _admin_production_evidence_manifest_from_env()
    )

    class Handler(CopilotAdminHandler):
        pass

    Handler.db_path = resolved_db_path
    Handler.auth_token = resolved_auth_token
    Handler.viewer_token = resolved_viewer_token
    Handler.sso_config = resolved_sso_config
    Handler.production_evidence_manifest = resolved_production_evidence_manifest
    server = CopilotAdminServer((host, port), Handler)
    server.db_path = resolved_db_path
    server.auth_token = resolved_auth_token
    server.viewer_token = resolved_viewer_token
    server.sso_config = resolved_sso_config
    server.production_evidence_manifest = resolved_production_evidence_manifest
    return server


class CopilotAdminHandler(BaseHTTPRequestHandler):
    db_path = str(db_path_from_env())
    auth_token: str | None = None
    viewer_token: str | None = None
    sso_config = AdminSsoConfig()
    production_evidence_manifest = str(DEFAULT_PRODUCTION_EVIDENCE_MANIFEST_PATH)
    server_version = "FeishuMemoryCopilotAdmin/0.1"

    def do_GET(self) -> None:
        self._handle_get(send_body=True)

    def do_HEAD(self) -> None:
        self._handle_get(send_body=False)

    def do_POST(self) -> None:
        self._handle_post()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_get(self, *, send_body: bool) -> None:
        parsed = urlparse(self.path)
        requires_auth = parsed.path.startswith("/api/") or parsed.path == "/metrics"
        auth_role = self._auth_role(parsed.query) if requires_auth else "public"
        try:
            if requires_auth and auth_role is None:
                self._send_json(
                    {"ok": False, "error": {"code": "admin_auth_required", "message": "Admin token required."}},
                    status=HTTPStatus.UNAUTHORIZED,
                    send_body=send_body,
                    headers={"WWW-Authenticate": 'Bearer realm="Feishu Memory Copilot Admin"'},
                )
                return
            if parsed.path == "/":
                self._send_html(_index_html(), send_body=send_body)
                return
            if parsed.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                return
            if parsed.path == "/healthz":
                self._send_json({"ok": True, "service": "copilot_admin"}, send_body=send_body)
                return
            if parsed.path == "/metrics":
                self._send_text(
                    self._metrics_text(),
                    content_type="text/plain; version=0.0.4; charset=utf-8",
                    send_body=send_body,
                )
                return
            if parsed.path == "/api/summary":
                self._send_json(self._api_summary(), send_body=send_body)
                return
            if parsed.path == "/api/health":
                self._send_json(self._api_health(), send_body=send_body)
                return
            if parsed.path == "/api/live":
                self._send_json(self._api_live(), send_body=send_body)
                return
            if parsed.path == "/api/launch-readiness":
                self._send_json(self._api_launch_readiness(), send_body=send_body)
                return
            if parsed.path == "/api/production-evidence":
                self._send_json(self._api_production_evidence(), send_body=send_body)
                return
            if parsed.path == "/api/tenants":
                self._send_json(self._api_tenants(parsed.query), send_body=send_body)
                return
            if parsed.path == "/api/tenant-policies":
                self._send_json(self._api_tenant_policies(parsed.query), send_body=send_body)
                return
            if parsed.path == "/api/memories":
                self._send_json(self._api_memories(parsed.query), send_body=send_body)
                return
            if parsed.path.startswith("/api/memories/"):
                memory_id = unquote(parsed.path.removeprefix("/api/memories/"))
                self._send_json(self._api_memory_detail(memory_id), send_body=send_body)
                return
            if parsed.path == "/api/audit":
                self._send_json(self._api_audit(parsed.query), send_body=send_body)
                return
            if parsed.path == "/api/wiki/export":
                if auth_role != "admin":
                    self._send_json(
                        {
                            "ok": False,
                            "error": {
                                "code": "admin_export_forbidden",
                                "message": "Wiki export requires an admin token.",
                            },
                        },
                        status=HTTPStatus.FORBIDDEN,
                        send_body=send_body,
                    )
                    return
                self._send_text(
                    self._api_wiki_export(parsed.query),
                    content_type="text/markdown; charset=utf-8",
                    send_body=send_body,
                    headers={"Content-Disposition": 'attachment; filename="copilot-memory-wiki.md"'},
                )
                return
            if parsed.path == "/api/wiki":
                self._send_json(self._api_wiki(parsed.query), send_body=send_body)
                return
            if parsed.path == "/api/graph":
                self._send_json(self._api_graph(parsed.query), send_body=send_body)
                return
            if parsed.path == "/api/tables":
                self._send_json(self._api_tables(), send_body=send_body)
                return
            self._send_json(
                {"ok": False, "error": {"code": "not_found"}}, status=HTTPStatus.NOT_FOUND, send_body=send_body
            )
        except LookupError as exc:
            self._send_json(
                {"ok": False, "error": {"code": "not_found", "message": str(exc)}},
                status=HTTPStatus.NOT_FOUND,
                send_body=send_body,
            )
        except sqlite3.OperationalError as exc:
            self._send_json(
                {"ok": False, "error": {"code": "database_unavailable", "message": str(exc)}},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                send_body=send_body,
            )
        except ValueError as exc:
            self._send_json(
                {"ok": False, "error": {"code": "bad_request", "message": str(exc)}},
                status=HTTPStatus.BAD_REQUEST,
                send_body=send_body,
            )

    def _handle_post(self) -> None:
        parsed = urlparse(self.path)
        auth_role = self._auth_role(parsed.query) if parsed.path.startswith("/api/") else None
        try:
            if parsed.path.startswith("/api/") and auth_role is None:
                self._send_json(
                    {"ok": False, "error": {"code": "admin_auth_required", "message": "Admin token required."}},
                    status=HTTPStatus.UNAUTHORIZED,
                    send_body=True,
                    headers={"WWW-Authenticate": 'Bearer realm="Feishu Memory Copilot Admin"'},
                )
                return
            if parsed.path == "/api/tenant-policies":
                if auth_role != "admin":
                    self._send_json(
                        {
                            "ok": False,
                            "error": {
                                "code": "admin_policy_forbidden",
                                "message": "Tenant policy changes require an admin token.",
                            },
                        },
                        status=HTTPStatus.FORBIDDEN,
                        send_body=True,
                    )
                    return
                payload = self._read_json_body()
                self._send_json(self._api_tenant_policy_upsert(payload, actor_id=self._auth_actor_id()), send_body=True)
                return
            self._method_not_allowed()
        except ValueError as exc:
            self._send_json(
                {"ok": False, "error": {"code": "bad_request", "message": str(exc)}},
                status=HTTPStatus.BAD_REQUEST,
                send_body=True,
            )
        except sqlite3.OperationalError as exc:
            self._send_json(
                {"ok": False, "error": {"code": "database_unavailable", "message": str(exc)}},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                send_body=True,
            )

    def _api_summary(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            return {"ok": True, "db_path": self.db_path, "data": AdminQueryService(conn).summary()}

    def _api_health(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            service = AdminQueryService(conn)
            wiki = service.wiki_overview(limit=1)
            graph = service.graph_workspace(limit=10)
            policies = service.tenant_policies(limit=1)
            launch = service.launch_readiness()
            return {
                "ok": True,
                "db_path": self.db_path,
                "data": {
                    "database": "readable",
                    "auth": "enabled"
                    if self.auth_token or self.viewer_token or self.sso_config.enabled
                    else "disabled_local_only",
                    "access_policy": {
                        "admin_token_configured": bool(self.auth_token),
                        "viewer_token_configured": bool(self.viewer_token),
                        "sso_enabled": bool(self.sso_config.enabled),
                        "sso_user_header": self.sso_config.user_header if self.sso_config.enabled else None,
                        "sso_email_header": self.sso_config.email_header if self.sso_config.enabled else None,
                        "sso_admin_users_configured": bool(self.sso_config.admin_users),
                        "sso_viewer_users_configured": bool(self.sso_config.viewer_users),
                        "sso_allowed_domains_configured": bool(self.sso_config.allowed_domains),
                        "viewer_token_can_export": False,
                        "wiki_export_requires_admin_token": bool(
                            self.viewer_token or self.auth_token or self.sso_config.enabled
                        ),
                    },
                    "read_only": False,
                    "read_only_knowledge_surfaces": True,
                    "tenant_policy_write_api": True,
                    "tenant_policy_table_available": bool(policies.get("available")),
                    "wiki_ready": bool(wiki.get("generation_policy"))
                    and wiki["generation_policy"].get("source") == "active_curated_memory_only",
                    "graph_ready": int(graph.get("workspace_node_count") or 0) >= 0,
                    "wiki_card_count": int(wiki.get("card_count") or 0),
                    "graph_workspace_node_count": int(graph.get("workspace_node_count") or 0),
                    "launch_readiness": {
                        "staging_status": launch.get("staging_status"),
                        "production_status": launch.get("production_status"),
                    },
                    "boundary": "local/pre-production admin readiness; no production deployment claim.",
                },
            }

    def _api_live(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            return {"ok": True, "db_path": self.db_path, "data": AdminQueryService(conn).live_overview()}

    def _api_launch_readiness(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).launch_readiness()
        production_evidence = run_production_evidence_check(Path(self.production_evidence_manifest))
        access_checks = [
            _launch_check(
                "shared_access_gate",
                "Shared access gate",
                "pass" if self.auth_token or self.viewer_token or self.sso_config.enabled else "warning",
                "token_or_sso_configured"
                if self.auth_token or self.viewer_token or self.sso_config.enabled
                else "local_only_auth_disabled",
                "Configure admin/viewer token or loopback SSO header gate before shared staging.",
            ),
            _launch_check(
                "admin_export_gate",
                "Admin export/write gate",
                "pass" if self.auth_token or (self.sso_config.enabled and self.sso_config.admin_users) else "warning",
                "admin_export_available"
                if self.auth_token or (self.sso_config.enabled and self.sso_config.admin_users)
                else "no_admin_export_identity",
                "Configure an admin token or SSO admin allowlist before Markdown export or tenant policy edits.",
            ),
        ]
        production_evidence_status = (
            "pass"
            if production_evidence.get("production_ready")
            else "warning"
            if production_evidence.get("ok")
            else "fail"
        )
        production_evidence_check = _launch_check(
            "production_evidence_manifest",
            "Production evidence manifest",
            production_evidence_status,
            "production_ready=true"
            if production_evidence.get("production_ready")
            else f"production_ready=false; warnings={len(production_evidence.get('warning_checks') or [])}",
            "Fill and validate real DB, IdP, TLS, monitoring, and 24h live evidence.",
        )
        data["checks"] = [*data.get("checks", []), *access_checks, production_evidence_check]
        data["staging_status"] = _rollup_status(data["checks"])
        data["access_policy"] = {
            "admin_token_configured": bool(self.auth_token),
            "viewer_token_configured": bool(self.viewer_token),
            "sso_enabled": bool(self.sso_config.enabled),
            "sso_admin_users_configured": bool(self.sso_config.admin_users),
            "viewer_token_can_export": False,
            "tenant_policy_write_requires_admin": True,
        }
        data["production_evidence"] = _compact_production_evidence(production_evidence)
        return {"ok": True, "db_path": self.db_path, "data": data}

    def _api_production_evidence(self) -> dict[str, Any]:
        data = run_production_evidence_check(Path(self.production_evidence_manifest))
        return {"ok": bool(data.get("ok")), "data": data}

    def _metrics_text(self) -> str:
        with _open_readonly_connection(self.db_path) as conn:
            return AdminQueryService(conn).prometheus_metrics()

    def _api_tenants(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).tenant_overview(
                tenant_id=_param(params, "tenant_id"),
                organization_id=_param(params, "organization_id"),
                limit=_int_param(params, "limit", 80),
            )
        return {"ok": True, "data": data}

    def _api_tenant_policies(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).tenant_policies(
                tenant_id=_param(params, "tenant_id"),
                organization_id=_param(params, "organization_id"),
                limit=_int_param(params, "limit", 80),
            )
        return {"ok": True, "data": data}

    def _api_tenant_policy_upsert(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        with _open_writable_connection(self.db_path) as conn:
            init_db(conn)
            data = AdminQueryService(conn).upsert_tenant_policy(payload, actor_id=actor_id)
        return {"ok": True, "data": data}

    def _api_memories(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).list_memories(
                status=_param(params, "status"),
                scope=_param(params, "scope"),
                tenant_id=_param(params, "tenant_id"),
                organization_id=_param(params, "organization_id"),
                query=_param(params, "q"),
                limit=_int_param(params, "limit", 50),
                offset=_int_param(params, "offset", 0),
            )
        return {"ok": True, "data": data}

    def _api_memory_detail(self, memory_id: str) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).memory_detail(memory_id)
        return {"ok": True, "data": data}

    def _api_audit(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).list_audit(
                event_type=_param(params, "event_type"),
                actor_id=_param(params, "actor_id"),
                tenant_id=_param(params, "tenant_id"),
                organization_id=_param(params, "organization_id"),
                permission_decision=_param(params, "permission_decision"),
                query=_param(params, "q"),
                limit=_int_param(params, "limit", 50),
                offset=_int_param(params, "offset", 0),
            )
        return {"ok": True, "data": data}

    def _api_wiki(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).wiki_overview(
                scope=_param(params, "scope"),
                tenant_id=_param(params, "tenant_id"),
                organization_id=_param(params, "organization_id"),
                query=_param(params, "q"),
                limit=_int_param(params, "limit", 50),
            )
        return {"ok": True, "data": data}

    def _api_wiki_export(self, query_string: str) -> str:
        params = parse_qs(query_string)
        scope = _param(params, "scope")
        if not scope:
            raise ValueError("scope is required for wiki export")
        with _open_readonly_connection(self.db_path) as conn:
            return AdminQueryService(conn).wiki_export_markdown(scope=scope)

    def _api_graph(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).graph_workspace(
                node_type=_param(params, "node_type"),
                status=_param(params, "status"),
                tenant_id=_param(params, "tenant_id"),
                organization_id=_param(params, "organization_id"),
                query=_param(params, "q"),
                limit=_int_param(params, "limit", 80),
            )
        return {"ok": True, "data": data}

    def _api_tables(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            return {"ok": True, "db_path": self.db_path, "data": AdminQueryService(conn).list_tables()}

    def _send_html(self, body: str, *, send_body: bool) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if send_body:
            self.wfile.write(encoded)

    def _send_text(
        self,
        body: str,
        *,
        content_type: str,
        send_body: bool,
        headers: dict[str, str] | None = None,
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if send_body:
            self.wfile.write(encoded)

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        send_body: bool,
        headers: dict[str, str] | None = None,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if send_body:
            self.wfile.write(encoded)

    def _method_not_allowed(self) -> None:
        self._send_json(
            {
                "ok": False,
                "error": {
                    "code": "admin_method_not_allowed",
                    "message": "Only GET/HEAD and admin-only POST /api/tenant-policies are supported.",
                },
            },
            status=HTTPStatus.METHOD_NOT_ALLOWED,
            send_body=True,
        )

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("JSON body is required")
        if length > 65536:
            raise ValueError("JSON body is too large")
        body = self.rfile.read(length)
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _auth_role(self, query_string: str) -> str | None:
        if not self.auth_token and not self.viewer_token and not self.sso_config.enabled:
            return "admin"
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
            if self.auth_token and hmac.compare_digest(token, self.auth_token):
                return "admin"
            if self.viewer_token and hmac.compare_digest(token, self.viewer_token):
                return "viewer"
        params = parse_qs(query_string)
        query_token = _param(params, "admin_token")
        if query_token and self.auth_token and hmac.compare_digest(query_token, self.auth_token):
            return "admin"
        viewer_query_token = _param(params, "viewer_token")
        if viewer_query_token and self.viewer_token and hmac.compare_digest(viewer_query_token, self.viewer_token):
            return "viewer"
        sso_role = self._sso_auth_role()
        if sso_role is not None:
            return sso_role
        return None

    def _sso_auth_role(self) -> str | None:
        if not self.sso_config.enabled:
            return None
        if not _is_loopback_client(self.client_address[0]):
            return None
        user = self.headers.get(self.sso_config.user_header)
        email = self.headers.get(self.sso_config.email_header)
        return self.sso_config.role_for(user=user, email=email)

    def _auth_actor_id(self) -> str:
        if self.sso_config.enabled and _is_loopback_client(self.client_address[0]):
            email = self.headers.get(self.sso_config.email_header)
            user = self.headers.get(self.sso_config.user_header)
            identity = (email or user or "").strip()
            if identity:
                return f"sso:{identity.lower()}"
        return "copilot_admin"


def _open_readonly_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _open_writable_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _admin_token_from_env() -> str | None:
    for name in ADMIN_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _admin_viewer_token_from_env() -> str | None:
    for name in ADMIN_VIEWER_TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _admin_production_evidence_manifest_from_env() -> Path:
    value = _env_first(ADMIN_PRODUCTION_EVIDENCE_MANIFEST_ENV_NAMES)
    if value:
        return Path(value).expanduser()
    return DEFAULT_PRODUCTION_EVIDENCE_MANIFEST_PATH


def admin_sso_config_from_env() -> AdminSsoConfig:
    return AdminSsoConfig(
        enabled=_env_bool(ADMIN_SSO_ENABLED_ENV_NAMES),
        user_header=_env_first(ADMIN_SSO_USER_HEADER_ENV_NAMES) or "X-Forwarded-User",
        email_header=_env_first(ADMIN_SSO_EMAIL_HEADER_ENV_NAMES) or "X-Forwarded-Email",
        admin_users=frozenset(_env_csv(ADMIN_SSO_ADMIN_USERS_ENV_NAMES)),
        viewer_users=frozenset(_env_csv(ADMIN_SSO_VIEWER_USERS_ENV_NAMES)),
        allowed_domains=frozenset(_env_csv(ADMIN_SSO_ALLOWED_DOMAINS_ENV_NAMES)),
    )


def _env_bool(names: tuple[str, ...]) -> bool:
    value = _env_first(names)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_first(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return None


def _env_csv(names: tuple[str, ...]) -> list[str]:
    value = _env_first(names)
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _is_loopback_client(address: str) -> bool:
    return address in {"127.0.0.1", "::1", "localhost"} or address.startswith("127.")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _tenant_policy_id(tenant_id: str, organization_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}\n{organization_id}".encode("utf-8")).hexdigest()[:16]
    return f"tenant_policy_{digest}"


def _validate_tenant_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _required_policy_string(payload, "tenant_id", max_len=160)
    organization_id = _required_policy_string(payload, "organization_id", max_len=160)
    status = _optional_policy_string(payload, "status", default="active", max_len=32)
    if status not in {"active", "disabled"}:
        raise ValueError("status must be active or disabled")
    default_visibility_policy = _optional_policy_string(
        payload,
        "default_visibility_policy",
        default="team",
        max_len=32,
    )
    if default_visibility_policy not in {"private", "team", "project", "org"}:
        raise ValueError("default_visibility_policy must be private, team, project, or org")
    return {
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "status": status,
        "default_visibility_policy": default_visibility_policy,
        "auto_confirm_low_risk": _optional_bool(payload, "auto_confirm_low_risk", default=True),
        "require_review_for_conflicts": _optional_bool(payload, "require_review_for_conflicts", default=True),
        "reviewer_roles": _string_list(payload.get("reviewer_roles"), field="reviewer_roles"),
        "admin_users": _string_list(payload.get("admin_users"), field="admin_users"),
        "sso_allowed_domains": _string_list(payload.get("sso_allowed_domains"), field="sso_allowed_domains"),
        "notes": _optional_policy_string(payload, "notes", default="", max_len=1000),
    }


def _required_policy_string(payload: dict[str, Any], field: str, *, max_len: int) -> str:
    value = _optional_policy_string(payload, field, default="", max_len=max_len)
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _optional_policy_string(payload: dict[str, Any], field: str, *, default: str, max_len: int) -> str:
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{field} is too long")
    return value


def _optional_bool(payload: dict[str, Any], field: str, *, default: bool) -> bool:
    value = payload.get(field, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a boolean")


def _string_list(value: Any, *, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} items must be strings")
        normalized = item.strip().lower()
        if normalized and normalized not in items:
            items.append(normalized[:160])
    return items[:50]


def _tenant_policy_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    payload = dict(row)
    payload["auto_confirm_low_risk"] = bool(payload.get("auto_confirm_low_risk"))
    payload["require_review_for_conflicts"] = bool(payload.get("require_review_for_conflicts"))
    payload["reviewer_roles"] = _loads_json(payload.get("reviewer_roles"), [])
    payload["admin_users"] = _loads_json(payload.get("admin_users"), [])
    payload["sso_allowed_domains"] = _loads_json(payload.get("sso_allowed_domains"), [])
    payload["created_at_iso"] = _ms_to_iso(payload.get("created_at"))
    payload["updated_at_iso"] = _ms_to_iso(payload.get("updated_at"))
    return payload


def _memory_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["current_value"] = _redact_sensitive_text(payload.get("current_value"))
    payload["summary"] = _redact_sensitive_text(payload.get("summary"))
    payload["scope"] = f"{row['scope_type']}:{row['scope_id']}"
    for key in ("created_at", "updated_at", "expires_at", "last_recalled_at", "source_visibility_revoked_at"):
        payload[f"{key}_iso"] = _ms_to_iso(payload.get(key))
    return payload


def _wiki_card_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    raw = _loads_json(row["raw_json"], {})
    document_title = raw.get("document_title") if isinstance(raw, dict) else None
    document_token = raw.get("document_token") if isinstance(raw, dict) else None
    source_id = row["raw_source_id"] or row["evidence_source_event_id"]
    return {
        "id": str(row["id"]),
        "tenant_id": row["tenant_id"],
        "organization_id": row["organization_id"],
        "visibility_policy": row["visibility_policy"],
        "scope": f"{row['scope_type']}:{row['scope_id']}",
        "type": row["type"],
        "subject": row["subject"],
        "current_value": _redact_sensitive_text(row["current_value"]),
        "summary": _redact_sensitive_text(row["summary"]),
        "confidence": row["confidence"],
        "importance": row["importance"],
        "owner_id": row["owner_id"],
        "updated_at": row["updated_at"],
        "updated_at_iso": _ms_to_iso(row["updated_at"]),
        "version": row["version_no"],
        "superseded_version_count": int(row["superseded_version_count"] or 0),
        "evidence": {
            "quote": _redact_sensitive_text(row["evidence_quote"]),
            "source_type": row["evidence_source_type"],
            "source_id": source_id,
            "source_url": row["evidence_source_url"],
            "document_title": document_title,
            "document_token": document_token,
            "actor_display": row["evidence_actor_display"],
            "event_time_iso": _ms_to_iso(row["evidence_event_time"]),
        },
    }


def _version_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["value"] = _redact_sensitive_text(payload.get("value"))
    payload["reason"] = _redact_sensitive_text(payload.get("reason"))
    payload["decision_reason"] = _redact_sensitive_text(payload.get("decision_reason"))
    payload["created_at_iso"] = _ms_to_iso(payload.get("created_at"))
    return payload


def _evidence_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["quote"] = _redact_sensitive_text(payload.get("quote"))
    raw_json = payload.pop("raw_json", None)
    raw = _loads_json(raw_json, {})
    if isinstance(raw, dict):
        payload["document_token"] = raw.get("document_token")
        payload["document_title"] = raw.get("document_title")
    payload["created_at_iso"] = _ms_to_iso(payload.get("created_at"))
    payload["event_time_iso"] = _ms_to_iso(payload.get("event_time"))
    payload["ingested_at_iso"] = _ms_to_iso(payload.get("ingested_at"))
    return payload


def _raw_event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["content"] = _redact_sensitive_text(payload.get("content"))
    payload["scope"] = f"{row['scope_type']}:{row['scope_id']}"
    payload["raw_json"] = _loads_json(payload.get("raw_json"), {})
    payload["event_time_iso"] = _ms_to_iso(payload.get("event_time"))
    payload["created_at_iso"] = _ms_to_iso(payload.get("created_at"))
    return payload


def _audit_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    for key in ("actor_roles", "visible_fields", "redacted_fields"):
        payload[key] = _loads_json(payload.get(key), [])
    payload["source_context"] = _loads_json(payload.get("source_context"), {})
    payload["created_at_iso"] = _ms_to_iso(payload.get("created_at"))
    return payload


def _redact_sensitive_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    patterns = [
        r"(?i)(app_secret\s*=\s*)[^\s,;]+",
        r"(?i)(token\s*=\s*)[^\s,;]+",
        r"(?i)(api[_-]?key\s*=\s*)[^\s,;]+",
    ]
    redacted = value
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
    return redacted


def _graph_node_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["metadata"] = _loads_json(payload.pop("metadata_json", None), {})
    payload["first_seen_at_iso"] = _ms_to_iso(payload.get("first_seen_at"))
    payload["last_seen_at_iso"] = _ms_to_iso(payload.get("last_seen_at"))
    return payload


def _graph_edge_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["metadata"] = _loads_json(payload.pop("metadata_json", None), {})
    payload["first_seen_at_iso"] = _ms_to_iso(payload.get("first_seen_at"))
    payload["last_seen_at_iso"] = _ms_to_iso(payload.get("last_seen_at"))
    return payload


def _loads_json(value: Any, fallback: Any) -> Any:
    if not isinstance(value, str):
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _ms_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(int(value) / 1000, tz=_dt.timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("invalid SQLite identifier")
    return '"' + identifier.replace('"', '""') + '"'


def _tenancy_where(
    *,
    alias: str | None,
    tenant_id: str | None,
    organization_id: str | None,
) -> tuple[str, list[Any]]:
    prefix = f"{alias}." if alias else ""
    conditions: list[str] = []
    params: list[Any] = []
    if tenant_id:
        conditions.append(f"{prefix}tenant_id = ?")
        params.append(tenant_id)
    if organization_id:
        conditions.append(f"{prefix}organization_id = ?")
        params.append(organization_id)
    return (" AND " + " AND ".join(conditions), params) if conditions else ("", [])


def _count_items_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "-")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _launch_check(
    check_id: str,
    label: str,
    status: str,
    evidence: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "evidence": evidence,
        "next_step": "" if status == "pass" else next_step,
    }


def _rollup_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "pass"


def _metric_label_value(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _compact_production_evidence(result: dict[str, Any]) -> dict[str, Any]:
    checks = result.get("checks") if isinstance(result.get("checks"), dict) else {}
    production_sections = {
        "production_db",
        "enterprise_idp_sso",
        "production_domain_tls",
        "production_monitoring",
        "productized_live_long_run",
    }
    section_status = {
        name: check.get("status")
        for name, check in checks.items()
        if name in production_sections and isinstance(check, dict)
    }
    return {
        "ok": bool(result.get("ok")),
        "production_ready": bool(result.get("production_ready")),
        "example_manifest": bool(result.get("example_manifest")),
        "manifest_path": result.get("manifest_path"),
        "warning_checks": result.get("warning_checks") or [],
        "failed_checks": result.get("failed_checks") or [],
        "section_status": section_status,
        "boundary": result.get("boundary"),
        "next_step": result.get("next_step"),
    }


def _param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = _param(params, name)
    if value is None:
        return default
    return int(value)


def _clamp_limit(value: int) -> int:
    return max(1, min(MAX_LIMIT, int(value)))


def _index_html() -> str:
    title = "Feishu Memory Copilot Admin"
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef1ed;
      --surface: #fbfaf5;
      --ink: #17201d;
      --muted: #5f6a66;
      --line: #cfd7d1;
      --accent: #0f766e;
      --accent-2: #99582a;
      --accent-3: #365d8d;
      --danger: #ad2f2f;
      --shadow: 0 14px 34px rgba(23, 32, 29, .09);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      min-width: 320px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: #17201d;
      color: #fbfaf5;
      padding: 20px 24px;
    }}
    .title-row {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      max-width: 1440px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0;
      font-size: 23px;
      line-height: 1.2;
      font-weight: 720;
      letter-spacing: 0;
    }}
    .boundary {{
      color: #ccd9d3;
      font-size: 13px;
      line-height: 1.4;
      text-align: right;
      max-width: 620px;
    }}
    main {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px 24px 32px;
    }}
    .toolbar, .summary, .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(180px, 2fr) repeat(5, minmax(120px, 1fr)) auto;
      gap: 10px;
      padding: 12px;
      position: sticky;
      top: 0;
      z-index: 3;
    }}
    input, select, button {{
      height: 38px;
      border: 1px solid #bfb5a4;
      border-radius: 6px;
      background: #fffdf8;
      color: var(--ink);
      font: inherit;
      font-size: 14px;
      min-width: 0;
    }}
    input, select {{ padding: 0 10px; }}
    button {{
      padding: 0 14px;
      background: var(--ink);
      color: #fffaf0;
      cursor: pointer;
      white-space: nowrap;
    }}
    button.secondary {{
      background: #fffdf8;
      color: var(--ink);
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(6, minmax(110px, 1fr));
      gap: 1px;
      margin: 14px 0;
      background: var(--line);
    }}
    .metric {{
      background: var(--surface);
      padding: 14px;
      min-height: 78px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .metric strong {{
      font-size: 24px;
      line-height: 1;
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 12px;
    }}
    .tab {{
      border-radius: 999px;
      background: transparent;
      color: var(--ink);
      border-color: var(--line);
    }}
    .tab.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }}
    .panel {{
      min-height: 480px;
      overflow: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #e2e9e4;
      z-index: 2;
      color: #353b36;
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    .status {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      background: #e6efe9;
      color: var(--accent);
      font-weight: 650;
      font-size: 12px;
    }}
    .status.candidate, .status.needs_evidence {{
      background: #fff2d6;
      color: var(--accent-2);
    }}
    .status.warning, .status.blocker {{
      background: #fbedd7;
      color: var(--accent-2);
    }}
    .status.rejected, .status.expired, .status.deny {{
      background: #f7dddd;
      color: var(--danger);
    }}
    .status.fail {{
      background: #f7dddd;
      color: var(--danger);
    }}
    .content-cell {{
      max-width: 460px;
      line-height: 1.45;
    }}
    .home-grid {{
      display: grid;
      grid-template-columns: minmax(320px, 1.2fr) minmax(280px, 1fr);
      gap: 1px;
      background: var(--line);
      min-width: 980px;
    }}
    .home-section {{
      background: var(--surface);
      padding: 14px;
      min-height: 220px;
    }}
    .home-section h2 {{
      margin: 0 0 12px;
      font-size: 15px;
      line-height: 1.2;
    }}
    .feed-item {{
      border-top: 1px solid var(--line);
      padding: 10px 0;
      line-height: 1.45;
    }}
    .feed-item:first-of-type {{
      border-top: 0;
      padding-top: 0;
    }}
    .feed-title {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 4px;
    }}
    .feed-meta {{
      color: var(--muted);
      font-size: 12px;
    }}
    .live-dot {{
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      margin-right: 6px;
    }}
    .kv {{
      display: grid;
      grid-template-columns: minmax(120px, auto) 1fr;
      gap: 6px 10px;
      font-size: 13px;
      margin-bottom: 12px;
      min-width: 0;
    }}
    .kv * {{
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .kv span:nth-child(odd) {{
      color: var(--muted);
    }}
    .detail {{
      border-left: 3px solid var(--accent);
      background: #fffdf8;
      padding: 14px;
      white-space: pre-wrap;
      line-height: 1.45;
    }}
    .split-view {{
      display: grid;
      grid-template-columns: minmax(340px, .9fr) minmax(460px, 1.1fr);
      gap: 1px;
      background: var(--line);
      min-width: 980px;
    }}
    .workspace-column {{
      background: var(--surface);
      padding: 16px;
      min-height: 560px;
    }}
    .section-title {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      margin: 0 0 14px;
    }}
    .section-title h2 {{
      margin: 0;
      font-size: 16px;
      line-height: 1.2;
    }}
    .section-title span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .action-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin: 0 0 12px;
    }}
    .policy-form {{
      border: 1px solid var(--line);
      background: #fffdf8;
      border-radius: 7px;
      padding: 12px;
      margin-top: 12px;
    }}
    .policy-form h3 {{
      margin: 0 0 10px;
      font-size: 14px;
      line-height: 1.2;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .form-grid label {{
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
    }}
    .form-grid input, .form-grid select, .form-grid textarea {{
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 9px 10px;
      font: inherit;
      font-size: 13px;
    }}
    .form-grid textarea {{
      min-height: 70px;
      resize: vertical;
      grid-column: 1 / -1;
    }}
    .form-grid .wide {{ grid-column: 1 / -1; }}
    .checkbox-row {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin: 12px 0;
      font-size: 13px;
    }}
    .checkbox-row label {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--ink);
    }}
    .wiki-card {{
      border: 1px solid var(--line);
      background: #fffdf8;
      padding: 14px;
      margin-bottom: 12px;
      border-radius: 7px;
    }}
    .wiki-card h3 {{
      margin: 0 0 8px;
      font-size: 16px;
      line-height: 1.25;
    }}
    .wiki-value {{
      font-size: 14px;
      line-height: 1.55;
      margin-bottom: 10px;
    }}
    .wiki-evidence {{
      border-left: 3px solid var(--accent-3);
      padding-left: 10px;
      color: #33413d;
      line-height: 1.45;
      font-size: 13px;
    }}
    .tag-row {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 2px 8px;
      background: #e7ede9;
      color: #24302d;
      font-size: 12px;
    }}
    .tag.warn {{ background: #fbedd7; color: var(--accent-2); }}
    .graph-board {{
      min-height: 540px;
      border: 1px solid var(--line);
      background:
        linear-gradient(90deg, rgba(15,118,110,.06) 1px, transparent 1px),
        linear-gradient(rgba(15,118,110,.06) 1px, transparent 1px),
        #f8faf7;
      background-size: 34px 34px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
      align-content: start;
      gap: 14px;
      padding: 14px;
      overflow: auto;
    }}
    .graph-node {{
      width: 100%;
      min-height: 76px;
      border: 1px solid #94aaa1;
      background: rgba(255,253,248,.95);
      border-radius: 8px;
      padding: 9px;
      box-shadow: 0 12px 24px rgba(23, 32, 29, .10);
      overflow-wrap: anywhere;
      cursor: pointer;
      text-align: left;
    }}
    .graph-node.selected {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .graph-node strong {{
      display: block;
      font-size: 13px;
      line-height: 1.2;
      margin-bottom: 6px;
    }}
    .graph-node small {{
      color: var(--muted);
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .graph-node.feishu_chat {{ border-color: var(--accent); }}
    .graph-node.feishu_user {{ border-color: var(--accent-3); }}
    .graph-node.feishu_message {{ border-color: var(--accent-2); }}
    .graph-node.memory {{ border-color: #111827; }}
    .graph-node.evidence_source {{ border-color: #64748b; }}
    .graph-edge-list {{
      max-height: 540px;
      overflow: auto;
    }}
    .edge-item {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 8px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
      font-size: 13px;
      cursor: pointer;
    }}
    .edge-item.selected {{ background: #f0eadf; }}
    .edge-type {{
      color: var(--accent);
      font-weight: 700;
      font-size: 12px;
      white-space: nowrap;
    }}
    .graph-detail {{
      margin-top: 12px;
      border: 1px solid var(--line);
      background: #fffdf8;
      border-radius: 7px;
      padding: 12px;
      line-height: 1.45;
    }}
    .graph-detail h3 {{ margin-bottom: 10px; }}
    .detail-grid {{
      display: grid;
      grid-template-columns: 130px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 13px;
    }}
    .detail-grid span:nth-child(odd) {{ color: var(--muted); }}
    .detail-json {{
      margin-top: 10px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
      white-space: pre-wrap;
      max-height: 180px;
      overflow: auto;
      font-size: 12px;
    }}
    .footer-mark {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 12px;
    }}
    .footer-mark a {{
      color: inherit;
      text-decoration: none;
      border-bottom: 1px solid transparent;
    }}
    .footer-mark a:hover {{ border-bottom-color: var(--muted); }}
    .empty, .error {{
      padding: 28px;
      color: var(--muted);
    }}
    .error {{ color: var(--danger); }}
    @media (max-width: 960px) {{
      .title-row {{ display: block; }}
      .boundary {{ text-align: left; margin-top: 8px; }}
      main {{ padding: 12px; }}
      .toolbar {{ grid-template-columns: 1fr 1fr; position: static; }}
      .summary {{ grid-template-columns: repeat(2, minmax(110px, 1fr)); }}
      .home-grid {{ grid-template-columns: 1fr; }}
      .split-view {{ grid-template-columns: 1fr; min-width: 0; }}
      .graph-board {{ min-height: 620px; grid-template-columns: 1fr; }}
      .edge-item {{ grid-template-columns: 1fr; gap: 3px; }}
      .detail-grid {{ grid-template-columns: 1fr; }}
      .form-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="title-row">
      <h1>{escaped_title}</h1>
      <div class="boundary">本地只读 LLM Wiki / 知识图谱后台，默认读取 SQLite / Copilot ledger；不代表生产部署或完整多租户企业后台。</div>
    </div>
  </header>
  <main>
    <form class="toolbar" id="filters">
      <input id="q" name="q" placeholder="搜索 subject / value / ID / trace">
      <select id="status" name="status">
        <option value="">全部状态</option>
        <option value="active">active</option>
        <option value="candidate">candidate</option>
        <option value="needs_evidence">needs_evidence</option>
        <option value="rejected">rejected</option>
        <option value="expired">expired</option>
      </select>
      <input id="scope" name="scope" placeholder="scope，例如 project:admin_demo">
      <input id="tenant" name="tenant" placeholder="tenant_id">
      <input id="organization" name="organization" placeholder="organization_id">
      <select id="decision" name="decision">
        <option value="">全部权限</option>
        <option value="allow">allow</option>
        <option value="deny">deny</option>
        <option value="withhold">withhold</option>
        <option value="redact">redact</option>
      </select>
      <button type="submit">查询</button>
    </form>
    <section class="summary" id="summary"></section>
    <nav class="tabs">
      <button class="tab active" data-view="home">Overview</button>
      <button class="tab" data-view="wiki">LLM Wiki</button>
      <button class="tab" data-view="graph">Graph</button>
      <button class="tab" data-view="tenants">Tenants</button>
      <button class="tab" data-view="launch">Launch</button>
      <button class="tab" data-view="memories">Ledger</button>
      <button class="tab" data-view="audit">Audit</button>
      <button class="tab" data-view="tables">Tables</button>
    </nav>
      <section class="panel" id="panel"><div class="empty">加载中</div></section>
      <div class="footer-mark">Created By <a href="https://deerflow.tech" target="_blank" rel="noreferrer">Deerflow</a></div>
    </main>
  <script>
    const state = {{ view: "home", selectedGraphItem: null }};
    let currentGraphData = null;
    const $ = (id) => document.getElementById(id);
    const text = (value) => value === null || value === undefined || value === "" ? "-" : String(value);
    const esc = (value) => text(value).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}})[c]);

      async function getJson(path) {{
        const token = sessionStorage.getItem("copilotAdminToken") || "";
        const headers = {{ "Accept": "application/json" }};
        if (token) headers.Authorization = `Bearer ${{token}}`;
        let response = await fetch(path, {{ headers }});
        if (response.status === 401) {{
          const entered = window.prompt("Admin token required");
          if (!entered) throw new Error("admin auth required");
          sessionStorage.setItem("copilotAdminToken", entered);
          response = await fetch(path, {{ headers: {{ "Accept": "application/json", "Authorization": `Bearer ${{entered}}` }} }});
        }}
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error?.message || payload.error?.code || "request failed");
        return payload.data;
      }}

    async function postJson(path, body) {{
      const token = sessionStorage.getItem("copilotAdminToken") || "";
      const headers = {{ "Accept": "application/json", "Content-Type": "application/json" }};
      if (token) headers.Authorization = `Bearer ${{token}}`;
      let response = await fetch(path, {{ method: "POST", headers, body: JSON.stringify(body) }});
      if (response.status === 401) {{
        const entered = window.prompt("Admin token required");
        if (!entered) throw new Error("admin auth required");
        sessionStorage.setItem("copilotAdminToken", entered);
        response = await fetch(path, {{
          method: "POST",
          headers: {{ "Accept": "application/json", "Content-Type": "application/json", "Authorization": `Bearer ${{entered}}` }},
          body: JSON.stringify(body)
        }});
      }}
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error?.message || payload.error?.code || "request failed");
      return payload.data;
    }}

    async function getText(path) {{
      const token = sessionStorage.getItem("copilotAdminToken") || "";
      const headers = {{ "Accept": "text/markdown" }};
      if (token) headers.Authorization = `Bearer ${{token}}`;
      let response = await fetch(path, {{ headers }});
      if (response.status === 401) {{
        const entered = window.prompt("Admin token required");
        if (!entered) throw new Error("admin auth required");
        sessionStorage.setItem("copilotAdminToken", entered);
        response = await fetch(path, {{ headers: {{ "Accept": "text/markdown", "Authorization": `Bearer ${{entered}}` }} }});
      }}
      if (!response.ok) {{
        const text = await response.text();
        throw new Error(text || `request failed: ${{response.status}}`);
      }}
      return response.text();
    }}

    async function loadSummary() {{
      const data = await getJson("/api/summary");
      $("summary").innerHTML = [
        metric("Memory", data.memory_total),
        metric("Active", data.memory_by_status.active || 0),
        metric("Candidate", data.memory_by_status.candidate || 0),
        metric("Audit", data.audit_total),
        metric("Raw Events", data.raw_event_total),
        metric("Evidence", data.evidence_total)
      ].join("");
    }}

    function metric(label, value) {{
      return `<div class="metric"><span>${{esc(label)}}</span><strong>${{esc(value)}}</strong></div>`;
    }}

    function paramsFor(view) {{
      const params = new URLSearchParams();
      const q = $("q").value.trim();
      const status = $("status").value;
      const scope = $("scope").value.trim();
      const tenant = $("tenant").value.trim();
      const organization = $("organization").value.trim();
      const decision = $("decision").value;
      if (q) params.set("q", q);
      if (tenant) params.set("tenant_id", tenant);
      if (organization) params.set("organization_id", organization);
      if (view === "wiki") {{
        if (scope) params.set("scope", scope);
      }} else if (view === "graph") {{
        if (status) params.set("status", status);
      }} else if (view === "memories") {{
        if (status) params.set("status", status);
        if (scope) params.set("scope", scope);
      }} else if (view === "audit") {{
        if (decision) params.set("permission_decision", decision);
      }}
      params.set("limit", "80");
      return params;
    }}

    async function loadView(options = {{}}) {{
      if (!options.quiet) $("panel").innerHTML = `<div class="empty">加载中</div>`;
      try {{
        if (state.view === "home") return renderHome(await getJson("/api/live"));
        if (state.view === "wiki") return renderWiki(await getJson(`/api/wiki?${{paramsFor("wiki")}}`));
        if (state.view === "graph") return renderGraph(await getJson(`/api/graph?${{paramsFor("graph")}}`));
        if (state.view === "tenants") return renderTenants(await getJson(`/api/tenants?${{paramsFor("tenants")}}`));
        if (state.view === "launch") return renderLaunch(await getJson("/api/launch-readiness"));
        if (state.view === "memories") return renderMemories(await getJson(`/api/memories?${{paramsFor("memories")}}`));
        if (state.view === "audit") return renderAudit(await getJson(`/api/audit?${{paramsFor("audit")}}`));
        return renderTables(await getJson("/api/tables"));
      }} catch (error) {{
        $("panel").innerHTML = `<div class="error">${{esc(error.message)}}</div>`;
      }}
    }}

      function renderHome(data) {{
        const activity = data.bot_activity || {{}};
      const rawRows = data.recent_raw_events.map(item => `
        <div class="feed-item">
          <div class="feed-title">
            <strong>${{esc(item.source_type)}}</strong>
            <span class="feed-meta mono">${{esc(item.event_time_iso)}}</span>
          </div>
          <div class="content-cell">${{esc(item.content)}}</div>
          <div class="feed-meta mono">${{esc(item.scope)}} · sender=${{esc(item.sender_id)}} · source=${{esc(item.source_id)}} · ${{esc(item.ingestion_status)}}</div>
        </div>`).join("");
      const auditRows = data.recent_audit.map(item => `
        <div class="feed-item">
          <div class="feed-title">
            <strong>${{esc(item.event_type)}}</strong>
            <span class="feed-meta mono">${{esc(item.created_at_iso)}}</span>
          </div>
          <div><span class="status ${{esc(item.permission_decision)}}">${{esc(item.permission_decision)}}</span> ${{esc(item.action)}} / ${{esc(item.reason_code)}}</div>
          <div class="feed-meta mono">${{esc(item.request_id)}} · ${{esc(item.trace_id)}}</div>
        </div>`).join("");
      const graph = data.knowledge_graph;
      const nodeRows = graph.recent_nodes.map(item => `
        <div class="feed-item">
          <div class="feed-title">
            <strong>${{esc(item.label)}}</strong>
            <span class="feed-meta mono">${{esc(item.last_seen_at_iso)}}</span>
          </div>
          <div class="feed-meta mono">${{esc(item.node_type)}} · observations=${{esc(item.observation_count)}} · ${{esc(item.status)}}</div>
        </div>`).join("");
      const memoryRows = data.knowledge_cards.map(item => `
        <div class="feed-item">
          <div class="feed-title">
            <strong>${{esc(item.subject)}}</strong>
            <span class="feed-meta mono">${{esc(item.updated_at_iso)}}</span>
          </div>
          <div class="content-cell">${{esc(item.current_value)}}</div>
          <div class="feed-meta mono">${{esc(item.scope)}} · ${{esc(item.type)}}</div>
        </div>`).join("");
      $("panel").innerHTML = `
        <div class="home-grid">
          <section class="home-section">
            <h2><span class="live-dot"></span>Bot 实时输入</h2>
            <div class="kv">
              <span>最新消息</span><strong class="mono">${{esc(activity.latest_raw_event_at)}}</strong>
              <span>最新审计</span><strong class="mono">${{esc(activity.latest_audit_at)}}</strong>
              <span>最新图谱观察</span><strong class="mono">${{esc(activity.latest_graph_seen_at)}}</strong>
            </div>
            ${{rawRows || `<div class="empty">暂无 raw event</div>`}}
          </section>
          <section class="home-section">
            <h2>工具调用 / 权限审计</h2>
            ${{auditRows || `<div class="empty">暂无 audit event</div>`}}
          </section>
          <section class="home-section">
            <h2>知识图谱</h2>
            <div class="kv">
              <span>节点</span><strong>${{esc(graph.node_total)}}</strong>
              <span>边</span><strong>${{esc(graph.edge_total)}}</strong>
              <span>节点类型</span><span class="mono">${{esc(JSON.stringify(graph.nodes_by_type))}}</span>
              <span>边类型</span><span class="mono">${{esc(JSON.stringify(graph.edges_by_type))}}</span>
            </div>
            ${{nodeRows || `<div class="empty">暂无 graph node</div>`}}
          </section>
          <section class="home-section">
            <h2>Wiki 记忆卡片</h2>
            ${{memoryRows || `<div class="empty">暂无 active memory</div>`}}
          </section>
          </div>`;
      }}

      function renderWiki(data) {{
        const policy = data.generation_policy || {{}};
        const exportScope = $("scope").value.trim() || (data.scopes[0] && data.scopes[0].scope) || "";
        const exportDisabled = exportScope ? "" : "disabled";
        const scopeRows = data.scopes.map(item => `<span class="tag">${{esc(item.scope)}} · ${{esc(item.count)}}</span>`).join("");
        const openRows = data.open_questions_by_scope.map(item => `<span class="tag warn">${{esc(item.scope)}} · open ${{esc(item.count)}}</span>`).join("");
        const cards = data.cards.map(item => {{
          const evidence = item.evidence || {{}};
          return `
            <article class="wiki-card">
              <h3>${{esc(item.subject)}}</h3>
              <div class="wiki-value">${{esc(item.current_value)}}</div>
              <div class="wiki-evidence">${{esc(evidence.quote)}}<br><span class="feed-meta mono">${{esc(evidence.source_type)}} / ${{esc(evidence.source_id)}} / ${{esc(evidence.document_title)}}</span></div>
              <div class="tag-row">
                <span class="tag">${{esc(item.scope)}}</span>
                <span class="tag">${{esc(item.type)}}</span>
                <span class="tag">v${{esc(item.version || 1)}}</span>
                <span class="tag">importance ${{esc(Number(item.importance || 0).toFixed(2))}}</span>
                ${{item.superseded_version_count ? `<span class="tag warn">${{esc(item.superseded_version_count)}} superseded</span>` : `<span class="tag">no superseded</span>`}}
              </div>
            </article>`;
        }}).join("");
        $("panel").innerHTML = `
          <div class="split-view">
            <section class="workspace-column">
              <div class="section-title"><h2>Compiled LLM Wiki</h2><span>${{esc(data.card_count)}} active cards</span></div>
              <div class="kv">
                <span>来源</span><strong>${{esc(policy.source)}}</strong>
                <span>raw events</span><strong>${{esc(policy.raw_events_included ? "included" : "excluded")}}</strong>
                <span>证据要求</span><strong>${{esc(policy.requires_evidence ? "required" : "optional")}}</strong>
                <span>写入飞书</span><strong>${{esc(policy.writes_feishu ? "yes" : "no")}}</strong>
              </div>
              <div class="action-row">
                <button type="button" id="wiki-export" data-scope="${{esc(exportScope)}}" ${{exportDisabled}}>导出 Markdown</button>
                <span class="feed-meta mono">${{esc(exportScope || "select a scope")}}</span>
              </div>
              <div class="tag-row">${{scopeRows || `<span class="tag">no active scope</span>`}}</div>
              <div class="tag-row">${{openRows || `<span class="tag">no open question</span>`}}</div>
            </section>
            <section class="workspace-column">
              <div class="section-title"><h2>Knowledge Cards</h2><span>evidence-backed current facts</span></div>
              ${{cards || `<div class="empty">暂无可编译 active memory</div>`}}
            </section>
          </div>`;
      }}

    async function downloadWikiExport(scope) {{
      if (!scope) throw new Error("select a scope before export");
      const markdown = await getText(`/api/wiki/export?scope=${{encodeURIComponent(scope)}}`);
      const blob = new Blob([markdown], {{ type: "text/markdown;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `copilot-memory-wiki-${{scope.replace(/[^a-zA-Z0-9._-]+/g, "_")}}.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }}

      function renderGraph(data) {{
        currentGraphData = data;
        const nodes = data.nodes || [];
        const edges = data.edges || [];
        if (!state.selectedGraphItem || !graphItemExists(state.selectedGraphItem, nodes, edges)) {{
          state.selectedGraphItem = nodes[0] ? {{ type: "node", id: nodes[0].id }} : edges[0] ? {{ type: "edge", id: edges[0].id }} : null;
        }}
        const nodeHtml = nodes.map(node => {{
          const selected = state.selectedGraphItem?.type === "node" && state.selectedGraphItem.id === node.id ? "selected" : "";
          return `<div class="graph-node ${{esc(node.node_type)}} ${{selected}}" role="button" tabindex="0" data-node-id="${{esc(node.id)}}">
            <strong>${{esc(node.label)}}</strong>
            <small class="mono">${{esc(node.node_type)}}<br>${{esc(node.node_key)}}<br>obs=${{esc(node.observation_count)}}</small>
          </div>`;
        }}).join("");
        const edgeRows = edges.map(edge => `
          <div class="edge-item ${{state.selectedGraphItem?.type === "edge" && state.selectedGraphItem.id === edge.id ? "selected" : ""}}" data-edge-id="${{esc(edge.id)}}">
            <span>${{esc(edge.source_label || edge.source_node_id)}}</span>
            <span class="edge-type">${{esc(edge.edge_type)}} x${{esc(edge.observation_count)}}</span>
            <span>${{esc(edge.target_label || edge.target_node_id)}}</span>
          </div>`).join("");
        $("panel").innerHTML = `
          <div class="split-view">
            <section class="workspace-column">
              <div class="section-title"><h2>Knowledge Graph</h2><span>${{esc(data.workspace_node_count)}} visible nodes / ${{esc(data.workspace_edge_count)}} visible edges</span></div>
              <div class="kv">
                <span>节点类型</span><span class="mono">${{esc(JSON.stringify(data.nodes_by_type))}}</span>
                <span>边类型</span><span class="mono">${{esc(JSON.stringify(data.edges_by_type))}}</span>
              </div>
              <div class="graph-board">${{nodeHtml || `<div class="empty">暂无 graph node</div>`}}</div>
              <div class="graph-detail" id="graph-detail">${{renderGraphDetail(nodes, edges)}}</div>
            </section>
            <section class="workspace-column">
              <div class="section-title"><h2>Relationship Ledger</h2><span>source / edge / target</span></div>
              <div class="graph-edge-list">${{edgeRows || `<div class="empty">暂无 graph edge</div>`}}</div>
            </section>
          </div>`;
      }}

      function graphItemExists(item, nodes, edges) {{
        if (item.type === "node") return nodes.some(node => node.id === item.id);
        if (item.type === "edge") return edges.some(edge => edge.id === item.id);
        return false;
      }}

      function renderGraphDetail(nodes, edges) {{
        if (!state.selectedGraphItem) return `<div class="empty">选择节点或关系</div>`;
        if (state.selectedGraphItem.type === "edge") {{
          const edge = edges.find(item => item.id === state.selectedGraphItem.id);
          return edge ? edgeDetail(edge) : `<div class="empty">选择 graph edge</div>`;
        }}
        const node = nodes.find(item => item.id === state.selectedGraphItem.id);
        return node ? nodeDetail(node, edges) : `<div class="empty">选择 graph node</div>`;
      }}

      function nodeDetail(node, edges) {{
        const related = edges.filter(edge => edge.source_node_id === node.id || edge.target_node_id === node.id);
        return `<h3>${{esc(node.label)}}</h3>
          <div class="detail-grid">
            <span>Node type</span><strong class="mono">${{esc(node.node_type)}}</strong>
            <span>Node key</span><strong class="mono">${{esc(node.node_key || node.id)}}</strong>
            <span>Tenant</span><strong class="mono">${{esc(node.tenant_id)}}</strong>
            <span>Organization</span><strong class="mono">${{esc(node.organization_id)}}</strong>
            <span>Visibility</span><strong>${{esc(node.visibility_policy)}}</strong>
            <span>Status</span><strong>${{esc(node.status)}}</strong>
            <span>Observations</span><strong>${{esc(node.observation_count)}}</strong>
            <span>First seen</span><strong class="mono">${{esc(node.first_seen_at_iso)}}</strong>
            <span>Last seen</span><strong class="mono">${{esc(node.last_seen_at_iso)}}</strong>
            <span>Related edges</span><strong>${{esc(related.length)}}</strong>
          </div>
          <pre class="detail-json mono">${{esc(JSON.stringify(node.metadata || {{}}, null, 2))}}</pre>`;
      }}

      function edgeDetail(edge) {{
        return `<h3>${{esc(edge.edge_type)}}</h3>
          <div class="detail-grid">
            <span>Source</span><strong class="mono">${{esc(edge.source_label || edge.source_node_id)}}</strong>
            <span>Target</span><strong class="mono">${{esc(edge.target_label || edge.target_node_id)}}</strong>
            <span>Source type</span><strong>${{esc(edge.source_type)}}</strong>
            <span>Target type</span><strong>${{esc(edge.target_type)}}</strong>
            <span>Tenant</span><strong class="mono">${{esc(edge.tenant_id)}}</strong>
            <span>Organization</span><strong class="mono">${{esc(edge.organization_id)}}</strong>
            <span>Observations</span><strong>${{esc(edge.observation_count)}}</strong>
            <span>First seen</span><strong class="mono">${{esc(edge.first_seen_at_iso)}}</strong>
            <span>Last seen</span><strong class="mono">${{esc(edge.last_seen_at_iso)}}</strong>
          </div>
          <pre class="detail-json mono">${{esc(JSON.stringify(edge.metadata || {{}}, null, 2))}}</pre>`;
      }}

      function renderMemories(data) {{
      if (!data.items.length) return $("panel").innerHTML = `<div class="empty">没有匹配的 memory</div>`;
      const rows = data.items.map(item => `
        <tr>
          <td class="mono">${{esc(item.id)}}</td>
          <td class="mono">${{esc(item.updated_at_iso)}}</td>
          <td><span class="status ${{esc(item.status)}}">${{esc(item.status)}}</span></td>
          <td>${{esc(item.scope)}}<br><span class="mono">${{esc(item.tenant_id)}} / ${{esc(item.organization_id)}}</span></td>
          <td>${{esc(item.subject)}}<br><span class="mono">${{esc(item.type)}}</span></td>
          <td class="content-cell">${{esc(item.current_value)}}</td>
          <td class="content-cell">${{esc((item.evidence[0] || {{}}).quote)}}<br><span class="mono">${{esc((item.evidence[0] || {{}}).source_type)}} ${{esc((item.evidence[0] || {{}}).document_title)}}</span></td>
          <td><button class="secondary" data-detail="${{esc(item.id)}}">详情</button></td>
        </tr>`).join("");
      $("panel").innerHTML = `<table><thead><tr><th>ID</th><th>Updated</th><th>Status</th><th>Scope</th><th>Subject</th><th>Value</th><th>Evidence</th><th></th></tr></thead><tbody>${{rows}}</tbody></table>`;
      document.querySelectorAll("[data-detail]").forEach(btn => btn.addEventListener("click", async () => {{
        const data = await getJson(`/api/memories/${{encodeURIComponent(btn.dataset.detail)}}`);
        btn.closest("tr").insertAdjacentHTML("afterend", `<tr><td colspan="8"><pre class="detail">${{esc(JSON.stringify(data, null, 2))}}</pre></td></tr>`);
      }}));
    }}

    function renderTenants(data) {{
      const capabilityRows = (data.missing_capabilities || []).map(item => `<span class="tag warn">${{esc(item)}}</span>`).join("");
      const rows = (data.items || []).map(item => {{
        const scopes = (item.scopes || []).map(scope => `${{scope.scope}}(${{scope.count}})`).join(", ");
        const readiness = item.readiness || {{}};
        const policy = item.tenant_policy || {{}};
        const policySummary = policy.id
          ? `${{policy.status}} · visibility=${{policy.default_visibility_policy}} · reviewers=${{(policy.reviewer_roles || []).join(", ") || "-"}}`
          : "not configured";
        return `
          <tr>
            <td class="mono">${{esc(item.tenant_id)}}<br>${{esc(item.organization_id)}}</td>
            <td>${{esc(item.memory_total)}} total<br><span class="mono">${{esc(item.active_memory_count)}} active / ${{esc(item.open_review_count)}} open review</span></td>
            <td>${{esc(item.graph_node_count)}} nodes<br><span class="mono">${{esc(item.graph_edge_count)}} edges</span></td>
            <td>${{esc(item.audit_total)}} events<br><span class="mono">${{esc(item.denied_audit_count)}} deny</span></td>
            <td class="content-cell">${{esc(scopes || "-")}}</td>
            <td class="mono">${{esc(readiness.access_gate)}}<br>SSO=${{esc(readiness.sso)}}<br>Policy=${{esc(readiness.policy_editor)}}<br>${{esc(policySummary)}}</td>
            <td class="mono">${{esc(item.latest_activity_at_iso)}}</td>
          </tr>`;
      }}).join("");
      const first = (data.items || [])[0] || {{}};
      const firstPolicy = first.tenant_policy || {{}};
      $("panel").innerHTML = `
        <div class="split-view">
          <section class="workspace-column">
            <div class="section-title"><h2>Tenant Inventory</h2><span>${{esc(data.tenant_count)}} tenants / ${{esc(data.organization_count)}} orgs</span></div>
            <div class="kv">
              <span>Source</span><strong>${{esc(data.source)}}</strong>
              <span>Policy editor</span><strong>${{esc(data.tenant_policy_editor_available ? "available" : "missing")}}</strong>
              <span>Boundary</span><strong>${{esc(data.boundary)}}</strong>
            </div>
            <div class="tag-row">${{capabilityRows || `<span class="tag">no missing capability listed</span>`}}</div>
            <form class="policy-form" id="tenant-policy-form">
              <h3>Tenant Policy Editor</h3>
              <div class="form-grid">
                <label>tenant_id<input name="tenant_id" value="${{esc($("tenant").value.trim() || first.tenant_id || "tenant:demo")}}"></label>
                <label>organization_id<input name="organization_id" value="${{esc($("organization").value.trim() || first.organization_id || "org:demo")}}"></label>
                <label>Status<select name="status">
                  <option value="active" ${{firstPolicy.status === "disabled" ? "" : "selected"}}>active</option>
                  <option value="disabled" ${{firstPolicy.status === "disabled" ? "selected" : ""}}>disabled</option>
                </select></label>
                <label>Default visibility<select name="default_visibility_policy">
                  ${{["team", "project", "org", "private"].map(value => `<option value="${{value}}" ${{(firstPolicy.default_visibility_policy || "team") === value ? "selected" : ""}}>${{value}}</option>`).join("")}}
                </select></label>
                <label class="wide">Reviewer roles<input name="reviewer_roles" value="${{esc((firstPolicy.reviewer_roles || ["reviewer", "owner"]).join(", "))}}"></label>
                <label class="wide">Admin users<input name="admin_users" value="${{esc((firstPolicy.admin_users || []).join(", "))}}" placeholder="admin@example.com, owner@example.com"></label>
                <label class="wide">SSO allowed domains<input name="sso_allowed_domains" value="${{esc((firstPolicy.sso_allowed_domains || []).join(", "))}}" placeholder="example.com"></label>
                <label class="wide">Notes<textarea name="notes">${{esc(firstPolicy.notes || "本地/pre-production 租户策略；真实企业 IdP 与生产 DB 仍需单独验收。")}}</textarea></label>
              </div>
              <div class="checkbox-row">
                <label><input type="checkbox" name="auto_confirm_low_risk" ${{firstPolicy.auto_confirm_low_risk === false ? "" : "checked"}}> low-risk auto confirm</label>
                <label><input type="checkbox" name="require_review_for_conflicts" ${{firstPolicy.require_review_for_conflicts === false ? "" : "checked"}}> conflicts require review</label>
              </div>
              <div class="action-row">
                <button type="submit">保存策略</button>
                <span class="feed-meta mono">admin-only POST /api/tenant-policies</span>
              </div>
            </form>
          </section>
          <section class="workspace-column">
            <div class="section-title"><h2>Tenant / Organization Readiness</h2><span>counts are scoped by tenant_id and organization_id</span></div>
            ${{rows ? `<table><thead><tr><th>Tenant / Org</th><th>Memory</th><th>Graph</th><th>Audit</th><th>Scopes</th><th>Readiness</th><th>Latest Activity</th></tr></thead><tbody>${{rows}}</tbody></table>` : `<div class="empty">暂无 tenant / organization ledger</div>`}}
          </section>
        </div>`;
    }}

    function renderLaunch(data) {{
      const checks = data.checks || [];
      const blockers = data.production_blockers || [];
      const summary = data.summary || {{}};
      const evidence = data.production_evidence || {{}};
      const evidenceStatus = evidence.section_status || {{}};
      const rows = checks.map(item => `
        <tr>
          <td><span class="status ${{esc(item.status)}}">${{esc(item.status)}}</span></td>
          <td>${{esc(item.label)}}<br><span class="mono">${{esc(item.id)}}</span></td>
          <td class="content-cell">${{esc(item.evidence)}}</td>
          <td class="content-cell">${{esc(item.next_step || "-")}}</td>
        </tr>`).join("");
      const blockerRows = blockers.map(item => `<span class="tag warn">${{esc(item.label || item.id)}}</span>`).join("");
      const evidenceRows = Object.entries(evidenceStatus).map(([name, status]) => `
        <tr><td class="mono">${{esc(name)}}</td><td><span class="status ${{esc(status)}}">${{esc(status)}}</span></td></tr>
      `).join("");
      $("panel").innerHTML = `
        <div class="split-view">
          <section class="workspace-column">
            <div class="section-title"><h2>Launch Readiness</h2><span>staging=${{esc(data.staging_status)}} / production=${{esc(data.production_status)}}</span></div>
            <div class="kv">
              <span>Wiki cards</span><strong>${{esc(summary.wiki_card_count)}}</strong>
              <span>Graph</span><strong>${{esc(summary.graph_node_count)}} nodes / ${{esc(summary.graph_edge_count)}} edges</strong>
              <span>Tenants</span><strong>${{esc(summary.tenant_count)}}</strong>
              <span>Tenant policies</span><strong>${{esc(summary.tenant_policy_count)}}</strong>
              <span>Audit events</span><strong>${{esc(summary.audit_total)}}</strong>
              <span>Boundary</span><strong>${{esc(data.boundary)}}</strong>
            </div>
            <div class="tag-row">${{blockerRows}}</div>
            <div class="section-title"><h2>Production Evidence</h2><span>production_ready=${{esc(evidence.production_ready)}}</span></div>
            <div class="kv">
              <span>Manifest</span><strong class="mono">${{esc(evidence.manifest_path)}}</strong>
              <span>Example</span><strong>${{esc(evidence.example_manifest)}}</strong>
              <span>Warnings</span><strong>${{esc((evidence.warning_checks || []).length)}}</strong>
              <span>Failures</span><strong>${{esc((evidence.failed_checks || []).length)}}</strong>
              <span>Boundary</span><strong>${{esc(evidence.boundary)}}</strong>
            </div>
            <table><thead><tr><th>Evidence section</th><th>Status</th></tr></thead><tbody>${{evidenceRows}}</tbody></table>
          </section>
          <section class="workspace-column">
            <div class="section-title"><h2>Gate Evidence</h2><span>pass / warning / fail</span></div>
            <table><thead><tr><th>Status</th><th>Gate</th><th>Evidence</th><th>Next step</th></tr></thead><tbody>${{rows}}</tbody></table>
          </section>
        </div>`;
    }}

    function renderAudit(data) {{
      if (!data.items.length) return $("panel").innerHTML = `<div class="empty">没有匹配的 audit event</div>`;
      const rows = data.items.map(item => `
        <tr>
          <td class="mono">${{esc(item.created_at_iso)}}</td>
          <td>${{esc(item.event_type)}}<br><span class="mono">${{esc(item.action)}}</span></td>
          <td><span class="status ${{esc(item.permission_decision)}}">${{esc(item.permission_decision)}}</span><br>${{esc(item.reason_code)}}</td>
          <td class="mono">${{esc(item.actor_id)}}<br>${{esc(item.tenant_id)}}</td>
          <td class="mono">${{esc(item.request_id)}}<br>${{esc(item.trace_id)}}</td>
          <td class="mono">${{esc(item.target_id || item.memory_id || item.candidate_id)}}</td>
        </tr>`).join("");
      $("panel").innerHTML = `<table><thead><tr><th>Time</th><th>Event</th><th>Decision</th><th>Actor</th><th>Trace</th><th>Target</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    function renderTables(data) {{
      const rows = data.tables.map(table => `
        <tr>
          <td class="mono">${{esc(table.name)}}</td>
          <td>${{esc(table.row_count)}}</td>
          <td class="content-cell">${{esc(table.columns.map(column => column.name + " " + column.type).join(", "))}}</td>
        </tr>`).join("");
      $("panel").innerHTML = `<table><thead><tr><th>Table</th><th>Rows</th><th>Columns</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    $("filters").addEventListener("submit", event => {{ event.preventDefault(); loadView(); }});
    document.addEventListener("submit", event => {{
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || form.id !== "tenant-policy-form") return;
      event.preventDefault();
      const data = new FormData(form);
      const splitList = (value) => String(value || "").split(",").map(item => item.trim()).filter(Boolean);
      postJson("/api/tenant-policies", {{
        tenant_id: String(data.get("tenant_id") || "").trim(),
        organization_id: String(data.get("organization_id") || "").trim(),
        status: String(data.get("status") || "active"),
        default_visibility_policy: String(data.get("default_visibility_policy") || "team"),
        reviewer_roles: splitList(data.get("reviewer_roles")),
        admin_users: splitList(data.get("admin_users")),
        sso_allowed_domains: splitList(data.get("sso_allowed_domains")),
        notes: String(data.get("notes") || ""),
        auto_confirm_low_risk: data.get("auto_confirm_low_risk") === "on",
        require_review_for_conflicts: data.get("require_review_for_conflicts") === "on"
      }}).then(() => {{
        $("panel").insertAdjacentHTML("afterbegin", `<div class="feed-item"><strong>Tenant policy saved</strong></div>`);
        loadView({{ quiet: true }});
        loadSummary();
      }}).catch(error => {{
        $("panel").insertAdjacentHTML("afterbegin", `<div class="error">${{esc(error.message)}}</div>`);
      }});
    }});
    document.addEventListener("click", event => {{
      const target = event.target;
      if (target && target.id === "wiki-export") {{
        event.preventDefault();
        downloadWikiExport(target.dataset.scope || "").catch(error => {{
          $("panel").insertAdjacentHTML("afterbegin", `<div class="error">${{esc(error.message)}}</div>`);
        }});
      }}
      if (!(target instanceof Element)) return;
      const graphNode = target.closest("[data-node-id]");
      if (graphNode && currentGraphData) {{
        state.selectedGraphItem = {{ type: "node", id: graphNode.dataset.nodeId }};
        renderGraph(currentGraphData);
        return;
      }}
      const graphEdge = target.closest("[data-edge-id]");
      if (graphEdge && currentGraphData) {{
        state.selectedGraphItem = {{ type: "edge", id: graphEdge.dataset.edgeId }};
        renderGraph(currentGraphData);
      }}
    }});
    document.addEventListener("keydown", event => {{
      const target = event.target;
      if (!(target instanceof Element)) return;
      if ((event.key === "Enter" || event.key === " ") && target.dataset?.nodeId && currentGraphData) {{
        event.preventDefault();
        state.selectedGraphItem = {{ type: "node", id: target.dataset.nodeId }};
        renderGraph(currentGraphData);
      }}
    }});
    document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", event => {{
      event.preventDefault();
      document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
      tab.classList.add("active");
      state.view = tab.dataset.view;
      if (state.view !== "graph") currentGraphData = null;
      loadView();
    }}));
    setInterval(() => {{
      loadSummary();
      if (state.view === "home") loadView({{ quiet: true }});
    }}, 3000);
    loadSummary().then(loadView).catch(error => $("panel").innerHTML = `<div class="error">${{esc(error.message)}}</div>`);
  </script>
</body>
</html>
"""
