# Feishu Memory Copilot

## 今天先做这个：我的任务

从 2026-04-27 起，本项目按程俊豪单人执行；原先拆出去的评测、文案、QA 和检查任务都并入我的补充任务。打开 GitHub 首页时先看这里，再进入当天计划。

进度说明：2026-05-05 的《Memory 定义与架构白皮书》初稿已经完成，OpenClaw / Copilot Core / Cognee / Feishu / Bitable/Card 的边界、Demo 证据和 Benchmark 证明已经串起来。下一步从 2026-05-06 提交材料、录屏、QA 和 scope freeze 开始，只修阻塞问题，不再临时扩大到真实飞书生产写入或新工具功能。

| 当前任务 | 直接入口 | 交付物 | 完成标准 |
|---|---|---|---|
| 继续进入 2026-05-06 提交材料、录屏、QA 和 scope freeze | [2026-05-06 plan](docs/plans/2026-05-06-implementation-plan.md)；[2026-05-05 handoff](docs/plans/2026-05-05-handoff.md)；[whitepaper](docs/memory-definition-and-architecture-whitepaper.md)；[demo-runbook.md](docs/demo-runbook.md)；[benchmark-report.md](docs/benchmark-report.md) | `docs/submission-checklist.md`、录屏分镜、截图清单、全流程 QA 结果 | 三大交付物可逐项验收；README/runbook/report/whitepaper 表述一致；只修提交阻塞，不新增未验证功能 |
| 2026-05-05 白皮书初稿已完成 | [2026-05-05 handoff](docs/plans/2026-05-05-handoff.md)；[2026-05-05 plan](docs/plans/2026-05-05-implementation-plan.md)；[whitepaper](docs/memory-definition-and-architecture-whitepaper.md)；[demo-runbook.md](docs/demo-runbook.md)；[benchmark-report.md](docs/benchmark-report.md) | Memory 定义与架构白皮书可提交初稿 | 能回答 Define it / Build it / Prove it；讲清 OpenClaw、Copilot Core、Cognee、Feishu、Bitable/Card 的边界；没有把未完成 live 能力写成已完成 |
| 2026-05-04 Demo 固定和 README 快速开始已完成 | [2026-05-04 handoff](docs/plans/2026-05-04-handoff.md)；[2026-05-04 plan](docs/plans/2026-05-04-implementation-plan.md)；[demo-runbook.md](docs/demo-runbook.md)；[demo_seed.py](scripts/demo_seed.py)；[OpenClaw examples](agent_adapters/openclaw/examples/)；[memory_tools.schema.json](agent_adapters/openclaw/memory_tools.schema.json) | 5 分钟 Demo runbook、README 快速开始、OpenClaw examples freeze、demo dry-run replay | 新读者能按 README / runbook 复现历史决策召回、冲突更新、prefetch 和 heartbeat dry-run；OpenClaw runtime 不稳时有 schema examples + CLI/dry-run 兜底 |
| 2026-05-03 Benchmark Report 和指标自证已完成 | [2026-05-03 handoff](docs/plans/2026-05-03-handoff.md)；[2026-05-03 plan](docs/plans/2026-05-03-implementation-plan.md)；[benchmark.py](memory_engine/benchmark.py)；[benchmark-report.md](docs/benchmark-report.md)；[bitable_sync.py](memory_engine/bitable_sync.py) | Copilot recall / candidate / conflict / layer / prefetch / heartbeat 指标报告、10 条难例、失败分类、反例说明、评委可读 Benchmark Report | Recall@3 = 1.0；Candidate Precision = 1.0；Conflict Accuracy = 1.0；Context Use = 1.0；Sensitive Reminder Leakage Rate = 0；Bitable dry-run 字段能承载指标 |
| 2026-05-02 prefetch、heartbeat 和 OpenClaw demo dry-run 已完成 | [2026-05-02 handoff](docs/plans/2026-05-02-handoff.md)；[2026-05-02 plan](docs/plans/2026-05-02-implementation-plan.md)；[service.py](memory_engine/copilot/service.py)；[heartbeat.py](memory_engine/copilot/heartbeat.py)；[task_prefetch_flow.json](agent_adapters/openclaw/examples/task_prefetch_flow.json)；[copilot_prefetch_cases.json](benchmarks/copilot_prefetch_cases.json)；[copilot_heartbeat_cases.json](benchmarks/copilot_heartbeat_cases.json) | `memory.prefetch` context pack、heartbeat reminder candidate、agent run summary candidate、OpenClaw demo flow、reminder card / Bitable dry-run | Agent 任务前能主动拿到相关记忆、evidence 和风险提示；reminder 只生成 candidate/dry-run，不真实骚扰用户；Sensitive Reminder Leakage Rate = 0 |
| 2026-05-01 冲突更新和版本解释已完成 | [2026-05-01 handoff](docs/plans/2026-05-01-handoff.md)；[2026-05-01 plan](docs/plans/2026-05-01-implementation-plan.md)；[governance.py](memory_engine/copilot/governance.py)；[copilot_conflict_cases.json](benchmarks/copilot_conflict_cases.json)；[test_copilot_benchmark.py](tests/test_copilot_benchmark.py) | old -> new 冲突更新、`memory.explain_versions`、candidate review card / version card、Bitable dry-run 字段设计 | Conflict Update Accuracy = 1.0；旧值进入 superseded 后不再作为默认 search 当前答案；版本解释能说清新旧值和 evidence |
| 2026-04-30 候选记忆治理已完成 | [2026-04-30 handoff](docs/plans/2026-04-30-handoff.md)；[governance.py](memory_engine/copilot/governance.py)；[copilot_candidate_cases.json](benchmarks/copilot_candidate_cases.json)；[test_copilot_governance.py](tests/test_copilot_governance.py) | `memory.create_candidate`、`memory.confirm`、`memory.reject`、evidence gate、30 条 candidate benchmark | candidate 默认不进入 search；confirm 后才 active；reject 后不召回；Candidate Precision = 1.0 |
| 2026-04-29 混合召回已完成 | [2026-04-29 handoff](docs/plans/2026-04-29-handoff.md)；[retrieval.py](memory_engine/copilot/retrieval.py)；[embeddings.py](memory_engine/copilot/embeddings.py)；[copilot_recall_cases.json](benchmarks/copilot_recall_cases.json) | `RecallIndexEntry` 短索引、keyword_index、curated vector、Cognee 可选通道、Recall@3 评测入口 | trace 能看到 structured / keyword / vector / cognee / rerank，结果展示 `matched_via` / `why_ranked`；不向量化 raw events |
| 4 月 28 日稳定性硬化已完成 | [2026-04-28 handoff：稳定性说明](docs/plans/2026-04-28-handoff.md#仍未完成或仍有风险)；[test_copilot_benchmark.py](tests/test_copilot_benchmark.py) | 分层指标、trace 契约、fixture 自检、错误路径测试 | `copilot_layer_cases.json` 的 15 条样例不只可读，还会校验 `layer_accuracy` |
| candidate 评测后续自查 | [copilot_candidate_cases.json](benchmarks/copilot_candidate_cases.json)；[test_copilot_benchmark.py](tests/test_copilot_benchmark.py) | 30 条候选识别样例、Candidate Precision（候选识别准确率）、失败分类 | 每条能看出原文、正确处理、白话原因和是否应该进入待确认记忆 |

飞书 AI 挑战赛 OpenClaw 赛道项目。当前主线已经从旧的 CLI-first / Bot-first memory demo 切换为 **OpenClaw-native Feishu Memory Copilot**。

## 当前状态

截至 2026-05-05，项目已完成 2026-04-26 至 2026-05-02 第一周 MVP 闭环、2026-05-03 Benchmark Report、2026-05-04 Demo 固定和 2026-05-05 Memory 定义与架构白皮书初稿：

- OpenClaw 版本固定为 `2026.4.24`，锁文件位于 `agent_adapters/openclaw/openclaw-version.lock`。
- OpenClaw MVP 工具 schema 已建立：`agent_adapters/openclaw/memory_tools.schema.json`。
- Copilot Core 第一批骨架已建立：`memory_engine/copilot/`。
- `memory.search` 已从最小 fallback 升级为 L0 / L1 / L2 / L3 query cascade：工具层薄封装，service 调 orchestrator，trace 能解释每层检索和 fallback。
- Cognee 已通过窄 adapter 隔离在 `memory_engine/copilot/cognee_adapter.py`。
- Cognee 本地 spike 已验证：RightCode 文本模型 + Ollama 本地 embedding 可跑通 `add -> cognify -> search`。
- 本地 embedding 基线锁定为 `qwen3-embedding:0.6b-fp16`，锁文件位于 `memory_engine/copilot/embedding-provider.lock`。
- 新增 `benchmarks/copilot_recall_cases.json`，并把 `benchmarks/copilot_layer_cases.json` 扩到 15 条分层样例；runner 已校验 `layer_accuracy`，fixture 自检会防重复、缺字段和缺失败排查提示。
- MemPalace 调研结论已转换为日期计划：只借鉴原文证据、短索引、分层召回、可解释评测，不把 MemPalace 作为新依赖接入。
- `memory.search` 已升级为 hybrid retrieval：先做 structured filter，再走 keyword_index、curated memory vector、可选 Cognee 通道，最后 merge/rerank；结果带 `matched_via` 和 `why_ranked`。
- `benchmarks/copilot_recall_cases.json` 已扩到 8 条，覆盖 keyword-only、vector-only、stale-conflict，runner 输出 Recall@3 和 Evidence Coverage。
- `memory.create_candidate`、`memory.confirm`、`memory.reject` 已接入 Copilot governance；手动记忆、自动候选和文档抽取都先进入 candidate（待确认记忆）路径，缺 evidence 不能升级为 active。
- 新增 `benchmarks/copilot_candidate_cases.json`，30 条样例覆盖 15 条应该记、15 条不应该记，runner 输出 Candidate Precision、candidate_not_detected、false_positive_candidate 和 evidence_missing。
- `memory.explain_versions` 已接入 Copilot service / tools；冲突 candidate 确认后新版本 active，旧版本 superseded，默认 `memory.search` 不返回旧值作为当前答案。
- 新增 `benchmarks/copilot_conflict_cases.json`，10 条样例覆盖真实冲突表达，runner 输出 Conflict Update Accuracy、stale leakage、superseded leakage 和 evidence coverage。
- Candidate Review card、Version Chain card 和 Bitable dry-run 五类表字段已成型，当前只消费 Copilot service 输出，不直接改状态。
- `memory.prefetch` 已接入 Copilot service / tools，返回 compact context pack，包含 relevant memory、evidence、risk/deadline、version status 和 trace summary，不带 raw events。
- `memory_engine/copilot/heartbeat.py` 已生成 heartbeat reminder candidate 和 agent run summary candidate；只做 dry-run，不真实发群，不绕过 governance 自动 active。
- `benchmarks/copilot_prefetch_cases.json` 已有 6 条样例，`benchmarks/copilot_heartbeat_cases.json` 已有 6 条样例；prefetch runner 输出 Agent Task Context Use Rate，heartbeat runner 输出 Sensitive Reminder Leakage Rate。
- `docs/benchmark-report.md` 已串联 recall、candidate、conflict、layer、prefetch、heartbeat 六类指标，报告包含失败分类、反例说明、PRD 指标映射和 Bitable Benchmark Results dry-run 字段说明。
- `docs/benchmark-report.md` 已加入 10 条证明力难例：recall 10 条、candidate 34 条、conflict 12 条、layer 15 条、prefetch 6 条、heartbeat 6 条全部通过。
- `docs/demo-runbook.md` 已改成 OpenClaw-native 5 分钟演示脚本，覆盖 `memory.search`、`memory.explain_versions`、`memory.prefetch`、heartbeat reminder candidate 和 benchmark 收口。
- `scripts/demo_seed.py` 已固定 demo dry-run replay：默认使用临时 SQLite，不写飞书生产空间；可用 `--json-output reports/demo_replay.json` 生成本地演示证据。
- `agent_adapters/openclaw/examples/*.json` 已标注 copyable / schema demo 边界，并和 `memory_tools.schema.json` 的实际 search 输出字段对齐。
- `docs/memory-definition-and-architecture-whitepaper.md` 已完成初赛可提交初稿，覆盖 Define it / Build it / Prove it、架构边界、状态机、证据链、Demo/Benchmark 证明、局限和复赛路线。

## 10 分钟快速开始

先确认 OpenClaw 版本锁：

```bash
python3 scripts/check_openclaw_version.py
```

再生成本地 Demo replay。这个命令默认用临时 SQLite，只写 `reports/demo_replay.json`，不会写真实飞书生产空间：

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

查看 OpenClaw tools 契约和三条演示样例：

```bash
sed -n '1,220p' agent_adapters/openclaw/memory_tools.schema.json
sed -n '1,140p' agent_adapters/openclaw/examples/historical_decision_search.json
sed -n '1,180p' agent_adapters/openclaw/examples/conflict_update_flow.json
sed -n '1,160p' agent_adapters/openclaw/examples/task_prefetch_flow.json
```

按 5 分钟脚本演示：

```bash
sed -n '1,260p' docs/demo-runbook.md
```

跑可复现指标证明：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

Cognee 本地 SDK path 用于真实 knowledge / memory engine spike，不是 Demo 的必需前置。需要验证 Cognee + 本地 embedding 时再运行：

```bash
python3 scripts/check_embedding_provider.py
python3 scripts/spike_cognee_local.py --dry-run
ollama ps
ollama stop qwen3-embedding:0.6b-fp16
```

飞书配置说明：

- OpenClaw 是主入口，工具契约在 `agent_adapters/openclaw/memory_tools.schema.json`。
- lark-cli 是飞书文档、Bitable 和看板同步工具，配置参考 [local-lark-cli-setup.md](docs/reference/local-lark-cli-setup.md)。
- 真实 Feishu Bot 和 Bitable 写入是 fallback / review surface；Demo 默认走 schema examples + dry-run，不真实写生产空间。

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
- `docs/plans/2026-04-29-handoff.md`
- `docs/plans/2026-04-30-implementation-plan.md`
- `docs/plans/2026-04-30-handoff.md`
- `docs/plans/2026-05-01-implementation-plan.md`
- `docs/plans/2026-05-01-handoff.md`
- `docs/plans/2026-05-02-implementation-plan.md`
- `docs/plans/2026-05-02-handoff.md`
- `docs/plans/2026-05-03-implementation-plan.md`
- `docs/plans/2026-05-03-handoff.md`
- `docs/plans/2026-05-04-implementation-plan.md`
- `docs/plans/2026-05-04-handoff.md`
- `docs/plans/2026-05-05-implementation-plan.md`
- `docs/plans/2026-05-05-handoff.md`
- `docs/plans/2026-05-06-implementation-plan.md`

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
- 2026-04-29 handoff：`docs/plans/2026-04-29-handoff.md`
- 2026-05-04 Demo runbook：`docs/demo-runbook.md`
- 2026-05-04 handoff：`docs/plans/2026-05-04-handoff.md`
- 2026-05-05 白皮书：`docs/memory-definition-and-architecture-whitepaper.md`
- 2026-05-05 handoff：`docs/plans/2026-05-05-handoff.md`
- 下一执行计划：`docs/plans/2026-05-06-implementation-plan.md`
- Windows embedding 配置：`docs/reference/local-windows-cognee-embedding-setup.md`
- 旧资料归档：`docs/archive/`
- 长期参考资料：`docs/reference/`
