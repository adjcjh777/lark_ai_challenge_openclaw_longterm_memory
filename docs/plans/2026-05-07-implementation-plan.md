# 2026-05-07 Implementation Plan

阶段：完整产品 Phase 1 准备（Storage + Permission Contract Freeze），同时保留初赛提交缓冲
主控：`docs/feishu-memory-copilot-implementation-plan.md`
产品化入口：`docs/productization/complete-product-roadmap-prd.md`、`docs/productization/complete-product-roadmap-test-spec.md`

## 执行前先看这个

1. 今天先确认初赛提交材料是否已经安全冻结；如果还有提交 blocker，先修 blocker，不抢跑产品化代码。
2. 如果提交闭环已安全，今天开始 Phase 1 契约冻结：把数据、权限、OpenClaw payload、审计和权限反例写成可执行契约。
3. 今天主要交付 contract 文档和测试计划，不直接接真实飞书数据。
4. 判断做对：后续 executor 能按契约写代码，不再争论字段名、权限上下文和 fail-closed 行为。
5. 遇到问题记录：缺字段、旧 benchmark 兼容风险、OpenClaw schema 兼容风险、lark-cli/Feishu 权限风险。

## 当日目标

在不破坏初赛提交缓冲的前提下，启动完整产品 **Phase 1：Storage + Permission Contract Freeze**。

今天不是大规模实现日，而是把后续实现前最容易漂移的契约冻结下来：

- `tenant_id`、`organization_id`、`visibility_policy` 的语义。
- permission context 如何进入 OpenClaw tool payload。
- Copilot service 如何返回 permission decision。
- `memory.search`、`memory.create_candidate`、`memory.confirm`、`memory.reject`、`memory.explain_versions`、`memory.prefetch`、heartbeat 的 fail-closed 行为。
- audit fields 和 negative permission cases。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/productization/complete-product-roadmap-prd.md`
- `docs/productization/complete-product-roadmap-test-spec.md`
- `docs/plans/2026-05-07-implementation-plan.md`
- `README.md`
- `agent_adapters/openclaw/memory_tools.schema.json`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/permissions.py`
- `memory_engine/copilot/service.py`
- `memory_engine/db.py`

## 我的主线任务

1. 先确认 Phase 0/0.5 文档已经存在并通过 `git diff --check`。
2. 创建或补充 Phase 1 contract sections；可以先集中写在 `docs/productization/complete-product-roadmap-prd.md` 和 test spec 中，必要时再拆成独立文档。
3. 冻结 storage contract：memory、candidate、evidence、audit 的最小字段。
4. 冻结 permission contract：permission context、permission decision、fail-closed、redaction。
5. 冻结 OpenClaw payload contract：首版优先用 `current_context.permission` 兼容方案，除非明确决定 schema break。
6. 冻结 service-action permission matrix 和 negative permission test plan。
7. 更新飞书共享看板：`2026-05-07 程俊豪 Phase 1 Contract Freeze`，备注写清“只冻结契约，不接真实 ingestion”。

## 今日做到什么程度

今天结束时，Phase 1 可以交给后续 `$ralph` 或 `$team` 执行，但还不能直接启动 `$team` 大规模并行：

- Contract Freeze Gate checklist 每一项都有文档位置。
- storage / permission / OpenClaw payload / audit / migration / negative tests 都有最小契约。
- 缺失 permission context 必须 fail closed 的规则写清楚。
- confirm/reject/explain_versions/prefetch/heartbeat 都进入权限矩阵。
- 旧数据迁移兼容规则写清楚：默认 tenant/org/visibility、迁移幂等、旧 benchmark 仍可跑、schema version 进 healthcheck。
- 仍不声称真实飞书 live ingestion 已完成。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 确认提交缓冲安全 | README/runbook/report/whitepaper | 没有提交 blocker；如有先修 blocker | checklist 或最终回复写清状态 |
| 2 | 校验版本锁 | OpenClaw | 仍是 `2026.4.24` | `python3 scripts/check_openclaw_version.py` 通过 |
| 3 | 冻结 storage contract | PRD/test spec 或独立 RFC | memory/candidate/evidence/audit 字段齐全 | 字段表可被代码实现引用 |
| 4 | 冻结 permission contract | PRD/test spec 或独立 RFC | permission context、decision、redaction、fail-closed | missing context 行为明确 |
| 5 | 冻结 OpenClaw payload | `agent_adapters/openclaw/memory_tools.schema.json` 对照文档 | 决定 `current_context.permission` 或顶层 `permission_context` | 不再是泛泛 “object any” 口径 |
| 6 | 写权限动作矩阵 | PRD/test spec | search/create/confirm/reject/explain/prefetch/heartbeat 全覆盖 | 每个 action 有 deny 行为 |
| 7 | 写 negative test plan | test spec | tenant/org/private/reviewer/source/missing context 全覆盖 | 可直接转成 `tests/test_copilot_permissions.py` |
| 8 | 写 migration 兼容规则 | PRD/test spec | 默认 tenant/org/visibility、幂等、旧 benchmark、schema version、rollback | 后续实现不会破坏旧 demo |
| 9 | 同步飞书看板 | lark-cli | 05-07 程俊豪 Phase 1 任务更新 | 读回确认或记录失败 |
| 10 | 验证文档改动 | 本地命令 | 文档-only 至少通过版本锁和 diff 检查 | `python3 scripts/check_openclaw_version.py`、`git diff --check` |

## 我的补充任务

1. 对照 `memory_engine/db.py`，列出现有 `scope_type/scope_id` 与新 `tenant_id/organization_id/visibility_policy` 的迁移差距。
2. 对照 `memory_engine/copilot/permissions.py`，标出当前 `allowed_scopes is None` 允许通过的风险，后续应改成 fail-closed。
3. 对照 `memory_engine/copilot/service.py`，标出 `confirm/reject/explain_versions` 顶层尚未统一权限门控的风险。
4. 对照 `agent_adapters/openclaw/memory_tools.schema.json`，标出 `current_context` 仍过宽的字段风险。
5. 检查 README 和产品化文档是否仍提醒：Phase 1 通过前不允许真实 Feishu ingestion。

## 今日不做

- 不实际改数据库迁移代码，除非用户明确进入实现阶段。
- 不改 OpenClaw 版本。
- 不接真实飞书消息、文档或 Bitable ingestion。
- 不启动 `$team` 并行实现。
- 不把权限契约写成“以后再说”；今天至少要写出最小字段和 fail-closed 行为。

## 需要改/新增的文件

优先文档：

- `docs/productization/complete-product-roadmap-prd.md`
- `docs/productization/complete-product-roadmap-test-spec.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-07-implementation-plan.md`
- `README.md`

只有进入实现阶段才触达：

- `memory_engine/db.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/permissions.py`
- `memory_engine/copilot/service.py`
- `agent_adapters/openclaw/memory_tools.schema.json`
- `tests/test_copilot_permissions.py`

## 验证

文档-only 改动至少运行：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

如果今天进入实现并触达 Python/schema/test，再追加：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
```

本阶段不运行 Cognee / embedding / Ollama；如果运行，结束前必须执行：

```bash
ollama ps
```

并停止本项目拉起的模型。

## 验收标准

- Phase 1 Contract Freeze Gate 有清晰 checklist 和文档位置。
- storage、permission、OpenClaw payload、audit、migration、negative tests 都能被后续实现引用。
- 所有 `memory.*` action 和 heartbeat 都有权限门控规则。
- 文档仍保护初赛提交材料，不把产品化工作写成已完成上线。
- 飞书共享看板与 README / 日期计划一致；如同步失败，写明失败命令和错误摘要。
