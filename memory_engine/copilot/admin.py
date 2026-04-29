from __future__ import annotations

import html
import json
import sqlite3
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from memory_engine.db import db_path_from_env


DEFAULT_ADMIN_HOST = "127.0.0.1"
DEFAULT_ADMIN_PORT = 8765
MAX_LIMIT = 200


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
) -> EmbeddedAdminRuntime:
    if not enabled:
        return EmbeddedAdminRuntime(enabled=False, reason="disabled")
    try:
        server = create_admin_server(host, port, db_path)
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
        knowledge_cards = self.list_memories(status="active", limit=8)["items"]
        return {
            "bot_activity": {
                "latest_raw_event_at": recent_raw_events[0]["event_time_iso"] if recent_raw_events else None,
                "latest_audit_at": recent_audit[0]["created_at_iso"] if recent_audit else None,
                "latest_graph_seen_at": graph["recent_nodes"][0]["last_seen_at_iso"] if graph["recent_nodes"] else None,
            },
            "recent_raw_events": recent_raw_events,
            "recent_audit": recent_audit,
            "knowledge_graph": graph,
            "knowledge_cards": knowledge_cards,
        }

    def list_memories(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = _clamp_limit(limit)
        offset = max(0, offset)
        where, params = self._memory_filters(status=status, scope=scope, query=query)
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
        if query:
            like = f"%{query}%"
            conditions.append(
                "(id LIKE ? OR subject LIKE ? OR current_value LIKE ? OR COALESCE(summary, '') LIKE ?)"
            )
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


def create_admin_server(host: str, port: int, db_path: str | Path | None = None) -> CopilotAdminServer:
    resolved_db_path = str(db_path or db_path_from_env())

    class Handler(CopilotAdminHandler):
        pass

    Handler.db_path = resolved_db_path
    server = CopilotAdminServer((host, port), Handler)
    server.db_path = resolved_db_path
    return server


class CopilotAdminHandler(BaseHTTPRequestHandler):
    db_path = str(db_path_from_env())
    server_version = "FeishuMemoryCopilotAdmin/0.1"

    def do_GET(self) -> None:
        self._handle_get(send_body=True)

    def do_HEAD(self) -> None:
        self._handle_get(send_body=False)

    def do_POST(self) -> None:
        self._method_not_allowed()

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
        try:
            if parsed.path == "/":
                self._send_html(_index_html(), send_body=send_body)
                return
            if parsed.path == "/api/summary":
                self._send_json(self._api_summary(), send_body=send_body)
                return
            if parsed.path == "/api/live":
                self._send_json(self._api_live(), send_body=send_body)
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
            if parsed.path == "/api/tables":
                self._send_json(self._api_tables(), send_body=send_body)
                return
            self._send_json({"ok": False, "error": {"code": "not_found"}}, status=HTTPStatus.NOT_FOUND, send_body=send_body)
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

    def _api_summary(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            return {"ok": True, "db_path": self.db_path, "data": AdminQueryService(conn).summary()}

    def _api_live(self) -> dict[str, Any]:
        with _open_readonly_connection(self.db_path) as conn:
            return {"ok": True, "db_path": self.db_path, "data": AdminQueryService(conn).live_overview()}

    def _api_memories(self, query_string: str) -> dict[str, Any]:
        params = parse_qs(query_string)
        with _open_readonly_connection(self.db_path) as conn:
            data = AdminQueryService(conn).list_memories(
                status=_param(params, "status"),
                scope=_param(params, "scope"),
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
                permission_decision=_param(params, "permission_decision"),
                query=_param(params, "q"),
                limit=_int_param(params, "limit", 50),
                offset=_int_param(params, "offset", 0),
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

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        send_body: bool,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if send_body:
            self.wfile.write(encoded)

    def _method_not_allowed(self) -> None:
        self._send_json(
            {"ok": False, "error": {"code": "read_only_admin", "message": "Only GET and HEAD are supported."}},
            status=HTTPStatus.METHOD_NOT_ALLOWED,
            send_body=True,
        )


def _open_readonly_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _memory_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["scope"] = f"{row['scope_type']}:{row['scope_id']}"
    for key in ("created_at", "updated_at", "expires_at", "last_recalled_at", "source_visibility_revoked_at"):
        payload[f"{key}_iso"] = _ms_to_iso(payload.get(key))
    return payload


def _version_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["created_at_iso"] = _ms_to_iso(payload.get("created_at"))
    return payload


def _evidence_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
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
      --bg: #f7f3ea;
      --surface: #fffaf0;
      --ink: #1d2521;
      --muted: #5f6b63;
      --line: #d9d0bf;
      --accent: #147d64;
      --accent-2: #b35418;
      --danger: #ad2f2f;
      --shadow: 0 10px 30px rgba(29, 37, 33, .08);
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
      background: #292f2b;
      color: #fbf7ec;
      padding: 18px 24px;
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
      font-size: 22px;
      line-height: 1.2;
      font-weight: 720;
      letter-spacing: 0;
    }}
    .boundary {{
      color: #dfd3bc;
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
      grid-template-columns: minmax(180px, 2fr) repeat(4, minmax(120px, 1fr)) auto;
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
      background: #fffcf4;
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
      background: #fffcf4;
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
      background: #eee5d3;
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
    .status.rejected, .status.expired, .status.deny {{
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
    }}
    .kv span:nth-child(odd) {{
      color: var(--muted);
    }}
    .detail {{
      border-left: 3px solid var(--accent);
      background: #fffcf4;
      padding: 14px;
      white-space: pre-wrap;
      line-height: 1.45;
    }}
    .empty, .error {{
      padding: 28px;
      color: var(--muted);
    }}
    .error {{ color: var(--danger); }}
    @media (max-width: 960px) {{
      .title-row {{ display: block; }}
      .boundary {{ text-align: left; margin-top: 8px; }}
      main {{ padding: 12px; }}
      .toolbar {{ grid-template-columns: 1fr 1fr; }}
      .summary {{ grid-template-columns: repeat(2, minmax(110px, 1fr)); }}
      .home-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="title-row">
      <h1>{escaped_title}</h1>
      <div class="boundary">本地只读运维后台，默认读取 SQLite / Copilot ledger；不代表生产部署或完整多租户企业后台。</div>
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
      <button class="tab active" data-view="home">Home</button>
      <button class="tab" data-view="memories">Memory</button>
      <button class="tab" data-view="audit">Audit</button>
      <button class="tab" data-view="tables">Tables</button>
    </nav>
    <section class="panel" id="panel"><div class="empty">加载中</div></section>
  </main>
  <script>
    const state = {{ view: "home" }};
    const $ = (id) => document.getElementById(id);
    const text = (value) => value === null || value === undefined || value === "" ? "-" : String(value);
    const esc = (value) => text(value).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}})[c]);

    async function getJson(path) {{
      const response = await fetch(path, {{ headers: {{ "Accept": "application/json" }} }});
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error?.message || payload.error?.code || "request failed");
      return payload.data;
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
      const decision = $("decision").value;
      if (q) params.set("q", q);
      if (view === "memories") {{
        if (status) params.set("status", status);
        if (scope) params.set("scope", scope);
      }} else if (view === "audit") {{
        if (tenant) params.set("tenant_id", tenant);
        if (decision) params.set("permission_decision", decision);
      }}
      params.set("limit", "80");
      return params;
    }}

    async function loadView(options = {{}}) {{
      if (!options.quiet) $("panel").innerHTML = `<div class="empty">加载中</div>`;
      try {{
        if (state.view === "home") return renderHome(await getJson("/api/live"));
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
    document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", event => {{
      event.preventDefault();
      document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
      tab.classList.add("active");
      state.view = tab.dataset.view;
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
