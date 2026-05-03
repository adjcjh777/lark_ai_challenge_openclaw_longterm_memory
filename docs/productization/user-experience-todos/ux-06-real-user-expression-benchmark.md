# UX-06：真实用户表达样本评测

日期：2026-04-29
负责人：程俊豪
状态：已完成（样本集、runner 和 pre-live 质量 gate 已完成；仍保留残余失败样例）
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 6 个

## 本轮要做什么

在现有 benchmark 上增加真实用户表达样本和 UX 指标，覆盖：

- 口语化提问。
- 含糊上下文。
- 多人改口。
- 闲聊误判。
- 权限场景。
- 误提醒和确认负担。

真实用户表达样本必须脱敏。不能提交真实 chat_id、open_id、token 或敏感业务内容。

## 本轮完成情况

- 已使用现有 `benchmarks/copilot_real_feishu_cases.json` 定义 UX-06 样本 schema。
- 每条样本包含用户输入、上下文、期望 intent、期望是否记忆、权限预期、当前 baseline 观察值和失败 debug hint。
- 已补 5 类脱敏样本，每类 5 条：口语、含糊、多轮改口、闲聊误判、权限场景。
- 已新增 `copilot_real_feishu` benchmark runner，指标包含 Recall@3、误记率、误提醒率、确认负担、解释覆盖率和旧值泄漏率。
- 已补 `tests/test_copilot_benchmark.py` 回归测试，覆盖样本格式、指标输出和失败输出。
- 已对齐 `docs/benchmark-report.md` 和上游 `docs/productization/user-experience-todo.md`。
- 已新增 `scripts/check_real_feishu_expression_quality_gate.py --json`，把本页“指标建议”转成可执行 pre-live 质量 gate。当前 gate 返回通过：旧值泄漏率已降到 `0.0000`，其他硬阈值也通过。

本地重跑结果：

| 指标 | 结果 | 当前判断 |
|---|---:|---|
| 样本数 | 25 | 口语、含糊、多轮改口、闲聊误判、权限场景各 5 条 |
| Case pass rate | 0.8000 | 保留失败样例，不作为生产结论 |
| Recall@3 | 0.8750 | 当前样本通过 |
| 误记率 | 0.0400 | 当前样本通过，但保留 1 条误记失败样例 |
| 误提醒率 | 0.0000 | 当前样本通过 |
| 确认负担 | 2.4000 | 每 10 条输入约 2.4 条需要人工候选处理 |
| 解释覆盖率 | 0.8500 | 当前样本通过，但保留解释缺口 |
| 旧值泄漏率 | 0.0000 | 当前样本通过 |

## 为什么现在做

当前 benchmark 已覆盖 recall、candidate、conflict、layer、prefetch、heartbeat，但很多样例仍偏 fixture。真实飞书用户不会按 schema 说话，会说“这个还按之前那个来吗”“刚才那个废掉”“哈哈这个先别记”。如果不测这些表达，产品体验会在演示外失真。

## 本阶段不用做

- 本阶段不用接全量飞书 workspace。
- 本阶段不用删除失败样例来保证好看的结果。
- 本阶段不用把 fixture 通过说成真实用户稳定可用。
- 本阶段不用提交未脱敏聊天记录。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 定义真实表达样本 schema | `benchmarks/copilot_real_feishu_cases.json` 或新 `benchmarks/copilot_user_expression_cases.json` | 每条样本包含输入、上下文、期望 intent、期望是否记忆、权限预期、失败 debug hint。 |
| 2 | 补 5 类脱敏样本 | `benchmarks/` | 口语、含糊、多轮改口、闲聊误判、权限场景各至少 5 条；失败样例保留。 |
| 3 | 扩 benchmark runner 指标 | `tests/test_copilot_benchmark.py`、benchmark runner 相关代码 | 指标包含 Recall@3、误记率、误提醒率、确认负担、解释覆盖率、旧值泄漏率。 |
| 4 | 对齐报告和阈值 | `docs/benchmark-report.md` | 报告区分 fixture benchmark 和真实表达样本；写清样本规模和不足。 |
| 5 | 补回归测试 | `tests/test_copilot_benchmark.py`、相关 `tests/test_copilot_*` | 样本文件格式、指标计算和失败输出都有测试。 |
| 6 | 补 pre-live 质量 gate | `scripts/check_real_feishu_expression_quality_gate.py`、`tests/test_real_feishu_expression_quality_gate.py` | Recall@3、误记率、误提醒率、解释覆盖率和旧值泄漏率按本页阈值 fail closed；当前 gate 已通过。 |

## 样本类型建议

| 类型 | 示例 | 期望行为 |
|---|---|---|
| 口语化提问 | 上次说的部署规则是啥？ | 召回 active 记忆，给证据和解释。 |
| 含糊上下文 | 这个还按之前那个来吗？ | 结合 thread_topic 或上下文判断；不确定时要求补充。 |
| 多人改口 | 不对，刚才那个废掉 | 进入 candidate / conflict 流程，不直接覆盖 active。 |
| 闲聊误判 | 哈哈这个先别记 | 不创建 candidate。 |
| 权限场景 | 别人私聊里的结论能不能搜到？ | permission fail closed，不泄露明文。 |

## 指标建议

| 指标 | 含义 | 建议阈值 |
|---|---|---|
| Recall@3 | 正确记忆进入前三结果的比例。 | >= 0.80 |
| 误记率 | 闲聊或低价值内容被记成 candidate 的比例。 | <= 0.05 |
| 误提醒率 | 不该触发提醒却生成 reminder candidate 的比例。 | <= 0.05 |
| 确认负担 | 每 10 条输入需要人工处理的候选数。 | 记录趋势，先不强设绝对阈值。 |
| 解释覆盖率 | 结果带用户可读原因的比例。 | >= 0.80 |
| 旧值泄漏率 | superseded 旧值进入默认答案的比例。 | 0.00 |

## 验收命令

代码或 benchmark 实现后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_benchmark tests.test_copilot_retrieval
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
git diff --check
ollama ps
```

如果新增了独立真实表达样本 runner，应追加对应命令，并把命令写入 `docs/benchmark-report.md`。

本轮已新增独立 runner，追加：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_real_feishu_cases.json
```

2026-05-03 追加 pre-live 质量 gate：

```bash
python3 scripts/check_real_feishu_expression_quality_gate.py --json
```

当前该 gate 已通过；边界仍是脱敏样本的 pre-live 本地质量门禁，不是真实 Feishu live evidence。

## 本轮验证记录

已运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_benchmark tests.test_copilot_retrieval
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_real_feishu_cases.json
git diff --check
ollama ps
```

验证边界：

- `copilot_real_feishu_cases.json` 是脱敏 fixture + baseline 标注，不是生产真实用户稳定可用结论。
- 当前失败样例保留，用于暴露解释缺口、含糊上下文和闲聊误记。
- `scripts/check_real_feishu_expression_quality_gate.py --json` 是本地 pre-live 质量 gate，不是真实 Feishu live evidence，也不是 productized live 证明。
- 真实飞书来源仍 candidate-only，不自动 active。
- 不宣称 production live、真实 Feishu DM live E2E 或 productized live 长期运行完成。

## 完成标准

- 新增真实表达样本集，且全部脱敏。
- 成功样例和失败样例都保留。
- 指标覆盖准确率、安全性和用户负担。
- benchmark 报告不把样本规模夸大成生产结论。
- `scripts/check_real_feishu_expression_quality_gate.py --json` 通过，尤其旧值泄漏率必须为 `0.0000`。
- 真实飞书来源仍 candidate-only，不自动 active。

## 失败处理

- 如果某类样本失败，保留失败记录和 debug hint，不要删除。
- 如果样本包含真实 ID 或 token，先脱敏再提交。
- 如果指标波动来自 fixture 假设过强，先调整样本标注和 runner 说明，不直接放宽安全阈值。

## 顺序执行出口

UX-06 质量 gate 已完成。UX-07 已有评委体验脚本，但不能用 UX-07 或 UX-06 的脱敏样本门禁代替真实 Feishu live evidence。
