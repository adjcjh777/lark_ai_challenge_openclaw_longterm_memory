# Workspace Ingestion Goal Completion Audit

Date: 2026-05-04

Status: Complete for the controlled workspace-ingestion readiness objective. This is still not a production full-workspace crawler or productized live long-running service.

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
- `scripts/check_feishu_dm_routing.py`
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
- `tests/test_feishu_dm_routing.py`
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
8623342 Route Feishu DM through copilot router
```

## Prompt-To-Artifact Checklist

| User requirement | Current artifact | Evidence | Audit result |
|---|---|---|---|
| Choose lark-cli vs native API | `docs/productization/workspace-ingestion-architecture-adr.md` | ADR chooses lark-cli first for the OpenClaw-native pilot and native OpenAPI/SDK for production hot paths or long-running daemon needs. | Complete for architecture decision. |
| Reference docs when deciding | `docs/productization/workspace-ingestion-architecture-adr.md`, `document-writing-style-guide-opus-4-6.md`, local lark skills, current `lark-cli --help` derived command choices | ADR names `drive +search`, `drive files list`, `wiki nodes list`, `docs +fetch`, `sheets +info/+read`, and `base +record-*`. | Complete enough for pilot; production API research remains a future implementation gate, not a missing pilot decision. |
| Discover and route Feishu documents/cloud docs | `memory_engine/feishu_workspace_fetcher.py`, `scripts/feishu_workspace_ingest.py` | Drive root/folder walk and Wiki `my_library` walk discovered docx resources; temporary SQLite smokes produced `document_feishu` sources and candidates. | Pilot complete; not production full workspace crawler. |
| Discover and route Bitable/Base | `memory_engine/feishu_bitable_fetcher.py`, `memory_engine/feishu_workspace_fetcher.py`, `scripts/feishu_workspace_ingest.py` | Explicit reviewed Bitable resource smoke produced 1 `lark_bitable` source and 1 candidate in a temporary SQLite DB; current lark-cli 1.0.22 output shapes are handled. | Pilot complete for Bitable. |
| Discover and route normal Sheet | `memory_engine/feishu_workspace_fetcher.py`, `document_ingestion.py`, `scripts/check_workspace_project_sheet_evidence_gate.py`, `tests/test_feishu_workspace_fetcher.py`, `tests/test_workspace_project_sheet_evidence_gate.py` | Code supports `lark_sheet`, `sheets +info`, `sheets +read`, source context, metadata, and tests. Parser handles real `drive +search` result shape through `result_meta.doc_types/token/url` and Wiki `icon_info.token`. Earlier broad read-only search proved the current account had no organic project normal Sheet: project keyword match was sheet-backed Bitable-only, and the only normal Sheet candidate was cross-tenant/non-project. After explicit approval, a controlled normal Sheet was created and inspected by `check_workspace_project_sheet_evidence_gate.py`; the gate returned `ok=true`, `eligible_project_normal_sheet_count=1`, `inspection_failure_count=0`. | Complete for controlled project normal Sheet evidence under the pilot boundary. Still not production all-workspace Sheet coverage. |
| Full workspace registry and cursoring | `memory_engine/feishu_workspace_registry.py`, `scripts/check_feishu_workspace_registry_gate.py` | Registry records runs, source keys, status, cursors, revision skip, same-filter stale, and failed fetch evidence. Real temporary DB gates read back skip/cursor, stale, and failed evidence. | Pilot complete; not production scheduler or all-enterprise coverage. |
| What should be remembered | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/review_policy.py`, `memory_engine/document_ingestion.py` | ADR defines durable decisions, workflow rules, project facts, conflicts, risks, and preferences as memory candidates, and excludes chatter, raw tables, inaccessible content, and secrets. Review policy can auto-confirm low-risk content and hold important/sensitive/conflict content as candidates. | Complete for policy. |
| Route should reuse group-chat architecture | `docs/productization/workspace-ingestion-architecture-adr.md`, `scripts/feishu_workspace_ingest.py`, `memory_engine/document_ingestion.py`, `memory_engine/copilot/tools.py` | Workspace fetches become `FeishuIngestionSource`, then `ingest_feishu_source()`, then `memory.create_candidate`, then `CopilotService` and review policy. | Complete for pilot. |
| Shared database across chat/docs/tables | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/db.py`, `memory_engine/document_ingestion.py` | ADR chooses one governed ledger with raw events, memories, evidence, versions, audit events, and graph nodes; source evidence keeps source type/id/quote/tenant/org. | Complete for local/staging ledger. |
| Corroboration and conflict handling | `docs/productization/workspace-ingestion-architecture-adr.md`, `memory_engine/copilot/governance.py`, `scripts/check_workspace_mixed_source_corroboration_gate.py`, `scripts/check_workspace_real_fetch_latency_gate.py`, `scripts/check_workspace_real_chat_resource_gate.py`, `scripts/check_workspace_real_same_conclusion_gate.py`, `scripts/check_workspace_real_same_conclusion_sample_finder.py`, `scripts/check_workspace_ingestion_goal_readiness.py` | The local gate confirms a chat source can create and confirm an active memory; a document source with the same value adds `document_feishu` evidence to the active version; a Bitable source with a different value becomes a conflict candidate and does not overwrite the active memory. Controlled real gates prove project docx/Base resources can enter the same candidate pipeline. After the controlled normal Sheet was created, a real OpenClaw Feishu group message repeated the same durable fact. `check_workspace_real_same_conclusion_sample_finder.py --event-log ~/.openclaw/logs/gateway.log --resource sheet:<redacted>:<title>` returned `ok=true`, `same_fact_match_count=1`, `resource_fetch_failure_count=0`, and strict gate `status=pass`; strict gate evidence source types were `feishu_message` and `lark_sheet`. | Complete for real chat + reviewed Sheet same-conclusion corroboration under the controlled pilot boundary. Still not proof of production long-running ingestion. |
| Bot DM can recall workspace memory | `agent_adapters/openclaw/plugin/index.js`, `scripts/check_feishu_dm_routing.py`, `tests/test_feishu_dm_routing.py`, `docs/productization/handoffs/feishu-dm-routing-handoff.md` | The first 2026-05-04 p2p DM reached OpenClaw but fell through to the generic agent because the plugin before-dispatch gate only routed group events. Commit `8623342` routes p2p text events through the same first-class memory router and teaches the live log checker to parse raw OpenClaw gateway text lines. After restart, bot single chat `/recall Workspace ingestion readiness gate Sheet 样本` produced a `memory.search` route result whose bridge tool was `fmc_memory_search`; the bot card's first active result was the controlled Sheet fact, with `lark_sheet` evidence, `request_id`, `trace_id`, and `permission: allow / scope_access_granted`. The same command was automatically sent again at 2026-05-04 11:47 and read back the same interactive card: first active result was the reviewed normal Sheet fact, route result `ok=true`, bridge tool `fmc_memory_search`, request/trace present, permission `allow / scope_access_granted`, and card delivery `reply_card`. | Complete for controlled bot DM readback of workspace memory. Still not proof of stable long-running DM routing or every Feishu conversation entering the tool chain. |
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
python3 -m unittest tests.test_feishu_dm_routing tests.test_openclaw_tool_registry
python3 scripts/check_feishu_dm_routing.py --json --event-log ~/.openclaw/logs/gateway.log --required-tools fmc_memory_search --min-first-class-results 1
```

## Remaining Productization Boundaries

1. **The controlled readiness objective is complete, but production full-workspace ingestion is not.**
   Final readiness now passes with `goal_complete=true`, `status=pass`, and `failures=[]`. This closes the user's current controlled workspace-ingestion objective. It does not create a production daemon, full enterprise scan guarantee, production rate-limit posture, or operational SLO.

2. **More organic enterprise samples should still be added before external launch.**
   The normal Sheet and same-fact evidence used a controlled Sheet plus a real OpenClaw Feishu group message. This is sufficient for the readiness gate, but productized rollout should add organic project/enterprise Sheets, Docs, Bases, Wiki spaces, and longer-running samples.

3. **Bot DM readback is controlled allow-path evidence, not stable productized live routing.**
   The 2026-05-04 `/recall` test proves a workspace memory can be recalled through OpenClaw p2p DM, `fmc_memory_search`, `CopilotService`, permission audit, and Feishu card delivery. It does not prove long-running production routing, all tool actions, all DM variants, or all real Feishu conversations.

4. **A stricter productized workspace ingestion gate now exists, and it is blocked by design until production evidence exists.**
   `scripts/check_workspace_productized_ingestion_readiness.py` validates a redacted evidence manifest for organic source coverage, scheduler/cursor, rate-limit/backoff, governance, operations, and 24h+ long-run evidence. The committed example manifest returns `goal_complete=false`; that is the expected result until a real non-example evidence manifest exists. `scripts/run_workspace_ingestion_schedule.py` now provides a one-shot schedule runner that defaults to plan-only and requires explicit `--execute` for side effects. A 2026-05-04 dry-run execute with the example schedule returned 34 discovered resources and did not fetch content or write the DB; this is scheduler-entry evidence, not long-run proof. `scripts/sample_workspace_ingestion_schedule.py` can write multiple sanitized reports and sampler status over time, and `scripts/collect_workspace_ingestion_long_run_evidence.py` can normalize those reports into a manifest patch; the current single-report collection correctly blocks with `successful_run_count=1` and `window_hours=0`.

5. **Performance optimization has bounded retrieval reuse, local warm-path evidence, and controlled real lark-cli fetch-path evidence, but not production SLO evidence.**
   `check_workspace_ingestion_latency_gate.py` measures local document/workspace candidate ingestion after warmup. Retrieval fallback now reuses the active-memory index and curated vector scores inside one request, and trace steps expose per-stage timing for structured, keyword, vector, Cognee, and rerank work. `FeishuApiResult.elapsed_ms` and workspace source metadata now expose lark-cli subprocess/fetch timing for documents, Sheets, and Bitable records. `check_workspace_real_fetch_latency_gate.py` measures a controlled real lark-cli fetch path through a temp DB; latest public-template Sheet evidence is green at 12.747s, 3 sources, 2 candidates, 0 failed fetches. This still does not include production storage, production rate-limit posture, OpenClaw live routing, or project/enterprise workspace resources.

6. **The active-doc rewrite request is complete for this slice.**
   New active productization docs follow the style guide. `README.md`, `docs/README.md`, `docs/human-product-guide.md`, `docs/productization/full-copilot-next-execution-doc.md`, and `docs/productization/prd-completion-audit-and-gap-tasks.md` have a first-pass human-readable rewrite. The full repo contains many historical handoffs and archived plans that intentionally remain audit records; they should only be rewritten if promoted back into active execution.

## Next Required Action

The next product step should not be another architecture discussion. It should be one of:

1. **Add more organic enterprise workspace samples** beyond the controlled Sheet: project Sheets, Docs, Bases, and Wiki spaces.
2. **Extend real lark-cli fetch latency evidence to project/enterprise workspace resources** once controlled resources are available.
3. **Run the schedule runner in plan mode** with a real non-example config, then use the sampler only after the plan is reviewed.
4. **Collect productized ingestion evidence** with sanitized sampler reports, merge them into a non-example manifest, then run `python3 scripts/check_workspace_productized_ingestion_readiness.py --manifest <manifest> --require-productized-ready --json`.
5. **Plan productized live ingestion** only after rate limits, scheduling, monitoring, data retention, and rollback are specified.
6. **Keep active docs aligned** when the workspace evidence changes, using `document-writing-style-guide-opus-4-6.md` and keeping archived plans unchanged unless promoted back into active execution.

Use `workspace-ingestion-evidence-request.md` when asking the project owner or a teammate for the missing Sheet and same-fact samples. It is the shortest handoff note for the current blocker.
Use `scripts/prepare_workspace_evidence_request.py --create-dirs --json` when the request should be packaged as a redacted operator packet with command templates.

The Sheet and real chat + workspace same-conclusion evidence gaps are now closed for the controlled readiness objective. Do not translate that into a production full-workspace ingestion claim.
