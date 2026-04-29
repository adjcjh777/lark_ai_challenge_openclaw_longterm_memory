---
tracker:
  kind: linear
  api_key: $LINEAR_API_KEY
  project_slug: $SYMPHONY_LINEAR_PROJECT_SLUG
  active_states:
    - Todo
    - In Progress
    - Rework
    - Merging
  terminal_states:
    - Done
    - Closed
    - Cancelled
    - Canceled
    - Duplicate
polling:
  interval_ms: 10000
workspace:
  root: $SYMPHONY_WORKSPACE_ROOT
hooks:
  after_create: |
    git clone --depth 1 "$SOURCE_REPO_URL" .
    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"
    python3 scripts/check_openclaw_version.py
    python3 scripts/check_agent_harness.py
agent:
  max_concurrent_agents: 2
  max_turns: 12
codex:
  command: "${CODEX_BIN:-codex} --config shell_environment_policy.inherit=all --config 'model=\"gpt-5.5\"' app-server"
  approval_policy: never
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    type: workspaceWrite
---

You are working on a Linear issue for `adjcjh777/lark_ai_challenge_openclaw_longterm_memory`.

Issue:
- Identifier: `{{ issue.identifier }}`
- Title: `{{ issue.title }}`
- State: `{{ issue.state }}`
- Labels: `{{ issue.labels }}`
- URL: `{{ issue.url }}`

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

## Mission

Work autonomously inside this Symphony-created workspace. Do not touch paths outside the workspace.

This repository is the OpenClaw-native Feishu Memory Copilot. Keep the main architecture:

```text
OpenClaw Agent
  -> fmc_* / memory.* tools
  -> handle_tool_request()
  -> CopilotService
  -> permissions / governance / retrieval / audit
  -> SQLite / Cognee adapter / Feishu / Bitable
```

Do not move the project back to CLI-first or legacy Bot-first implementation. Legacy CLI/Bot paths are fallback/reference unless the issue explicitly targets them.

## Required Reading

Before changing files, read:

```text
AGENTS.md
README.md
docs/harness/README.md
docs/productization/agent-execution-contract.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/complete-product-roadmap-prd.md
docs/productization/complete-product-roadmap-test-spec.md
```

For productization, judge-facing docs, handoff, live Feishu/OpenClaw evidence, or deployment boundaries, also read:

```text
docs/README.md
docs/human-product-guide.md
docs/productization/workflow-and-test-process.md
docs/productization/launch-polish-todo.md
docs/productization/contracts/
```

Only read historical dated plans when the issue explicitly names that date.

## Linear Workflow

Use Linear MCP or Symphony's injected `linear_graphql` app-server tool if available.

1. If the issue is `Todo`, move it to `In Progress` before implementation.
2. Maintain one persistent Linear comment headed `## Codex Workpad`.
3. Keep the workpad current with plan, acceptance criteria, validation, commit hash, and blockers.
4. If blocked by missing secrets, missing Linear access, missing GitHub auth, or missing required external services, record the blocker in the workpad and move the issue to `Human Review`.
5. When implementation and validation are complete, push a branch, open or update a PR, add the `symphony` label, link the PR on the issue, and move the issue to `Human Review`.
6. If the issue is `Merging`, do not merge directly unless the repo's current instructions explicitly allow it. Follow the repo's merge/land policy.
7. If the issue reaches `Done`, `Closed`, `Cancelled`, `Canceled`, or `Duplicate`, stop work.

## Project Rules

- New Copilot capabilities belong in `memory_engine/copilot/`, `agent_adapters/openclaw/`, `docs/productization/`, `tests/test_copilot_*.py`, and `benchmarks/copilot_*.json`.
- Any new entrypoint must route through `handle_tool_request()` / `CopilotService`.
- `memory.*` tools must include `current_context.permission` and fail closed on missing, malformed, scope, tenant, or organization mismatch.
- Real Feishu sources stay candidate-only until reviewer confirmation.
- Do not vectorize all raw events; only curated memory fields should be embedded.
- Cognee must stay behind `memory_engine/copilot/cognee_adapter.py`.
- Do not claim production deployment, full Feishu workspace ingestion, multi-tenant enterprise backend, long-running embedding service, stable real Feishu DM routing into project first-class tools, or productized live.

## Validation

Always run before handoff:

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

If Python, scripts, schema, or benchmark runner files changed, also run:

```bash
python3 -m compileall memory_engine scripts
```

If Copilot schema / tools / service changed, also run:

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
```

If permissions, governance, or candidate memory changed, also run:

```bash
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance
```

If Symphony setup files changed, also run:

```bash
python3 scripts/check_symphony_setup.py
python3 -m unittest tests.test_symphony_setup
```

If Cognee, embedding, or Ollama checks run, finish with `ollama ps` and stop only this project's model if it remains running.

## Final Handoff

The final message should include:

- files changed,
- commit and PR link if available,
- validation commands and outcomes,
- exact blockers if any,
- whether Ollama/project models were started and cleaned up.

Do not include extra claims outside the repo's no-overclaim boundary.
