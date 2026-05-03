# Workspace Ingestion Architecture ADR

Date: 2026-05-04

Status: Accepted for L2 limited workspace pilot. This is not production full-workspace ingestion yet.

## Decision

Use **lark-cli first** for the current OpenClaw-native pilot, and keep the architecture ready to move hot paths to native Feishu OpenAPI / SDK when the pilot becomes a long-running service.

The reason is practical. `lark-cli` already wraps the Feishu operations this project needs for controlled ingestion: `drive +search` for broad resource discovery, `drive files list` for deterministic Drive root/folder listing, `wiki nodes list` for deterministic Wiki space listing, `docs +fetch --api-version v2` for document content, `sheets +info/+read` for spreadsheet content, and `base +table-list/+record-list/+record-get` for Bitable. It is easy for OpenClaw, scripts, and operators to run, inspect, and replay. When Drive search returns zero resources or the operator already has a reviewed token, the script also supports explicit resources through `--resource type:token[:title] --skip-discovery`; that is an operator-scoped pilot path, not a hidden full-workspace crawler.

Native Feishu OpenAPI remains the production direction for a daemon because it gives tighter control over pagination, cursor state, retries, rate limits, event subscriptions, telemetry, and deployment. Do not force a binary choice: keep `lark-cli` as the pilot and operations adapter, then replace the subprocess boundary only where the service needs production-grade throughput or lifecycle control.

Research basis:

- Anthropic describes Opus 4.6 as better at gathering context, following long tasks, and judging when to work independently; this ADR keeps that style: read the system first, then make the smallest durable decision.
- Anthropic's Opus 4.7 announcement describes a more opinionated model with stronger literal instruction following; this repo should not copy that 4.7 voice when the requested style target is Opus 4.6.
- The local lark-cli skills and `lark-cli --help` confirm `drive +search`, `docs +fetch`, `sheets +read`, and `base +record-*` are first-class shortcut commands.

## Non-Goals

- Do not claim production deployment.
- Do not claim every workspace object is already ingested.
- Do not vectorize all raw document or table content.
- Do not open a second Feishu listener alongside OpenClaw websocket, Copilot lark-cli sandbox, or the legacy listener.
- Do not let an Agent call an `ingest_all_workspace` tool without admin policy and source review gates.

## Source Routing

| Source | Discovery | Fetch | Permission key | Ingestion mode | Notes |
|---|---|---|---|---|---|
| Doc / Docx | `drive +search --doc-types doc,docx,wiki` | `docs +fetch --api-version v2 --doc <url-or-token>` | `document_id` | candidate pipeline | Wiki URLs must resolve or be passed through `docs +fetch` only when the CLI can resolve them. |
| Drive folder/root | `drive files list --params '{"folder_token":"..."}'` or root listing | route each returned docx/sheet/bitable by type | per routed source | candidate pipeline | This is the reliable fallback when search has no results. Folder recursion is bounded by `--walk-max-depth`. |
| Wiki space | `wiki nodes list --params '{"space_id":"my_library"}'` or real space id | route each node `obj_type/obj_token` by type | per routed source | candidate pipeline | Wiki node token is not used as the fetch token; the route uses `obj_token`. |
| Sheet | `drive +search --doc-types sheet` | `sheets +info`, then `sheets +read` per sheet | `sheet_token`, optional `sheet_id` | candidate pipeline | Read a bounded range first. Do not export whole files by default. |
| Bitable / Base | `drive +search --doc-types bitable` | `base +table-list`, `base +record-list`, `base +record-get` | `bitable_app_token`, `bitable_table_id`, `bitable_record_id` | candidate pipeline | Treat each record as a source with field-level evidence. |
| Feishu Task | task list or explicit task id | task OpenAPI via lark-cli | `task_id` | candidate pipeline | Already implemented as `feishu.fetch_task` internally. |
| Meeting / Minutes | minutes list or explicit token | minutes APIs via lark-cli | `meeting_id` | candidate pipeline | Prefer AI summary/todos/chapters; fall back to transcript snippets. |
| IM message | OpenClaw Feishu websocket only | event payload | `chat_id` | candidate probe then review policy | Reuse existing allowlist / `/enable_memory` group policy. |

All routes converge here:

```text
lark-cli resource fetch
  -> FeishuIngestionSource
  -> ingest_feishu_source()
  -> memory.create_candidate
  -> review policy
  -> active / candidate / rejected / stale / superseded
```

## Memory Judgment

The system should not remember “everything.” It should remember durable operational facts that stay useful after the original message, document, row, or meeting is no longer open.

Remember candidates when the source contains:

- Decisions: selected plan, final owner, final deadline, launch window, rollout rule, rollback rule.
- Stable workflow rules: required approval, review path, deployment checklist, escalation route.
- Project facts: system boundary, environment, API contract, storage policy, permission rule.
- Conflicts or overrides: “改成…”, “之前那条废弃”, “以后按…”.
- Risks and constraints: compliance, security, tenant boundary, sensitive-data handling.
- Preferences that affect future agent behavior: writing style, routing preference, reviewer preference.

Do not remember by default:

- Short-lived chatter, acknowledgements, jokes, social filler, status pings without durable facts.
- Raw tables or long documents as embeddings.
- Content the current actor cannot fetch, cite, or review.
- Sensitive secrets, credentials, raw tokens, or private content outside the permission boundary.

Low-risk, low-importance, non-conflicting candidates may auto-confirm by review policy. Important project progress, sensitive content, important-role statements, and conflicting updates stay as candidates and go to reviewer/owner.

## Route Reuse

Yes, the workspace route should extend the group-chat architecture instead of creating a new memory path.

The group-chat pipeline already has the right properties:

- source-specific `current_context.permission`;
- source-context mismatch fail closed before fetch;
- candidate-first governance;
- review policy;
- evidence and audit;
- stale-on-revocation behavior;
- OpenClaw-facing `fmc_*` tools for recall and review actions.

The workspace pilot adds a discovery layer before this pipeline. It does not replace `CopilotService`.

## Shared Database

Use one governed ledger, not separate memory databases per source.

The existing SQLite schema already separates raw events, memories, evidence, versions, audit events, and graph nodes. That is the right model for combining chat, docs, sheets, Bitable, tasks, and meetings because the memory object can stay source-agnostic while each evidence row keeps source type, source id, quote, tenant/org, and revocation state.

Cross-source corroboration should work like this:

1. The active memory has one current value.
2. Evidence rows can point to chat messages, docs, sheets, Bitable records, tasks, or meetings.
3. A new source that supports the same value increases confidence and adds evidence.
4. A new source that contradicts the value creates a conflict candidate, not a silent overwrite.
5. Revoking a source marks its evidence stale and hides affected active memory when needed.

## Code Change In This Slice

This slice adds a controlled adapter:

- `memory_engine/feishu_workspace_fetcher.py`
  - discovers resources with `drive +search`;
  - discovers Drive root/folder resources with `drive files list`;
  - discovers Wiki space resources with `wiki nodes list` and routes `obj_token` by `obj_type`;
  - routes document, sheet, and Bitable resources;
  - builds per-source permission context.
- `memory_engine/feishu_workspace_registry.py`
  - records workspace ingestion runs;
  - stores discovered resource keys and fetched source keys;
  - stores resumable discovery cursors by discovery filter key;
  - skips unchanged versioned resources on repeat runs;
  - marks sources stale only inside the same discovery filter when explicitly requested;
  - records fetch permission denied / not found as registry revocation.
- `scripts/feishu_workspace_ingest.py`
  - dry-run discovery mode;
  - controlled candidate-only ingestion mode requiring an actor id.
  - registry-backed repeat-run summary with fetched, skipped, failed, and stale counts.
  - Drive search scan filters for `--mine`, creator/sharer/chat IDs, sort, and since/until time windows.
  - `--resume-cursor` / `--reset-cursor` for long scans across multiple runs.
  - `--resource type:token[:title]` and `--skip-discovery` for explicit, reviewed resources when Drive search is not the right entry point.
  - `--folder-walk-root`, `--folder-walk-tokens`, `--wiki-space-walk-ids`, `--walk-max-depth`, and `--walk-page-size` for deterministic folder/wiki discovery.
  - direct folder/wiki walk respects `--doc-types`, matching the search path's type filtering.
  - explicit `no_sources` result rows when a discovered resource returns no supported text source, instead of silently disappearing.
- `scripts/check_feishu_workspace_registry_gate.py`
  - read-only gate for workspace runs, source registry rows, cursor rows, and required ingested / skipped / stale / failed evidence.
- `scripts/check_workspace_mixed_source_corroboration_gate.py`
  - local temp-SQLite gate proving chat evidence, document evidence, and Bitable evidence share the same governed ledger: same-value document evidence corroborates the active memory, while different-value Bitable evidence becomes a conflict candidate and does not overwrite active memory.
- `scripts/check_workspace_ingestion_latency_gate.py`
  - local warm-path latency gate for document/workspace candidate ingestion. It reuses the existing document ingestion benchmark and checks quality plus conservative latency thresholds without calling Feishu APIs.
- `lark_sheet` source support in schema and ingestion metadata.
- Bitable fetch compatibility for the current lark-cli 1.0.22 output shapes: `base +table-list` can return `tables[].id`, `base +record-list` can return tabular rows plus `record_id_list`, and `base +record-get` can return fields directly under `record`.
- Tests in `tests/test_feishu_fetchers.py`, `tests/test_feishu_workspace_fetcher.py`, and `tests/test_feishu_workspace_registry.py`.

Example dry run:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --query "" \
  --mine \
  --opened-since 30d \
  --sort edit_time \
  --limit 20 \
  --profile feishu-ai-challenge \
  --dry-run \
  --json
```

Example controlled ingestion:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --query "" \
  --mine \
  --opened-since 30d \
  --sort edit_time \
  --limit 20 \
  --profile feishu-ai-challenge \
  --actor-open-id "$COPILOT_REVIEWER_OPEN_ID" \
  --tenant-id tenant:demo \
  --organization-id org:demo \
  --json
```

Example repeat run with registry stale marking:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --query "" \
  --mine \
  --opened-since 30d \
  --sort edit_time \
  --limit 20 \
  --profile feishu-ai-challenge \
  --actor-open-id "$COPILOT_REVIEWER_OPEN_ID" \
  --mark-missing-stale \
  --json
```

Only use `--mark-missing-stale` when the query/folder/wiki-space filter is stable and represents the set you want to compare. It does not mean the whole Feishu workspace was scanned.

Example cursor resume:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --query "" \
  --mine \
  --opened-since 30d \
  --sort edit_time \
  --limit 20 \
  --max-pages 3 \
  --profile feishu-ai-challenge \
  --actor-open-id "$COPILOT_REVIEWER_OPEN_ID" \
  --resume-cursor \
  --json
```

The cursor is keyed by tenant, organization, workspace id, and the discovery filter hash. Changing query, doc types, time windows, folder/wiki space, creator/sharer/chat filters, or sort creates a different cursor.

Example explicit resource smoke when a reviewed Base token is already known:

```bash
MEMORY_DB_PATH="$(mktemp -t fmc-workspace-smoke.XXXXXX.sqlite)" \
python3 scripts/feishu_workspace_ingest.py \
  --skip-discovery \
  --resource bitable:"$BITABLE_APP_TOKEN":"飞书挑战赛任务跟进看板" \
  --max-bitable-records 1 \
  --candidate-limit 2 \
  --actor-open-id "$COPILOT_REVIEWER_OPEN_ID" \
  --json
```

2026-05-04 controlled evidence: using a temporary SQLite database and a reviewed Bitable token, this path produced `resource_count=1`, `source_count=1`, `fetched_count=1`, `candidate_count=1`, `failed_count=0`, and no writes to the default project database. The same day `drive +search` still returned zero resources for the available account context, so the correct claim is "explicit resource candidate smoke works"; it is not "full workspace discovery is complete."

Example direct folder and Wiki discovery:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --dry-run \
  --skip-discovery \
  --folder-walk-root \
  --wiki-space-walk-ids my_library \
  --limit 20 \
  --json
```

2026-05-04 controlled evidence: Drive root dry-run returned 8 supported resources; Wiki `my_library` dry-run returned 8 supported resources; combined dry-run returned 16 docx/sheet/bitable resources. Sheet-only direct discovery now respects `--doc-types`: Drive root returned 0 sheets, Wiki `my_library` returned 1 sheet-backed Bitable tab. Temporary SQLite smoke results: Drive folder/root walk ingested 1 docx resource into 1 `document_feishu` source and 2 candidates; Wiki walk with limit 3 fetched 3 resources, produced 2 document sources and 2 candidates, and surfaced the sheet-backed Bitable tab as `stage=no_sources` instead of treating it as a successful source. Repeating the same folder walk in the same temporary SQLite database, then running `check_feishu_workspace_registry_gate.py --min-runs 2 --require-ingested --require-skipped --require-cursor --json`, returned `ok=true`, `run_count=2`, `totals.ingested=1`, `totals.skipped_unchanged=1`, and `cursor_count=1`. A second temporary SQLite run with the same stable folder discovery filter and `--mark-missing-stale` returned `ok=true`, `run_count=2`, `totals.ingested=2`, `totals.skipped_unchanged=1`, `totals.stale_marked=3`, `cursor_count=1`, and `evidence.has_stale=true`. A failed-fetch negative smoke using an invalid explicit docx token returned latest run `status=completed_with_errors`, `totals.failed=1`, `evidence.has_failed=true`, and `status_counts.error=1`. The mixed-source gate returned `ok=true`, `active_evidence_source_types=["document_feishu","feishu_message"]`, `conflict_evidence_source_types=["lark_bitable"]`, and version status counts `active=1`, `candidate=1`. This proves deterministic folder/wiki discovery, small candidate ingestion, repeat-run skip, same-filter stale marking, failed-fetch registry evidence, and local mixed-source corroboration/conflict behavior work in the current account context; it still does not prove production full-workspace crawling, long-running scheduling, complete enterprise coverage, real normal-sheet ingestion, or real mixed-source live sampling.

2026-05-04 latency evidence: `check_workspace_ingestion_latency_gate.py --json` passed after one warmup run. It reported `case_pass_rate=1.0`, `avg_quote_coverage=1.0`, `document_evidence_coverage=1.0`, `avg_ingestion_latency_ms=5.51`, and `max_ingestion_latency_ms=5.599`. This is a local hot-path regression gate, not a production SLO and not evidence for lark-cli network fetch speed.

## Performance Plan

Keep the current feature stable first, then optimize the hot path:

1. Batch discovery with `drive +search`; keep page size bounded and record `page_token`.
2. Fetch by type and skip unsupported objects early.
3. Avoid full document/table reads on the first pass; read outline or bounded sheet ranges first.
4. Deduplicate by `source_key + source_revision` before candidate extraction when Drive returns a usable revision/update timestamp.
5. Cache lark-cli discovery results in `feishu_workspace_source_registry` before repeated fetches.
6. Move high-volume fetches from lark-cli subprocesses to native OpenAPI only after the pilot shows real bottlenecks.
7. Keep embeddings limited to confirmed curated memory fields.
8. Keep `check_workspace_ingestion_latency_gate.py --json` green before expanding workspace ingestion features; treat cold-start and network latency separately from local hot-path candidate ingestion.

## Acceptance Criteria

- Discovery can list doc/docx/wiki/sheet/bitable resources without writing the DB.
- Operators can scope discovery with `--mine`, creator/sharer/chat IDs, folder/wiki filters, sort, and since/until time windows.
- Folder/wiki direct discovery obeys `--doc-types`.
- Operators can ingest reviewed explicit resources with `--resource type:token[:title] --skip-discovery` when Drive discovery is empty or intentionally bypassed.
- Operators can bypass search and directly list Drive root/folders or Wiki spaces with bounded recursion.
- Document, Sheet, and Bitable resources can become `FeishuIngestionSource` objects.
- Every source fetch has a matching source-context permission key.
- Candidate creation still goes through `ingest_feishu_source()` and `CopilotService`.
- Repeat runs can skip unchanged versioned resources from the registry.
- Long discovery can resume from the last saved Drive `page_token` for the same discovery filter.
- Missing sources are marked stale only when the operator explicitly asks for stale marking and uses the same discovery filter.
- Fetch permission denied / not found writes registry revocation instead of silently retrying forever.
- A read-only registry gate can prove run, source, cursor, skip, stale, and failed evidence from SQLite.
- A mixed-source gate can prove chat, document, and Bitable evidence share one governed ledger and handle corroboration/conflict without silent overwrite.
- A local latency gate can prove warm-path document/workspace candidate ingestion stays within conservative local thresholds while quality checks remain green.
- Default output says candidate-only and pilot, not production full workspace ingestion.
- Tests cover discovery, type routing, sheet ingestion, Bitable routing, candidate-only behavior, registry skip, stale marking, revocation status, and run summary.
