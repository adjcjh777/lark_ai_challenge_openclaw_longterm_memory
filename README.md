# Feishu Memory Copilot

## 今天先做这个：我的任务

从 2026-04-27 起，本项目按程俊豪单人执行；原先拆出去的评测、文案、QA 和检查任务都并入我的补充任务。打开 GitHub 首页时先看这里，再进入当天计划。

当前主线已经升级为 **完整产品推进路线**：先保护初赛提交闭环，再补齐产品化契约，最后按阶段推进 OpenClaw live bridge、Feishu review surface、有限飞书 ingestion、heartbeat、healthcheck 和 Product QA。这里的“完整产品”不是零散 demo，也不是一上来做完整企业后台，而是按 PRD 做一个可用、可复现、可治理、可审计的 OpenClaw-native Feishu Memory Copilot。

| 当前任务 | 直接入口 | 交付物 | 完成标准 |
|---|---|---|---|
| 2026-04-28 PRD 完成度核对与未完成任务拆分 | [PRD completion audit and gap tasks](docs/productization/prd-completion-audit-and-gap-tasks.md)；[Feishu Memory Copilot PRD](docs/feishu-memory-copilot-prd.md)；[2026-05-08 handoff](docs/plans/2026-05-08-demo-readiness-handoff.md) | 回答 MVP 是否完成、是否接入飞书、是否接入 OpenClaw 做产品形态测试，并把未完成任务拆成可执行清单 | 明确区分 demo/pre-production、受控测试群 live sandbox 和 productized live；未完成项有负责人、位置、截止建议和完成标准 |
| Feishu 测试群 live sandbox：用旧测试群承载新的 Memory Copilot | [start_copilot_feishu_live.sh](scripts/start_copilot_feishu_live.sh)；[feishu_live.py](memory_engine/copilot/feishu_live.py)；[test_copilot_feishu_live.py](tests/test_copilot_feishu_live.py)；[2026-05-08 handoff](docs/plans/2026-05-08-demo-readiness-handoff.md) | 飞书真实群消息 -> `copilot-feishu listen` -> `handle_tool_request()` -> `CopilotService` -> bot 回复 | 旧测试群只作为真实环境容器；启动时解析该群为 allowlist；reviewer 不默认 `*`；`/remember` 进入 candidate；`/confirm` 后才 active；普通 @ 提问触发 `memory.search`；回复包含 request_id / trace_id；仍不是生产部署、全量 Feishu workspace ingestion 或 productized live |
| 2026-05-08 Demo-ready + Pre-production Readiness：本地演示前一键检查 | [2026-05-08 Ralph plan](docs/plans/2026-05-08-ralph-plan-demo-readiness.md)；[2026-05-08 handoff](docs/plans/2026-05-08-demo-readiness-handoff.md)；[check_demo_readiness.py](scripts/check_demo_readiness.py)；[demo_seed.py](scripts/demo_seed.py)；[test_demo_readiness.py](tests/test_demo_readiness.py)；[test_demo_seed.py](tests/test_demo_seed.py) | 聚合 OpenClaw 版本、Phase 6 healthcheck、Demo replay step-level、provider configuration-only 检查 | `python3 scripts/check_demo_readiness.py` 和 `--json` 可运行；Demo replay 每个 step 都是 `ok=true`；任一 step 失败会让 readiness 整体失败；仍不是生产部署、真实飞书推送、完整 audit migration 或 productized live |
| Phase 6 Deployability + Healthcheck 已完成本地闭环：只做可检查、可初始化、可诊断 | [2026-05-07 handoff](docs/plans/2026-05-07-handoff.md)；[check_copilot_health.py](scripts/check_copilot_health.py)；[healthcheck.py](memory_engine/copilot/healthcheck.py)；[test_copilot_healthcheck.py](tests/test_copilot_healthcheck.py)；[memory_tools.schema.json](agent_adapters/openclaw/memory_tools.schema.json) | Phase 6 healthcheck 命令、可读输出、JSON 输出、OpenClaw/schema/service/storage/permission/Cognee/embedding 检查、search/permission deny/candidate review smoke test | `python3 scripts/check_copilot_health.py` 可运行；schema/tool version 可见；storage schema 可检查但明确未做 tenant/audit migration；Cognee 使用 repository fallback；embedding 只做 configuration-only 检查；这不是生产部署、真实飞书推送或 productized live |
| Phase 5 Heartbeat Controlled Reminder 已完成本地闭环：active memory 只生成受控 reminder candidate（提醒候选） | [2026-05-07 handoff](docs/plans/2026-05-07-handoff.md)；[heartbeat.py](memory_engine/copilot/heartbeat.py)；[tools.py](memory_engine/copilot/tools.py)；[feishu_cards.py](memory_engine/feishu_cards.py)；[bitable_sync.py](memory_engine/bitable_sync.py)；[copilot_heartbeat_cases.json](benchmarks/copilot_heartbeat_cases.json) | `heartbeat.review_due` 工具入口、reason/evidence/target actor/cooldown/permission trace、敏感内容 redacted/withheld、card/Bitable dry-run 安全摘要 | active memory 能生成 candidate；不自动 active；不真实飞书群推送；不是生产调度服务；non-reviewer 看不到敏感 evidence/current_value；Sensitive Reminder Leakage Rate = 0 |
| Phase 4 Limited Feishu ingestion 已完成本地闭环：指定飞书来源只进入 candidate（待确认记忆）队列 | [2026-05-07 handoff](docs/plans/2026-05-07-handoff.md)；[完整产品 PRD](docs/productization/complete-product-roadmap-prd.md)；[完整产品测试规格](docs/productization/complete-product-roadmap-test-spec.md)；[Permission Contract](docs/productization/contracts/permission-contract.md)；[Audit Contract](docs/productization/contracts/audit-observability-contract.md)；[document_ingestion.py](memory_engine/document_ingestion.py)；[Phase 4 OpenClaw example](agent_adapters/openclaw/examples/limited_feishu_ingestion_candidate_only.json) | 指定来源 -> candidate pipeline、权限拒绝样例、candidate-only 证据、request_id/trace_id、source metadata、review surface 可审核 | 真实飞书来源不能自动 active；`document_feishu` 的 `auto_confirm=True` 会被忽略；无权限 actor 看不到未授权内容；这仍不是 productized live 或全量 Feishu workspace ingestion |
| Phase 3 Feishu UI / Review Surface 已完成本地闭环：card、Bitable dry-run 和 card action 消费 permission-aware service/tool output | [feishu_cards.py](memory_engine/feishu_cards.py)；[bitable_sync.py](memory_engine/bitable_sync.py)；[feishu_runtime.py](memory_engine/feishu_runtime.py)；[test_feishu_interactive_cards.py](tests/test_feishu_interactive_cards.py)；[test_bitable_sync.py](tests/test_bitable_sync.py) | Candidate Review card、Version Chain card、Bitable Candidate Review dry-run、permission denied 安全摘要、request_id/trace_id/permission_decision | approve/reject 通过 `CopilotService` / `handle_tool_request`；non-reviewer 被拒绝且 candidate 不变；未授权 payload 不展示 evidence/current_value；这仍不是 Feishu live ingestion |
| Phase 2 OpenClaw live bridge 已完成，用 OpenClaw/本地桥真实调用 permission-aware Copilot service | [memory_tools.schema.json](agent_adapters/openclaw/memory_tools.schema.json)；[tools.py](memory_engine/copilot/tools.py)；[test_copilot_tools.py](tests/test_copilot_tools.py)；[OpenClaw examples](agent_adapters/openclaw/examples/) | seed/local service bridge、permission-aware tool response、trace/request id、missing/malformed permission fail-closed demo | commit `cb21bc7` 已完成；OpenClaw 版本仍为 `2026.4.24`；`memory.*` 工具通过 service 调用；明确这不是 Feishu live ingestion |
| Phase 1 契约冻结和 Phase 2 权限前置实现已完成，可以作为下一步代码事实源 | [2026-05-07 产品化计划](docs/plans/2026-05-07-implementation-plan.md)；[Storage Contract](docs/productization/contracts/storage-contract.md)；[Permission Contract](docs/productization/contracts/permission-contract.md)；[OpenClaw Payload Contract](docs/productization/contracts/openclaw-payload-contract.md)；[Audit Contract](docs/productization/contracts/audit-observability-contract.md)；[Migration RFC](docs/productization/contracts/migration-rfc.md)；[Negative Permission Test Plan](docs/productization/contracts/negative-permission-test-plan.md)；[test_copilot_permissions.py](tests/test_copilot_permissions.py) | 六份契约文档、统一权限门控、负例测试、真实 Feishu doc fetch 前 fail closed | commit `a81be0c` 完成 Phase 1 contract freeze；commit `b6b17b4` 完成 permission pre-implementation；51 个专项测试和 124 个全量测试通过；飞书看板已同步 |
| Phase 0 / 0.5 已完成：保护初赛提交闭环，并把产品化基线路线落到仓库文档 | [2026-05-06 产品化计划](docs/plans/2026-05-06-implementation-plan.md)；[总控计划](docs/feishu-memory-copilot-implementation-plan.md)；[完整产品 PRD](docs/productization/complete-product-roadmap-prd.md)；[完整产品测试规格](docs/productization/complete-product-roadmap-test-spec.md) | README 顶部入口、总控计划、05-06/05-07 日期计划、产品化 PRD/Test Spec | 三大初赛交付物不被破坏；文档清楚区分 schema demo / dry-run / replay / OpenClaw live bridge / limited Feishu ingestion；Phase 1 Contract Freeze Gate 明确后才能进入代码实现或 `$team` 并行 |
| 2026-05-05 白皮书初稿已完成，作为 Phase 0 提交冻结证据 | [2026-05-05 handoff](docs/plans/2026-05-05-handoff.md)；[whitepaper](docs/memory-definition-and-architecture-whitepaper.md)；[demo-runbook.md](docs/demo-runbook.md)；[benchmark-report.md](docs/benchmark-report.md) | Memory 定义与架构白皮书可提交初稿 | 能回答 Define it / Build it / Prove it；没有把未完成 live 能力写成已完成 |
| 2026-05-04 Demo 固定和 README 快速开始已完成，作为 Phase 0 可复现证据 | [2026-05-04 handoff](docs/plans/2026-05-04-handoff.md)；[demo-runbook.md](docs/demo-runbook.md)；[demo_seed.py](scripts/demo_seed.py)；[OpenClaw examples](agent_adapters/openclaw/examples/) | 5 分钟 Demo runbook、OpenClaw examples、demo dry-run replay | 新读者能复现历史决策召回、冲突更新、prefetch 和 heartbeat dry-run；OpenClaw runtime 不稳时有 schema examples + CLI/dry-run 兜底 |
| 2026-05-03 Benchmark Report 和指标自证已完成，作为 Phase 0 评测证据 | [2026-05-03 handoff](docs/plans/2026-05-03-handoff.md)；[benchmark-report.md](docs/benchmark-report.md)；[benchmark.py](memory_engine/benchmark.py) | Copilot recall / candidate / conflict / layer / prefetch / heartbeat 指标报告 | Recall@3、Candidate Precision、Conflict Accuracy、Context Use、Sensitive Reminder Leakage Rate 等 PRD 指标有可复现命令和报告 |

飞书 AI 挑战赛 OpenClaw 赛道项目。当前主线已经从旧的 CLI-first / Bot-first memory demo 切换为 **OpenClaw-native Feishu Memory Copilot**。

## 当前状态

截至 2026-05-08 最新口径：2026-04-26 至 2026-05-05 已完成第一周 MVP 闭环、Benchmark Report、Demo 固定和 Memory 定义与架构白皮书初稿；2026-05-06/2026-05-07 已完成完整产品路线、Phase 1 契约冻结、Phase 2 权限前置实现、Phase 2 OpenClaw live bridge、Phase 3 Feishu UI / Review Surface、Phase 4 Limited Feishu ingestion、Phase 5 Heartbeat Controlled Reminder 和 Phase 6 Deployability + Healthcheck 本地闭环；2026-05-08 已追加 Demo-ready + Pre-production Readiness 聚合门禁，并把旧飞书测试群接成新的 Memory Copilot live sandbox：

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
- `benchmarks/copilot_prefetch_cases.json` 已有 6 条样例，`benchmarks/copilot_heartbeat_cases.json` 已有 7 条样例；prefetch runner 输出 Agent Task Context Use Rate，heartbeat runner 输出 Sensitive Reminder Leakage Rate，并覆盖非 reviewer 敏感提醒 withheld。
- `docs/benchmark-report.md` 已串联 recall、candidate、conflict、layer、prefetch、heartbeat 六类指标，报告包含失败分类、反例说明、PRD 指标映射和 Bitable Benchmark Results dry-run 字段说明。
- `docs/benchmark-report.md` 已加入 10 条证明力难例；当前 runner 样例为 recall 10 条、candidate 34 条、conflict 12 条、layer 15 条、prefetch 6 条、heartbeat 7 条，Phase 5 新增非 reviewer 敏感提醒 withheld 证明。
- `docs/demo-runbook.md` 已改成 OpenClaw-native 5 分钟演示脚本，覆盖 `memory.search`、`memory.explain_versions`、`memory.prefetch`、heartbeat reminder candidate 和 benchmark 收口。
- `scripts/demo_seed.py` 已固定 demo dry-run replay：默认使用临时 SQLite，不写飞书生产空间；可用 `--json-output reports/demo_replay.json` 生成本地演示证据。
- `agent_adapters/openclaw/examples/*.json` 已标注 copyable / schema demo 边界，并和 `memory_tools.schema.json` 的实际 search 输出字段对齐。
- `docs/memory-definition-and-architecture-whitepaper.md` 已完成初赛可提交初稿，覆盖 Define it / Build it / Prove it、架构边界、状态机、证据链、Demo/Benchmark 证明、局限和复赛路线。
- Phase 1 contract freeze 已完成：storage、permission、OpenClaw payload、audit、migration、negative permission test plan 均已落到 `docs/productization/contracts/`。
- Phase 2 权限前置实现已完成：`current_context.permission` 缺失或畸形会 fail closed；`memory.search/create_candidate/confirm/reject/explain_versions/prefetch` 都经过 `CopilotService` 统一权限门控；真实 Feishu document ingestion 在 fetch 前必须通过权限校验。
- Phase 2 OpenClaw live bridge 已完成：`handle_tool_request` 统一桥接 MVP `memory.*` 和 `heartbeat.review_due` 工具到 permission-aware `CopilotService`，返回 `bridge.request_id`、`bridge.trace_id` 和 `permission_decision`。
- Phase 3 Feishu UI / Review Surface 已完成本地闭环：Candidate Review card、Version Chain card、Bitable dry-run 和 Feishu card action 都消费 service/tool 输出；权限拒绝时只展示安全摘要，不泄露未授权 evidence/current_value。
- Phase 4 Limited Feishu ingestion 已完成本地闭环：指定 Feishu document source 在授权上下文下进入 candidate；source context document_id 不匹配会在 fetch 前 fail closed；candidate 带 evidence quote、source metadata 和 ingestion trace；真实飞书来源仍不会自动 active。
- Phase 5 Heartbeat Controlled Reminder 已完成本地闭环：active memory 只生成受控 reminder candidate，输出 reason、evidence、target actor、cooldown 和 permission trace；敏感内容对非 reviewer 只给 withheld/redacted payload；card/Bitable dry-run 不展示未授权 evidence/current_value。本阶段仍不真实推送飞书群消息，不做生产调度服务，也不写成 productized live。
- Phase 6 Deployability + Healthcheck 已完成本地闭环：`python3 scripts/check_copilot_health.py` 能输出可读摘要，`--json` 能输出 handoff 可复制 JSON；检查 OpenClaw 版本、Copilot service 初始化、OpenClaw schema/tool version、storage schema、permission fail-closed、Cognee adapter、embedding provider，以及 search / permission deny / candidate review smoke test。本阶段只做可检查性，不做生产部署、真实飞书推送、完整 audit migration 或 productized live。
- Demo readiness 已追加本地聚合入口：`python3 scripts/check_demo_readiness.py` 同时检查 OpenClaw version、Phase 6 healthcheck、Demo replay 每个 step 和 provider configuration-only 状态；`--json` 可输出机器可读报告。只要 Demo replay 任一 step `ok=false`，readiness 整体就会失败。
- Feishu 测试群 live sandbox 已追加：`python3 -m memory_engine copilot-feishu listen` 和 `scripts/start_copilot_feishu_live.sh` 监听真实测试群消息，但消息处理层只走 `memory_engine/copilot/feishu_live.py` -> `handle_tool_request()` -> `CopilotService`；旧 `memory_engine feishu listen` 只保留为 fallback。启动脚本默认把“Feishu Memory Engine 测试群”解析成群聊 allowlist，并把当前登录用户解析为 reviewer；真实 ID 不写入仓库。
- 已在旧测试群完成一次真实消息闭环：`/health` 返回 CopilotService live 状态，`/remember` 创建 candidate，`/confirm` 后 active，普通 @ 提问触发 `memory.search` 并返回 request_id、trace_id、hybrid retrieval trace。本能力是受控测试群联调，不是生产部署或全量 workspace ingestion。

## 10 分钟快速开始

先确认 OpenClaw 版本锁：

```bash
python3 scripts/check_openclaw_version.py
```

再运行 Phase 6 healthcheck。这个命令只做本地可检查性和 smoke test，不做真实飞书推送，也不触发真实 embedding 调用：

```bash
python3 scripts/check_copilot_health.py
python3 scripts/check_copilot_health.py --json
```

再运行 Demo readiness 聚合门禁。这个命令会顺手生成 `reports/demo_replay.json`，并检查每个 Demo step 是否为 `ok=true`：

```bash
python3 scripts/check_demo_readiness.py
python3 scripts/check_demo_readiness.py --json
```

如果只想生成本地 Demo replay，可以单独运行。这个命令默认用临时 SQLite，只写 `reports/demo_replay.json`，不会写真实飞书生产空间：

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

受控接入旧飞书测试群时运行新的 Copilot live sandbox。这个入口不是旧 Memory Engine handler；它把飞书消息路由到 `CopilotService` 和 OpenClaw memory tools：

```bash
python3 scripts/check_openclaw_version.py
# 可选：不设置时脚本会用 lark-cli user auth 解析“Feishu Memory Engine 测试群”和当前登录用户
export COPILOT_FEISHU_ALLOWED_CHAT_QUERY="Feishu Memory Engine 测试群"
# export COPILOT_FEISHU_ALLOWED_CHAT_IDS="oc_xxx"
# export COPILOT_FEISHU_REVIEWER_OPEN_IDS="ou_xxx"
scripts/start_copilot_feishu_live.sh
```

测试群中使用：

```text
@Feishu Memory Engine bot /health
@Feishu Memory Engine bot /remember 决定：Copilot live sandbox 验收口径是 candidate 先确认再 active
@Feishu Memory Engine bot /confirm <candidate_id>
@Feishu Memory Engine bot Copilot live sandbox 验收口径是什么？
```

查看 OpenClaw tools 契约和三条演示样例：

```bash
sed -n '1,220p' agent_adapters/openclaw/memory_tools.schema.json
sed -n '1,140p' agent_adapters/openclaw/examples/historical_decision_search.json
sed -n '1,180p' agent_adapters/openclaw/examples/conflict_update_flow.json
sed -n '1,160p' agent_adapters/openclaw/examples/task_prefetch_flow.json
sed -n '1,180p' agent_adapters/openclaw/examples/limited_feishu_ingestion_candidate_only.json
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
- 旧 Feishu Bot handler 是 fallback / reference；新的测试群联调入口是 `scripts/start_copilot_feishu_live.sh`，默认只在旧测试群做受控 live sandbox，不写成生产空间上线。

## 快速验证

基础验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

Copilot contract 验证：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_retrieval tests.test_copilot_cognee_adapter tests.test_copilot_healthcheck
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
- `docs/plans/2026-05-07-implementation-plan.md`
- `docs/plans/2026-05-07-handoff.md`

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
