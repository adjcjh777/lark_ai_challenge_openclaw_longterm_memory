# Workspace Ingestion Goal Completion Audit

Date: 2026-05-04

Status: Not complete. The repo now has a limited workspace pilot with real controlled evidence, but it does not yet satisfy the user's full objective.

## Objective Restated

The user asked for a Feishu workspace ingestion product path that covers:

1. Decide how to connect the full Feishu workspace, especially whether the pilot should use lark-cli or native Feishu API.
2. Ingest enterprise knowledge sources such as Feishu documents, cloud documents, Sheets, and Bitable/Base.
3. Decide what should become memory and what should stay out.
4. Reuse the earlier group-chat memory routing where possible.
5. Combine document/table/workspace memory with group-chat memory in a shared governed memory system, including corroboration and conflict handling.
6. Keep the current product stable while improving response speed.
7. Rewrite active docs in a Claude Opus 4.6-like human engineering voice, explicitly not Opus 4.7.
8. Think as architect and product manager, but keep evidence, permissions, audit, and no-overclaim boundaries intact.

## Evidence Inspected In This Audit

- `AGENTS.md`
- `README.md`
- `docs/productization/agent-execution-contract.md`
- `docs/productization/full-copilot-next-execution-doc.md`
- `docs/productization/prd-completion-audit-and-gap-tasks.md`
- `docs/productization/workspace-ingestion-architecture-adr.md`
- `docs/productization/workspace-ingestion-evidence-request.md`
- `docs/productization/document-writing-style-guide-opus-4-6.md`
- `memory_engine/feishu_workspace_fetcher.py`
- `memory_engine/feishu_workspace_registry.py`
- `memory_engine/document_ingestion.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/feishu_api_client.py`
- `memory_engine/feishu_bitable_fetcher.py`
- `memory_engine/copilot/tools.py`
- `scripts/feishu_workspace_ingest.py`
- `scripts/check_feishu_workspace_registry_gate.py`
- `scripts/check_workspace_mixed_source_corroboration_gate.py`
- `scripts/check_workspace_ingestion_latency_gate.py`
- `scripts/check_workspace_real_fetch_latency_gate.py`
- `scripts/check_workspace_project_sheet_evidence_gate.py`
- `scripts/check_workspace_real_chat_resource_gate.py`
- `scripts/check_workspace_real_same_conclusion_gate.py`
- `scripts/check_workspace_real_same_conclusion_sample_finder.py`
- `scripts/check_workspace_ingestion_goal_readiness.py`
- `scripts/prepare_workspace_evidence_request.py`
- `tests/test_feishu_workspace_fetcher.py`
- `tests/test_feishu_workspace_registry.py`
- `tests/test_feishu_workspace_registry_gate.py`
- `tests/test_workspace_mixed_source_corroboration_gate.py`
- `tests/test_workspace_ingestion_latency_gate.py`
- `tests/test_workspace_real_fetch_latency_gate.py`
- `tests/test_workspace_project_sheet_evidence_gate.py`
- `tests/test_workspace_real_chat_resource_gate.py`
- `tests/test_workspace_real_same_conclusion_gate.py`
- `tests/test_workspace_real_same_conclusion_sample_finder.py`
- `tests/test_workspace_ingestion_goal_readiness.py`
- `tests/test_prepare_workspace_evidence_request.py`

Recent implementation commits inspected:

```text
f38a19d Surface workspace fetch timings
a424486 Track lark CLI call latency
07a83ee Record retrieval stage timings
3b101d1 Speed up layered retrieval fallback
194fb7e Document Feishu workspace stale and failed evidence
83c3fd3 Respect doc type filters in direct workspace discovery
f62dc87 Add Feishu workspace registry evidence gate
c0a2309 Document Feishu workspace repeat discovery evidence
dba049f Add direct Feishu folder and wiki discovery
6736030 Add explicit Feishu workspace resource ingestion
002ee0d Persist Feishu workspace discovery cursors
4e3e054 Add Feishu workspace discovery filters
66bced9 Add corroboration discovery to readiness gate
```

## Prompt-To-Artifact Checklist

| User requirement | Current artifact | Evidence | Audit result |
|---|---|---|---|
| Choose lark-cli vs native API | `docs/productization/workspace-ingestion-architecture-adr.md` | ADR chooses lark-cli first for the OpenClaw-native pilot and native OpenAPI/SDK for production hot paths or long-running daemon needs. | Complete for architecture decision. |
| Reference docs when deciding | `docs/productization/workspace-ingestion-architecture-adr.md`, `document-writing-style-guide-opus-4-6.md`, local lark skills, current `lark-cli --help` derived command choices | ADR names `drive +search`, `drive files list`, `wiki nodes list`, `docs +fetch`, `sheets +info/+read`, and `base +record-*`. | Complete enough for pilot; production API research remains a future implementation gate, not a missing pilot decision. |
| Discover and route Feishu documents/cloud docs | `memory_engine/feishu_workspace_fetcher.py`, `scripts/feishu_workspace_ingest.py` | Drive root/folder walk and Wiki `my_library` walk discovered docx resources; temporary SQLite smokes produced `document_feishu` sources and candidates. | Pilot complete; not production full workspace crawler. |
| Discover and route Bitable/Base | `memory_engine/feishu_bitable_fetcher.py`, `memory_engine/feishu_workspace_fetcher.py`, `scripts/feishu_workspace_ingest.py` | Explicit reviewed Bitable resource smoke produced 1 `lark_bitable` source and 1 candidate in a temporary SQLite DB; current lark-cli 1.0.22 output shapes are handled. | Pilot complete for Bitable. |
| Discover and route normal Sheet | `memory_engine/feishu_workspace_fetcher.py`, `document_ingestion.py`, `scripts/check_workspace_project_sheet_evidence_gate.py`, `tests/test_feishu_workspace_fetcher.py`, `tests/test_workspace_project_sheet_evidence_gate.py` | Code supports `lark_sheet`, `sheets +info`, `sheets +read`, source context, metadata, and tests. Current parser now handles real `drive +search` result shape through `result_meta.doc_types/token/url` and Wiki `icon_info.token`. Current project Sheet gate is read-only and calls only `sheets +info`: 365 天窗口和空查询仍只找到 2 个 Sheet candidates，项目关键词命中项是 sheet-backed Bitable-only，另一个 normal Sheet 是 cross-tenant/non-project，所以 `eligible_project_normal_sheet_count=0`. A docs search then found a public/template normal Sheet; explicit temp-DB ingestion read 3 `lark_sheet` sources, generated 2 candidates, and registry gate read back `ingested_count=3`, `cursor_count=1`. | Complete for normal Sheet adapter technical readback and current-account project Sheet absence evidence. Incomplete for project/enterprise workspace evidence; still needs a real project/enterprise normal Sheet token/folder/wiki space or explicit approval to create a controlled test Sheet. |
| Full workspace registry and cursoring | `memory_engine/feishu_workspace_registry.py`, `scripts/check_feishu_workspace_registry_gate.py` | Registry records runs, source keys, status, cursors, revision skip, same-filter stale, and failed fetch evidence. Real temporary DB gates read back skip/cursor, stale, and failed evidence. | Pilot complete; not production scheduler or all-enterprise coverage. |
| What should be remembered | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/review_policy.py`, `memory_engine/document_ingestion.py` | ADR defines durable decisions, workflow rules, project facts, conflicts, risks, and preferences as memory candidates, and excludes chatter, raw tables, inaccessible content, and secrets. Review policy can auto-confirm low-risk content and hold important/sensitive/conflict content as candidates. | Complete for policy. |
| Route should reuse group-chat architecture | `docs/productization/workspace-ingestion-architecture-adr.md`, `scripts/feishu_workspace_ingest.py`, `memory_engine/document_ingestion.py`, `memory_engine/copilot/tools.py` | Workspace fetches become `FeishuIngestionSource`, then `ingest_feishu_source()`, then `memory.create_candidate`, then `CopilotService` and review policy. | Complete for pilot. |
| Shared database across chat/docs/tables | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/db.py`, `memory_engine/document_ingestion.py` | ADR chooses one governed ledger with raw events, memories, evidence, versions, audit events, and graph nodes; source evidence keeps source type/id/quote/tenant/org. | Complete for local/staging ledger. |
| Corroboration and conflict handling | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/governance.py`, `scripts/check_workspace_mixed_source_corroboration_gate.py`, `scripts/check_workspace_real_fetch_latency_gate.py`, `scripts/check_workspace_real_chat_resource_gate.py`, `scripts/check_workspace_real_same_conclusion_gate.py`, `scripts/check_workspace_real_same_conclusion_sample_finder.py`, `scripts/check_workspace_ingestion_goal_readiness.py` | The local gate confirms a chat source can create and confirm an active memory; a document source with the same value adds `document_feishu` evidence to the active version; a Bitable source with a different value becomes a conflict candidate and does not overwrite the active memory. A controlled real workspace temp-DB run proves a project docx and project Base can enter the same candidate pipeline: 1 `document_feishu` source, 3 `lark_bitable` sources, 10 candidates, 0 failed, 8.356s. The real chat + workspace resource gate then uses a captured non-@ group-message log plus the same reviewed resources and proves `feishu_message=1`, `document_feishu=1`, `lark_bitable=3`, chat candidates 1, workspace candidates 10, 0 failed, 7.779s in one temp DB. The stricter real same-conclusion gate now rejects the current sample after fetching 4 workspace sources because `same_fact_found_in_workspace_source=0`. The sample finder now accepts explicit resources plus read-only `--query` / Drive folder/root / Wiki space discovery; the expanded run scanned 2 real logs, 4 chat messages, 3 chat candidate facts, explicit project docx/Base, Drive root, and Wiki `my_library`, fetched 48 workspace sources (`document_feishu=22`, `lark_bitable=25`, `lark_sheet=1`), and still returned `same_fact_match_count=0`; optional discovery fetch failures are reported separately from explicit reviewed resource failures, so broad scan noise does not mask the same-conclusion blocker. The combined readiness gate now also accepts `--corroboration-query`, `--corroboration-folder-walk-*`, and `--corroboration-wiki-space-walk-ids` to expand the same-conclusion resource pool directly; the latest Drive root + Wiki `my_library` readiness run still returned `goal_complete=false` with explicit fetch failure 0, optional discovery failure 1, workspace sources 17, `eligible_project_normal_sheet_count=0`, and `same_fact_match_count=0`. The overall objective stays blocked until both real normal Sheet evidence and real same-conclusion corroboration pass. | Complete for local/staging corroboration behavior, real chat/docx/Bitable candidate co-ingestion, and readiness-gate discovery plumbing. Still incomplete for real chat + doc/table same-conclusion corroboration. |
| Keep stability while improving response speed | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/retrieval.py`, `memory_engine/feishu_api_client.py`, `memory_engine/feishu_workspace_fetcher.py`, `memory_engine/feishu_bitable_fetcher.py`, `memory_engine/feishu_workspace_registry.py`, `scripts/feishu_workspace_ingest.py`, `scripts/check_workspace_ingestion_latency_gate.py`, `scripts/check_workspace_real_fetch_latency_gate.py` | Bounded discovery, bounded fetch sizes, candidate limits, registry skip, cursor resume, no raw event embedding, same-filter stale marking, and a local warm-path latency gate reduce repeated work and detect regressions. Retrieval now reuses active-memory index and curated vector scores across layer fallback inside one request, and trace steps expose stage-level `elapsed_ms` for structured, keyword, vector, Cognee, and rerank. `FeishuApiResult.elapsed_ms` now covers lark-cli success, parse error, nonzero return, timeout, missing CLI, and unexpected error paths. Workspace source metadata now records document fetch, Sheet info/read, and Bitable record-get elapsed time. Latest warm-path gate: `avg_ingestion_latency_ms=5.51`, `max_ingestion_latency_ms=5.599`, quality checks pass. New real lark-cli fetch latency gate uses a temp SQLite DB and measures the full subprocess/network/fetch/source-render/candidate-route/registry path; current controlled public-template Sheet run passed at 12.747s with 3 sources, 2 candidates, and 0 failed fetches. | Complete for local warm-path baseline, bounded retrieval optimization, and controlled real lark-cli fetch-path evidence. Production SLO and project/enterprise workspace latency evidence remain future work. |
| Opus 4.6-like docs, not 4.7 | `docs/productization/document-writing-style-guide-opus-4-6.md`, `workspace-ingestion-architecture-adr.md`, `README.md`, `docs/README.md`, `docs/human-product-guide.md`, `docs/productization/full-copilot-next-execution-doc.md`, `docs/productization/prd-completion-audit-and-gap-tasks.md` | Style guide exists and the new ADR uses shorter human engineering prose. It explicitly excludes Opus 4.7 voice. First-pass rewrites are complete for `README.md`, `docs/README.md`, `docs/human-product-guide.md`, `full-copilot-next-execution-doc.md`, and `prd-completion-audit-and-gap-tasks.md`. | Complete for active entry-doc first pass. The guide still says historical handoffs and archived plans are not rewritten unless they are promoted back into active execution. |
| Use subagents/skills/MCP as needed | Current run used lark skill guidance and repo-local checks; previous implementation used lark-cli evidence and board sync. | No direct artifact needed, but actions stayed inside project rules. | Sufficient. |

## Verification Commands Already Proven For This Slice

An earlier doc/evidence sync commit `194fb7e` passed:

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

Earlier workspace implementation commits also passed the relevant Python compile and unit suites, including:

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_feishu_workspace_fetcher tests.test_feishu_workspace_registry_gate
python3 -m unittest tests.test_feishu_workspace_registry_gate tests.test_feishu_workspace_registry tests.test_feishu_workspace_fetcher
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_permissions tests.test_copilot_governance
python3 scripts/check_workspace_mixed_source_corroboration_gate.py --json
python3 -m unittest tests.test_workspace_mixed_source_corroboration_gate
python3 scripts/check_workspace_ingestion_latency_gate.py --json
python3 -m unittest tests.test_workspace_ingestion_latency_gate
python3 scripts/check_workspace_real_fetch_latency_gate.py --json --resource 'sheet:<token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu
python3 -m unittest tests.test_workspace_real_fetch_latency_gate
python3 scripts/check_workspace_project_sheet_evidence_gate.py --json --opened-since 90d --limit 20 --max-pages 2
python3 scripts/check_workspace_project_sheet_evidence_gate.py --json --folder-walk-tokens <folder_token> --wiki-space-walk-ids <space_id_or_my_library> --walk-max-depth 2 --limit 50
python3 -m unittest tests.test_workspace_project_sheet_evidence_gate
python3 scripts/prepare_workspace_evidence_request.py --create-dirs --json
python3 -m unittest tests.test_prepare_workspace_evidence_request
python3 scripts/check_workspace_real_fetch_latency_gate.py --json --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3 --candidate-limit 8 --min-source-count 2 --min-candidate-count 2
python3 scripts/check_workspace_real_chat_resource_gate.py --json --event-log <captured_non_at_group_message.ndjson> --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3 --candidate-limit 8 --min-chat-candidates 1 --min-resource-sources 2 --min-resource-candidates 2
python3 -m unittest tests.test_workspace_real_chat_resource_gate
python3 scripts/check_workspace_real_same_conclusion_gate.py --json --event-log <captured_non_at_group_message.ndjson> --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3
python3 -m unittest tests.test_workspace_real_same_conclusion_gate
python3 scripts/check_workspace_real_same_conclusion_sample_finder.py --json --event-log <captured_non_at_group_message.ndjson> --event-log <captured_first_class_routing.ndjson> --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3
python3 -m unittest tests.test_workspace_real_same_conclusion_sample_finder
python3 scripts/check_workspace_ingestion_goal_readiness.py --json --event-log <captured_non_at_group_message.ndjson> --event-log <captured_first_class_routing.ndjson> --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3
python3 -m unittest tests.test_workspace_ingestion_goal_readiness
python3 scripts/check_workspace_ingestion_goal_readiness.py --json --event-log <captured_non_at_group_message.ndjson> --event-log <captured_first_class_routing.ndjson> --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --sheet-folder-walk-root --sheet-wiki-space-walk-ids my_library --corroboration-folder-walk-root --corroboration-wiki-space-walk-ids my_library --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3
```

## Missing Or Weakly Verified Requirements

1. **Project/enterprise normal Sheet evidence is missing.**
   The code path exists and tests pass. A public/template normal Sheet has now proven the adapter can fetch `lark_sheet` sources and create candidates in a temp DB. The read-only project Sheet gate can now inspect explicit Sheet specs, Drive folder/root walks, and Wiki space walks directly with `sheets +info` only. Current evidence still finds no eligible project normal Sheet: the project match is sheet-backed Bitable-only, and the only normal Sheet candidate is cross-tenant and non-project. This is not yet enterprise workspace Sheet evidence.

2. **"Full workspace ingestion" is not achieved.**
   The system has deterministic discovery, registry, cursoring, stale marking, and failed fetch evidence for a limited pilot. It does not yet have a production long-running daemon, full enterprise coverage guarantees, production rate-limit handling, monitoring, or operational SLOs.

3. **Mixed-source corroboration is locally proven; real chat/docx/Bitable co-ingestion is proven; same-conclusion corroboration is still missing.**
   `check_workspace_mixed_source_corroboration_gate.py` proves the ledger behavior in a temp SQLite DB. Controlled real gates now prove a captured real group message, project docx, and project Base can be fetched into the same temp DB and create candidates together. `check_workspace_real_same_conclusion_gate.py` adds the stricter real-source check and currently fails the existing sample because the chat fact is not present in the fetched workspace sources. `check_workspace_real_same_conclusion_sample_finder.py` now supports read-only Drive/Wiki discovery expansion; the expanded run fetched 48 workspace sources across documents, Bitable, and one Sheet, but still found no exact same-fact match. `check_workspace_ingestion_goal_readiness.py` now supports the same corroboration expansion inputs directly, and the latest Drive root + Wiki `my_library` readiness run confirms the blocker is missing matching evidence; optional discovery has one fetch failure, but explicit reviewed resources still fetch cleanly. It still does not prove that real Feishu chat, document, Sheet, and Bitable objects from the same workspace have been sampled around the same conclusion.

4. **Performance optimization now has bounded retrieval reuse, local warm-path evidence, and controlled real lark-cli fetch-path evidence, but not production SLO evidence.**
   `check_workspace_ingestion_latency_gate.py` measures local document/workspace candidate ingestion after warmup. Retrieval fallback now reuses the active-memory index and curated vector scores inside one request, and trace steps expose per-stage timing for structured, keyword, vector, Cognee, and rerank work. `FeishuApiResult.elapsed_ms` and workspace source metadata now expose lark-cli subprocess/fetch timing for documents, Sheets, and Bitable records. `check_workspace_real_fetch_latency_gate.py` measures a controlled real lark-cli fetch path through a temp DB; latest public-template Sheet evidence is green at 12.747s, 3 sources, 2 candidates, 0 failed fetches. This still does not include production storage, production rate-limit posture, OpenClaw live routing, or project/enterprise workspace resources.

5. **The active-doc rewrite request is complete for this slice.**
   New active productization docs follow the style guide. `README.md`, `docs/README.md`, `docs/human-product-guide.md`, `docs/productization/full-copilot-next-execution-doc.md`, and `docs/productization/prd-completion-audit-and-gap-tasks.md` have a first-pass human-readable rewrite. The full repo contains many historical handoffs and archived plans that intentionally remain audit records; they should only be rewritten if promoted back into active execution.

## Next Required Action

The next product step should not be another architecture discussion. It should be one of:

1. **Prove project/enterprise normal Sheet ingestion** with an existing normal Sheet token/folder/wiki space, or with explicit user approval to create a controlled test Sheet.
2. **Run `check_workspace_real_same_conclusion_gate.py` on real chat + sampled document/table resources** once a matching chat statement is available.
3. **Extend real lark-cli fetch latency evidence to project/enterprise workspace resources** once controlled resources are available.
4. **Keep active docs aligned** when the workspace evidence changes, using `document-writing-style-guide-opus-4-6.md` and keeping archived plans unchanged unless promoted back into active execution.

Use `workspace-ingestion-evidence-request.md` when asking the project owner or a teammate for the missing Sheet and same-fact samples. It is the shortest handoff note for the current blocker.
Use `scripts/prepare_workspace_evidence_request.py --create-dirs --json` when the request should be packaged as a redacted operator packet with command templates.

Until at least the Sheet and real chat + doc/table same-conclusion corroboration evidence gaps are closed, do not call the overall objective complete.
