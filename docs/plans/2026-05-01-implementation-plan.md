# 2026-05-01 Implementation Plan

阶段：conflict update、versions、stale leakage  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

让 Copilot Core 能处理 old -> new 冲突更新：旧版本进入 superseded / cold，新版本成为 active 或候选确认；默认 recall 不泄漏旧值，`memory.explain_versions` 能解释版本链。

## 用户白天主线任务

1. 在 `governance.py` 中实现同 scope + 同 normalized subject 的冲突检测。
2. 在 confirm 流程中处理 old active -> superseded。
3. 实现 `memory.explain_versions`。
4. 增加 stale / superseded leakage 测试。
5. 创建或扩展 `benchmarks/copilot_conflict_cases.json`。

## 需要改/新增的文件

- `memory_engine/copilot/governance.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/retrieval.py`
- `tests/test_copilot_governance.py`
- `benchmarks/copilot_conflict_cases.json`

## 测试

```bash
python3 -m unittest tests.test_copilot_governance
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
```

如果 `copilot_conflict_cases.json` runner 尚未实现，先把数据集和单测跑通，再补 runner。

## 验收标准

- Conflict Update Accuracy >= 70%。
- 旧版本进入 superseded / cold。
- 默认 recall 不返回旧值作为当前答案。
- explain_versions 能说明旧值为什么失效，并带 evidence。

## 队友晚上补位任务

1. 设计 20 组真实冲突表达，例如“刚才说错了”“统一改成”“以后别用这个”。
2. 检查版本链文案是否能让非技术评委看懂。
3. 标注哪些冲突表达应该进入人工确认。

今晚不用做：

- 不用删除旧版本。
- 不用做完整权限后台。

