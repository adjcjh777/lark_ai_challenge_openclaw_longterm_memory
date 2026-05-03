# Document Writing Style Guide

Date: 2026-05-04

Purpose: make productization docs easier for humans to read while keeping audit facts precise.

This guide is based on official Anthropic material about Claude Opus 4.6, not Opus 4.7. The useful writing cues are: gather context before acting, follow constraints across long work, stay warm and collaborative, and explain intent rather than piling up reminders. Anthropic's Opus 4.7 announcement describes stronger literal instruction following and a more opinionated style; do not use that 4.7 voice as the model for this repo.

## Voice

Use clear, human, engineering prose.

Good:

```text
当前完成的是受控 workspace pilot。它能发现资源、按类型读取内容，并把候选记忆送回现有 review pipeline。它还不是长期生产 crawler。
```

Avoid:

```text
本系统已全面实现飞书 workspace 全量接入能力，并完成生产级长期运行闭环。
```

## Structure

Start every long doc with:

1. Decision or current state.
2. Boundary and non-goals.
3. What changed.
4. How to verify.
5. What remains.

Do not start with a long history of dates unless the document is a handoff.

## Claims

Use these words consistently:

| Term | Meaning |
|---|---|
| demo / pre-production | Local or controlled evidence exists. |
| controlled live sandbox | Real Feishu/OpenClaw evidence exists in a bounded test surface. |
| limited workspace pilot | Workspace resources can be discovered and routed through policy-gated candidate ingestion. |
| productized live | Long-running deployment, monitoring, storage, rollback, and operations gates are proven. |
| full workspace ingestion | Full source registry, cursoring, policy, revocation, monitoring, and production service behavior are proven. |

If only the pilot exists, say pilot.

## Rewrite Rules

- Prefer short paragraphs over giant status tables.
- Keep evidence links, but move long evidence lists below the decision.
- Preserve exact commands and file paths.
- Keep no-overclaim language visible.
- Replace “已经全部完成” with the exact surface that is complete.
- Replace “全量接入” with “limited workspace pilot” unless production source registry and long-running ingestion are proven.
- When a doc has a historical list, keep the list but add a short “current reader should care because…” sentence.

## Example Rewrite

Before:

```text
已完成 Limited Feishu ingestion 本地受控 ingestion 底座，支持文档、任务、会议、Bitable，以及 allowlist / 已启用群策略中被动探测或显式路由到 memory.create_candidate 的飞书消息。
```

After:

```text
当前已经有受控 ingestion 底座。文档、任务、会议、Bitable 和已授权群消息都能进入同一条 candidate pipeline。系统仍不会把这些来源直接写成 active memory；重要、敏感或冲突内容要先交给 reviewer/owner。
```

## Current Rewrite Boundary

This slice does not rewrite every historical handoff. The repo has many archived date plans that must stay useful as audit records. Apply this style to new productization docs first, then rewrite active entry docs in this order:

1. `README.md` - first pass completed on 2026-05-04.
2. `docs/README.md` - first pass completed on 2026-05-04.
3. `docs/human-product-guide.md` - first pass completed on 2026-05-04.
4. `docs/productization/full-copilot-next-execution-doc.md`
5. `docs/productization/prd-completion-audit-and-gap-tasks.md`

Archived plans should only be rewritten when they are promoted back into active execution.
