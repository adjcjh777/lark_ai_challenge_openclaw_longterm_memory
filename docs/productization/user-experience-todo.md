# 用户体验产品化 TODO 清单

日期：2026-04-29
负责人：程俊豪
适用范围：飞书内真实用户体验、评委演示路径、记忆卡片、解释层、审核队列、提醒候选、真实样本评测和 10 分钟体验包。

## 先看这个

1. 本清单记录 7 个用户体验缺口是否完成，来源是 2026-04-29 产品复盘。
2. 当前技术基线已经完成 MVP / Demo / Pre-production、本地 OpenClaw `fmc_*` 工具调用验证、受控飞书测试群 sandbox、一次受控真实 Feishu DM `fmc_memory_search` allow-path live E2E、review-policy 治理、权限门控、审计和 benchmark。
3. 本清单不改变 no-overclaim 边界：当前只能说已有一次受控真实 DM allow-path 证据，不能说真实 Feishu DM 已稳定长期路由到本项目 `fmc_*` / `memory.*` 工具链路；productized live 长期运行仍未完成。
4. 完成标准优先看普通用户能否在飞书里完成动作，而不是只看 tool call、trace 或脚本通过。

## 状态字段

| 状态 | 含义 |
|---|---|
| 待启动 | 还没有形成可验收的产品交付物 |
| 进行中 | 底层能力已有，但用户体验、文档或验收还不完整 |
| 已完成 | 普通用户和评委都能按脚本复现；有测试、截图或读回证据 |
| 暂缓 | 当前阶段不建议做，原因写在备注里 |

## 总览

| ID | 用户体验缺口 | 当前状态 | 是否完成 | 优先级 | 完成标准 |
|---|---|---|---|---|---|
| UX-01 | 飞书主路径从命令集合升级为完整体验 | 已完成 | 是 | P0 | 用户不理解 `candidate_id`、`trace_id`、`memory_id` 也能完成搜索、候选确认、版本解释和任务前预取；边界仍是 sandbox/demo path，不是 production live |
| UX-02 | 重做记忆卡片信息架构 | 已完成 | 是 | P0 | 搜索结果、候选审核、版本解释、任务前上下文 4 类卡片模板稳定；候选审核卡在受控飞书 interactive 路径可点击；半成品按钮不暴露给评委 |
| UX-03 | 用户可理解的“为什么这样回答”解释层 | 已完成 | 是 | P1 | 主答案讲清当前结论、证据、版本覆盖和权限原因；工程字段进入审计详情；permission denied 不泄露未授权 current_value / summary / evidence |
| UX-04 | 记忆收件箱 / 审核队列 | 已完成 | 是 | P1 | 有“待我审核、冲突需判断、高风险暂不建议确认”三类视图和候选状态流转 |
| UX-05 | 主动提醒变成可控提醒体验 | 已完成 | 是 | P1 | reminder candidate 可确认、忽略、延后、关闭同类提醒；不直接真实群推送 |
| UX-06 | 真实用户表达样本评测 | 已完成 | 是 | P1 | 已覆盖口语、含糊上下文、多人改口、闲聊误判和权限场景各 5 条；指标包含 Recall@3、误记率、误提醒率、确认负担、解释覆盖率和旧值泄漏率 |
| UX-07 | 10 分钟评委体验包 | 已完成 | 是 | P0 | 评委按一条脚本在 10 分钟内看懂问题、飞书体验、可选受控 DM allow-path、benchmark、安全边界和架构；入口为 `docs/judge-10-minute-experience.md` |

## 详细执行文档

按下面顺序执行，不要跳过还没有验收的前置体验任务。

| 顺序 | TODO | 详细文档 | 本阶段出口 |
|---|---|---|---|
| 1 | UX-01 | [飞书主路径从命令集合升级为完整体验](user-experience-todos/ux-01-feishu-main-path.md) | 普通用户不输入内部 ID 也能完成搜索、候选确认、版本解释和任务前 prefetch。 |
| 2 | UX-02 | [重做记忆卡片信息架构](user-experience-todos/ux-02-memory-card-information-architecture.md) | 搜索结果、候选审核、版本解释、任务前上下文 4 类卡片模板稳定。 |
| 3 | UX-03 | [用户可理解的“为什么这样回答”解释层](user-experience-todos/ux-03-user-facing-explanation-layer.md) | 主答案能解释当前结论、证据、版本覆盖和权限原因，工程字段进入审计详情。 |
| 4 | UX-04 | [记忆收件箱 / 审核队列](user-experience-todos/ux-04-memory-inbox-review-queue.md) | 待我审核、冲突需判断、高风险暂不建议确认三类视图可处理。 |
| 5 | UX-05 | [主动提醒变成可控提醒体验](user-experience-todos/ux-05-controlled-reminder-experience.md) | reminder candidate 可确认、忽略、延后和关闭同类提醒，不直接真实群推送。 |
| 6 | UX-06 | [真实用户表达样本评测](user-experience-todos/ux-06-real-user-expression-benchmark.md) | 覆盖真实表达样本和误记率、误提醒率、确认负担等 UX 指标。 |
| 7 | UX-07 | [10 分钟评委体验包](user-experience-todos/ux-07-ten-minute-judge-experience-pack.md) | 评委按一条脚本在 10 分钟内看懂体验、benchmark、安全边界和架构。 |

## UX-07：10 分钟评委体验包

当前情况：

- 已新增 [docs/judge-10-minute-experience.md](../judge-10-minute-experience.md)，包含每分钟输入、动作、预期输出、失败 fallback 和讲解词。
- 已在 [docs/demo-runbook.md](../demo-runbook.md) 固定演示数据、截图清单入口和计时验收记录。
- 已把一次受控真实 DM `fmc_memory_search` allow-path 证据整理成可选现场验收入口；包含准备检查、固定脱敏 DM 文案、预期字段和失败 fallback。
- 已在 [docs/benchmark-report.md](../benchmark-report.md)、[docs/human-product-guide.md](../human-product-guide.md)、[README.md](../../README.md) 对齐 benchmark 与 no-overclaim 口径。
- 已在 [docs/diagrams/README.md](../diagrams/README.md) 和 [docs/README.md](../README.md) 补系统架构、产品交互流和 benchmark loop 入口。

验收标准：

- 已完成：10 分钟脚本按分钟覆盖问题定义、当前结论召回、候选确认、版本解释、prefetch、reminder candidate、benchmark、架构和安全边界。
- 已完成：可选真实 DM 验收只使用脱敏请求，预期读回命中数、request_id、trace_id 和 permission_decision，不要求评委理解真实 chat_id / open_id。
- 已完成：演示数据固定为 `ap-shanghai` / `--canary` 部署规则；截图清单不包含真实 ID、token 或敏感内容。
- 已完成：UX-06 指标和残余风险进入评委讲法，不把 benchmark 写成全部达标。
- 已完成：计时走查记录为 9 分 40 秒内可走完；飞书 sandbox 或 Mermaid 渲染失败时有 replay / `.mmd` fallback。

剩余边界：

- 本阶段不生成截图二进制。
- 本阶段不跑重 benchmark；只保留已有 UX-06 runner 命令。
- 本阶段不宣称 production live、全量 Feishu workspace 接入或真实 Feishu DM 稳定长期路由；一次受控 DM allow-path 只覆盖 `fmc_memory_search`。

## UX-01：飞书主路径从命令集合升级为完整体验

当前情况：

- 已有 `/remember`、`/confirm`、`/reject`、`/prefetch`、`/heartbeat` 等能力。
- `memory_engine/copilot/feishu_live.py` 已有自然语言分流到 search / candidate / prefetch 的基础。
- 体验仍偏向懂系统的人操作工具，用户还需要理解候选、trace 或 memory id。

要做什么：

1. 定义一条评委和真实用户都能复现的飞书主路径：普通话输入 -> Agent 判断动作 -> 返回结果 -> 用户确认/拒绝/看来源/看版本 -> 审计可查。
2. 让自然语言回复优先给用户动作，而不是暴露内部 ID。
3. 所有确认、拒绝、版本解释和 prefetch 仍必须进入 `handle_tool_request()` / `CopilotService`。

验收标准：

- 用户只输入普通话，不输入内部 ID，也能完成一次候选确认或拒绝。
- 搜索、候选、版本解释、prefetch 至少各有 1 条飞书侧演示脚本。
- 结果里保留 request / trace / permission 审计信息，但不抢占主答案。

主要文件：

- `memory_engine/copilot/feishu_live.py`
- `memory_engine/feishu_cards.py`
- `tests/test_copilot_feishu_live.py`
- `tests/test_feishu_interactive_cards.py`
- `docs/demo-runbook.md`

## UX-02：重做记忆卡片信息架构

当前情况：

- 候选卡片已有 confirm / reject / source / version 等按钮基础。
- 已完成 4 类稳定 payload builder：`search_result_payload()`、`candidate_review_payload()`、`version_chain_payload()`、`prefetch_context_payload()`。
- Feishu live `card_mode=interactive` 已按 Copilot service output 选择 typed card builder，候选审核卡不再只是文本 fallback 卡片。
- 卡片主内容和审计详情已分层：用户先看当前结论、证据、风险和下一步；`request_id`、`trace_id`、`permission_decision` 放入审计详情。
- 评委版不暴露不可用按钮；候选卡只给 reviewer / owner / admin 显示确认、拒绝、要求补证据和标记过期，搜索卡只保留已有版本解释动作。

要做什么：

| 模板 | 用户看到的核心 |
|---|---|
| 搜索结果卡 | 当前结论、证据、版本状态、是否过滤旧值 |
| 候选审核卡 | 新记忆、来源、风险、是否冲突、确认/拒绝 |
| 版本解释卡 | 当前版本、旧版本、覆盖原因、时间线 |
| 任务前上下文卡 | 本次任务要带入的规则、风险、deadline、缺失信息 |

验收标准：

- 已完成：4 类卡片都有稳定 payload builder 和测试。
- 已完成：卡片第一屏回答“这是什么、为什么重要、我该点什么”。
- 已完成：不可用按钮在评委版隐藏；可见按钮只保留可路由到现有 confirm / reject / needs_evidence / expire / versions 动作的按钮。
- 已完成：候选审核卡按钮 value 不内嵌 `current_context`，点击时按当前 operator 重新生成权限上下文；非 reviewer 伪造点击 fail closed，候选不变。

主要文件：

- `memory_engine/feishu_cards.py`
- `memory_engine/copilot/feishu_live.py`
- `memory_engine/feishu_events.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_copilot_feishu_live.py`
- `memory_engine/bitable_sync.py`
- `docs/demo-runbook.md`

## UX-03：用户可理解的“为什么这样回答”解释层

当前情况：

- 已完成 search、version chain 和 permission denied 的用户解释出口。
- `memory.explain_versions` 的 `user_explanation` 已被 `version_chain_payload()` / `build_version_chain_card()` 消费为主解释字段，同时保留旧的 `active_version`、`versions`、`explanation` 字段向后兼容。
- 搜索卡的 `rank_reason` 已转成用户语言，能覆盖“命中当前 active 记忆、证据相关、旧值已过滤”。
- `request_id`、`trace_id`、`permission_decision` 保留在审计详情，不抢占主答案。

要做什么：

1. 已完成：把工程解释翻译成用户语言：当前 active 版本、旧值被谁覆盖、证据来自哪里、权限为何允许或隐藏。
2. 已完成：主答案只放结论和理由；审计字段放到卡片底部或“审计详情”。
3. 已完成：权限拒绝时说清“为什么不能看”，但不泄露敏感字段。

验收标准：

- 已完成：搜索结果和版本解释都能输出面向用户的原因说明。
- 已完成：默认召回只显示 active 版本；旧值只在版本解释里出现。
- 已完成：权限拒绝不包含未授权 current_value、summary 或 evidence。
- 已验证：
  - `python3 scripts/check_openclaw_version.py`
  - `python3 -m compileall memory_engine scripts`
  - `python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_permissions`
  - `python3 -m unittest tests.test_copilot_tools tests.test_feishu_interactive_cards`
  - `python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json`（runner exit 0；当前扩样指标不理想，conflict case pass rate = 0.4000，stale leakage rate = 0.4286）
  - `python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json`（runner exit 0；Recall@3 = 0.9250，但 case pass rate = 0.5750，stale leakage rate = 0.4444）
  - `git diff --check`
  - `ollama ps`

剩余风险：

- 当前解释覆盖率主要由单测和文档口径约束，benchmark runner 还没有自动汇总 User Explanation Coverage。
- 当前 recall / conflict 扩样 benchmark 可运行但仍有旧值泄漏和失败样例；UX-03 完成只代表解释出口补齐，不代表召回指标全部达标。
- 真实飞书表达样本仍需 UX-06 扩样；本条完成不代表真实 Feishu DM 到本项目 `fmc_*` / `memory.*` 已稳定长期路由，当前只覆盖一次 `fmc_memory_search` allow-path。
- 本阶段不宣称 production live 或长期运行完成。

主要文件：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/feishu_cards.py`
- `benchmarks/copilot_conflict_cases.json`
- `tests/test_copilot_retrieval.py`

## UX-04：记忆收件箱 / 审核队列

当前情况：

- review policy 是核心亮点：低重要性安全候选减少确认负担，重要/敏感/冲突候选仍由人确认。
- Bitable Candidate Review 已有本地写回、upsert 和读回确认。
- 已补清晰的待处理队列、状态视图和 `needs_evidence` / `expired` 服务层状态动作。
- 已新增 Feishu live `/review` 审核收件箱：默认显示“待我审核”，支持 `/review conflicts`、`/review high_risk`，卡片只对当前 reviewer/owner 定向可见。
- 审核收件箱卡片不在可见内容里展示 `candidate_id`、`memory_id`、`request_id`、`trace_id`；按钮 value 仍携带候选定位字段以便回调路由。
- 冲突候选卡显示“旧结论 / 新结论”，并提供“确认合并”动作；合并仍走 `memory.confirm` / `CopilotService`，不是绕过治理层直接改库。
- 已补 `/undo` 和 card action router 的撤销入口，可把已确认/已拒绝/需补证据/已过期的候选撤回待审核状态。

要做什么：

1. 已完成：设计三类视图：待我审核、有冲突需要判断、高风险/敏感暂不建议确认。
2. 已完成：让候选状态流转可读：新候选 -> 待审核 -> 已确认 / 已拒绝 / 需补证据 / 已过期 -> 可撤销回待审核。
3. 已完成：每条候选显示来源、风险、冲突、建议动作和适用范围，不把内部 ID 放进可见主内容。

验收标准：

- 已完成：Feishu `/review` 卡片能按 mine/conflicts/high_risk 查看候选，并直接触发 confirm / reject / needs_evidence。
- 已完成：冲突候选能在卡片上比较旧结论和新结论，并通过“确认合并”进入 `memory.confirm`。
- 已完成：`/undo` 和 card action router 支持撤销确认后的状态变更。
- 已完成：confirm / reject / 需补证据 / 过期 / undo 都走 `handle_tool_request()` / `CopilotService`，并进入审计。
- 剩余：真实飞书测试群还需要继续扩样点击 `/review`、`确认合并`、`/undo` 并读回审计；当前不能写成生产级长期运行。

主要文件：

- `memory_engine/bitable_sync.py`
- `memory_engine/copilot/governance.py`
- `tests/test_bitable_sync.py`
- `docs/productization/handoffs/review-surface-operability-handoff.md`

## UX-05：主动提醒变成可控提醒体验

当前情况：

- 已完成可控 reminder candidate 体验，仍只生成候选提醒，不做真实群推送。
- Reminder Candidate 已有 confirm useful、ignore、snooze、mute same type 四类动作。
- 卡片和 Bitable 队列能展示触发原因、目标 reviewer、cooldown、`next_review_at`、`mute_key` 和敏感内容脱敏状态。

要做什么：

1. 已完成：先做提醒候选审核体验，不做默认真实群推送。
2. 已完成：用户可以确认、忽略、延后、关闭同类提醒。
3. 已完成：每条提醒写清触发原因、冷却时间、敏感字段处理和目标 reviewer。

验收标准：

- 已完成：reminder candidate 出现在审核队列。
- 已完成：用户能延后或关闭同类提醒，状态可查。
- 已完成：敏感提醒不直接暴露敏感内容；误提醒率、敏感泄漏率、重复提醒率和用户确认负担进入 heartbeat benchmark。

已验证：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m compileall memory_engine scripts`
- `python3 -m unittest tests.test_copilot_heartbeat tests.test_copilot_tools`
- `python3 -m unittest tests.test_bitable_sync tests.test_feishu_interactive_cards`
- `python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json`
- `git diff --check`
- `ollama ps`

剩余边界：

- 本阶段不做真实群推送。
- 本阶段不把 reminder candidate 自动变成 active memory。
- 本阶段不宣称 production live 或真实 Feishu DM 稳定长期路由；一次受控 DM allow-path 只覆盖 `fmc_memory_search`。

主要文件：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/schemas.py`
- `benchmarks/copilot_heartbeat_cases.json`
- `tests/test_copilot_heartbeat.py`

## UX-06：真实用户表达样本评测

当前情况：

- 已新增 `benchmarks/copilot_real_feishu_cases.json` 脱敏真实表达样本集。
- 样本覆盖口语、含糊上下文、多人改口、闲聊误判和权限场景各 5 条。
- `memory_engine/benchmark.py` 已新增 `copilot_real_feishu` runner，输出 Recall@3、误记率、误提醒率、确认负担、解释覆盖率和旧值泄漏率。
- 失败样例保留，不删除失败记录来制造好看的指标。

要做什么：

| 样本类型 | 示例 |
|---|---|
| 口语化提问 | 上次说的部署规则是啥？ |
| 含糊上下文 | 这个还按之前那个来吗？ |
| 多人改口 | 不对，刚才那个废掉 |
| 闲聊误判 | 哈哈这个先别记 |
| 权限场景 | 别人私聊里的结论能不能搜到？ |

验收标准：

- 已完成：新增真实表达样本集，保留失败样例，不只保留成功样例。
- 已完成：指标包含 Recall@3、误记率、误提醒率、确认负担、回答可解释性、旧值泄漏率。
- 已完成：样本来源脱敏，不提交真实 chat_id、open_id、token。

已验证：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m compileall memory_engine scripts`
- `python3 -m unittest tests.test_copilot_benchmark tests.test_copilot_retrieval`
- `python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json`
- `python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json`
- `python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json`
- `python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json`
- `python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json`
- `python3 -m memory_engine benchmark run benchmarks/copilot_real_feishu_cases.json`
- `git diff --check`
- `ollama ps`

剩余边界：

- `copilot_real_feishu_cases.json` 是脱敏 fixture + baseline 标注，不是生产真实用户稳定可用结论。
- 当前失败样例包括解释缺口、闲聊误记和旧值泄漏，后续应修能力而不是删样例。
- 真实飞书来源先走 review policy；低重要性安全候选可自动 active，重要/敏感/冲突候选仍需人工确认。
- 本阶段不宣称 production live、真实 Feishu DM 稳定长期路由或 productized live 长期运行完成；一次受控 DM allow-path 只覆盖 `fmc_memory_search`。

主要文件：

- `benchmarks/copilot_recall_cases.json`
- `benchmarks/copilot_candidate_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`
- `benchmarks/copilot_real_feishu_cases.json`
- `memory_engine/benchmark.py`
- `docs/benchmark-report.md`
- `tests/test_copilot_benchmark.py`

## UX-07：10 分钟评委体验包

当前情况：

- README、demo runbook、benchmark report、白皮书都已有。
- 当前入口仍偏工程验收，评委需要一条更短的产品演示路线。

要做什么：

| 时间 | 内容 |
|---|---|
| 1 分钟 | 项目解决什么问题 |
| 2 分钟 | 飞书里看一次当前结论召回 |
| 2 分钟 | 看一次候选确认 |
| 1 分钟 | 看一次旧版本解释 |
| 1 分钟 | 看一次任务前 prefetch |
| 1 分钟 | 看 benchmark 和安全边界 |
| 2 分钟 | 看架构图和 no-overclaim 边界 |

验收标准：

- 新增评委体验脚本或重写 demo runbook 的评委入口。
- 每一步有输入、预期输出、失败 fallback 和不能 overclaim 的边界。
- 10 分钟内不要求评委理解内部 ID。

主要文件：

- `docs/demo-runbook.md`
- `docs/human-product-guide.md`
- `README.md`
- `docs/diagrams/`

## 当前不做

- 不直接把 heartbeat 改成真实群推送。
- 不把一次受控真实 Feishu DM allow-path 写成稳定长期路由。
- 不做完整多租户企业后台。
- 不绕过 `CopilotService` 直接改 active memory。
- 不把 Bitable / card dry-run 当作生产级长期运行。

## 收口验证

文档更新最低验证：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

如果后续触达代码，再按对应模块追加专项测试：

```bash
python3 -m unittest tests.test_copilot_feishu_live tests.test_feishu_interactive_cards tests.test_bitable_sync
python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_benchmark tests.test_copilot_heartbeat
```
