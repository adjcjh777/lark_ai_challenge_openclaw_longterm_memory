from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from memory_engine.feishu_events import FeishuMessageEvent
from memory_engine.repository import new_id, now_ms


@dataclass(frozen=True)
class GraphNodeRegistration:
    node_id: str
    node_type: str
    node_key: str
    label: str
    status: str
    edge_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "node_key": self.node_key,
            "label": self.label,
            "status": self.status,
            "edge_id": self.edge_id,
        }


@dataclass(frozen=True)
class FeishuMessageGraphRegistration:
    chat_node_id: str
    user_node_id: str
    message_node_id: str
    membership_edge_id: str
    sent_edge_id: str
    contains_edge_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat_node_id": self.chat_node_id,
            "user_node_id": self.user_node_id,
            "message_node_id": self.message_node_id,
            "membership_edge_id": self.membership_edge_id,
            "sent_edge_id": self.sent_edge_id,
            "contains_edge_id": self.contains_edge_id,
        }


def review_targets_for_chat(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    tenant_id: str,
    organization_id: str,
    limit: int = 8,
) -> list[str]:
    """Return Feishu user ids connected to a chat node for review routing hints."""

    if not chat_id:
        return []
    rows = conn.execute(
        """
        SELECT user_node.node_key AS user_id
        FROM knowledge_graph_edges edge
        JOIN knowledge_graph_nodes user_node ON user_node.id = edge.source_node_id
        JOIN knowledge_graph_nodes chat_node ON chat_node.id = edge.target_node_id
        WHERE edge.tenant_id = ?
          AND edge.organization_id = ?
          AND edge.edge_type = 'member_of_feishu_chat'
          AND user_node.node_type = 'feishu_user'
          AND chat_node.node_type = 'feishu_chat'
          AND chat_node.node_key = ?
          AND user_node.status = 'active'
          AND chat_node.status = 'active'
        ORDER BY edge.last_seen_at DESC, user_node.node_key
        LIMIT ?
        """,
        (tenant_id, organization_id, chat_id, max(0, int(limit))),
    ).fetchall()
    targets: list[str] = []
    for row in rows:
        value = str(row["user_id"] or "").strip()
        if value and value not in targets:
            targets.append(value)
    return targets


def register_feishu_chat_node(
    conn: sqlite3.Connection,
    event: FeishuMessageEvent,
    *,
    scope: str,
    tenant_id: str,
    organization_id: str,
    visibility_policy: str,
    entrypoint: str,
    allowed: bool,
) -> GraphNodeRegistration:
    """Register the Feishu chat as an enterprise graph node without ingesting message content."""

    ts = _event_time_ms(event)
    status = "active" if allowed else "discovered"
    org_node = _upsert_node(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        node_type="organization",
        node_key=organization_id,
        label=organization_id,
        visibility_policy=visibility_policy,
        status="active",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
        },
        seen_at=ts,
    )
    chat_node = _upsert_node(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        node_type="feishu_chat",
        node_key=event.chat_id,
        label=_chat_label(event),
        visibility_policy=visibility_policy,
        status=status,
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "chat_type": event.chat_type,
            "last_message_id": event.message_id,
            "allowed_by_current_runtime": allowed,
        },
        seen_at=ts,
    )
    edge_id = _upsert_edge(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        source_node_id=org_node["id"],
        target_node_id=chat_node["id"],
        edge_type="contains_feishu_chat",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "chat_type": event.chat_type,
        },
        seen_at=ts,
    )
    return GraphNodeRegistration(
        node_id=chat_node["id"],
        node_type="feishu_chat",
        node_key=event.chat_id,
        label=chat_node["label"],
        status=chat_node["status"],
        edge_id=edge_id,
    )


def register_feishu_message_context(
    conn: sqlite3.Connection,
    event: FeishuMessageEvent,
    *,
    scope: str,
    tenant_id: str,
    organization_id: str,
    visibility_policy: str,
    entrypoint: str,
    chat_node_id: str | None = None,
) -> FeishuMessageGraphRegistration:
    """Register allowed Feishu actor/message topology without storing raw message text."""

    ts = _event_time_ms(event)
    chat_node = None
    if chat_node_id:
        chat_node = conn.execute(
            "SELECT * FROM knowledge_graph_nodes WHERE id = ?",
            (chat_node_id,),
        ).fetchone()
    if chat_node is None:
        chat_registration = register_feishu_chat_node(
            conn,
            event,
            scope=scope,
            tenant_id=tenant_id,
            organization_id=organization_id,
            visibility_policy=visibility_policy,
            entrypoint=entrypoint,
            allowed=True,
        )
        chat_node = conn.execute(
            "SELECT * FROM knowledge_graph_nodes WHERE id = ?",
            (chat_registration.node_id,),
        ).fetchone()
    sender_key = event.sender_id or "unknown_feishu_actor"
    user_node = _upsert_node(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        node_type="feishu_user",
        node_key=sender_key,
        label=f"Feishu user {sender_key}",
        visibility_policy=visibility_policy,
        status="active",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "sender_type": event.sender_type,
            "identity_policy": "one_user_node_per_tenant_org_actor_id",
        },
        seen_at=ts,
    )
    message_node = _upsert_node(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        node_type="feishu_message",
        node_key=event.message_id,
        label=f"Feishu message {event.message_id}",
        visibility_policy=visibility_policy,
        status="observed",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "chat_id": event.chat_id,
            "chat_type": event.chat_type,
            "sender_type": event.sender_type,
            "message_type": event.message_type,
            "content_policy": "raw_text_not_stored_in_graph_node",
            "raw_event_policy": "content_lives_in_raw_events_after_allowlist_and_candidate_gate",
        },
        seen_at=ts,
    )
    if chat_node is None:
        raise RuntimeError("Feishu chat graph node was not registered")
    membership_edge = _upsert_edge(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        source_node_id=user_node["id"],
        target_node_id=chat_node["id"],
        edge_type="member_of_feishu_chat",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "chat_type": event.chat_type,
        },
        seen_at=ts,
    )
    sent_edge = _upsert_edge(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        source_node_id=user_node["id"],
        target_node_id=message_node["id"],
        edge_type="sent_feishu_message",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "chat_id": event.chat_id,
        },
        seen_at=ts,
    )
    contains_edge = _upsert_edge(
        conn,
        tenant_id=tenant_id,
        organization_id=organization_id,
        source_node_id=chat_node["id"],
        target_node_id=message_node["id"],
        edge_type="contains_feishu_message",
        metadata={
            "scope": scope,
            "entrypoint": entrypoint,
            "message_type": event.message_type,
            "content_policy": "raw_text_not_stored_in_graph_node",
        },
        seen_at=ts,
    )
    return FeishuMessageGraphRegistration(
        chat_node_id=chat_node["id"],
        user_node_id=user_node["id"],
        message_node_id=message_node["id"],
        membership_edge_id=membership_edge,
        sent_edge_id=sent_edge,
        contains_edge_id=contains_edge,
    )


def _upsert_node(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    organization_id: str,
    node_type: str,
    node_key: str,
    label: str,
    visibility_policy: str,
    status: str,
    metadata: dict[str, Any],
    seen_at: int,
) -> sqlite3.Row:
    existing = conn.execute(
        """
        SELECT *
        FROM knowledge_graph_nodes
        WHERE tenant_id = ?
          AND organization_id = ?
          AND node_type = ?
          AND node_key = ?
        """,
        (tenant_id, organization_id, node_type, node_key),
    ).fetchone()
    if existing is None:
        node_id = new_id("kgn")
        conn.execute(
            """
            INSERT INTO knowledge_graph_nodes (
              id, tenant_id, organization_id, node_type, node_key, label,
              visibility_policy, status, metadata_json, first_seen_at,
              last_seen_at, observation_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                node_id,
                tenant_id,
                organization_id,
                node_type,
                node_key,
                label,
                visibility_policy,
                status,
                json.dumps(metadata, ensure_ascii=False),
                seen_at,
                seen_at,
            ),
        )
        return conn.execute("SELECT * FROM knowledge_graph_nodes WHERE id = ?", (node_id,)).fetchone()

    next_status = _merge_status(existing["status"], status)
    conn.execute(
        """
        UPDATE knowledge_graph_nodes
        SET label = ?,
            visibility_policy = ?,
            status = ?,
            metadata_json = ?,
            last_seen_at = ?,
            observation_count = observation_count + 1
        WHERE id = ?
        """,
        (
            label,
            visibility_policy,
            next_status,
            json.dumps(_merge_metadata(existing["metadata_json"], metadata), ensure_ascii=False),
            seen_at,
            existing["id"],
        ),
    )
    return conn.execute("SELECT * FROM knowledge_graph_nodes WHERE id = ?", (existing["id"],)).fetchone()


def _upsert_edge(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    organization_id: str,
    source_node_id: str,
    target_node_id: str,
    edge_type: str,
    metadata: dict[str, Any],
    seen_at: int,
) -> str:
    existing = conn.execute(
        """
        SELECT id, metadata_json
        FROM knowledge_graph_edges
        WHERE tenant_id = ?
          AND organization_id = ?
          AND source_node_id = ?
          AND target_node_id = ?
          AND edge_type = ?
        """,
        (tenant_id, organization_id, source_node_id, target_node_id, edge_type),
    ).fetchone()
    if existing is None:
        edge_id = new_id("kge")
        conn.execute(
            """
            INSERT INTO knowledge_graph_edges (
              id, tenant_id, organization_id, source_node_id, target_node_id,
              edge_type, metadata_json, first_seen_at, last_seen_at,
              observation_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                edge_id,
                tenant_id,
                organization_id,
                source_node_id,
                target_node_id,
                edge_type,
                json.dumps(metadata, ensure_ascii=False),
                seen_at,
                seen_at,
            ),
        )
        return edge_id

    conn.execute(
        """
        UPDATE knowledge_graph_edges
        SET metadata_json = ?,
            last_seen_at = ?,
            observation_count = observation_count + 1
        WHERE id = ?
        """,
        (json.dumps(_merge_metadata(existing["metadata_json"], metadata), ensure_ascii=False), seen_at, existing["id"]),
    )
    return str(existing["id"])


def _chat_label(event: FeishuMessageEvent) -> str:
    chat_kind = event.chat_type or "chat"
    return f"Feishu {chat_kind} {event.chat_id}"


def _event_time_ms(event: FeishuMessageEvent) -> int:
    if event.create_time:
        try:
            return int(event.create_time)
        except ValueError:
            return now_ms()
    return now_ms()


def _merge_status(current: str, incoming: str) -> str:
    if current == "active" or incoming == "active":
        return "active"
    return incoming or current


def _merge_metadata(current_json: str, incoming: dict[str, Any]) -> dict[str, Any]:
    try:
        current = json.loads(current_json) if current_json else {}
    except json.JSONDecodeError:
        current = {}
    current = current if isinstance(current, dict) else {}
    current.update(incoming)
    return current
