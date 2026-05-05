# Feishu Memory Copilot Benchmark Report

日期：2026-05-03
主线：OpenClaw-native Feishu Memory Copilot
证据来源：`memory_engine/benchmark.py`、`benchmarks/copilot_*_cases.json`、本地 `reports/copilot_*.json` / `reports/copilot_*.csv`

> **状态更新（2026-04-28）**：本报告对应的 2026-05-03 指标自证任务已经完成，不再作为后续待执行计划。后续若继续扩展 Benchmark（评测脚本），必须服务完整可用 Copilot 产品化，入口见 `docs/productization/full-copilot-next-execution-doc.md`。

> **UX-03 历史更新（2026-04-29）**：本轮为用户解释层补充了 User Explanation Coverage、Unauthorized Value Leakage Rate 和 Stale / Superseded Leakage Rate 口径。当时重跑 `copilot_conflict_cases.json` 和 `copilot_recall_cases.json` 已暴露 recall / conflict 扩样指标未全部达标；最新数字以后续 2026-05-01 稳定性修复更新为准。它们应写作残余风险和后续扩样/修复入口，不能写成全部达标。

> **稳定性修复更新（2026-05-01）**：本轮按 `deep-research-report.md` 的建议补了 retrieval score breakdown、默认检索 stale shadow filter，以及 benchmark forbidden-value 泄漏判定的否定语境处理。重跑 `copilot_recall_cases.json` 后 case pass rate = 0.7250、Recall@3 = 0.9250、stale leakage rate = 0.2500；重跑 `copilot_conflict_cases.json` 后 conflict accuracy 仍为 0.4000、stale leakage rate = 0.3429。结论：旧值泄漏风险下降，但 conflict 的核心瓶颈已更多暴露为 subject normalization / stable memory key 问题，仍不能写成全部达标。

> **Deep research 收口更新（2026-05-01）**：本轮继续落地 stable memory key / alias、contextual override、reject benchmark runner、score breakdown summary 和 deterministic embedding fallback。使用 `EMBEDDING_PROVIDER=deterministic` 重跑后，`copilot_recall_cases.json` case pass rate = 0.8000、Recall@3 = 0.9000、stale leakage rate = 0.1667；`copilot_conflict_cases.json` conflict accuracy = 0.8857、stale leakage rate = 0.0000、evidence coverage = 1.0000。结论：冲突更新和旧值泄漏已达 MVP 指标；recall stale leakage 接近但仍略高于 0.1500 目标，真实飞书扩样和 productized live gate 仍是残余风险。

> **Recall stale leakage 收口更新（2026-05-01）**：本轮继续补充 subject normalization 和 override intent 规则，覆盖容器编排、数据库选型、日志格式、覆盖率、看板列、发布策略和跨主题周报/前端干扰；同时把“旧值出现在明确拒绝/回退理由中”从 stale leak 误报中排除。使用 `EMBEDDING_PROVIDER=deterministic` 重跑 `copilot_recall_cases.json` 后，case pass rate = 0.9250、Recall@3 = 0.9250、Evidence Coverage = 0.9500、stale leakage rate = 0.0000。剩余失败为组合式答案/跨语言 evidence 聚合能力，不再是旧值泄漏。

> **组合式 search 摘要更新（2026-05-01）**：本轮补充 composite search result，用于“格式 + 位置”“规范 + 组件要求”这类需要多条 active memory 共同回答的查询，并补跨语言 query expansion。使用 `EMBEDDING_PROVIDER=deterministic` 重跑 `copilot_recall_cases.json` 后，case pass rate = 1.0000、Recall@3 = 1.0000、Evidence Coverage = 1.0000、stale leakage rate = 0.0000。

> **Conflict stress pack 收口更新（2026-05-01）**：本轮继续补充 CI 并行度、API 超时、缓存策略、备份策略和部署参数 subject 规则，修正 conflict stress pack 的剩余口径漂移。使用 `EMBEDDING_PROVIDER=deterministic` 重跑 `copilot_conflict_cases.json` 后，case pass rate / conflict accuracy = 1.0000，stale leakage rate = 0.0000，Evidence Coverage = 1.0000。

> **Prefetch stress pack 收口更新（2026-05-01）**：本轮把 `copilot_prefetch_cases.json` 扩到 20 条，覆盖模糊任务、空上下文、优先级排序和 superseded 旧值过滤；同时修正空上下文 case 的 benchmark 判定口径。使用 `EMBEDDING_PROVIDER=deterministic` 重跑后，case pass rate = 1.0000、context-required case = 18、Agent Task Context Use Rate = 1.0000、Evidence Coverage = 1.0000、Stale Leakage = 0.0000。

> **UX-05 更新（2026-04-29）**：本轮把 `heartbeat.review_due` 收敛为可控提醒体验，仍只生成 reminder candidate，不做真实群推送，不自动 active。`copilot_heartbeat_cases.json` 扩到 20 条，并新增 False Reminder Rate、Duplicate Reminder Rate、User Confirmation Burden 三个 UX 指标；本地重跑结果为 case pass rate = 1.0000、误提醒率 0.0000、敏感泄漏率 0.0000、重复提醒率 0.0000、用户确认负担 4.0000。

> **UX-06 更新（2026-04-29）**：本轮新增 `benchmarks/copilot_real_feishu_cases.json` 作为脱敏真实表达样本评测入口，覆盖口语、含糊、多轮改口、闲聊误判和权限场景各 5 条。2026-05-03 修复 CI 工具改口 stable key、current_value 归一化、低价值闲聊 guard、source revoked 权限解释、冲突候选审核解释、搜索结果解释和自然语言 prefetch 收口路由后，本地重跑结果为 case pass rate = 1.0000、Recall@3 = 1.0000、误记率 0.0000、误提醒率 0.0000、确认负担 2.0000、解释覆盖率 1.0000、旧值泄漏率 0.0000。该集合是人工脱敏样本和当前 baseline 标注，不是生产真实用户稳定可用结论；后续继续扩样而不是把 25 条样本当成生产证明。

> **UX-06 quality gate 更新（2026-05-03）**：新增 `scripts/check_real_feishu_expression_quality_gate.py --json`，把真实表达样本的 Recall@3、误记率、误提醒率、解释覆盖率和旧值泄漏率变成 pre-live 本地硬门禁。当前 gate 已通过：旧值泄漏率 0.0000，其他硬阈值也通过；这仍只是脱敏样本的 pre-live 本地门禁，不是真实 Feishu live evidence 或 productized live 证明。

> **真实挑战集更新（2026-05-04）**：新增 `benchmarks/copilot_realistic_recall_challenge.json` 和 `scripts/check_realistic_recall_challenge_gate.py --json`。这组 benchmark 不再按 case 各自创建小数据库，而是把 60 条共享语料事件和 80 条查询放进同一个 temp DB，让当前结论、旧值、相似项目、不同来源、拒答问题和权限负例共同竞争。当前 gate 通过的是“挑战集有效性和最低质量线”：case pass rate = 0.5750、Recall@3 = 0.7500、MRR = 0.7417、Evidence Coverage = 0.7500、Evidence Source Accuracy = 0.9500、Abstention Accuracy = 0.3333、Permission Negative Accuracy = 1.0000、Distractor Leakage Rate = 0.2000、Stale Leakage Rate = 0.5000。这个结果刻意暴露 `vector_miss`、`distractor_leakage`、`no_answer_failed` 三类短板；不能和旧 fixture 的 100% 混写成生产真实用户稳定性。

> **Benchmark 扩样更新（2026-05-05）**：本轮按“更真实、样例更多”的要求扩充两条主评测入口。`copilot_real_feishu_cases.json` 从 25 条扩到 40 条，口语、含糊、多轮改口、闲聊误判、权限场景各 8 条；`scripts/check_real_feishu_expression_quality_gate.py --json` 仍通过：case pass rate = 1.0000、Recall@3 = 1.0000、误记率 0.0000、误提醒率 0.0000、解释覆盖率 1.0000、旧值泄漏率 0.0000。`copilot_realistic_recall_challenge.json` 从 60 条共享语料 / 80 query 扩到 80 条共享语料 / 125 query，新增跨来源佐证、撤权、错别字、跨语言、completion standard、更多拒答和权限负例；`scripts/check_realistic_recall_challenge_gate.py --json` 通过新的规模阈值：case pass rate = 0.6000、Recall@3 = 0.7065、MRR = 0.6649、Evidence Coverage = 0.7065、Evidence Source Accuracy = 0.9239、Abstention Accuracy = 0.6667、Permission Negative Accuracy = 1.0000、Distractor Leakage Rate = 0.1957、Stale Leakage Rate = 0.3333。失败类型仍保留为 hardening backlog：`vector_miss` 26、`distractor_leakage` 18、`no_answer_failed` 6；这说明 benchmark 更真实了，但仍不是生产真实用户稳定性证明。

> **UX-07 更新（2026-04-29，2026-05-05 校准）**：10 分钟评委体验包入口为 `docs/judge-10-minute-experience.md`。评委版只引用本报告已有 runner 和 UX-06 指标，不重复跑重 benchmark；讲法必须同时展示通过项和残余风险，尤其是 UX-06 真实表达样本当前 40 条全部通过但仍只是脱敏 pre-live gate，以及真实 Feishu live evidence 仍未覆盖全链路。

## 先看这个

1. 这份报告证明 Copilot MVP 已经有可复现的评测入口，不只是“看起来能用”。
2. 本轮覆盖 recall（历史决策召回）、candidate（待确认记忆识别）、conflict（冲突更新）、layer（分层召回）、prefetch（任务前上下文包）、heartbeat（主动提醒候选）六类能力。
3. 今天不追求最终指标冲高，先保证每个 PRD 指标都有输入字段、输出字段、失败分类和可复现命令。
4. Bitable Benchmark Results 已有 dry-run 字段承载这些指标；今天不真实写飞书生产表。
5. 历史更新记录保留为过程证据；当前对外以“复赛三类证明”和最新重跑结果为准。难例不能为了保持好看指标被删除，必须继续作为失败分类和回归样本保留。

## 复赛三类证明

评委现场不需要看七类 runner 的内部细节。复赛材料把 benchmark 收敛成三类赛题证明：

| 赛题证明 | 使用哪些 runner | 对外指标 | 当前结果 | 说明 |
|---|---|---|---|---|
| 抗干扰测试 | `copilot_recall_cases.json`、`copilot_layer_cases.json`、`copilot_real_feishu_cases.json`、`copilot_realistic_recall_challenge.json` | Recall@3、Evidence Coverage、Stale Leakage Rate、Real Expression Recall@3、Abstention Accuracy、Distractor Leakage Rate | 旧 fixture recall 40/40、Recall@3 1.0000；真实表达样本 40/40 通过；真实挑战集 125 queries：case pass rate 0.6000、Recall@3 0.7065、Abstention Accuracy 0.6667、Distractor Leakage 0.1957 | 旧 fixture 证明功能回归；真实挑战集证明共享语料竞争下仍有可复现短板，尤其是语义改写、相似干扰和拒答 |
| 矛盾更新测试 | `copilot_conflict_cases.json`、`memory.explain_versions` 对应样例 | Conflict Update Accuracy、Superseded Leakage、Evidence Coverage | conflict 35/35、Conflict Accuracy 1.0000、Superseded Leakage 0.0000、Evidence Coverage 1.0000 | 证明新结论确认后旧值进入 superseded，默认 search / prefetch 不把旧值当当前答案 |
| 效能验证 | `copilot_prefetch_cases.json`、`copilot_candidate_cases.json`、`copilot_heartbeat_cases.json` | Agent Task Context Use Rate、Candidate Precision、False Reminder Rate、Duplicate Reminder Rate、Sensitive Reminder Leakage Rate | prefetch 20/20、candidate 57/57、heartbeat 20/20；误提醒、重复提醒和敏感泄漏均为 0.0000 | 证明 Agent 做任务前能拿到 compact context pack，低价值内容不乱记，提醒受控且可审计 |

当前不要把 `Steps Saved` 或 `Time-to-Answer` 写成自动化硬指标。它们适合作为 10 分钟评委体验包里的人工计时观察：评委不需要翻群聊、不需要复制内部 ID，就能完成搜索、确认、版本解释和 prefetch。除非后续补计时 runner 或手动测试记录，否则对外硬指标只使用上表已由 runner 覆盖的指标。

## 可复现实验命令

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json --json-output reports/copilot_recall.json --csv-output reports/copilot_recall.csv
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json --json-output reports/copilot_candidate.json --csv-output reports/copilot_candidate.csv
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json --json-output reports/copilot_conflict.json --csv-output reports/copilot_conflict.csv
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json --json-output reports/copilot_layer.json --csv-output reports/copilot_layer.csv
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json --json-output reports/copilot_prefetch.json --csv-output reports/copilot_prefetch.csv
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json --json-output reports/copilot_heartbeat.json --csv-output reports/copilot_heartbeat.csv
python3 -m memory_engine benchmark run benchmarks/copilot_real_feishu_cases.json --json-output reports/copilot_real_feishu.json --csv-output reports/copilot_real_feishu.csv
python3 scripts/check_real_feishu_expression_quality_gate.py --json
python3 -m memory_engine benchmark run benchmarks/copilot_realistic_recall_challenge.json --json-output reports/copilot_realistic_recall_challenge.json --csv-output reports/copilot_realistic_recall_challenge.csv
python3 scripts/check_realistic_recall_challenge_gate.py --json
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

`reports/` 是本地运行证据目录，默认不提交。提交物里保留本报告和 benchmark case 文件。

## PRD 指标映射

| PRD 指标 | 本轮入口 | 当前结果 | MVP 目标 | 结论 |
|---|---|---:|---:|---|
| Recall@3 | `copilot_recall_cases.json` | 1.0000（2026-05-01 重跑） | >= 0.6000 | 通过；case pass rate = 1.0000 |
| Conflict Update Accuracy | `copilot_conflict_cases.json` | 1.0000（2026-05-01 重跑） | >= 0.7000 | 通过 |
| Evidence Coverage | recall / conflict / layer / prefetch | recall 1.0000；conflict 1.0000；prefetch 1.0000（2026-05-01 重跑） | >= 0.8000 | 当前重跑入口通过 |
| Candidate Precision | `copilot_candidate_cases.json` | 1.0000 | >= 0.6000 | 通过 |
| Agent Task Context Use Rate | `copilot_prefetch_cases.json` | 1.0000（20 cases；18 context-required cases；2026-05-01 重跑） | >= 0.7000 | 通过 |
| L1 Hot Recall p95 | `copilot_layer_cases.json` | 1.602 ms | 先记录，不设硬阈值 | 已有入口 |
| Sensitive Reminder Leakage Rate | `copilot_heartbeat_cases.json` | 0.0000 | 0.0000 | 通过 |
| False Reminder Rate | `copilot_heartbeat_cases.json` | 0.0000（2026-04-29 重跑） | <= 0.1000 | 通过 |
| Duplicate Reminder Rate | `copilot_heartbeat_cases.json` | 0.0000（2026-04-29 重跑） | <= 0.1000 | 通过 |
| User Confirmation Burden | `copilot_heartbeat_cases.json` | 4.0000（2026-04-29 重跑） | 先记录，不设硬阈值 | 已有口径 |
| Stale Leakage Rate | recall / conflict / layer / prefetch | recall 0.0000；conflict 0.0000；prefetch 0.0000（2026-05-01 重跑） | <= 0.1500 | 当前重跑入口通过 |
| User Explanation Coverage | search / explain_versions / permission denied card payload | 已有单测入口，runner 暂未汇总 | 先记录，不设硬阈值 | 已有口径 |
| Unauthorized Value Leakage Rate | permission denied card payload | 0.0000（单测覆盖） | 0.0000 | 已有口径 |
| Real Expression Recall@3 | `copilot_real_feishu_cases.json` | 1.0000（40 cases；2026-05-05 gate 重跑） | >= 0.8000 | 当前样本通过 |
| Real Expression False Memory Rate | `copilot_real_feishu_cases.json` | 0.0000（40 cases；2026-05-05 gate 重跑） | <= 0.0500 | 当前样本通过 |
| Real Expression False Reminder Rate | `copilot_real_feishu_cases.json` | 0.0000（40 cases；2026-05-05 gate 重跑） | <= 0.0500 | 当前样本通过 |
| Real Expression Confirmation Burden | `copilot_real_feishu_cases.json` | 2.0000（40 cases；2026-05-05 gate 重跑） | 先记录，不设硬阈值 | UX-06 样本入口 |
| Real Expression Explanation Coverage | `copilot_real_feishu_cases.json` | 1.0000（40 cases；2026-05-05 gate 重跑） | >= 0.8000 | 当前样本通过 |
| Real Expression Old Value Leakage Rate | `copilot_real_feishu_cases.json` | 0.0000（40 cases；2026-05-05 gate 重跑） | 0.0000 | 当前样本通过 |
| Realistic Challenge Recall@3 | `copilot_realistic_recall_challenge.json` | 0.7065（125 queries；2026-05-05 gate 重跑） | >= 0.6000 | 通过最低线；不是生产质量证明 |
| Realistic Challenge Abstention Accuracy | `copilot_realistic_recall_challenge.json` | 0.6667（2026-05-05 gate 重跑） | >= 0.3000 | 通过最低线，仍保留 no-answer 失败样例 |
| Realistic Challenge Distractor Leakage Rate | `copilot_realistic_recall_challenge.json` | 0.1957（2026-05-05 gate 重跑） | <= 0.2500 | 通过最低线但仍有 18 条 distractor leakage |
| Realistic Challenge Permission Negative Accuracy | `copilot_realistic_recall_challenge.json` | 1.0000（15 permission-negative queries；2026-05-05 gate 重跑） | 1.0000 | 通过 |

## 分项结果

| benchmark | 样例数 | 通过率 | 核心指标 | 失败分类 |
|---|---:|---:|---|---|
| copilot_recall | 40 | 1.0000 | Recall@3 = 1.0000；Evidence Coverage = 1.0000；Stale Leakage = 0.0000 | 无失败 |
| copilot_candidate | 57 | 1.0000 | Candidate Precision = 1.0000；candidate_not_detected = 0；false_positive_candidate = 0 | 无失败 |
| copilot_conflict | 35 | 1.0000 | Conflict Accuracy = 1.0000；Superseded Leakage = 0.0000；Evidence Coverage = 1.0000 | 无失败 |
| copilot_layer | 40 | 1.0000 | Layer Accuracy = 1.0000；L1 Hot Recall p95 = 1.602 ms | 无失败 |
| copilot_prefetch | 20 | 1.0000 | Context-required cases = 18；Agent Task Context Use Rate = 1.0000；Evidence Coverage = 1.0000；Stale Leakage = 0.0000 | 无失败 |
| copilot_heartbeat | 20 | 1.0000 | Reminder Candidate Rate = 1.0000；Sensitive Reminder Leakage Rate = 0.0000；False Reminder Rate = 0.0000；Duplicate Reminder Rate = 0.0000；User Confirmation Burden = 4.0000 | 无失败 |
| copilot_real_feishu | 40 | 1.0000 | Recall@3 = 1.0000；误记率 = 0.0000；误提醒率 = 0.0000；确认负担 = 2.0000；解释覆盖率 = 1.0000；旧值泄漏率 = 0.0000 | 无失败 |
| copilot_realistic_recall_challenge | 125 | 0.6000 | Recall@3 = 0.7065；MRR = 0.6649；Evidence Coverage = 0.7065；Evidence Source Accuracy = 0.9239；Abstention Accuracy = 0.6667；Permission Negative Accuracy = 1.0000；Distractor Leakage = 0.1957；Stale Leakage = 0.3333 | `vector_miss` 26；`distractor_leakage` 18；`no_answer_failed` 6 |
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
| heartbeat | `heartbeat_no_trigger_noisy_1` / `heartbeat_no_trigger_noisy_2` | 闲聊天气和午餐不应触发 reminder candidate | False Reminder Rate 计入 0.0000 |
| heartbeat | `heartbeat_cooldown_dedup_1` / `heartbeat_cooldown_dedup_2` | cooldown 内同类提醒不能重复打扰 | Duplicate Reminder Rate 计入 0.0000 |
| heartbeat | `heartbeat_sensitive_password_redaction_1` / `heartbeat_sensitive_private_key_redaction_2` / `heartbeat_sensitive_oauth_token_redaction_3` | password、私钥路径、OAuth token 不能出现在 reminder 输出中 | Sensitive Reminder Leakage Rate 保持 0.0000 |

## UX-06 真实表达样本

`benchmarks/copilot_real_feishu_cases.json` 是本轮新增的真实用户表达样本集。它采用脱敏、可提交的人工样本，不包含真实 `chat_id`、`open_id`、token 或敏感业务内容。每条样本都包含：

- 用户输入。
- 上下文，包括来源类型、脱敏 source id、thread topic 和必要的上一轮消息。
- 期望 intent。
- 期望是否进入记忆或候选。
- 权限预期。
- 当前 baseline 观察值。
- 失败 debug hint。

样本规模：

| 类型 | 数量 | 关注点 |
|---|---:|---|
| 口语 | 8 | “上次说的”“那个”“来着”“长跑窗口”等自然表达能否召回 Top 3 并解释 |
| 含糊 | 8 | 代词、缺 thread_topic、多入口并存或人称指代不足时是否要求补充，而不是乱记 |
| 多轮改口 | 8 | “不对”“收回”“不是旧群”等先进入 review policy；冲突更新不直接覆盖 active，必须经人工确认后才替换当前结论 |
| 闲聊误判 | 8 | 玩笑、临时状态、显式“别记”和未定 UI 想法不应误记或误提醒 |
| 权限场景 | 8 | 私聊、跨租户、跨 org、非 reviewer、source revoked、missing permission 必须 fail closed |

当前边界：

- 这是 fixture benchmark 与真实表达样本的连接层，不是生产真实用户稳定可用结论。
- `observed_baseline` 是当前本地能力的标注，用于让 runner 计算 UX 指标和暴露失败类别。
- 难例必须保留，例如含糊上下文和改口样例，不为了好看的 pass rate 删除或简化。
- 真实飞书来源先进入 review policy；低风险安全内容可自动确认，多轮改口、重要、敏感或冲突内容不会自动覆盖 active memory。
- 本报告不宣称真实 Feishu DM 到本项目 `fmc_*` / `memory.*` live E2E 或 productized live 已完成。

## UX-07 评委讲法

10 分钟评委体验包只把 benchmark 当成“可复现证据和风险入口”，不把它讲成生产质量保证。

| 现场问题 | 评委版回答 |
|---|---|
| 你们怎么证明不是临场 demo？ | 每条演示能力都能映射到 `benchmarks/copilot_*_cases.json` 和本文档的指标表；`reports/` 只是本地运行证据，不提交。 |
| 指标是不是全部达标？ | 本地 runner 当前通过：recall、candidate、conflict、layer、prefetch、heartbeat 和 UX-06 脱敏样本都已达当前门槛；但这不能外推为生产真实用户稳定可用、长期 live 或全量 workspace ingestion 已完成。 |
| 真实用户表达覆盖了吗？ | UX-06 有 40 条脱敏样本，覆盖口语、含糊、多轮改口、闲聊误判和权限场景各 8 条；这是 baseline，不是生产稳定结论。 |
| 安全边界是什么？ | 权限拒绝不能泄露未授权内容；真实飞书来源先过 review policy，重要/敏感/冲突内容停在 candidate；reminder 只生成 candidate；不宣称 production live 或真实 DM 到 `fmc_*` / `memory.*` live E2E 已完成。 |

评委现场若没有时间跑 benchmark，只展示本报告和以下命令即可：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_real_feishu_cases.json --json-output reports/copilot_real_feishu.json --csv-output reports/copilot_real_feishu.csv
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json --json-output reports/copilot_heartbeat.json --csv-output reports/copilot_heartbeat.csv
```

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

2026-04-29 重跑已有失败样例；后续不要为了保持 100% 指标删除难例，应按上表归因并修复。

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
| False Reminder Rate | 不该提醒的闲聊、午餐、天气等低价值内容不能进入 reminder candidate | `heartbeat_no_trigger_noisy_1`、`heartbeat_no_trigger_noisy_2` |
| Duplicate Reminder Rate | 同一 subject / trigger 在 cooldown、snooze 或 mute 后不能重复打扰 | `heartbeat_cooldown_dedup_1`、`heartbeat_cooldown_dedup_2` |
| User Confirmation Burden | 每条 reminder candidate 暴露给用户的可控动作数量，用于衡量确认负担 | `heartbeat_*` 输出中的 `actions` 数量 |
| Stale Leakage Rate | superseded 旧值可以用于解释版本链，但不能出现在默认 search / prefetch 当前上下文中 | `copilot_recall_multi_turn_deadline_override_002`、`prefetch_stale_value_filtered` |
| User Explanation Coverage | 默认搜索、版本解释和权限拒绝都应该有用户能读懂的原因说明，而不是只展示 trace、request_id 或内部字段 | `tests.test_feishu_interactive_cards` 覆盖搜索卡 `rank_reason` / `explanation`、版本卡 `user_explanation` 和 denied redaction；后续需要把该指标接入 benchmark runner |
| Unauthorized Value Leakage Rate | permission denied 输出不能泄露未授权 `current_value`、`summary` 或 `evidence` 明文 | `tests.test_feishu_interactive_cards` 覆盖 version-chain denied card；后续需要扩到 search/prefetch/card action 真实样本 |

## UX-03 解释层指标口径

2026-04-29 补充：UX-03 已补用户解释层出口，当前先把口径写入报告，不把它夸大成完整复赛级 UX benchmark。

| 指标 | 定义 | 当前证据 | 残余风险 |
|---|---|---|---|
| User Explanation Coverage | 用户主内容中能解释当前结论、证据来源、版本覆盖或权限拒绝原因的样例占比 | `tests.test_feishu_interactive_cards` 验证 search result payload、version chain payload/card 和 permission denied card | 现有 `memory_engine benchmark run` 仍主要评测 recall/conflict，不自动汇总解释覆盖率 |
| Unauthorized Value Leakage Rate | permission denied payload/card 中出现未授权 `current_value`、`summary`、`evidence.quote` 明文的比例 | version-chain denied card 单测用敏感字段注入，渲染结果不包含这些明文 | 还需要在 UX-06 真实表达样本里扩到更多入口和更多权限失败原因 |
| Stale / Superseded Leakage Rate | 旧值可出现在 `memory.explain_versions` 版本链解释里，但不能出现在默认 search / prefetch 当前答案里 | recall、conflict、prefetch benchmark 已有 stale/superseded 检查；搜索卡明确标记旧值已过滤 | 样例规模仍小，真实飞书表达扩样后可能暴露新的归一化或含糊上下文缺口 |

## Bitable Dry-Run 对齐

`memory_engine/bitable_sync.py` 的 `Benchmark Results` 已扩展以下字段，能承载 2026-05-03 指标：

- `benchmark_type`
- `recall_at_3`
- `candidate_precision`
- `candidate_recall`
- `agent_task_context_use_rate`
- `l1_hot_recall_p95_ms`
- `sensitive_reminder_leakage_rate`
- `false_reminder_rate`
- `duplicate_reminder_rate`
- `user_confirmation_burden`
- `failure_type_counts`
- `recommended_fix_summary`

真实写飞书生产表不是今天阻塞项。今天只要求 dry-run payload 能展示字段，避免把评测结果锁死在本地日志里。

## 当前局限

- 样例规模仍是 MVP / 产品化打磨级：recall 40 条、candidate 57 条、conflict 35 条、layer 40 条、prefetch 20 条、heartbeat 20 条、real_feishu 40 条、realistic shared-corpus 80 条语料 / 125 个 query。适合证明链路和暴露短板，不代表最终复赛级压力测试或生产稳定性。
- `reports/` 的 JSON / CSV 是本地运行证据，没有提交；评委材料优先读本报告和可复现命令。
- Cognee optional recall channel 在这些本地 benchmark 中显示为 unavailable；本报告验证的是 Copilot runner、状态机、hybrid retrieval、prefetch 和 heartbeat dry-run。真实 Cognee / Ollama embedding 已由 Phase D live gate 单独验证，不把本 benchmark 报告写成长期 embedding 服务证明。
- heartbeat 仍是 reminder candidate / dry-run，不真实发群，不绕过治理层自动写 active memory；UX-05 只补确认有用、忽略、延后、关闭同类提醒的可控动作、冷却状态和审计口径。
- Bitable 仍是展示和审核面，不是 source of truth。
- UX-03 的解释覆盖率和旧值泄漏率已经有测试口径，但尚未成为所有 benchmark runner 的汇总指标；当前不能说“解释体验全部达标”，只能说 search、version chain、permission denied 的关键出口已补齐。

## 下一步

2026-05-04 Demo runbook、OpenClaw examples 和 `scripts/demo_seed.py` 已完成；2026-05-05《Memory 定义与架构白皮书》也已完成。后续不要再按旧日期 implementation plan 继续执行，本报告作为历史评测证据；新的 Benchmark 扩展应围绕产品化 Phase A-E 的 storage/audit、runtime、staging、embedding 和 QA 缺口展开。
