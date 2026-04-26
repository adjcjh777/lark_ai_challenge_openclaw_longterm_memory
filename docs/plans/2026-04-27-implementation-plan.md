# 2026-04-27 Implementation Plan

阶段：Cognee local spike、adapter contract、Copilot schemas、`memory.search` 最小 fallback
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

确认 Cognee 在本机的最小可跑路径，并把它封装在 `CogneeAdapter` 后面；同时定义 Copilot-owned schema，让 `memory.search` 的最小 fallback 路径能返回 Top K active memory with evidence。今天不追求完整 hybrid retrieval，重点是“接口稳定、可调试、可 fallback”。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-27-implementation-plan.md`
- `docs/feishu-memory-copilot-prd.md`
- 旧 repository fallback：`memory_engine/repository.py`
- 旧基线测试：`benchmarks/day1_cases.json`
- Cognee 官方安装和本地配置文档

## 用户白天主线任务

1. 新增 `memory_engine/copilot/schemas.py`，定义 `Evidence`、`MemoryResult`、`CandidateMemory`、`RecallTrace`、`ToolError`、search input/output。
2. 新增 `scripts/spike_cognee_local.py`，支持真实 Cognee SDK 闭环和 `--dry-run` 两种模式。
3. 在 `.gitignore` 中确保 `.data/` 或 `.data/cognee/` 不进入提交。
4. 新增 `memory_engine/copilot/cognee_adapter.py`，定义窄接口：`add_raw_event`、`cognify_scope`、`remember_candidate_text`、`recall`、`search`、`delete_scope(dry_run=True)`。
5. 新增 `tests/test_copilot_cognee_adapter.py`，用 fake adapter 锁住 dataset 命名、evidence metadata、不可用 fallback、状态不被 Cognee 改写。
6. 新增 `memory_engine/copilot/permissions.py`，先实现同 scope 访问的最小校验和错误格式。
7. 新增 `memory_engine/copilot/service.py` 和 `tools.py`，让 `memory.search` 第一版复用旧 `MemoryRepository.recall_candidates()`，但不把业务逻辑写进 CLI 或 Feishu handler。
8. 创建或补充 `agent_adapters/openclaw/memory_tools.schema.json`，至少覆盖 `memory.search` 和统一错误格式。

## 需要改/新增的文件

- `.gitignore`
- `agent_adapters/openclaw/memory_tools.schema.json`
- `memory_engine/copilot/__init__.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `scripts/spike_cognee_local.py`
- `tests/test_copilot_schemas.py`
- `tests/test_copilot_tools.py`
- `tests/test_copilot_cognee_adapter.py`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/spike_cognee_local.py --dry-run
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_cognee_adapter
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

如果 Cognee 已安装并配置本地 provider，再追加：

```bash
python3 scripts/spike_cognee_local.py
```

## 验收标准

- `scripts/spike_cognee_local.py` 能清楚输出真实跑通、dry-run 或 blocked 的状态。
- Cognee 本地数据目录固定在项目内 `.data/cognee/`，不会污染系统环境，也不会进入提交。
- `CogneeAdapter` 是唯一直接接触 Cognee 的文件；`service.py` 不直接 `import cognee`。
- Adapter contract tests 覆盖 evidence metadata、dataset/scope 映射、fallback 和 dry-run。
- `memory.search` 对 active memory 返回 Top K 结果。
- 每条结果包含 `memory_id`、`type`、`subject`、`current_value`、`status`、`version`、`score`、`evidence`。
- 缺 scope、无结果、权限不足时返回统一错误结构。
- 默认不返回 candidate / rejected / superseded。

## 队友晚上补位任务

给队友先看这个：

1. 今天会先验证 Cognee（本地记忆引擎）能不能在本机最小跑通；如果没装好，也要有 dry-run 输出说明原因。
2. 你准备 10 条真实项目协作问题，写入 `benchmarks/copilot_recall_cases.json` 草稿。
3. 每条问题写清正确答案、应该出现的来源证据关键词，以及为什么这是项目长期记忆。
4. 检查 `scripts/spike_cognee_local.py` 输出说明是否能看出“真实跑通 / dry-run / blocked”的区别。
5. 遇到问题发我：具体 case_id、问题句子和你觉得不清楚的字段。

今晚不用做：

- 不用配置真实 OpenClaw runtime。
- 不用接真实飞书权限。
- 不用改旧 `memory_engine/repository.py`。
