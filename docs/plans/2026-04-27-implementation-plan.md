# 2026-04-27 Implementation Plan

阶段：`memory.search` contract  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

跑通第一条 OpenClaw-native 工具链：`memory.search` 接收结构化输入，调用 Copilot service，返回 Top K active memory with evidence，并保持旧 Day1 benchmark 通过。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-27-implementation-plan.md`
- 旧 repository fallback：`memory_engine/repository.py`
- 旧基线测试：`benchmarks/day1_cases.json`

## 用户白天主线任务

1. 新增 `memory_engine/copilot/schemas.py`，定义 search input/output、memory result、evidence、error schema。
2. 新增 `memory_engine/copilot/permissions.py`，先实现同 scope 访问的最小校验和错误格式。
3. 新增 `memory_engine/copilot/service.py`，实现 `CopilotService.search()`。
4. 新增 `memory_engine/copilot/tools.py`，实现 `memory_search()` 薄封装。
5. 让 `memory.search` 第一版复用旧 `MemoryRepository.recall_candidates()`，但不要把业务逻辑写进 CLI 或 Feishu handler。

## 需要改/新增的文件

- `memory_engine/copilot/__init__.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `tests/test_copilot_schemas.py`
- `tests/test_copilot_tools.py`
- `tests/test_copilot_retrieval.py`

## 测试

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_retrieval
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

## 验收标准

- `memory.search` 对 active memory 返回 Top K 结果。
- 每条结果包含 `memory_id`、`type`、`subject`、`current_value`、`status`、`version`、`score`、`evidence`。
- 缺 scope、无结果、权限不足时返回统一错误结构。
- 默认不返回 candidate / rejected / superseded。

## 队友晚上补位任务

1. 准备 10 条真实项目协作 query，写入 `benchmarks/copilot_recall_cases.json` 草稿。
2. 每条 query 标注正确答案和必须出现的 evidence 关键词。
3. 检查工具输出字段名是否像评委能理解的产品能力，不要只像内部 debug JSON。

今晚不用做：

- 不用改数据库 schema。
- 不用配置真实 OpenClaw runtime。

