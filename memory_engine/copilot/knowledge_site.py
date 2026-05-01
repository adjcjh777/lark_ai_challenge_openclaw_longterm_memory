from __future__ import annotations

import datetime as _dt
import html
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from memory_engine.copilot.admin import AdminQueryService, _redact_sensitive_text


STATIC_SITE_BOUNDARY = (
    "static read-only knowledge site export for local/staging review; "
    "no production deployment, SSO, or productized live claim."
)


def export_knowledge_site(
    *,
    db_path: str | Path,
    output_dir: str | Path,
    scope: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    """Export a self-contained, read-only Wiki + graph site bundle."""

    output = Path(output_dir).expanduser().resolve()
    data_dir = output / "data"
    wiki_dir = output / "wiki"
    data_dir.mkdir(parents=True, exist_ok=True)
    wiki_dir.mkdir(parents=True, exist_ok=True)

    with _open_readonly_connection(db_path) as conn:
        service = AdminQueryService(conn)
        summary = _redact_payload(service.summary())
        wiki = _redact_payload(service.wiki_overview(scope=scope, limit=limit))
        graph = _redact_payload(service.graph_workspace(limit=limit))
        scopes = [scope] if scope else [str(item["scope"]) for item in wiki.get("scopes", [])]
        wiki_files = _write_scope_markdown(service, wiki_dir=wiki_dir, scopes=scopes)

    generated_at = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
    manifest = {
        "ok": True,
        "generated_at": generated_at,
        "boundary": STATIC_SITE_BOUNDARY,
        "read_only": True,
        "entrypoint": "index.html",
        "scope": scope,
        "scope_count": len(scopes),
        "wiki_card_count": int(wiki.get("card_count") or 0),
        "graph_node_count": int(graph.get("workspace_node_count") or 0),
        "graph_edge_count": int(graph.get("workspace_edge_count") or 0),
        "generation_policy": wiki.get("generation_policy") or {},
        "files": {
            "index": "index.html",
            "manifest": "data/manifest.json",
            "wiki": "data/wiki.json",
            "graph": "data/graph.json",
            "summary": "data/summary.json",
            "scope_markdown": [item["path"] for item in wiki_files],
        },
    }
    site_payload = {
        "manifest": manifest,
        "summary": summary,
        "wiki": wiki,
        "graph": graph,
        "wiki_files": wiki_files,
    }

    _write_json(data_dir / "manifest.json", manifest)
    _write_json(data_dir / "summary.json", summary)
    _write_json(data_dir / "wiki.json", wiki)
    _write_json(data_dir / "graph.json", graph)
    (output / "index.html").write_text(_render_index_html(site_payload), encoding="utf-8")
    return {
        "ok": True,
        "output_dir": str(output),
        "entrypoint": str(output / "index.html"),
        "manifest": manifest,
    }


def _open_readonly_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _write_scope_markdown(
    service: AdminQueryService,
    *,
    wiki_dir: Path,
    scopes: list[str],
) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for scope in scopes:
        markdown = service.wiki_export_markdown(scope=scope)
        filename = f"{_safe_slug(scope)}.md"
        target = wiki_dir / filename
        target.write_text(markdown, encoding="utf-8")
        files.append({"scope": scope, "path": f"wiki/{filename}"})
    return files


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_payload(item) for key, item in value.items()}
    return value


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()).strip("_")
    return slug or "scope"


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")


def _render_index_html(site_payload: dict[str, Any]) -> str:
    title = "Feishu Memory Copilot Knowledge Site"
    data = _json_for_script(site_payload)
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
      --paper: #fbfaf5;
      --ink: #18201d;
      --muted: #66706b;
      --line: #d8ddd6;
      --field: #eef1ed;
      --moss: #355c4b;
      --clay: #9d5d3f;
      --blue: #2f5f89;
      --gold: #b2872d;
      --danger: #9f3434;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--field);
      color: var(--ink);
      font-family: ui-sans-serif, "Avenir Next", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 14px;
    }}
    main {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
    }}
    aside {{
      background: #17201d;
      color: #f4f0e8;
      padding: 18px;
      border-right: 1px solid #0f1613;
    }}
    h1, h2, h3 {{ margin: 0; line-height: 1.2; }}
    h1 {{ font-size: 22px; max-width: 250px; }}
    h2 {{ font-size: 16px; }}
    h3 {{ font-size: 15px; margin-bottom: 8px; }}
    .boundary {{
      margin: 14px 0 18px;
      color: #cbd5cf;
      line-height: 1.45;
      font-size: 12px;
    }}
    .scope-list, .metric-list {{
      display: grid;
      gap: 8px;
      margin-top: 16px;
    }}
    .metric {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 8px 0;
      border-top: 1px solid rgba(244, 240, 232, .16);
    }}
    .metric span {{ color: #cbd5cf; }}
    .metric strong {{ color: #fff; }}
    button, a.button {{
      min-height: 34px;
      border: 1px solid var(--line);
      background: #fffdf8;
      color: var(--ink);
      padding: 0 12px;
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font: inherit;
    }}
    button.active {{
      background: var(--moss);
      border-color: var(--moss);
      color: #fff;
    }}
    .content {{
      padding: 18px;
      overflow: auto;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }}
    .search {{
      width: min(460px, 100%);
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: #fff;
      font: inherit;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(360px, 1fr) minmax(360px, 1fr);
      gap: 14px;
      align-items: start;
    }}
    .panel {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-height: 220px;
      padding: 14px;
    }}
    .policy {{
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 6px 10px;
      font-size: 13px;
      margin-top: 12px;
    }}
    .policy span:nth-child(odd) {{ color: var(--muted); }}
    .card {{
      border-top: 1px solid var(--line);
      padding: 12px 0;
    }}
    .card:first-child {{ border-top: 0; padding-top: 0; }}
    .value {{ line-height: 1.55; margin: 8px 0; }}
    .evidence {{
      border-left: 3px solid var(--gold);
      padding-left: 10px;
      color: #33413d;
      line-height: 1.45;
      font-size: 13px;
    }}
    .tag-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }}
    .tag {{
      min-height: 24px;
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 2px 8px;
      background: #e7ede9;
      color: #27322f;
      font-size: 12px;
    }}
    .tag.warn {{ background: #f4e6d6; color: #6f3f21; }}
    .graph {{
      position: relative;
      min-height: 520px;
      border: 1px solid var(--line);
      background: #fffdf8;
      overflow: hidden;
    }}
    .node {{
      position: absolute;
      width: 162px;
      min-height: 70px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 7px;
      background: #fff;
      padding: 9px;
      box-shadow: 0 8px 22px rgba(23, 32, 29, .08);
      cursor: pointer;
      text-align: left;
    }}
    .node.memory {{ border-left-color: var(--moss); }}
    .node.evidence_source {{ border-left-color: var(--gold); }}
    .node.feishu_user {{ border-left-color: var(--clay); }}
    .node.selected {{
      outline: 2px solid var(--moss);
      outline-offset: 2px;
    }}
    .node strong {{
      display: block;
      font-size: 12px;
      margin-bottom: 4px;
      overflow-wrap: anywhere;
    }}
    .node small {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      overflow-wrap: anywhere;
    }}
    .edge-list {{
      margin-top: 12px;
      max-height: 260px;
      overflow: auto;
    }}
    .graph-detail {{
      margin-top: 12px;
      border: 1px solid var(--line);
      background: #f6f4ed;
      border-radius: 7px;
      padding: 12px;
      line-height: 1.45;
    }}
    .graph-detail h3 {{
      margin-bottom: 10px;
    }}
    .relationship-focus {{
      margin-top: 12px;
      border: 1px solid #d8c8aa;
      background: #fffaf0;
      border-radius: 7px;
      padding: 12px;
      line-height: 1.45;
    }}
    .relationship-focus h3 {{
      margin: 0 0 10px;
      font-size: 14px;
    }}
    .path-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
      gap: 8px;
      align-items: center;
      border-top: 1px solid var(--line);
      padding: 8px 0;
      font-size: 12px;
    }}
    .path-row:first-of-type {{ border-top: 0; }}
    .node-pill {{
      min-width: 0;
      overflow-wrap: anywhere;
      border: 1px solid var(--line);
      background: #fffdf8;
      border-radius: 999px;
      padding: 5px 8px;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: 128px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 12px;
    }}
    .detail-grid span:nth-child(odd) {{
      color: var(--muted);
    }}
    .detail-json {{
      margin-top: 10px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
      white-space: pre-wrap;
      font-size: 12px;
      max-height: 170px;
      overflow: auto;
    }}
    .edge {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 8px;
      align-items: center;
      border-top: 1px solid var(--line);
      padding: 8px 0;
      font-size: 12px;
      cursor: pointer;
    }}
    .edge:first-child {{ border-top: 0; }}
    .edge.selected {{
      background: #f0eadf;
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }}
    .footer-mark {{
      margin-top: 18px;
      color: #aeb8b2;
      font-size: 12px;
    }}
    .footer-mark a {{ color: #f4f0e8; }}
    .empty {{ color: var(--muted); padding: 16px 0; }}
    @media (max-width: 980px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ position: static; }}
      .grid {{ grid-template-columns: 1fr; }}
      .topbar {{ align-items: stretch; flex-direction: column; }}
      .graph {{ min-height: 680px; }}
      .path-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <aside>
      <h1>{escaped_title}</h1>
      <div class="boundary" id="boundary"></div>
      <div class="metric-list" id="metrics"></div>
      <div class="scope-list" id="scopes"></div>
      <div class="footer-mark">Created By <a href="https://deerflow.tech" target="_blank" rel="noreferrer">Deerflow</a></div>
    </aside>
    <section class="content">
      <div class="topbar">
        <div class="tag-row" id="policy"></div>
        <input class="search" id="search" type="search" placeholder="Filter wiki cards or graph nodes">
      </div>
      <div class="grid">
        <section class="panel">
          <h2>LLM Wiki</h2>
          <div class="policy" id="policyKv"></div>
          <div id="cards"></div>
        </section>
        <section class="panel">
          <h2>Knowledge Graph</h2>
          <div class="graph" id="graph"></div>
          <div class="graph-detail" id="graphDetail"></div>
          <div class="relationship-focus" id="relationshipFocus"></div>
          <div class="edge-list" id="edges"></div>
        </section>
      </div>
    </section>
  </main>
  <script>
    window.COPILOT_KNOWLEDGE_SITE = {data};
    const site = window.COPILOT_KNOWLEDGE_SITE;
    const $ = (id) => document.getElementById(id);
    const text = (value) => value === null || value === undefined || value === "" ? "-" : String(value);
    const esc = (value) => text(value).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}})[c]);
    let selectedGraphItem = null;

    function render() {{
      const query = $("search").value.trim().toLowerCase();
      renderShell();
      renderCards(query);
      renderGraph(query);
    }}

    function renderShell() {{
      const manifest = site.manifest || {{}};
      const wiki = site.wiki || {{}};
      const summary = site.summary || {{}};
      const policy = wiki.generation_policy || {{}};
      $("boundary").textContent = manifest.boundary || "";
      $("metrics").innerHTML = [
        metric("Active cards", manifest.wiki_card_count),
        metric("Graph nodes", manifest.graph_node_count),
        metric("Graph edges", manifest.graph_edge_count),
        metric("Memories", summary.memory_total),
        metric("Audit", summary.audit_total)
      ].join("");
      $("policy").innerHTML = [
        tag(policy.source || "unknown"),
        tag(policy.raw_events_included ? "raw events included" : "raw events excluded"),
        tag(policy.requires_evidence ? "evidence required" : "evidence optional"),
        tag(policy.writes_feishu ? "writes Feishu" : "read-only")
      ].join("");
      $("policyKv").innerHTML = `
        <span>Generated</span><strong class="mono">${{esc(manifest.generated_at)}}</strong>
        <span>Boundary</span><strong>${{esc(manifest.read_only ? "read-only" : "unknown")}}</strong>
        <span>Entry</span><strong class="mono">${{esc(manifest.entrypoint)}}</strong>
      `;
      $("scopes").innerHTML = (site.wiki_files || []).map(item =>
        `<a class="button" href="${{esc(item.path)}}">${{esc(item.scope)}}</a>`
      ).join("") || `<div class="empty">No exported scope</div>`;
    }}

    function metric(label, value) {{
      return `<div class="metric"><span>${{esc(label)}}</span><strong>${{esc(value)}}</strong></div>`;
    }}

    function tag(value, klass = "") {{
      return `<span class="tag ${{klass}}">${{esc(value)}}</span>`;
    }}

    function renderCards(query) {{
      const cards = (site.wiki.cards || []).filter(card => matchCard(card, query));
      $("cards").innerHTML = cards.map(card => {{
        const evidence = card.evidence || {{}};
        return `<article class="card">
          <h3>${{esc(card.subject)}}</h3>
          <div class="value">${{esc(card.current_value)}}</div>
          <div class="evidence">${{esc(evidence.quote)}}<br><span class="mono">${{esc(evidence.source_type)}} / ${{esc(evidence.source_id)}} / ${{esc(evidence.document_title)}}</span></div>
          <div class="tag-row">
            ${{tag(card.scope)}}
            ${{tag(card.type)}}
            ${{tag(`v${{card.version || 1}}`)}}
            ${{card.superseded_version_count ? tag(`${{card.superseded_version_count}} superseded`, "warn") : tag("current")}}
          </div>
        </article>`;
      }}).join("") || `<div class="empty">No matching Wiki cards</div>`;
    }}

    function matchCard(card, query) {{
      if (!query) return true;
      return [card.subject, card.current_value, card.scope, card.type, card.evidence?.quote]
        .some(value => text(value).toLowerCase().includes(query));
    }}

    function renderGraph(query) {{
      const nodes = (site.graph.nodes || []).filter(node => matchNode(node, query));
      const ids = new Set(nodes.map(node => node.id));
      const edges = (site.graph.edges || []).filter(edge =>
        (!query && ids.has(edge.source_node_id) && ids.has(edge.target_node_id)) ||
        ids.has(edge.source_node_id) ||
        ids.has(edge.target_node_id) ||
        text(edge.edge_type).toLowerCase().includes(query)
      );
      if (!selectedGraphItem || !graphItemExists(selectedGraphItem, nodes, edges)) {{
        selectedGraphItem = nodes[0] ? {{ type: "node", id: nodes[0].id }} : edges[0] ? {{ type: "edge", id: edges[0].id }} : null;
      }}
      const width = $("graph").clientWidth || 720;
      const cardWidth = 162;
      const cardGap = 18;
      const rowHeight = 112;
      const cols = Math.max(1, Math.floor((width - 24) / (cardWidth + cardGap)));
      const rows = Math.ceil(nodes.length / cols);
      const columnWidth = (width - 24) / cols;
      $("graph").style.minHeight = `${{Math.max(520, rows * rowHeight + 28)}}px`;
      $("graph").innerHTML = nodes.map((node, index) => {{
        const col = index % cols;
        const row = Math.floor(index / cols);
        const x = 12 + col * columnWidth;
        const y = 14 + row * rowHeight;
        const selected = selectedGraphItem?.type === "node" && selectedGraphItem.id === node.id ? "selected" : "";
        return `<div class="node ${{esc(node.node_type)}} ${{selected}}" role="button" tabindex="0" data-node-id="${{esc(node.id)}}" style="left:${{x}}px;top:${{y}}px">
          <strong>${{esc(node.label)}}</strong>
          <small class="mono">${{esc(node.node_type)}} / ${{esc(node.node_key || node.id)}}</small>
        </div>`;
      }}).join("") || `<div class="empty">No matching graph nodes</div>`;
      $("edges").innerHTML = edges.slice(0, 80).map(edge => `
        <div class="edge ${{selectedGraphItem?.type === "edge" && selectedGraphItem.id === edge.id ? "selected" : ""}}" data-edge-id="${{esc(edge.id)}}">
          <span class="mono">${{esc(edge.source_label || edge.source_node_id)}}</span>
          <strong>${{esc(edge.edge_type)}}</strong>
          <span class="mono">${{esc(edge.target_label || edge.target_node_id)}}</span>
        </div>`
      ).join("") || `<div class="empty">No matching graph edges</div>`;
      renderGraphDetail(nodes, edges);
    }}

    function graphItemExists(item, nodes, edges) {{
      if (item.type === "node") return nodes.some(node => node.id === item.id);
      if (item.type === "edge") return edges.some(edge => edge.id === item.id);
      return false;
    }}

    function renderGraphDetail(nodes, edges) {{
      if (!selectedGraphItem) {{
        $("graphDetail").innerHTML = `<div class="empty">Select a node or edge</div>`;
        $("relationshipFocus").innerHTML = `<h3>Relationship Focus</h3><div class="empty">Select a node or edge</div>`;
        return;
      }}
      if (selectedGraphItem.type === "edge") {{
        const edge = edges.find(item => item.id === selectedGraphItem.id);
        $("graphDetail").innerHTML = edge ? edgeDetail(edge) : `<div class="empty">Select a graph edge</div>`;
        $("relationshipFocus").innerHTML = edge ? relationshipFocusForEdge(edge, nodes) : `<h3>Relationship Focus</h3><div class="empty">Select a graph edge</div>`;
        return;
      }}
      const node = nodes.find(item => item.id === selectedGraphItem.id);
      $("graphDetail").innerHTML = node ? nodeDetail(node, edges) : `<div class="empty">Select a graph node</div>`;
      $("relationshipFocus").innerHTML = node ? relationshipFocusForNode(node, edges, nodes) : `<h3>Relationship Focus</h3><div class="empty">Select a graph node</div>`;
    }}

    function relationshipFocusForNode(node, edges, nodes) {{
      const related = edges.filter(edge => edge.source_node_id === node.id || edge.target_node_id === node.id);
      const rows = related.slice(0, 8).map(edge => pathRow(edge, nodes)).join("");
      return `<h3>Relationship Focus</h3>
        <div class="detail-grid">
          <span>Selected node</span><strong class="mono">${{esc(node.node_type)}} / ${{esc(node.node_key || node.id)}}</strong>
          <span>Evidence paths</span><strong>${{esc(related.length)}}</strong>
        </div>
        ${{rows || `<div class="empty">No adjacent relationship in current filter</div>`}}`;
    }}

    function relationshipFocusForEdge(edge, nodes) {{
      return `<h3>Relationship Focus</h3>
        <div class="detail-grid">
          <span>Selected edge</span><strong class="mono">${{esc(edge.edge_type)}}</strong>
          <span>Evidence path</span><strong>${{esc(edge.source_type)}} → ${{esc(edge.target_type)}}</strong>
        </div>
        ${{pathRow(edge, nodes)}}`;
    }}

    function pathRow(edge, nodes) {{
      return `<div class="path-row" data-focus-edge-id="${{esc(edge.id)}}">
        <span class="node-pill">${{esc(labelForNode(edge.source_node_id, edge.source_label, nodes))}}</span>
        <strong>${{esc(edge.edge_type)}}</strong>
        <span class="node-pill">${{esc(labelForNode(edge.target_node_id, edge.target_label, nodes))}}</span>
      </div>`;
    }}

    function labelForNode(nodeId, fallback, nodes) {{
      const node = nodes.find(item => item.id === nodeId);
      return node ? `${{node.label}} (${{node.node_type}})` : (fallback || nodeId);
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

    function matchNode(node, query) {{
      if (!query) return true;
      return [node.label, node.node_type, node.node_key, node.id]
        .some(value => text(value).toLowerCase().includes(query));
    }}

    $("search").addEventListener("input", render);
    document.addEventListener("click", event => {{
      const target = event.target;
      if (!(target instanceof Element)) return;
      const node = target.closest("[data-node-id]");
      if (node) {{
        selectedGraphItem = {{ type: "node", id: node.dataset.nodeId }};
        renderGraph($("search").value.trim().toLowerCase());
        return;
      }}
      const edge = target.closest("[data-edge-id]");
      if (edge) {{
        selectedGraphItem = {{ type: "edge", id: edge.dataset.edgeId }};
        renderGraph($("search").value.trim().toLowerCase());
      }}
    }});
    document.addEventListener("keydown", event => {{
      if ((event.key === "Enter" || event.key === " ") && event.target.dataset?.nodeId) {{
        event.preventDefault();
        selectedGraphItem = {{ type: "node", id: event.target.dataset.nodeId }};
        renderGraph($("search").value.trim().toLowerCase());
      }}
    }});
    window.addEventListener("resize", () => renderGraph($("search").value.trim().toLowerCase()));
    render();
  </script>
</body>
</html>
"""
