# Feishu Memory Copilot Benchmark Report

日期：2026-05-03
主线：OpenClaw-native Feishu Memory Copilot
证据来源：`memory_engine/benchmark.py`、`benchmarks/copilot_*_cases.json`、本地 `reports/copilot_*.json` / `reports/copilot_*.csv`

> **状态更新（2026-04-28）**：本报告对应的 2026-05-03 指标自证任务已经完成，不再作为后续待执行计划。后续若继续扩展 Benchmark（评测脚本），必须服务完整可用 Copilot 产品化，入口见 `docs/productization/full-copilot-next-execution-doc.md`。

## 先看这个

1. 这份报告证明 Copilot MVP 已经有可复现的评测入口，不只是“看起来能用”。
2. 本轮覆盖 recall（历史决策召回）、candidate（待确认记忆识别）、conflict（冲突更新）、layer（分层召回）、prefetch（任务前上下文包）、heartbeat（主动提醒候选）六类能力。
3. 今天不追求最终指标冲高，先保证每个 PRD 指标都有输入字段、输出字段、失败分类和可复现命令。
4. Bitable Benchmark Results 已有 dry-run 字段承载这些指标；今天不真实写飞书生产表。
5. 当前所有样例通过；本轮额外加入 10 条难例，覆盖多轮改口、未采纳方案、Bitable block 写入、OpenClaw-first Demo 和敏感提醒脱敏。

## 可复现实验命令

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json --json-output reports/copilot_recall.json --csv-output reports/copilot_recall.csv
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json --json-output reports/copilot_candidate.json --csv-output reports/copilot_candidate.csv
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json --json-output reports/copilot_conflict.json --csv-output reports/copilot_conflict.csv
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json --json-output reports/copilot_layer.json --csv-output reports/copilot_layer.csv
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json --json-output reports/copilot_prefetch.json --csv-output reports/copilot_prefetch.csv
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json --json-output reports/copilot_heartbeat.json --csv-output reports/copilot_heartbeat.csv
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

`reports/` 是本地运行证据目录，默认不提交。提交物里保留本报告和 benchmark case 文件。

## PRD 指标映射

| PRD 指标 | 本轮入口 | 当前结果 | MVP 目标 | 结论 |
|---|---|---:|---:|---|
| Recall@3 | `copilot_recall_cases.json` | 1.0000 | >= 0.6000 | 通过 |
| Conflict Update Accuracy | `copilot_conflict_cases.json` | 1.0000 | >= 0.7000 | 通过 |
| Evidence Coverage | recall / conflict / layer / prefetch | 1.0000 | >= 0.8000 | 通过 |
| Candidate Precision | `copilot_candidate_cases.json` | 1.0000 | >= 0.6000 | 通过 |
| Agent Task Context Use Rate | `copilot_prefetch_cases.json` | 1.0000 | >= 0.7000 | 通过 |
| L1 Hot Recall p95 | `copilot_layer_cases.json` | 1.602 ms | 先记录，不设硬阈值 | 已有入口 |
| Sensitive Reminder Leakage Rate | `copilot_heartbeat_cases.json` | 0.0000 | 0.0000 | 通过 |
| Stale Leakage Rate | recall / conflict / layer / prefetch | 0.0000 | <= 0.1500 | 通过 |

## 分项结果

| benchmark | 样例数 | 通过率 | 核心指标 | 失败分类 |
|---|---:|---:|---|---|
| copilot_recall | 10 | 1.0000 | Recall@3 = 1.0000；Evidence Coverage = 1.0000；Stale Leakage = 0.0000 | 无失败 |
| copilot_candidate | 34 | 1.0000 | Candidate Precision = 1.0000；candidate_not_detected = 0；false_positive_candidate = 0 | 无失败 |
| copilot_conflict | 12 | 1.0000 | Conflict Accuracy = 1.0000；Superseded Leakage = 0.0000；Evidence Coverage = 1.0000 | 无失败 |
| copilot_layer | 15 | 1.0000 | Layer Accuracy = 1.0000；L1 Hot Recall p95 = 1.602 ms | 无失败 |
| copilot_prefetch | 6 | 1.0000 | Agent Task Context Use Rate = 1.0000；Evidence Coverage = 1.0000 | 无失败 |
| copilot_heartbeat | 6 | 1.0000 | Reminder Candidate Rate = 1.0000；Sensitive Reminder Leakage Rate = 0.0000 | 无失败 |
| day1 fallback | 10 | 1.0000 | 旧本地 memory demo 仍可复现 | 无失败 |

## 样例证据

| 能力 | 样例 | 证明点 |
|---|---|---|
| 历史决策召回 | `copilot_recall_deploy_region_001` | 旧 `cn-shanghai` 被覆盖后不进入当前答案，Top 3 返回 `ap-shanghai` 并带 evidence。 |
| 候选记忆识别 | `cand_should_006` | 旧生产部署规则存在时，新 region 文本进入 conflict candidate，不直接覆盖 active 记忆。 |
| 冲突更新 | `conflict_region_override_001` | confirm 后新版本 active，旧版本 superseded，`memory.explain_versions` 能展示版本链证据。 |
| 分层召回 | `copilot_layer_hot_openclaw_version_001` | OpenClaw 版本锁规则走 L1 Hot Memory，并保留 evidence quote。 |
| 任务前预取 | `prefetch_stale_value_filtered` | `memory.prefetch` 返回 compact context pack，只带 active `ap-shanghai`，不泄漏旧 `cn-shanghai`。 |
| 主动提醒候选 | `heartbeat_sensitive_redaction` | reminder candidate 生成前会把 `api_key` 原文脱敏，Sensitive Reminder Leakage Rate = 0。 |

## 难例加固

本轮新增的 10 条样例不是为了冲高指标，而是为了覆盖评委容易追问的“系统是否足够克制”。

| 类型 | 新增样例 | 难在哪里 | 期望行为 |
|---|---|---|---|
| recall | `copilot_recall_multi_turn_deadline_override_002` | 同一截止时间被多轮改口 | 只返回 `2026-05-07 中午前`，旧的“周日晚上提交”不进当前答案 |
| recall | `copilot_recall_tentative_tool_not_decision_002` | 群里出现过未采纳的 lark-oapi 讨论 | 返回最终的 `lark-cli base` 决策，不把“研究 lark-oapi”当当前方案 |
| candidate | `cand_should_016` | reminder 只做候选、不真实发群是产品边界 | 进入待确认记忆，后续 Demo 和实现都能复用 |
| candidate | `cand_should_017` | 失败样例必须带 case_id 和 recommended_fix | 进入待确认记忆，保障后续排障可追踪 |
| candidate | `cand_skip_016` | 只是“可以先听听”的讨论态度 | 不生成 candidate |
| candidate | `cand_skip_017` | 未采纳工具方案还没定 | 不生成 candidate |
| conflict | `conflict_bitable_block_write_011` | Bitable 写入链路从错误 Sheets API 改为 base record | 新值 active，旧值 superseded |
| conflict | `conflict_demo_recording_flow_012` | Demo 编排从 Bot-first 改为 OpenClaw-first | 默认答案返回 `OpenClaw memory.search` |
| prefetch | `prefetch_bitable_block_not_sheet_api` | 任务前上下文不能带入旧 Sheets 写法 | context pack 只带 active `lark-cli base record` |
| heartbeat | `heartbeat_sensitive_webhook_redaction` | reminder 可以提示风险，但不能泄漏 secret | 生成 reminder candidate，并脱敏 `secret` 原文 |

## 失败分类

| failure_type | 用户会看到什么坏结果 | 代表检查入口 | recommended fix |
|---|---|---|---|
| `candidate_not_detected` | 重要规则没有进入待确认列表，后续 Agent 仍会忘 | `memory.create_candidate` 输出、`risk_flags`、case 原文 | 检查 candidate 规则是否覆盖决策、负责人、截止时间、流程规则和风险结论。 |
| `false_positive_candidate` | 闲聊、临时想法或未采纳方案被乱记 | `cand_skip_*`、candidate precision | 检查低价值闲聊和临时确认的过滤规则，避免乱记。 |
| `wrong_subject_normalization` | 新旧表达没归到同一主题，冲突更新失败 | `subject`、`normalized_subject`、`memory.explain_versions` | 检查 subject 归一化，确认新旧表达被归到同一主题。 |
| `wrong_layer_routing` | 应在 L1/L2/L3 的记忆走错层，trace 解释不可信 | `trace.steps[].layer`、`expected_layer` | 检查 L1/L2/L3 分层过滤、fallback 顺序和 trace 中的 layer 标记。 |
| `vector_miss` | 用户换一种说法后 Top 3 找不到正确记忆 | `matched_via`、`why_ranked.vector_score` | 检查 curated memory embedding 文本和 rerank 权重，确认语义改写能进入 Top 3。 |
| `keyword_miss` | 明确文件名、参数名或版本号没有命中 | keyword_index、query token、Top 3 | 检查关键词索引、文件名/参数名保留，以及 query token 是否被过度清洗。 |
| `stale_value_leaked` | 旧版本或 superseded 值混进当前答案 | version chain、active-only filter、Top 3 | 检查 active-only 过滤和 version chain，确保 superseded / stale 不作为当前答案返回。 |
| `evidence_missing` | 答案看似正确但没有证据，评委无法信任 | evidence quote、source_id、tool output | 检查 evidence quote 写入和工具输出，召回结果必须带来源证据。 |
| `agent_did_not_prefetch` | Agent 开始任务前没有拿到上下文包 | `memory.prefetch` 调用记录、context pack | 检查 memory.prefetch 是否在 Agent 任务前被调用，且 context pack 非空。 |
| `reminder_too_noisy` | 该提醒没出现，或不该提醒时乱提醒 | heartbeat trigger、cooldown、relevance gate | 检查 heartbeat 触发条件、cooldown 和 relevance gate，避免漏发或乱发 reminder candidate。 |
| `permission_scope_error` | 跨 scope 数据或敏感内容出现在输出里 | scope permission、redaction、risk_flags | 检查 scope permission、敏感内容脱敏和 reminder 输出权限门控。 |

当前本轮无失败样例；后续不要为了保持 100% 指标删除难例，新增失败时按上表归因。

## 指标反例说明

| 指标 | 反例要证明什么 | 本轮覆盖 |
|---|---|---|
| Recall@3 | 不是所有提到过的内容都应召回，临时建议不能压过最终决策 | `copilot_recall_tentative_tool_not_decision_002` |
| Conflict Update Accuracy | 旧值必须保留在版本链里，但不能继续作为当前答案 | `conflict_bitable_block_write_011`、`conflict_demo_recording_flow_012` |
| Evidence Coverage | 正确答案没有 evidence quote 也不能算通过 | 所有 Copilot runner 都把 evidence 纳入 passed 条件 |
| Candidate Precision | 普通闲聊、未定方案、个人临时状态都不应进入 candidate | `cand_skip_016`、`cand_skip_017` |
| Agent Task Context Use Rate | prefetch 不是把所有相关聊天塞给 Agent，只能带 active 且与任务相关的记忆 | `prefetch_bitable_block_not_sheet_api` |
| L1 Hot Recall p95 | Hot Memory 只证明高频规则的快速入口，不把所有记忆都强行塞进 L1 | `copilot_layer_cases.json` 保持 L1/L2/L3 均衡 |
| Sensitive Reminder Leakage Rate | reminder 可以提示“需要检查风险”，但不能泄漏 token、secret 或密钥原文 | `heartbeat_sensitive_redaction`、`heartbeat_sensitive_webhook_redaction` |
| Stale Leakage Rate | superseded 旧值可以用于解释版本链，但不能出现在默认 search / prefetch 当前上下文中 | `copilot_recall_multi_turn_deadline_override_002`、`prefetch_stale_value_filtered` |

## Bitable Dry-Run 对齐

`memory_engine/bitable_sync.py` 的 `Benchmark Results` 已扩展以下字段，能承载 2026-05-03 指标：

- `benchmark_type`
- `recall_at_3`
- `candidate_precision`
- `candidate_recall`
- `agent_task_context_use_rate`
- `l1_hot_recall_p95_ms`
- `sensitive_reminder_leakage_rate`
- `failure_type_counts`
- `recommended_fix_summary`

真实写飞书生产表不是今天阻塞项。今天只要求 dry-run payload 能展示字段，避免把评测结果锁死在本地日志里。

## 当前局限

- 样例规模仍是 MVP 级：recall 10 条、candidate 34 条、conflict 12 条、layer 15 条、prefetch 6 条、heartbeat 6 条。适合证明链路，不代表最终复赛级压力测试。
- `reports/` 的 JSON / CSV 是本地运行证据，没有提交；评委材料优先读本报告和可复现命令。
- Cognee optional recall channel 在这些本地 benchmark 中显示为 unavailable；本报告验证的是 Copilot runner、状态机、hybrid retrieval、prefetch 和 heartbeat dry-run。真实 Cognee / Ollama embedding 已由 Phase D live gate 单独验证，不把本 benchmark 报告写成长期 embedding 服务证明。
- heartbeat 仍是 reminder candidate / dry-run，不真实发群，不绕过治理层自动写 active memory。
- Bitable 仍是展示和审核面，不是 source of truth。

## 下一步

2026-05-04 Demo runbook、OpenClaw examples 和 `scripts/demo_seed.py` 已完成；2026-05-05《Memory 定义与架构白皮书》也已完成。后续不要再按旧日期 implementation plan 继续执行，本报告作为历史评测证据；新的 Benchmark 扩展应围绕产品化 Phase A-E 的 storage/audit、runtime、staging、embedding 和 QA 缺口展开。
