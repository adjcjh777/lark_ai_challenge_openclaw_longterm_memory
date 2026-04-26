# 2026-05-01 Implementation Plan

阶段：conflict update、versions、stale leakage、Card/Bitable review surface design
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

让 Copilot Core 能处理 old -> new 冲突更新：旧版本进入 superseded / cold，新版本成为 active 或候选确认；默认 recall 不泄漏旧值，`memory.explain_versions` 能解释版本链。同时冻结候选记忆卡片、版本链卡片和 Bitable review tables 的字段设计，确保它们只消费 Copilot service 输出，不直接改状态。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-01-implementation-plan.md`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `docs/reference/bitable-ledger-views.md`，如存在

## 用户白天主线任务

1. 在 `governance.py` 中实现同 scope + 同 normalized subject 的冲突检测。
2. 在 confirm 流程中处理 old active -> superseded。
3. 实现 `memory.explain_versions`。
4. 增加 stale / superseded leakage 测试，默认 search 只返回 active。
5. 创建或扩展 `benchmarks/copilot_conflict_cases.json`，至少覆盖 5-10 条最小样例。
6. 在 `feishu_cards.py` 中设计 Copilot candidate review card / version chain card 的 typed payload，不直接调用 repository 改状态。
7. 在 `bitable_sync.py` 中设计 Memory Ledger、Versions、Candidate Review、Benchmark Results、Reminder Candidates 五类表字段和 dry-run payload。
8. 明确 MVP buttons：确认保存、拒绝候选为必做；查看版本链、查看来源、标记需要复核可以先 dry-run。

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
python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
```

如果 `copilot_conflict_cases.json` runner 尚未实现，先把数据集和单测跑通，再补 runner，不把 Conflict Update Accuracy 写成已通过。

## 验收标准

- Conflict Update Accuracy >= 70% 的统计入口成型。
- Stale Leakage Rate 和 superseded leakage 能被 benchmark 或单测统计。
- 旧版本进入 superseded / cold。
- 默认 recall 不返回旧值作为当前答案。
- explain_versions 能说明旧值为什么失效，并带 evidence。
- 候选记忆卡片展示当前结论、类型、主题、状态、版本、来源 evidence、是否覆盖旧值、风险标记。
- Card / Bitable 只消费 Copilot service 输出，不直接改状态；真实写入失败时能输出 dry-run payload。

## 队友晚上补位任务

给队友先看这个：

1. 今天要证明“旧规则不会继续误导 Agent”，重点看冲突更新和版本解释。
2. 设计 20 组真实冲突表达，例如“刚才说错了”“统一改成”“以后别用这个”。
3. 检查版本链文案是否能让非技术评委看懂：哪个是新值、哪个旧值已失效、证据来自哪里。
4. 标注哪些冲突表达应该进入人工确认。
5. 检查 Candidate Review 表字段是否能支持晚上人工复核。

今晚不用做：

- 不用删除旧版本。
- 不用做完整权限后台。
- 不用把 Bitable 当成 source of truth。
