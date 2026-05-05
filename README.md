# Feishu Memory Copilot

OpenClaw-native enterprise memory copilot for Feishu / Lark workflows.

This project turns long-lived collaboration facts from Feishu messages, docs,
Sheets, Base/Bitable, and workspace resources into governed enterprise memory:
evidence-backed, permission-aware, reviewable, versioned, and auditable.

It is built for the Feishu AI Challenge OpenClaw track.

## Status

Current stage: **MVP / demo / pre-production**.

What is ready:

- OpenClaw-facing `fmc_*` memory tools.
- A unified `handle_tool_request()` -> `CopilotService` service boundary.
- Candidate memory review, confirmation, rejection, conflict merge, version
  history, retrieval, prefetch, and audit.
- Controlled Feishu sandbox flows, including review cards and permission
  negative cases.
- Limited workspace ingestion pilot and productized readiness evidence.
- Demo replay, readiness checks, benchmark reports, and judge-facing materials.

What is not claimed:

- Production deployment.
- Full enterprise-wide Feishu workspace rollout.
- Production multi-tenant admin backend.
- Production-grade long-running embedding service.
- Stable long-running routing for every real Feishu DM/group/workspace event.

## Why This Exists

Teams do not only need to search chat history. They need to know:

- Which decision is currently valid?
- What evidence supports it?
- Who is allowed to see or confirm it?
- Which older decision was superseded?
- What context should an Agent carry before doing work?

Feishu Memory Copilot treats memory as a governed object instead of a raw RAG
snippet.

## Core Ideas

| Concept | Meaning |
|---|---|
| `candidate` | A possible memory extracted from collaboration context, not yet trusted. |
| `active` | The current trusted memory used by search and task prefetch. |
| `superseded` | An older version kept for explanation, but filtered from default answers. |
| `evidence` | Source quote, source type, source id, tenant/org/scope metadata. |
| `permission` | Fail-closed access check carried in `current_context.permission`. |
| `audit` | Request id, trace id, actor, decision, and review/action metadata. |

## Architecture

```text
Feishu / Workspace sources
  -> candidate extraction
  -> review policy
  -> CopilotService
  -> permissions / governance / retrieval / audit
  -> SQLite ledger / optional Cognee adapter
  -> OpenClaw fmc_* tools
  -> Agent search / versions / prefetch
```

Key paths:

- `agent_adapters/openclaw/` - OpenClaw schema, plugin, and examples.
- `memory_engine/copilot/` - service, tools, permissions, governance, retrieval.
- `memory_engine/` - storage, Feishu adapters, benchmark support.
- `scripts/` - demo, readiness, evidence, and workspace utilities.
- `benchmarks/` - benchmark cases.
- `tests/` - regression tests.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 -m memory_engine init-db
```

Run the basic checks:

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

OpenClaw is pinned to:

```text
2026.4.24
```

Do not upgrade OpenClaw while validating this project.

## Demo

Replay the fixed demo flow:

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

The replay covers:

- Search for the current active decision.
- Conflict update and version explanation.
- Task prefetch context pack.
- Controlled reminder candidate.
- Readiness evidence for demo / pre-production.

For the judge-facing script, see:

- `docs/judge-10-minute-experience.md`
- `docs/demo-runbook.md`
- `docs/productization/expanded-demo-showcase-plan.md`

## Benchmarks

Benchmark cases live in `benchmarks/copilot_*.json` and cover recall,
stale-value filtering, conflict handling, candidate governance, task prefetch,
heartbeat reminder candidates, and realistic Feishu expressions.

See `docs/benchmark-report.md` for results and interpretation.

## Feishu / Workspace Notes

The current Feishu path is controlled:

- New groups are `pending_onboarding` by default.
- Passive candidate screening only runs for allowlisted or explicitly enabled
  groups.
- Important, sensitive, or conflicting facts stay as candidates until reviewer
  or owner confirmation.
- Workspace ingestion is proven as a limited/productized readiness pilot, not as
  an unrestricted enterprise-wide crawler.

Workspace docs:

- `docs/productization/workspace-ingestion-architecture-adr.md`
- `docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md`
- `docs/productization/workspace-ingestion-evidence-collection-runbook.md`

## Documentation

Start here:

- `docs/human-product-guide.md` - human-readable product explanation.
- `docs/README.md` - documentation map.
- `docs/demo-runbook.md` - demo script.
- `docs/benchmark-report.md` - benchmark report.
- `docs/productization/full-copilot-next-execution-doc.md` - active execution
  source of truth.

Historical plans and handoffs live under `docs/archive/` and
`docs/productization/handoffs/`. They are evidence, not the current execution
entry point.

## Development Checks

Before submitting changes, run at least:

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

For Python, schema, tool, or benchmark changes, also run the relevant unit tests.
See `AGENTS.md` and `docs/productization/agent-execution-contract.md` for the
full validation matrix.

## License

Competition prototype. Add a license before using this as a public production
project.
