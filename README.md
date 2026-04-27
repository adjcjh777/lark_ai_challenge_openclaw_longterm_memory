# Feishu Memory Copilot

## 今天先做这个：我的任务

从 2026-04-27 起，本项目按程俊豪单人执行；原先拆出去的评测、文案、QA 和检查任务都并入我的补充任务。打开 GitHub 首页时先看这里，再进入当天计划。

进度说明：当前自然日期仍按项目上下文记录为 2026-04-27；本地代码和文档已经提前完成 2026-04-28 的分层查询切片，所以当前可继续从 2026-04-29 的混合召回计划进入。不要回头重做 2026-04-28 的逐层查询和分层评测脚本，除非验证失败。

| 当前任务 | 直接入口 | 交付物 | 完成标准 |
|---|---|---|---|
| 按 MemPalace 转换方案进入 2026-04-29 混合召回 | [2026-04-29 plan](docs/plans/2026-04-29-implementation-plan.md)；[主控 6.4](docs/feishu-memory-copilot-implementation-plan.md#64-mempalace-借鉴的转换接入边界)；[retrieval.py](memory_engine/copilot/retrieval.py)；[benchmark.py](memory_engine/benchmark.py) | `RecallIndexEntry` 短索引、keyword/FTS、embedding 接口、Recall@3 评测入口 | trace 能看到 structured / keyword_index / vector / cognee / rerank，并展示 `matched_via` / `why_ranked`；不向量化 raw events |
| 4 月 28 日稳定性硬化已完成 | [2026-04-28 handoff：稳定性说明](docs/plans/2026-04-28-handoff.md#仍未完成或仍有风险)；[test_copilot_benchmark.py](tests/test_copilot_benchmark.py) | 分层指标、trace 契约、fixture 自检、错误路径测试 | `copilot_layer_cases.json` 的 15 条样例不只可读，还会校验 `layer_accuracy` |
| 继续扩展 recall 评测 | [copilot_recall_cases.json](benchmarks/copilot_recall_cases.json)；[2026-04-29 plan](docs/plans/2026-04-29-implementation-plan.md) | 失败样例备注和 Recall@3 指标 | 问题像真实飞书项目群提问，每条能看出正确答案、证据关键词、企业记忆意图和可能失败原因 |

飞书 AI 挑战赛 OpenClaw 赛道项目。当前主线已经从旧的 CLI-first / Bot-first memory demo 切换为 **OpenClaw-native Feishu Memory Copilot**。

## 当前状态

截至 2026-04-28，项目已完成 2026-04-26 至 2026-04-28 三天任务：

- OpenClaw 版本固定为 `2026.4.24`，锁文件位于 `agent_adapters/openclaw/openclaw-version.lock`。
- OpenClaw MVP 工具 schema 已建立：`agent_adapters/openclaw/memory_tools.schema.json`。
- Copilot Core 第一批骨架已建立：`memory_engine/copilot/`。
- `memory.search` 已从最小 fallback 升级为 L0 / L1 / L2 / L3 query cascade：工具层薄封装，service 调 orchestrator，trace 能解释每层检索和 fallback。
- Cognee 已通过窄 adapter 隔离在 `memory_engine/copilot/cognee_adapter.py`。
- Cognee 本地 spike 已验证：RightCode 文本模型 + Ollama 本地 embedding 可跑通 `add -> cognify -> search`。
- 本地 embedding 基线锁定为 `qwen3-embedding:0.6b-fp16`，锁文件位于 `memory_engine/copilot/embedding-provider.lock`。
- 新增 `benchmarks/copilot_recall_cases.json`，并把 `benchmarks/copilot_layer_cases.json` 扩到 15 条分层样例；runner 已校验 `layer_accuracy`，fixture 自检会防重复、缺字段和缺失败排查提示。
- MemPalace 调研结论已转换为日期计划：只借鉴原文证据、短索引、分层召回、可解释评测，不把 MemPalace 作为新依赖接入。
- `docs/demo-runbook.md` 和 `docs/benchmark-report.md` 仍保留旧 demo / 旧 benchmark 证明材料，按 2026-05-03 至 2026-05-04 计划再系统更新；当前不要把它们当成 OpenClaw Copilot 最终材料。

## 快速验证

基础验证：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

Copilot contract 验证：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_retrieval tests.test_copilot_cognee_adapter
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
- `docs/plans/2026-04-28-handoff.md`
- `docs/plans/2026-04-29-implementation-plan.md`

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
- 2026-04-28 handoff：`docs/plans/2026-04-28-handoff.md`
- 下一执行计划：`docs/plans/2026-04-29-implementation-plan.md`
- Windows embedding 配置：`docs/reference/local-windows-cognee-embedding-setup.md`
- 旧资料归档：`docs/archive/`
- 长期参考资料：`docs/reference/`
