# Workspace Ingestion Evidence Collection Runbook

Date: 2026-05-04

Status: active runbook for closing the two remaining workspace-ingestion evidence gaps.

This runbook is deliberately narrow. It does not create Feishu resources, send messages, or claim production full-workspace ingestion. It tells the next operator exactly what evidence is still missing, how to collect it, and which gates must pass before the overall workspace objective can be called complete.

## Current Blocking Evidence

The combined readiness gate still returns `goal_complete=false`.

Two blockers remain:

1. A project or enterprise normal Sheet sample.
2. A real chat message and a real document, Sheet, or Base source that repeat the same durable fact.

Already proven:

- lark-cli-first architecture decision.
- memory judgment policy.
- reuse of `FeishuIngestionSource -> ingest_feishu_source() -> memory.create_candidate -> CopilotService`.
- shared governed ledger for chat, documents, Sheets, and Base/Bitable evidence.
- local mixed-source corroboration and conflict behavior.
- real docx + Base candidate co-ingestion.
- real chat log + docx/Base candidate co-ingestion.
- public/template normal Sheet technical fetch path.
- broad same-conclusion sample search over current evidence pool.

Not yet proven:

- project or enterprise workspace normal Sheet ingestion evidence.
- real chat + doc/table same-conclusion corroboration.
- production full-workspace crawling or productized live long-run operation.

## Rules Before Collecting Evidence

Use only controlled resources.

Do not commit raw Feishu tokens, chat ids, message ids, user ids, record ids, screenshots with private content, or exported chat text. The existing gates redact tokens and facts in their JSON output; use those outputs for docs and board updates.

Do not create a new Sheet unless the user explicitly approves it. If approval is missing, keep the blocker open.

Do not start multiple Feishu listeners. For live chat evidence, follow the current single-listener path already documented in the Feishu live run preflight docs.

## Evidence A: Project Normal Sheet

### Acceptable Sample

Use one of these:

- an existing project or enterprise normal Sheet token;
- a Drive folder containing a project or enterprise normal Sheet;
- a Wiki space containing a project or enterprise normal Sheet;
- a controlled test Sheet, but only after explicit user approval.

The sample must be a normal Sheet. A sheet-backed Bitable tab is not enough.

### First Read-Only Check

If the operator has a Sheet token:

```bash
python3 scripts/check_workspace_project_sheet_evidence_gate.py \
  --json \
  --resource 'sheet:<sheet_token>:<reviewed_title>'
```

If the operator has only a folder or Wiki space, use the workspace discovery path first and then pass the discovered normal Sheet token explicitly:

```bash
python3 scripts/feishu_workspace_ingest.py \
  --json \
  --dry-run \
  --skip-discovery \
  --folder-walk-tokens '<folder_token>' \
  --doc-types sheet \
  --limit 50
```

```bash
python3 scripts/feishu_workspace_ingest.py \
  --json \
  --dry-run \
  --skip-discovery \
  --wiki-space-walk-ids '<space_id_or_my_library>' \
  --doc-types sheet \
  --limit 50
```

Pass criteria:

- `ok=true`
- `eligible_project_normal_sheet_count >= 1`
- `inspection_failure_count=0`

### Candidate Pipeline Check

After the read-only Sheet evidence passes, prove the normal Sheet can enter the same candidate pipeline:

```bash
python3 scripts/check_workspace_real_fetch_latency_gate.py \
  --json \
  --resource 'sheet:<sheet_token>:<reviewed_title>' \
  --actor-open-id '<reviewer_open_id>' \
  --roles reviewer \
  --scope workspace:feishu \
  --max-sheet-rows 20
```

Pass criteria:

- `ok=true`
- at least one `lark_sheet` source
- candidate routing completes
- no fetch failures

This is still pilot evidence, not a production SLO.

## Evidence B: Real Same-Conclusion Corroboration

### Acceptable Sample

The sample must contain the same durable fact in both places:

- one real Feishu/OpenClaw chat log message;
- one reviewed Feishu document, Sheet, or Base source fetched through lark-cli.

Good facts look like:

- a deployment rule;
- an owner or reviewer rule;
- a project decision;
- a deadline or workflow policy;
- a durable configuration value.

Bad facts:

- casual chat;
- one-off status noise;
- vague summaries;
- facts not repeated in a workspace source;
- sensitive or secret values.

### Find A Match In Existing Evidence

Use this first. It is redacted and only writes to a temporary SQLite DB.

```bash
python3 scripts/check_workspace_real_same_conclusion_sample_finder.py \
  --json \
  --event-log '<real_event_log.ndjson>' \
  --resource 'docx:<doc_token>:<reviewed_title>' \
  --resource 'bitable:<base_token>:<reviewed_title>' \
  --resource 'sheet:<sheet_token>:<reviewed_title>' \
  --actor-open-id '<reviewer_open_id>' \
  --roles reviewer \
  --scope workspace:feishu \
  --max-bitable-records 3 \
  --max-sheet-rows 20
```

For a broader read-only scan, optional discovery inputs can be added:

```bash
  --query '' \
  --folder-walk-root \
  --wiki-space-walk-ids my_library
```

Interpretation:

- `explicit_resource_fetch_succeeded=pass` means all explicitly reviewed resources were fetched.
- `optional_resource_fetch_failure_count` may be nonzero during broad discovery; it should be investigated, but it does not by itself prove or disprove same-conclusion evidence.
- `same_fact_match_count >= 1` is required before the strict gate can pass.

### Strict Gate

Once a matching sample exists, run:

```bash
python3 scripts/check_workspace_real_same_conclusion_gate.py \
  --json \
  --event-log '<real_event_log.ndjson>' \
  --resource '<matching_resource_spec>' \
  --actor-open-id '<reviewer_open_id>' \
  --roles reviewer \
  --scope workspace:feishu
```

Pass criteria:

- the same durable fact exists in chat and workspace source text;
- chat evidence creates or confirms an active memory;
- workspace evidence is added as duplicate/corroborating evidence on the active version;
- conflict behavior does not overwrite active memory.

## Final Readiness Gate

After both evidence streams pass, run:

```bash
python3 scripts/check_workspace_ingestion_goal_readiness.py \
  --json \
  --event-log '<real_event_log.ndjson>' \
  --resource '<reviewed_doc_or_sheet_or_bitable>' \
  --resource 'sheet:<sheet_token>:<reviewed_title>' \
  --actor-open-id '<reviewer_open_id>' \
  --roles reviewer \
  --scope workspace:feishu \
  --max-bitable-records 3 \
  --max-sheet-rows 20
```

If a `sheet:<token>` spec is passed through `--resource`, the readiness gate also reuses it for the project normal Sheet evidence check. Use `--sheet-resource` only when the Sheet evidence pool should differ from the same-conclusion resource pool.

If the Sheet evidence is known only through a folder or Wiki space, pass the walk input directly to the readiness gate:

```bash
  --sheet-folder-walk-tokens '<folder_token>' \
  --sheet-wiki-space-walk-ids '<space_id_or_my_library>' \
  --sheet-walk-max-depth 2
```

Use `--sheet-folder-walk-root` only for a controlled read-only root scan.

If the same-conclusion resource pool also needs read-only expansion, pass the corroboration inputs directly to the same readiness gate:

```bash
  --corroboration-query '' \
  --corroboration-folder-walk-tokens '<folder_token>' \
  --corroboration-wiki-space-walk-ids '<space_id_or_my_library>' \
  --corroboration-walk-max-depth 2
```

These inputs only expand the reviewed workspace sources used to search for a chat/doc/table same-fact match. Explicit `--resource` fetch failures remain hard failures; optional discovery fetch failures are counted separately as `optional_resource_fetch_failure_count`.

The objective is not complete unless this returns:

- `goal_complete=true`
- `status=pass`
- no failures

If the gate still fails, update the productization docs and Feishu board with the exact blocker. Do not call the objective complete.

## Documentation And Board Sync

When new evidence changes the project state, update:

- `README.md`
- `docs/productization/full-copilot-next-execution-doc.md`
- `docs/productization/prd-completion-audit-and-gap-tasks.md`
- `docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md`

Then run the required checks, commit, push, and sync the Feishu task board.

Minimum checks for doc-only evidence updates:

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

If scripts or Python changed, also run:

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_workspace_real_same_conclusion_sample_finder tests.test_workspace_ingestion_goal_readiness
```
