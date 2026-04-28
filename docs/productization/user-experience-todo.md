# 用户体验产品化 TODO 清单

日期：2026-04-29
负责人：程俊豪
适用范围：飞书内真实用户体验、评委演示路径、记忆卡片、解释层、审核队列、提醒候选、真实样本评测和 10 分钟体验包。

## 先看这个

1. 本清单记录 7 个用户体验缺口是否完成，来源是 2026-04-29 产品复盘。
2. 当前技术基线已经完成 MVP / Demo / Pre-production、本地 OpenClaw `fmc_*` 工具调用验证、受控飞书测试群 sandbox、candidate-only 治理、权限门控、审计和 benchmark。
3. 本清单不改变 no-overclaim 边界：真实 Feishu DM 到本项目 `fmc_*` / `memory.*` 工具链路的 live E2E 仍未完成；productized live 长期运行仍未完成。
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
| UX-01 | 飞书主路径从命令集合升级为完整体验 | 进行中 | 否 | P0 | 用户不理解 `candidate_id`、`trace_id`、`memory_id` 也能完成搜索、候选确认、版本解释和任务前预取 |
| UX-02 | 重做记忆卡片信息架构 | 进行中 | 否 | P0 | 搜索结果、候选审核、版本解释、任务前上下文 4 类卡片模板稳定；半成品按钮不暴露给评委 |
| UX-03 | 用户可理解的“为什么这样回答”解释层 | 进行中 | 否 | P1 | 主答案讲清当前结论、证据、版本覆盖和权限原因；工程字段进入审计详情 |
| UX-04 | 记忆收件箱 / 审核队列 | 进行中 | 否 | P1 | 有“待我审核、冲突需判断、高风险暂不建议确认”三类视图和候选状态流转 |
| UX-05 | 主动提醒变成可控提醒体验 | 进行中 | 否 | P1 | reminder candidate 可确认、忽略、延后、关闭同类提醒；不直接真实群推送 |
| UX-06 | 真实用户表达样本评测 | 进行中 | 否 | P1 | 覆盖口语、含糊上下文、多人改口、闲聊误判和权限场景；指标包含误记率、误提醒率和确认负担 |
| UX-07 | 10 分钟评委体验包 | 待启动 | 否 | P0 | 评委按一条脚本在 10 分钟内看懂问题、飞书体验、benchmark、安全边界和架构 |

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
- `candidate_review_payload()` 仍有 source、versions、needs_review 等 dry-run 痕迹。
- 现有卡片更像调试输出，还没有按用户决策任务拆模板。

要做什么：

| 模板 | 用户看到的核心 |
|---|---|
| 搜索结果卡 | 当前结论、证据、版本状态、是否过滤旧值 |
| 候选审核卡 | 新记忆、来源、风险、是否冲突、确认/拒绝 |
| 版本解释卡 | 当前版本、旧版本、覆盖原因、时间线 |
| 任务前上下文卡 | 本次任务要带入的规则、风险、deadline、缺失信息 |

验收标准：

- 4 类卡片都有稳定 payload builder 和测试。
- 卡片第一屏回答“这是什么、为什么重要、我该点什么”。
- 不可用按钮在评委版隐藏；可见按钮必须真实可用并写审计。

主要文件：

- `memory_engine/feishu_cards.py`
- `tests/test_feishu_interactive_cards.py`
- `memory_engine/bitable_sync.py`
- `docs/demo-runbook.md`

## UX-03：用户可理解的“为什么这样回答”解释层

当前情况：

- 项目已有 evidence、trace、version chain、permission decision。
- `request_id`、`trace_id`、`permission_decision` 仍偏工程审计字段。
- 普通用户需要的是可读解释，而不是内部链路字段。

要做什么：

1. 把工程解释翻译成用户语言：当前 active 版本、旧值被谁覆盖、证据来自哪里、权限为何允许或隐藏。
2. 主答案只放结论和理由；审计字段放到卡片底部或“审计详情”。
3. 权限拒绝时说清“为什么不能看”，但不泄露敏感字段。

验收标准：

- 搜索结果和版本解释都能输出一段面向用户的原因说明。
- 默认召回只显示 active 版本；旧值只在版本解释里出现。
- 权限拒绝不包含未授权 current_value、summary 或 evidence。

主要文件：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/feishu_cards.py`
- `benchmarks/copilot_conflict_cases.json`
- `tests/test_copilot_retrieval.py`

## UX-04：记忆收件箱 / 审核队列

当前情况：

- candidate-only 是核心亮点。
- Bitable Candidate Review 已有本地写回、upsert 和读回确认。
- 用户侧还缺清晰的待处理队列和状态视图。

要做什么：

1. 设计三类视图：待我审核、有冲突需要判断、高风险/敏感暂不建议确认。
2. 让候选状态流转可读：新候选 -> 待审核 -> 已确认 / 已拒绝 / 需补证据 / 已过期。
3. 每条候选显示来源、风险、冲突、建议动作和最后处理人。

验收标准：

- Bitable 或文档入口能按状态查看候选。
- confirm / reject / 需补证据 / 过期都能被记录到审计或同步字段。
- 写回失败时不声称同步成功。

主要文件：

- `memory_engine/bitable_sync.py`
- `memory_engine/copilot/governance.py`
- `tests/test_bitable_sync.py`
- `docs/productization/handoffs/review-surface-operability-handoff.md`

## UX-05：主动提醒变成可控提醒体验

当前情况：

- `heartbeat.review_due` 是 MVP 原型，只生成 reminder candidate。
- 这条边界是安全的，不应直接升级为真实群推送。
- 产品体验还缺“为什么提醒、提醒谁、什么时候提醒、能否暂停”的控制面。

要做什么：

1. 先做提醒候选审核体验，不做默认真实群推送。
2. 用户可以确认、忽略、延后、关闭同类提醒。
3. 每条提醒写清触发原因、冷却时间、敏感字段处理和目标 reviewer。

验收标准：

- reminder candidate 出现在审核队列。
- 用户能延后或关闭同类提醒，状态可查。
- 敏感提醒不直接暴露敏感内容；误提醒率进入评测。

主要文件：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/schemas.py`
- `benchmarks/copilot_heartbeat_cases.json`
- `tests/test_copilot_heartbeat.py`

## UX-06：真实用户表达样本评测

当前情况：

- benchmark 已覆盖 recall、candidate、conflict、layer、prefetch、heartbeat。
- 当前样例仍偏 fixture，需要补真实测试群表达和 UX 指标。

要做什么：

| 样本类型 | 示例 |
|---|---|
| 口语化提问 | 上次说的部署规则是啥？ |
| 含糊上下文 | 这个还按之前那个来吗？ |
| 多人改口 | 不对，刚才那个废掉 |
| 闲聊误判 | 哈哈这个先别记 |
| 权限场景 | 别人私聊里的结论能不能搜到？ |

验收标准：

- 新增真实表达样本集，保留失败样例，不只保留成功样例。
- 指标至少包含 Recall@3、误记率、误提醒率、确认负担、回答可解释性、旧值泄漏率。
- 样本来源脱敏，不提交真实 chat_id、open_id、token。

主要文件：

- `benchmarks/copilot_recall_cases.json`
- `benchmarks/copilot_candidate_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`
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
- 不把真实 Feishu DM live E2E 写成已完成。
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
