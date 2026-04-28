# 2026-05-01 Implementation Plan

> **历史状态更新（2026-04-28）**：本文件对应的 2026-05-05 及以前任务已经完成，保留为历史计划/交接证据，不再作为后续执行入口。新的执行入口是 `docs/productization/full-copilot-next-execution-doc.md`，下一步优先 Phase A：Storage Migration + Audit Table。

阶段：conflict update、versions、stale leakage、Card/Bitable review surface design
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

让 Copilot Core 能处理 old -> new 冲突更新：旧版本进入 superseded / cold，新版本成为 active 或候选确认；默认 recall 不泄漏旧值，`memory.explain_versions` 能解释版本链。同时冻结候选记忆卡片、版本链卡片和 Bitable review tables 的字段设计，确保它们只消费 Copilot service 输出，不直接改状态。

## MemPalace 转换落点

今天只借鉴 MemPalace temporal knowledge graph 的“事实有时间窗口、旧事实不删除”思想，不照搬 SQLite KG 或引入新图数据库。对应到本项目就是 Copilot governance 的版本链：新值确认后，旧 active 变成 `superseded` 和 Cold evidence；默认 search 只回答当前 active，`memory.explain_versions` 才展示旧值、新值、覆盖关系和证据。

今天要坚持两条边界：

- 旧版本不删除，但不能继续作为当前答案出现在 `memory.search` 或 `memory.prefetch`。
- Card / Bitable 只展示和审核 Copilot service 输出，不直接改变版本状态。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-01-implementation-plan.md`
- `docs/plans/2026-04-30-handoff.md`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `docs/reference/bitable-ledger-views.md`，如存在

## 程俊豪今日主线任务

今天只要求程俊豪一个人闭环，不等待其他人交付。主线先做“冲突更新 + 版本解释 + 旧值不泄漏”的代码和评测，review surface 只做到 typed payload / dry-run，不接真实按钮回调或真实 Bitable 写入。

1. 在 `memory_engine/copilot/governance.py` 中硬化同 scope + 同 normalized subject 的冲突检测。
2. 在 `memory_engine/copilot/service.py` 和 `memory_engine/copilot/governance.py` 的 confirm 流程中处理 old active -> superseded、new -> active。
3. 在 `memory_engine/copilot/service.py` 和 `memory_engine/copilot/tools.py` 实现 `memory.explain_versions`。
4. 在 `memory_engine/copilot/retrieval.py` 和 `tests/test_copilot_governance.py` 增加 stale / superseded leakage 测试，默认 `memory.search` 只返回 active。
5. 如果当前代码已有 `memory.prefetch` 入口，只复用 active-only 过滤；不要为了这一天提前实现完整 prefetch。
6. 创建或扩展 `benchmarks/copilot_conflict_cases.json`，至少纳入 8-10 条可跑的真实冲突样例。
7. 在 `memory_engine/feishu_cards.py` 设计 Copilot candidate review card / version chain card 的 typed payload，不直接调用 repository 改状态。
8. 在 `memory_engine/bitable_sync.py` 设计 Memory Ledger、Versions、Candidate Review、Benchmark Results、Reminder Candidates 五类表字段和 dry-run payload。
9. 明确 MVP buttons：确认保存、拒绝候选为必做；查看版本链、查看来源、标记需要复核可以先 dry-run。

## 今日做到什么程度

今天结束时必须能证明“旧值不会继续当成当前答案”：

- 同一 scope + normalized subject 的冲突更新能生成版本关系。
- 新值确认后成为 active，旧值进入 superseded / cold。
- 默认 `memory.search` 不返回 superseded / stale 作为当前答案。
- `memory.explain_versions` 能看到旧值、新值、覆盖关系和 evidence。
- Card/Bitable 只做 review surface 和 dry-run payload，不绕过 Copilot service 改状态，也不要求真实飞书写入。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 标准化 subject | `memory_engine/copilot/governance.py` | 同义、纠错和“以后统一改成”能归到同一 normalized subject 的最小规则 | `tests/test_copilot_governance.py` 覆盖同 subject 冲突 |
| 2 | 冲突检测 | `memory_engine/copilot/governance.py` | 发现 old active 和 new candidate 的覆盖关系，并保留旧值 evidence | candidate 输出包含 conflict object |
| 3 | 版本状态转移 | `memory_engine/copilot/service.py`、`memory_engine/copilot/governance.py` | confirm 冲突候选时 old -> superseded，new -> active | 单测验证旧值不再作为 search 当前答案 |
| 4 | 实现 explain_versions | `memory_engine/copilot/service.py`、`memory_engine/copilot/tools.py` | 返回 active_version、versions、supersedes、evidence 和失效原因 | `tests/test_copilot_tools.py` 或 governance 单测覆盖版本链 |
| 5 | Cold evidence 边界 | `memory_engine/copilot/retrieval.py` | superseded/stale 只进入 explain_versions 或 deep trace，不进入默认 Top K | `memory.search` 旧值泄漏测试为 0 |
| 6 | stale leakage 测试 | `memory_engine/copilot/retrieval.py`、`tests/test_copilot_governance.py` | 默认 search 不泄漏 stale/superseded；如已有 prefetch 入口也复用同一过滤 | stale/superseded leakage 为 0，不提前实现 prefetch |
| 7 | 建 conflict benchmark | `benchmarks/copilot_conflict_cases.json`、`memory_engine/benchmark.py` | 8-10 条真实冲突表达可跑；runner 未完成时先用单测统计 | Conflict Update Accuracy 入口成型，不把未跑结果写成已通过 |
| 8 | 设计 card payload | `memory_engine/feishu_cards.py`、`tests/test_feishu_interactive_cards.py` | candidate review card 和 version chain card typed payload | card 单测或 snapshot 通过；不接真实回调 |
| 9 | 设计 Bitable dry-run | `memory_engine/bitable_sync.py`、`tests/test_bitable_sync.py` | 5 类表字段和 dry-run payload 明确 | bitable 单测验证字段齐全；不把 Bitable 当 source of truth |

## 今日不做

- 不删除旧版本，只改状态。
- 不把 Bitable 当成 source of truth。
- 不做完整多租户权限后台。
- 不在未验证前接真实群聊按钮回调。
- 不提前实现 2026-05-02 的 `memory.prefetch` 完整 context pack 或 heartbeat reminder。
- 不安装新依赖，不改 OpenClaw / Cognee / embedding provider 锁定。
- 不把 `benchmarks/day1_cases.json` 当成今天的默认主验收；只有触达 legacy fallback、旧 CLI/Bot、本地 repository 或 day1 runner 时才追加。

## 需要改/新增的文件

- `memory_engine/copilot/governance.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `memory_engine/benchmark.py`
- `tests/test_copilot_governance.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_bitable_sync.py`
- `benchmarks/copilot_conflict_cases.json`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_copilot_governance
python3 -m unittest tests.test_copilot_tools
python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
```

如果 `copilot_conflict_cases.json` runner 尚未实现，先把数据集和单测跑通，再补 runner，不把 Conflict Update Accuracy 写成已通过。

只有触达 legacy fallback、旧 Bot、旧 CLI、本地 repository、文档摄取、Bitable 真实同步或历史 benchmark runner 时，才追加：

```bash
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

本次计划修正如果只改文档，提交前只需要运行：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

## 验收标准

- Conflict Update Accuracy >= 70% 的统计入口成型；如果当天 runner 尚未完全接通，用单测统计并在 handoff 写清未跑原因。
- Stale Leakage Rate 和 superseded leakage 能被 benchmark 或单测统计。
- 旧版本进入 superseded / cold。
- 默认 recall 不返回旧值作为当前答案。
- explain_versions 能说明旧值为什么失效，并带 evidence。
- superseded / stale 只作为 Cold evidence 或版本解释材料出现，不进入默认当前答案。
- 候选记忆卡片展示当前结论、类型、主题、状态、版本、来源 evidence、是否覆盖旧值、风险标记。
- Card / Bitable 只消费 Copilot service 输出，不直接改状态；真实写入失败时能输出 dry-run payload。

## 我的补充任务

先看这个：

1. 在 `benchmarks/copilot_conflict_cases.json` 或 2026-05-01 handoff 草稿里设计 20 组真实冲突表达，例如“刚才说错了”“统一改成”“以后别用这个”；完成标准是能挑出 8-10 条进入可跑 benchmark。
2. 检查 `memory.explain_versions` 的输出文案是否能让非技术评委看懂：哪个是新值、哪个旧值已失效、证据来自哪里。
3. 标注哪些冲突表达应该进入人工确认；完成标准是每条样例都有 expected_action 或同等字段。
4. 检查 `memory_engine/feishu_cards.py` 的 Candidate Review 表达是否能看出“待确认记忆”和“覆盖旧值”的区别。
5. 检查 `memory_engine/bitable_sync.py` 的 Candidate Review 表字段是否支持后续人工复核；完成标准是字段包含状态、主题、新值、旧值、证据、风险、操作建议。

本阶段不用做：

- 不用删除旧版本。
- 不用做完整权限后台。
- 不用把 Bitable 当成 source of truth。
