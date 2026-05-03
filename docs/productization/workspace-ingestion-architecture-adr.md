# Workspace Ingestion Architecture ADR

Date: 2026-05-04

Status: Accepted for L2 limited workspace pilot. This is not production full-workspace ingestion yet.

## Decision

Use **lark-cli first** for the current OpenClaw-native pilot, and keep the architecture ready to move hot paths to native Feishu OpenAPI / SDK when the pilot becomes a long-running service.

The reason is practical. `lark-cli` already wraps the Feishu operations this project needs for controlled ingestion: `drive +search` for resource discovery, `docs +fetch --api-version v2` for document content, `sheets +info/+read` for spreadsheet content, and `base +table-list/+record-list/+record-get` for Bitable. It is easy for OpenClaw, scripts, and operators to run, inspect, and replay.

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
  - routes document, sheet, and Bitable resources;
  - builds per-source permission context.
- `scripts/feishu_workspace_ingest.py`
  - dry-run discovery mode;
  - controlled candidate-only ingestion mode requiring an actor id.
- `lark_sheet` source support in schema and ingestion metadata.
- Tests in `tests/test_feishu_workspace_fetcher.py`.

Example dry run:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --query "" \
  --edited-since 30d \
  --limit 20 \
  --profile feishu-ai-challenge \
  --dry-run \
  --json
```

Example controlled ingestion:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --query "" \
  --edited-since 30d \
  --limit 20 \
  --profile feishu-ai-challenge \
  --actor-open-id "$COPILOT_REVIEWER_OPEN_ID" \
  --tenant-id tenant:demo \
  --organization-id org:demo \
  --json
```

## Performance Plan

Keep the current feature stable first, then optimize the hot path:

1. Batch discovery with `drive +search`; keep page size bounded and record `page_token`.
2. Fetch by type and skip unsupported objects early.
3. Avoid full document/table reads on the first pass; read outline or bounded sheet ranges first.
4. Deduplicate by `source_type + source_id + source_revision` before candidate extraction.
5. Cache lark-cli discovery results in a source registry before repeated fetches.
6. Move high-volume fetches from lark-cli subprocesses to native OpenAPI only after the pilot shows real bottlenecks.
7. Keep embeddings limited to confirmed curated memory fields.

## Acceptance Criteria

- Discovery can list doc/docx/wiki/sheet/bitable resources without writing the DB.
- Document, Sheet, and Bitable resources can become `FeishuIngestionSource` objects.
- Every source fetch has a matching source-context permission key.
- Candidate creation still goes through `ingest_feishu_source()` and `CopilotService`.
- Default output says candidate-only and pilot, not production full workspace ingestion.
- Tests cover discovery, type routing, sheet ingestion, Bitable routing, and candidate-only behavior.
