# Deep Research Improvement Backlog

日期：2026-05-01
来源：仓库根目录 `deep-research-report.md`
阶段：OpenClaw-native Feishu Memory Copilot 稳定性与口径收敛

## 先看这个

1. 本清单不是新的产品主控文档；事实源仍以 `README.md`、`full-copilot-next-execution-doc.md` 和当前代码为准。
2. 本清单只把深研报告里的建议转成可执行事项，优先处理本地可验证的稳定性、benchmark 和文档口径问题。
3. 任何真实飞书、OpenClaw gateway 或 productized live 相关事项，必须继续按受控 sandbox / pre-production 边界描述，不能写成生产长期运行。

## 改进事项总览

| 优先级 | 事项 | 为什么要做 | 可本地完成 | 完成标准 |
|---|---|---|---|---|
| P0 | 统一对外指标口径 | 深研报告指出 README、白皮书、PRD audit 和 benchmark report 对 recall/conflict 的乐观程度不一致，评委会质疑自证可信度 | 是 | 已同步 README、docs/README、benchmark report 和 UX todo；受控真实 Feishu Task smoke 后已更新，不宣称生产长期运行 |
| P0 | 降低旧值泄漏和冲突更新风险 | recall / conflict 扩样暴露 stale leakage 与 conflict accuracy 风险，这是“记得住、改得对”的核心 | 部分可本地完成 | recall / conflict 主 benchmark 已达标；2026-05-03 新增真实表达 pre-live 质量 gate 后发现 `old_value_leakage_rate=0.1429`，仍需修复旧 Jenkins 等真实表达泄漏样例 |
| P0 | 让 retrieval 分数可调、可解释 | 当前 keyword、vector、evidence、layer bonus 和 hot threshold 写死，排障时难解释旧值为何排前 | 是 | 已完成：集中 scoring config、`why_ranked.score_breakdown` 和 benchmark `score_breakdown_summary` |
| P1 | 建立稳定 memory key / alias 设计 | 只靠 `normalized_subject` 容易把同一业务槽位拆散，影响冲突识别 | 是 | 已完成设计与首版实现：`memory_engine/copilot/stable_keys.py`，通过 raw event metadata 承载，不做 schema migration |
| P1 | 扩大 contradiction stress pack | 评委最容易追问自然表达、跨天改口、多人冲突和旧值过滤 | 是 | 已整理 35 条 conflict stress pack；runner 支持 confirm/reject 分支、stable key 输出和 forbidden-value 否定语境 |
| P1 | 把图谱用于 review target / prefetch | 当前图谱已登记群/用户/消息拓扑，但产品价值还没有充分体现在主路径 | 部分可本地完成 | 已完成 review target 最小闭环：review inbox 会从 Feishu chat membership 图谱补充 `graph_review_targets`，参与 mine 视图过滤；prefetch 已返回 `graph_context`，并通过 20 条 prefetch stress pack：case pass rate = 1.0000、stale leakage = 0.0000 |
| P1 | OpenClaw runtime 体验前推 | 深研报告建议对齐 interactive handler / memory supplement，但这依赖 OpenClaw 能力和当前版本约束 | 需谨慎 | 先写设计和边界；不升级 OpenClaw；不宣称已完成 production integration |
| P2 | 工程收口 | 插件自动拉 dashboard、fetcher 重复 connect/init_db、coverage 门槛偏低都是产品化信号风险 | 是 | 已完成 embedding provider deterministic fallback 开关、vector unavailable fallback、graph review target 测试、OpenClaw 插件 dashboard 显式 opt-in；其他非阻塞清理保留后续 |
| P2 | 编译型知识层 | 把 active memory 编译成项目决策页或记忆卡册，增强比赛展示价值 | 是 | 已完成本地只读编译入口：`memory_engine/copilot/knowledge_pages.py` 和 `python3 -m memory_engine copilot-knowledge compile --markdown`；输出带 provenance、版本、open questions，不向量化 raw events、不写飞书 |

## 本轮执行拆分

| 子任务 | 子代理/执行者 | 写入范围 | 当前状态 |
|---|---|---|---|
| retrieval score breakdown 与旧值泄漏诊断 | 子代理 1 | `memory_engine/copilot/retrieval.py`、`memory_engine/benchmark.py`、相关测试 | 完成 |
| deep research 改进 backlog 文档 | 主线程 | `docs/productization/deep-research-improvement-backlog.md` | 完成 |
| 文档入口同步 | 主线程 | `docs/README.md`、`README.md`、`docs/benchmark-report.md`、UX todo | 完成 |
| stable memory key / alias 设计与首版实现 | 主线程 | `docs/productization/`、`memory_engine/copilot/`、相关测试 | 完成 |
| 真实飞书扩样 gate | 主线程 | `docs/productization/real-feishu-controlled-expansion-checklist.md`、`scripts/check_real_feishu_expansion_gate.py`、`memory_engine/feishu_task_fetcher.py` | 完成 readiness gate；完成 1 条受控真实 Feishu Task fetch -> candidate smoke，读回 evidence 与 audit |
| productized live 小 gate | 主线程 | `docs/productization/audit-read-only-live-gate.md` | 完成，选择 audit read-only view |
| 编译型知识层 | 主线程 | `memory_engine/copilot/knowledge_pages.py`、`tests/test_copilot_knowledge_pages.py`、CLI | 完成，本地 Markdown/JSON 生成，不写飞书 |

## 本轮不做

- 只接受控真实飞书测试资源；不提交真实 `chat_id`、`open_id`、token 或日志。
- 不把受控 sandbox、fixture benchmark、dry-run、单次真实 DM 证据写成生产长期运行。
- 不删除 benchmark 失败样例来提高指标。
- 不升级 OpenClaw，不安装 latest。
- 不切换 Cognee 选型。

## 验证建议

文档-only 改动：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

触达 retrieval、benchmark 或 Copilot 代码时追加：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_benchmark
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
```
