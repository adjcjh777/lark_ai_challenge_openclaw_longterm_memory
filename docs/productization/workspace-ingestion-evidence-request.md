# Workspace Ingestion Evidence Request

Date: 2026-05-04

Status: active request note for closing the two remaining workspace-ingestion blockers.

This note is meant to be sent to the project owner or operator when the repo is otherwise ready but still lacks real workspace samples. It does not create Feishu resources, send messages, or claim production full-workspace ingestion.

## What Is Needed

The current readiness gate already proves the architecture and local/staging behavior. It is still blocked by real sample coverage:

1. A project or enterprise normal Sheet sample.
2. A real Feishu chat message that repeats a durable fact already present in a reviewed document, Sheet, or Base source.

The latest broader read-only gate used Drive root plus Wiki `my_library` and still returned:

```text
goal_complete=false
eligible_project_normal_sheet_count=0
same_fact_match_count=0
explicit_resource_fetch_failure_count=0
optional_resource_fetch_failure_count=1
workspace_source_count=17
```

That means the current blocker is missing evidence, not a missing architecture decision or a broken explicit fetch path.

## Please Provide One Normal Sheet Sample

Any one of these is enough:

- an existing project or enterprise normal Sheet token;
- a Drive folder token that contains a project or enterprise normal Sheet;
- a Wiki space id that contains a project or enterprise normal Sheet;
- explicit approval to create a controlled test Sheet.

The sample must be a normal Sheet. A sheet-backed Bitable tab is not enough.

Do not paste private cell contents into GitHub, docs, or chat. The gates only need the token/folder/wiki input and will redact evidence in output.

## Please Provide One Same-Fact Sample

We need one durable fact that appears in both places:

- a real Feishu chat message captured by the existing event-log path;
- one reviewed document, Sheet, or Base source fetched by lark-cli.

Good sample facts:

- "The review owner for workspace memory is <role or person>."
- "The pilot uses lark-cli first; native OpenAPI is reserved for production hot paths."
- "Normal Sheet evidence must pass before workspace ingestion can be called complete."
- "Important or conflicting workspace facts stay candidate until reviewer confirmation."

Avoid:

- secrets, tokens, passwords, private customer data;
- casual chat;
- one-off status noise;
- facts that appear only in chat and not in a reviewed workspace source.

## Commands To Run After Samples Arrive

If the Sheet sample is explicit:

```bash
python3 scripts/check_workspace_project_sheet_evidence_gate.py \
  --json \
  --resource 'sheet:<sheet_token>:<reviewed_title>'
```

If the Sheet sample is in a folder or Wiki:

```bash
python3 scripts/check_workspace_project_sheet_evidence_gate.py \
  --json \
  --folder-walk-tokens '<folder_token>' \
  --wiki-space-walk-ids '<space_id_or_my_library>' \
  --walk-max-depth 2 \
  --limit 50
```

If the same-fact sample is available:

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

Only after both evidence streams pass, rerun the final readiness gate:

```bash
python3 scripts/check_workspace_ingestion_goal_readiness.py \
  --json \
  --event-log '<real_event_log.ndjson>' \
  --resource '<reviewed_doc_or_bitable_or_sheet>' \
  --resource 'sheet:<sheet_token>:<reviewed_title>' \
  --actor-open-id '<reviewer_open_id>' \
  --roles reviewer \
  --scope workspace:feishu \
  --max-bitable-records 3 \
  --max-sheet-rows 20
```

The objective can be called complete only when this gate returns:

```text
goal_complete=true
status=pass
failures=[]
```

Until then, keep the status as limited workspace pilot.
