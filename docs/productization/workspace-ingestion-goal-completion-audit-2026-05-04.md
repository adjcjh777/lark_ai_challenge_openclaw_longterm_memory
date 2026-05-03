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
- `docs/productization/document-writing-style-guide-opus-4-6.md`
- `memory_engine/feishu_workspace_fetcher.py`
- `memory_engine/feishu_workspace_registry.py`
- `memory_engine/document_ingestion.py`
- `memory_engine/copilot/tools.py`
- `scripts/feishu_workspace_ingest.py`
- `scripts/check_feishu_workspace_registry_gate.py`
- `scripts/check_workspace_mixed_source_corroboration_gate.py`
- `scripts/check_workspace_ingestion_latency_gate.py`
- `scripts/check_workspace_real_fetch_latency_gate.py`
- `scripts/check_workspace_project_sheet_evidence_gate.py`
- `scripts/check_workspace_real_chat_resource_gate.py`
- `tests/test_feishu_workspace_fetcher.py`
- `tests/test_feishu_workspace_registry.py`
- `tests/test_feishu_workspace_registry_gate.py`
- `tests/test_workspace_mixed_source_corroboration_gate.py`
- `tests/test_workspace_ingestion_latency_gate.py`
- `tests/test_workspace_real_fetch_latency_gate.py`
- `tests/test_workspace_project_sheet_evidence_gate.py`
- `tests/test_workspace_real_chat_resource_gate.py`

Recent implementation commits inspected:

```text
194fb7e Document Feishu workspace stale and failed evidence
83c3fd3 Respect doc type filters in direct workspace discovery
f62dc87 Add Feishu workspace registry evidence gate
c0a2309 Document Feishu workspace repeat discovery evidence
dba049f Add direct Feishu folder and wiki discovery
6736030 Add explicit Feishu workspace resource ingestion
002ee0d Persist Feishu workspace discovery cursors
4e3e054 Add Feishu workspace discovery filters
```

## Prompt-To-Artifact Checklist

| User requirement | Current artifact | Evidence | Audit result |
|---|---|---|---|
| Choose lark-cli vs native API | `docs/productization/workspace-ingestion-architecture-adr.md` | ADR chooses lark-cli first for the OpenClaw-native pilot and native OpenAPI/SDK for production hot paths or long-running daemon needs. | Complete for architecture decision. |
| Reference docs when deciding | `docs/productization/workspace-ingestion-architecture-adr.md`, `document-writing-style-guide-opus-4-6.md`, local lark skills, current `lark-cli --help` derived command choices | ADR names `drive +search`, `drive files list`, `wiki nodes list`, `docs +fetch`, `sheets +info/+read`, and `base +record-*`. | Complete enough for pilot; production API research remains a future implementation gate, not a missing pilot decision. |
| Discover and route Feishu documents/cloud docs | `memory_engine/feishu_workspace_fetcher.py`, `scripts/feishu_workspace_ingest.py` | Drive root/folder walk and Wiki `my_library` walk discovered docx resources; temporary SQLite smokes produced `document_feishu` sources and candidates. | Pilot complete; not production full workspace crawler. |
| Discover and route Bitable/Base | `memory_engine/feishu_bitable_fetcher.py`, `memory_engine/feishu_workspace_fetcher.py`, `scripts/feishu_workspace_ingest.py` | Explicit reviewed Bitable resource smoke produced 1 `lark_bitable` source and 1 candidate in a temporary SQLite DB; current lark-cli 1.0.22 output shapes are handled. | Pilot complete for Bitable. |
| Discover and route normal Sheet | `memory_engine/feishu_workspace_fetcher.py`, `document_ingestion.py`, `scripts/check_workspace_project_sheet_evidence_gate.py`, `tests/test_feishu_workspace_fetcher.py`, `tests/test_workspace_project_sheet_evidence_gate.py` | Code supports `lark_sheet`, `sheets +info`, `sheets +read`, source context, metadata, and tests. Current parser now handles real `drive +search` result shape through `result_meta.doc_types/token/url` and Wiki `icon_info.token`. Current project Sheet gate is read-only and calls only `sheets +info`: it found 2 Sheet candidates, where the project keyword match is sheet-backed Bitable-only and the other normal Sheet is cross-tenant/non-project, so `eligible_project_normal_sheet_count=0`. A docs search then found a public/template normal Sheet; explicit temp-DB ingestion read 3 `lark_sheet` sources, generated 2 candidates, and registry gate read back `ingested_count=3`, `cursor_count=1`. | Complete for normal Sheet adapter technical readback and current-account project Sheet absence evidence. Incomplete for project/enterprise workspace evidence; still needs a real project/enterprise normal Sheet token/folder/wiki space or explicit approval to create a controlled test Sheet. |
| Full workspace registry and cursoring | `memory_engine/feishu_workspace_registry.py`, `scripts/check_feishu_workspace_registry_gate.py` | Registry records runs, source keys, status, cursors, revision skip, same-filter stale, and failed fetch evidence. Real temporary DB gates read back skip/cursor, stale, and failed evidence. | Pilot complete; not production scheduler or all-enterprise coverage. |
| What should be remembered | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/review_policy.py`, `memory_engine/document_ingestion.py` | ADR defines durable decisions, workflow rules, project facts, conflicts, risks, and preferences as memory candidates, and excludes chatter, raw tables, inaccessible content, and secrets. Review policy can auto-confirm low-risk content and hold important/sensitive/conflict content as candidates. | Complete for policy. |
| Route should reuse group-chat architecture | `docs/productization/workspace-ingestion-architecture-adr.md`, `scripts/feishu_workspace_ingest.py`, `memory_engine/document_ingestion.py`, `memory_engine/copilot/tools.py` | Workspace fetches become `FeishuIngestionSource`, then `ingest_feishu_source()`, then `memory.create_candidate`, then `CopilotService` and review policy. | Complete for pilot. |
| Shared database across chat/docs/tables | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/db.py`, `memory_engine/document_ingestion.py` | ADR chooses one governed ledger with raw events, memories, evidence, versions, audit events, and graph nodes; source evidence keeps source type/id/quote/tenant/org. | Complete for local/staging ledger. |
| Corroboration and conflict handling | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/governance.py`, `scripts/check_workspace_mixed_source_corroboration_gate.py`, `scripts/check_workspace_real_fetch_latency_gate.py`, `scripts/check_workspace_real_chat_resource_gate.py` | The local gate confirms a chat source can create and confirm an active memory; a document source with the same value adds `document_feishu` evidence to the active version; a Bitable source with a different value becomes a conflict candidate and does not overwrite the active memory. A controlled real workspace temp-DB run proves a project docx and project Base can enter the same candidate pipeline: 1 `document_feishu` source, 3 `lark_bitable` sources, 10 candidates, 0 failed, 8.356s. The real chat + workspace resource gate then uses a captured non-@ group-message log plus the same reviewed resources and proves `feishu_message=1`, `document_feishu=1`, `lark_bitable=3`, chat candidates 1, workspace candidates 10, 0 failed, 7.779s in one temp DB. | Complete for local/staging corroboration behavior and real chat/docx/Bitable candidate co-ingestion. Still incomplete for real chat + doc/table same-conclusion corroboration. |
| Keep stability while improving response speed | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/feishu_workspace_registry.py`, `scripts/feishu_workspace_ingest.py`, `scripts/check_workspace_ingestion_latency_gate.py`, `scripts/check_workspace_real_fetch_latency_gate.py` | Bounded discovery, bounded fetch sizes, candidate limits, registry skip, cursor resume, no raw event embedding, same-filter stale marking, and a local warm-path latency gate reduce repeated work and detect regressions. Latest warm-path gate: `avg_ingestion_latency_ms=5.51`, `max_ingestion_latency_ms=5.599`, quality checks pass. New real lark-cli fetch latency gate uses a temp SQLite DB and measures the full subprocess/network/fetch/source-render/candidate-route/registry path; current controlled public-template Sheet run passed at 12.747s with 3 sources, 2 candidates, and 0 failed fetches. | Complete for local warm-path baseline and controlled real lark-cli fetch-path evidence. Production SLO and project/enterprise workspace latency evidence remain future work. |
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
python3 -m unittest tests.test_workspace_project_sheet_evidence_gate
python3 scripts/check_workspace_real_fetch_latency_gate.py --json --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3 --candidate-limit 8 --min-source-count 2 --min-candidate-count 2
python3 scripts/check_workspace_real_chat_resource_gate.py --json --event-log <captured_non_at_group_message.ndjson> --resource 'docx:<project_docx_token>:<title>' --resource 'bitable:<project_base_token>:<title>' --actor-open-id <reviewer_open_id> --roles reviewer --scope workspace:feishu --max-bitable-records 3 --candidate-limit 8 --min-chat-candidates 1 --min-resource-sources 2 --min-resource-candidates 2
python3 -m unittest tests.test_workspace_real_chat_resource_gate
```

## Missing Or Weakly Verified Requirements

1. **Project/enterprise normal Sheet evidence is missing.**
   The code path exists and tests pass. A public/template normal Sheet has now proven the adapter can fetch `lark_sheet` sources and create candidates in a temp DB. The new read-only project Sheet gate proves the current account can parse real `drive +search` results, but still finds no eligible project normal Sheet: the project match is sheet-backed Bitable-only, and the only normal Sheet candidate is cross-tenant and non-project. This is not yet enterprise workspace Sheet evidence.

2. **"Full workspace ingestion" is not achieved.**
   The system has deterministic discovery, registry, cursoring, stale marking, and failed fetch evidence for a limited pilot. It does not yet have a production long-running daemon, full enterprise coverage guarantees, production rate-limit handling, monitoring, or operational SLOs.

3. **Mixed-source corroboration is locally proven; real chat/docx/Bitable co-ingestion is proven; same-conclusion corroboration is still missing.**
   `check_workspace_mixed_source_corroboration_gate.py` proves the ledger behavior in a temp SQLite DB. Controlled real gates now prove a captured real group message, project docx, and project Base can be fetched into the same temp DB and create candidates together. It still does not prove that real Feishu chat, document, Sheet, and Bitable objects from the same workspace have been sampled around the same conclusion.

4. **Performance optimization now has local warm-path and controlled real lark-cli fetch-path evidence, but not production SLO evidence.**
   `check_workspace_ingestion_latency_gate.py` measures local document/workspace candidate ingestion after warmup. `check_workspace_real_fetch_latency_gate.py` measures a controlled real lark-cli fetch path through a temp DB; latest public-template Sheet evidence is green at 12.747s, 3 sources, 2 candidates, 0 failed fetches. This still does not include production storage, production rate-limit posture, OpenClaw live routing, or project/enterprise workspace resources.

5. **The active-doc rewrite request is complete for this slice.**
   New active productization docs follow the style guide. `README.md`, `docs/README.md`, `docs/human-product-guide.md`, `docs/productization/full-copilot-next-execution-doc.md`, and `docs/productization/prd-completion-audit-and-gap-tasks.md` have a first-pass human-readable rewrite. The full repo contains many historical handoffs and archived plans that intentionally remain audit records; they should only be rewritten if promoted back into active execution.

## Next Required Action

The next product step should not be another architecture discussion. It should be one of:

1. **Prove project/enterprise normal Sheet ingestion** with an existing normal Sheet token/folder/wiki space, or with explicit user approval to create a controlled test Sheet.
2. **Run same-conclusion corroboration on real chat + sampled document/table resources** once a matching chat statement is available.
3. **Extend real lark-cli fetch latency evidence to project/enterprise workspace resources** once controlled resources are available.
4. **Keep active docs aligned** when the workspace evidence changes, using `document-writing-style-guide-opus-4-6.md` and keeping archived plans unchanged unless promoted back into active execution.

Until at least the Sheet and real chat + doc/table same-conclusion corroboration evidence gaps are closed, do not call the overall objective complete.
