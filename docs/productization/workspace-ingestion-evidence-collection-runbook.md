# Workspace Ingestion Evidence Collection Runbook

Date: 2026-05-04

Status: active runbook for moving from controlled workspace readiness to productized workspace-ingestion evidence.

This runbook is deliberately narrow. It does not create Feishu resources, send messages, or claim production full-workspace ingestion. It tells the next operator exactly what evidence is still missing, how to collect it, and which gates must pass before the overall workspace objective can be called complete.

If the next step is asking the project owner or a teammate for the missing samples, use `workspace-ingestion-evidence-request.md`. This runbook is the operator procedure after those samples exist.

To generate a redacted packet with the exact request, checklist, and command templates, run:

```bash
python3 scripts/prepare_workspace_evidence_request.py \
  --create-dirs \
  --json
```

The packet writes under `logs/workspace-evidence-requests/<run_id>/` when `--create-dirs` is used. It does not call Feishu, create resources, read Sheet cells, or write the memory DB.

## Current Blocking Evidence

The controlled workspace readiness gate has passed. The stricter productized workspace gate still returns `goal_complete=false`.

The current productized blockers are:

1. Organic source coverage for `lark_doc`, `lark_sheet`, and `wiki`.
2. Same-conclusion evidence across chat and workspace sources beyond the controlled sample.
3. Conflict-negative evidence in the productized evidence packet.
4. Real multi-run scheduler/cursor evidence is now proven in a partial manifest; keep rerunning it in the 24h+ window.
5. Rate-limit/backoff, governance, and operations evidence refs.
6. A 24h+ long-run window with at least 3 successful schedule executions and no unresolved failed runs.

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
- controlled normal Sheet + real OpenClaw Feishu group message same-conclusion readiness.
- bot DM readback of the controlled workspace Sheet memory through `fmc_memory_search`.
- non-dry-run bounded schedule sampling in an isolated SQLite DB: 4 successful runs, real candidate pipeline entry, `document_feishu=8`, `lark_bitable=43`.
- discovery/cursoring partial evidence: cursor resume, revision skip, stale marking, revocation/failed-fetch signal, bounded pages/resources, and non-secret evidence refs all pass. The registry now reads Drive/Wiki `result_meta.icon_info.version`, so repeated resources can skip unchanged fetches.

Not yet proven:

- complete organic coverage for Docs, Sheets, Base/Bitable, Wiki, same-conclusion, and conflict-negative evidence.
- production full-workspace crawling or productized live long-run operation.
- productized evidence manifest that passes `check_workspace_productized_ingestion_readiness.py --require-productized-ready`.

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

If the operator has only a folder or Wiki space, pass it directly to the read-only Sheet evidence gate:

```bash
python3 scripts/check_workspace_project_sheet_evidence_gate.py \
  --json \
  --folder-walk-tokens '<folder_token>' \
  --walk-max-depth 2 \
  --limit 50
```

```bash
python3 scripts/check_workspace_project_sheet_evidence_gate.py \
  --json \
  --wiki-space-walk-ids '<space_id_or_my_library>' \
  --walk-max-depth 2 \
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
