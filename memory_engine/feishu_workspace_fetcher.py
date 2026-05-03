"""Workspace-level Feishu resource discovery and source routing.

This module keeps lark-cli as the operational adapter: `drive +search` is used
for resource discovery, then the concrete resource type is routed to docs,
sheets, or Base/Bitable shortcuts. It returns `FeishuIngestionSource` objects so
the existing candidate, review-policy, permission, and audit path remains the
single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .document_ingestion import FeishuIngestionSource
from .feishu_api_client import FeishuApiResult, run_lark_cli
from .feishu_bitable_fetcher import fetch_bitable_record_text, list_bitable_records, list_bitable_tables


WORKSPACE_DOC_TYPES = ("doc", "docx", "wiki", "sheet", "bitable")


@dataclass(frozen=True)
class WorkspaceResource:
    resource_type: str
    token: str
    title: str
    url: str | None = None
    obj_type: str | None = None
    table_id: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def route_type(self) -> str:
        value = (self.obj_type or self.resource_type).lower()
        if value in {"doc", "docx", "wiki"}:
            return "document"
        if value in {"sheet", "sheets", "spreadsheet"}:
            return "sheet"
        if value in {"bitable", "base"}:
            return "bitable"
        return value


@dataclass(frozen=True)
class WorkspaceActor:
    user_id: str | None = None
    open_id: str | None = None
    tenant_id: str = "tenant:demo"
    organization_id: str = "org:demo"
    roles: tuple[str, ...] = ("member", "reviewer")


def discover_workspace_resources(
    *,
    query: str = "",
    doc_types: Iterable[str] = WORKSPACE_DOC_TYPES,
    limit: int = 100,
    max_pages: int = 5,
    page_size: int = 20,
    edited_since: str | None = None,
    edited_until: str | None = None,
    opened_since: str | None = None,
    opened_until: str | None = None,
    created_since: str | None = None,
    created_until: str | None = None,
    commented_since: str | None = None,
    commented_until: str | None = None,
    folder_tokens: str | None = None,
    space_ids: str | None = None,
    mine: bool = False,
    creator_ids: str | None = None,
    sharer_ids: str | None = None,
    chat_ids: str | None = None,
    sort: str | None = None,
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[WorkspaceResource]:
    """Discover Feishu Drive/Wiki resources through `lark-cli drive +search`."""

    resources: list[WorkspaceResource] = []
    page_token: str | None = None
    pages_seen = 0
    while len(resources) < limit and pages_seen < max_pages:
        result = _drive_search(
            query=query,
            doc_types=doc_types,
            page_size=min(page_size, max(1, limit - len(resources))),
            page_token=page_token,
            edited_since=edited_since,
            edited_until=edited_until,
            opened_since=opened_since,
            opened_until=opened_until,
            created_since=created_since,
            created_until=created_until,
            commented_since=commented_since,
            commented_until=commented_until,
            folder_tokens=folder_tokens,
            space_ids=space_ids,
            mine=mine,
            creator_ids=creator_ids,
            sharer_ids=sharer_ids,
            chat_ids=chat_ids,
            sort=sort,
            profile=profile,
            as_identity=as_identity,
        )
        if not result.ok:
            raise ValueError(f"workspace discovery failed: {result.error_message} (error_code={result.error_code})")
        payload = result.data or {}
        found = [_resource_from_search_result(item) for item in _search_results(payload)]
        resources.extend(resource for resource in found if resource is not None)
        pages_seen += 1
        page_token = _next_page_token(payload)
        if not page_token:
            break
    return resources[:limit]


def fetch_workspace_resource_sources(
    resource: WorkspaceResource,
    *,
    max_sheet_rows: int = 80,
    max_bitable_records: int = 50,
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[FeishuIngestionSource]:
    """Fetch one discovered resource and return candidate-pipeline sources."""

    if resource.route_type == "document":
        return [_fetch_document_resource(resource, profile=profile, as_identity=as_identity)]
    if resource.route_type == "sheet":
        return _fetch_sheet_resource(resource, max_rows=max_sheet_rows, profile=profile, as_identity=as_identity)
    if resource.route_type == "bitable":
        return _fetch_bitable_resource(
            resource,
            max_records=max_bitable_records,
            profile=profile,
            as_identity=as_identity,
        )
    return []


def workspace_current_context(
    *,
    scope: str,
    actor: WorkspaceActor,
    source: FeishuIngestionSource,
    request_id: str | None = None,
    trace_id: str | None = None,
    timestamp: str | None = None,
    visibility: str = "team",
) -> dict[str, Any]:
    """Build a per-source permission context for workspace ingestion."""

    source_context: dict[str, Any] = {
        "entrypoint": "feishu_workspace_ingestion",
        "workspace_id": scope,
    }
    metadata = source.metadata or {}
    if source.source_type in {"document_feishu", "lark_doc"}:
        source_context["document_id"] = source.source_id
    if source.source_type == "lark_sheet":
        source_context["sheet_token"] = str(metadata.get("sheet_token") or source.source_id)
        if metadata.get("sheet_id"):
            source_context["sheet_id"] = str(metadata["sheet_id"])
    if source.source_type == "lark_bitable":
        source_context["bitable_record_id"] = str(metadata.get("record_id") or source.source_id)
        if metadata.get("table_id"):
            source_context["bitable_table_id"] = str(metadata["table_id"])
        if metadata.get("app_token"):
            source_context["bitable_app_token"] = str(metadata["app_token"])

    actor_payload: dict[str, Any] = {
        "tenant_id": actor.tenant_id,
        "organization_id": actor.organization_id,
        "roles": list(actor.roles),
    }
    if actor.user_id:
        actor_payload["user_id"] = actor.user_id
    if actor.open_id:
        actor_payload["open_id"] = actor.open_id

    return {
        "scope": scope,
        "tenant_id": actor.tenant_id,
        "organization_id": actor.organization_id,
        "permission": {
            "request_id": request_id or f"req_workspace_ingest_{_safe_id(source.source_id)}",
            "trace_id": trace_id or f"trace_workspace_ingest_{_safe_id(source.source_id)}",
            "actor": actor_payload,
            "source_context": source_context,
            "requested_action": "memory.create_candidate",
            "requested_visibility": visibility,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        },
    }


def _drive_search(
    *,
    query: str,
    doc_types: Iterable[str],
    page_size: int,
    page_token: str | None,
    edited_since: str | None,
    edited_until: str | None,
    opened_since: str | None,
    opened_until: str | None,
    created_since: str | None,
    created_until: str | None,
    commented_since: str | None,
    commented_until: str | None,
    folder_tokens: str | None,
    space_ids: str | None,
    mine: bool,
    creator_ids: str | None,
    sharer_ids: str | None,
    chat_ids: str | None,
    sort: str | None,
    profile: str | None,
    as_identity: str | None,
) -> FeishuApiResult:
    argv = _build_argv(
        [
            "drive",
            "+search",
            "--query",
            query,
            "--doc-types",
            ",".join(doc_types),
            "--page-size",
            str(page_size),
            "--format",
            "json",
        ],
        profile=profile,
        as_identity=as_identity or "user",
    )
    if page_token:
        argv.extend(["--page-token", page_token])
    if mine:
        argv.append("--mine")
    for flag, value in (
        ("--edited-since", edited_since),
        ("--edited-until", edited_until),
        ("--opened-since", opened_since),
        ("--opened-until", opened_until),
        ("--created-since", created_since),
        ("--created-until", created_until),
        ("--commented-since", commented_since),
        ("--commented-until", commented_until),
        ("--folder-tokens", folder_tokens),
        ("--space-ids", space_ids),
        ("--creator-ids", creator_ids),
        ("--sharer-ids", sharer_ids),
        ("--chat-ids", chat_ids),
        ("--sort", sort),
    ):
        if value:
            argv.extend([flag, value])
    return run_lark_cli(argv)


def _fetch_document_resource(
    resource: WorkspaceResource,
    *,
    profile: str | None,
    as_identity: str | None,
) -> FeishuIngestionSource:
    from .document_ingestion import fetch_feishu_document_text

    doc_ref = resource.url or resource.token
    text = fetch_feishu_document_text(doc_ref, profile=profile, as_identity=as_identity or "user")
    return FeishuIngestionSource(
        source_type="document_feishu",
        source_id=resource.token,
        title=resource.title,
        text=text,
        actor_id="workspace_document_fetch",
        source_url=resource.url,
        metadata={
            "document_id": resource.token,
            "resource_type": resource.resource_type,
            "obj_type": resource.obj_type,
        },
    )


def _fetch_sheet_resource(
    resource: WorkspaceResource,
    *,
    max_rows: int,
    profile: str | None,
    as_identity: str | None,
) -> list[FeishuIngestionSource]:
    info = _sheet_info(resource.token, profile=profile, as_identity=as_identity)
    sources: list[FeishuIngestionSource] = []
    for sheet in _sheets_from_info(info.data or {}):
        sheet_id = str(sheet.get("sheet_id") or sheet.get("id") or "")
        if not sheet_id:
            continue
        title = str(sheet.get("title") or sheet.get("name") or resource.title)
        values = _sheet_values(resource.token, sheet_id, max_rows=max_rows, profile=profile, as_identity=as_identity)
        if not values:
            continue
        text = _render_sheet_text(resource.title, title, values)
        sources.append(
            FeishuIngestionSource(
                source_type="lark_sheet",
                source_id=resource.token,
                title=f"{resource.title} / {title}",
                text=text,
                actor_id="workspace_sheet_fetch",
                source_url=resource.url,
                metadata={
                    "sheet_token": resource.token,
                    "sheet_id": sheet_id,
                    "sheet_title": title,
                    "resource_type": resource.resource_type,
                },
            )
        )
    return sources


def _fetch_bitable_resource(
    resource: WorkspaceResource,
    *,
    max_records: int,
    profile: str | None,
    as_identity: str | None,
) -> list[FeishuIngestionSource]:
    sources: list[FeishuIngestionSource] = []
    tables = list_bitable_tables(resource.token, profile=profile, as_identity=as_identity or "user")
    for table in tables:
        table_id = str(table.get("table_id") or "")
        if not table_id:
            continue
        records = list_bitable_records(
            resource.token,
            table_id,
            limit=max_records,
            profile=profile,
            as_identity=as_identity or "user",
        )
        for record in records[:max_records]:
            record_id = str(record.get("record_id") or "")
            if not record_id:
                continue
            sources.append(
                fetch_bitable_record_text(
                    resource.token,
                    table_id,
                    record_id,
                    profile=profile,
                    as_identity=as_identity or "user",
                )
            )
    return sources


def _sheet_info(token: str, *, profile: str | None, as_identity: str | None) -> FeishuApiResult:
    argv = _build_argv(
        ["sheets", "+info", "--spreadsheet-token", token],
        profile=profile,
        as_identity=as_identity or "user",
    )
    result = run_lark_cli(argv)
    if not result.ok:
        raise ValueError(f"sheet info failed: {result.error_message} (error_code={result.error_code})")
    return result


def _sheet_values(
    token: str,
    sheet_id: str,
    *,
    max_rows: int,
    profile: str | None,
    as_identity: str | None,
) -> list[list[Any]]:
    argv = _build_argv(
        [
            "sheets",
            "+read",
            "--spreadsheet-token",
            token,
            "--sheet-id",
            sheet_id,
            "--range",
            f"{sheet_id}!A1:Z{max_rows}",
            "--value-render-option",
            "ToString",
        ],
        profile=profile,
        as_identity=as_identity or "user",
    )
    result = run_lark_cli(argv)
    if not result.ok:
        raise ValueError(f"sheet read failed: {result.error_message} (error_code={result.error_code})")
    return _values_from_sheet_read(result.data or {})


def _resource_from_search_result(item: dict[str, Any]) -> WorkspaceResource | None:
    nested = _first_dict(item, "doc", "document", "wiki", "resource", "entity") or item
    resource_type = _first_string(item, "type", "doc_type", "resource_type", "obj_type")
    resource_type = resource_type or _first_string(nested, "type", "doc_type", "resource_type", "obj_type")
    token = _first_string(nested, "token", "file_token", "obj_token", "doc_token", "wiki_token", "app_token")
    token = token or _first_string(item, "token", "file_token", "obj_token", "doc_token", "wiki_token", "app_token")
    if not resource_type or not token:
        return None
    title = _first_string(nested, "title", "name") or _first_string(item, "title", "name") or token
    url = _first_string(nested, "url", "link") or _first_string(item, "url", "link")
    obj_type = _first_string(nested, "obj_type") or _first_string(item, "obj_type")
    return WorkspaceResource(
        resource_type=_normalize_resource_type(resource_type),
        token=token,
        title=title,
        url=url,
        obj_type=_normalize_resource_type(obj_type) if obj_type else None,
        table_id=_first_string(nested, "table_id"),
        raw=item,
    )


def _search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("results", "items", "docs"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _next_page_token(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    token = data.get("page_token") or data.get("next_page_token")
    has_more = data.get("has_more")
    return token if isinstance(token, str) and token and has_more is not False else None


def _sheets_from_info(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    candidates = [
        data.get("sheets") if isinstance(data, dict) else None,
        data.get("sheet") if isinstance(data, dict) else None,
    ]
    spreadsheet = data.get("spreadsheet") if isinstance(data, dict) else None
    if isinstance(spreadsheet, dict):
        candidates.extend([spreadsheet.get("sheets"), spreadsheet.get("sheet")])
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _values_from_sheet_read(payload: dict[str, Any]) -> list[list[Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return []
    value_range = data.get("valueRange") or data.get("value_range")
    values = value_range.get("values") if isinstance(value_range, dict) else data.get("values")
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, list)]


def _render_sheet_text(resource_title: str, sheet_title: str, values: list[list[Any]]) -> str:
    lines = [f"# {resource_title}", f"## Sheet: {sheet_title}"]
    for row in values:
        rendered_cells = [str(cell).strip() for cell in row if str(cell).strip()]
        if rendered_cells:
            lines.append(" | ".join(rendered_cells))
    return "\n".join(lines)


def _build_argv(
    command: list[str],
    *,
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[str]:
    argv: list[str] = []
    if profile:
        argv.extend(["--profile", profile])
    if as_identity:
        argv.extend(["--as", as_identity])
    argv.extend(command)
    return argv


def _first_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return None


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_resource_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "base":
        return "bitable"
    return normalized


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)[:64] or "source"
