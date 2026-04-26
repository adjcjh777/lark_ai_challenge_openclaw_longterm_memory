# Feishu Memory Copilot

飞书 AI 挑战赛 OpenClaw 赛道项目。当前主线已经从旧的 CLI-first / Bot-first memory demo 切换为 **OpenClaw-native Feishu Memory Copilot**。

## 当前状态

截至 2026-04-27，项目已完成 2026-04-26 和 2026-04-27 两天任务：

- OpenClaw 版本固定为 `2026.4.24`，锁文件位于 `agent_adapters/openclaw/openclaw-version.lock`。
- OpenClaw MVP 工具 schema 已建立：`agent_adapters/openclaw/memory_tools.schema.json`。
- Copilot Core 第一批骨架已建立：`memory_engine/copilot/`。
- `memory.search` 已有最小 service/tool contract，并可通过旧 `MemoryRepository` fallback 返回 active memory with evidence。
- Cognee 已通过窄 adapter 隔离在 `memory_engine/copilot/cognee_adapter.py`。
- Cognee 本地 spike 已验证：RightCode 文本模型 + Ollama 本地 embedding 可跑通 `add -> cognify -> search`。
- 本地 embedding 基线锁定为 `qwen3-embedding:0.6b-fp16`，锁文件位于 `memory_engine/copilot/embedding-provider.lock`。

## 快速验证

基础验证：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

Copilot contract 验证：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_cognee_adapter
```

Embedding provider 验证：

```bash
python3 scripts/check_embedding_provider.py
ollama ps
ollama stop qwen3-embedding:0.6b-fp16
```

`check_embedding_provider.py` 会拉起本地 Ollama embedding 模型；验证结束后需要检查 `ollama ps`，并停止本项目拉起的 `qwen3-embedding:0.6b-fp16`，避免持续占用 Mac mini GPU/内存。

## 每日任务入口

每天开工前先读：

1. `AGENTS.md`
2. `docs/feishu-memory-copilot-implementation-plan.md`
3. 当天的 `docs/plans/YYYY-MM-DD-implementation-plan.md`

总控文档里已经提供可复制的每日启动 Prompt：

- `docs/feishu-memory-copilot-implementation-plan.md` 的 `1.2 每日任务启动 Prompt`

当前日期计划：

- `docs/plans/2026-04-26-implementation-plan.md`
- `docs/plans/2026-04-27-implementation-plan.md`
- `docs/plans/2026-04-27-handoff.md`
- `docs/plans/2026-04-28-implementation-plan.md`

## 主架构边界

新功能优先进入：

```text
memory_engine/copilot/
agent_adapters/openclaw/
```

不要从大改这些旧路径开始：

```text
memory_engine/repository.py
memory_engine/feishu_runtime.py
memory_engine/cli.py
```

旧实现保留为 reference / fallback，包括本地 SQLite 记忆、Feishu Bot、Bitable 同步、文档 ingestion 和旧 benchmark 样例。

## 本地数据和敏感文件

以下内容不得提交：

- `.env`
- `.env.local`
- `.data/`
- `.omx/`
- `data/*.sqlite`
- `logs/`
- `reports/`
- 真实飞书日志、群聊 ID、用户 ID、token

Cognee 本地数据目录固定在 `.data/cognee/`。

## 旧 CLI / Bot 兜底

旧本地 memory loop 仍可作为 fallback 使用：

```bash
python3 -m memory_engine init-db
python3 -m memory_engine remember --scope project:feishu_ai_challenge "生产部署必须加 --canary --region cn-shanghai"
python3 -m memory_engine recall --scope project:feishu_ai_challenge "生产部署参数"
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

旧 Feishu Bot replay 仍可用于回归：

```bash
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

真实监听仍使用：

```bash
scripts/start_feishu_bot.sh --dry-run
```

注意：旧 Bot 是 fallback 和可复现测试面，不是新 Copilot 主入口。

## 关键文档

- 主控计划：`docs/feishu-memory-copilot-implementation-plan.md`
- PRD：`docs/feishu-memory-copilot-prd.md`
- 日期计划索引：`docs/plans/README.md`
- 2026-04-27 handoff：`docs/plans/2026-04-27-handoff.md`
- 队友 Windows embedding 配置：`docs/reference/teammate-windows-cognee-embedding-setup.md`
- 旧资料归档：`docs/archive/`
- 长期参考资料：`docs/reference/`
