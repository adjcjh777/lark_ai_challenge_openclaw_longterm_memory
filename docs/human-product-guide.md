# Feishu Memory Copilot 人类阅读指南

日期：2026-04-29
面向读者：第一次接手项目的人、评委、产品/技术同学、后续维护者

## 这个项目为什么立项

团队协作里的重要信息通常散在飞书群聊、文档、任务、会议纪要和 Bitable 里。问题不是“搜不到”，而是：

- 搜出来的内容太多，不知道哪条是当前有效结论。
- 旧决定和新决定混在一起，容易误用过期规则。
- 新同学或 Agent 执行任务前，不知道历史上下文。
- 关键 deadline、负责人、部署参数、风险结论没有被整理成可复用记忆。

Feishu Memory Copilot 的目标是把这些分散信息整理成“企业记忆”：有当前结论、有来源证据、有版本、有权限、有人工确认、有审计记录。

## 一句话产品定义

Feishu Memory Copilot 是一个 OpenClaw-native 的飞书企业记忆助手。它让 OpenClaw Agent 在飞书工作场景里调用团队记忆，帮助用户找回当前有效结论、识别冲突更新、在任务前预取上下文，并把需要复核的记忆变成候选提醒。

OpenClaw 对外看到的工具名统一是 `fmc_*`，例如 `fmc_memory_search`；仓库里的 `memory.*` 是 Python 内部服务名，用来进入 `CopilotService`。

## 它不是普通搜索

普通搜索返回相关文本；Memory Copilot 返回可治理的当前结论。

| 普通搜索 | Memory Copilot |
|---|---|
| 找到相关聊天或文档片段 | 返回 active memory，也就是当前有效记忆 |
| 不知道旧信息是否失效 | 能解释 superseded 旧版本为什么失效 |
| 没有人工确认流程 | 真实飞书来源先进入 candidate，确认后才 active |
| 不一定有来源证据 | active memory 必须有 evidence quote |
| 不管权限和审计 | permission fail-closed，并写 audit record |

## 现在已经做到什么程度

可以说已经完成：

- 本地 demo / pre-production 闭环。
- `memory.search`：查当前有效记忆。
- `memory.create_candidate`：把值得记的信息变成待确认候选。
- `memory.confirm` / `memory.reject`：人工确认或拒绝。
- `memory.explain_versions`：解释旧版本和当前版本。
- `memory.prefetch`：Agent 做任务前预取相关记忆。
- `heartbeat.review_due`：生成受控 reminder candidate，不自动推送、不自动 active。
- 本地 SQLite schema 已有 tenant / organization / visibility 字段和 audit table。
- OpenClaw Agent runtime 已有受控证据；`memory.*` / `fmc_*` first-class 原生工具注册和本地 Agent 调用验证也已有本机证据。
- 飞书测试群 live sandbox 已接入 Copilot path，但不是生产 live。
- 当前飞书 live 主路径仍是受控入口：allowlist 测试群里，非 `@Bot` 消息可以静默探测 candidate，但默认不回群消息；`@Bot` / 私聊才走主动交互路径。普通问句不会因为命中“部署 / 负责人 / 截止”这类主题词就自动变成 candidate。
- OpenClaw Feishu websocket running 已有本机 staging 证据；一次受控真实 DM -> `fmc_memory_search` -> `CopilotService` allow-path live E2E 已补齐，但这不等于稳定长期路由或所有 `fmc_*` 工具动作都已验证。
- 飞书 live interactive 卡片已接入 typed card：候选审核卡在受控 sandbox/pre-production 路径里可点击确认、拒绝、要求补证据和标记过期；点击动作仍会按当前 operator 权限重新进入 `handle_tool_request()` / `CopilotService`。
- Limited Feishu ingestion 本地底座已支持文档、任务、会议、Bitable，以及 allowlist 群里被动探测或被显式路由到 `memory.create_candidate` 的飞书消息进入 candidate-only pipeline；这不是被动全量群聊摄入。
- Cognee / Ollama live embedding gate 已通过，但不是长期 embedding 服务。

不能说已经完成：

- 生产部署。
- 全量接入 Feishu workspace。
- 完整多租户后台。
- 审计 UI、管理员配置和长期运维。
- 长期 embedding 服务。

## 当前最容易误解的边界

如果你直接拿真实群聊来测，很容易把当前能力高估。按当前代码，下面这些都要明确：

- 当前不是“机器人自动旁听所有群聊并提炼企业记忆”，而是 **allowlist 群里的静默 candidate 探测**。
- 当前最可靠的显式记忆创建路径仍然是 `@Bot /remember ...`；但 allowlist 群里的非 `@Bot` 企业级记忆句子，也可以被动进入 candidate。
- 普通问题、闲聊、追问，不会因为命中主题词就自动变成 candidate；主动搜索仍主要由 `@Bot` / 私聊触发。
- 不在 allowlist 的 chat 不会进入正式处理链路。
- 真实飞书来源即使被系统识别，也仍然先进入 candidate，不会自动 active。

## 核心概念

### raw event

原始飞书消息、文档片段、任务或会议内容。它是证据来源，不应该全部直接塞进长期记忆。

### candidate

待确认记忆。真实飞书来源默认只进入 candidate，不能自动 active。

### active memory

当前有效记忆。只有经过治理流程并且带证据的内容，才能成为 active memory。

### superseded

被新版本覆盖的旧记忆。默认 search 不返回它，只在版本解释里出现。

### evidence

来源证据。一般是飞书消息、文档或其他来源中的 quote，用来说明这条记忆从哪里来。

### permission context

权限上下文，包含用户、租户、组织、入口、chat/document、请求动作和可见性。缺失或畸形时必须 fail closed，也就是拒绝返回敏感内容。

### audit event

审计记录。确认、拒绝、权限拒绝、ingestion、heartbeat 等动作都应该留下记录，方便追溯。

## 产品架构怎么理解

可以把系统分成 8 层：

1. 飞书工作空间：群聊、文档、任务、会议、Bitable。
2. OpenClaw Feishu Plugin：接收飞书消息、线程上下文、用户身份和 Agent 事件。
3. OpenClaw Agent Runtime：理解意图，判断该查记忆、建候选、解释版本还是预取上下文。
4. Memory Orchestrator：决定查哪层记忆、是否 prefetch、是否做冲突检测。
5. Multi-Level Memory Core：L0/L1/L2/L3 分层记忆。
6. Cognee Knowledge Engine：dataset、DataPoints、graph store、vector store、recall。
7. Memory Governance：candidate、active、superseded、rejected、stale、archived 状态机。
8. Feishu Action Layer：lark-cli / OpenAPI / card / Bitable，用于发送卡片、读文档、写表和回写确认状态。

当前仓库已经实现了中间的 Copilot Core、schema、benchmark、demo、受控接入证据、OpenClaw first-class 工具注册和 Feishu websocket running 本机 staging 证据；上线前还要补真实 DM 多工具动作稳定性、真实权限生产化校验和生产运维。

## 使用者能怎么用

### 查历史结论

用户在飞书或 OpenClaw 里问：

```text
生产部署 region 最后定的是哪个？
```

系统应该调用 `memory.search`，返回当前 active 结论、证据、版本和 trace。

### 创建候选记忆

用户说：

```text
@Bot /remember 生产部署必须加 --canary，region 用 ap-shanghai。
```

当前代码里，这是最可靠的显式创建候选方式。系统会调用 `memory.create_candidate`，生成 candidate。真实飞书来源不会自动 active。除此之外，allowlist 群里不 `@Bot` 的企业级记忆句子，也会走静默 candidate probe，但默认不回群消息。

### 确认候选

reviewer 说：

```text
确认这条
```

系统会在当前 chat / thread / reviewer context 下定位最近 candidate，内部仍通过 `memory.confirm` 和 `CopilotService` 把 candidate 变成 active，并写 audit record。用户不需要复制 `candidate_id`；如果上下文无法可靠定位，才提示使用 `/confirm <candidate_id>` 作为 fallback。

### 拒绝候选

reviewer 说：

```text
不要记这个
```

系统会定位当前上下文最近 candidate，内部调用 `memory.reject`，并说明这条候选不会成为当前有效记忆。权限不足、permission 缺失或畸形时必须 fail closed。

### 解释版本

用户问：

```text
为什么旧 region 不用了？
```

系统调用 `memory.explain_versions`，说明当前版本、旧版本、覆盖原因和证据。

### 任务前预取

用户说：

```text
帮我生成今天的部署 checklist。
```

OpenClaw Agent 应该调用 `memory.prefetch`，把部署规则、风险、deadline 作为任务上下文。

## 本地怎么验证现在的产品形态

评委现场建议先走 [10 分钟评委体验包](judge-10-minute-experience.md)。它把固定数据、每分钟脚本、失败 fallback、截图清单、benchmark 讲法和架构图入口放在一处，避免评委先理解内部 ID 或工程 trace。

最小检查：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

跑 demo replay：

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

跑核心 benchmark：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

这些命令证明 demo / pre-production 能力，不等于生产上线。

## 飞书主路径普通话脚本

| 路径 | 用户输入 | 用户应该看到什么 | 失败 fallback | 边界 |
|---|---|---|---|---|
| 搜索 | `@Bot 上次定的生产部署 region 是哪个？` | 当前 active 结论、证据 quote、下一步动作；审计详情放在底部。 | 没找到时提示补充主题或先创建候选。 | 主动搜索仍主要由 `@Bot` / 私聊触发，不展示 superseded 旧值或 raw events。 |
| 候选确认 | `@Bot /remember 生产部署必须加 --canary，region 用 ap-shanghai。` -> `确认这条` | 先生成 candidate，再确认最近 candidate；创建者自己会收到可点击确认卡片，owner 可以直接确认；用户不用输入内部 ID。 | 上下文不明确时提示 `/confirm <candidate_id>`。 | 真实飞书来源不能自动 active。 |
| 被动识别 | 群里直接说：`上线窗口固定为每周四下午，回滚负责人是程俊豪，截止周五中午。` | 系统静默识别为 candidate，后续由 reviewer 在审核面确认。 | 低信号或问句会被忽略，不主动回群消息。 | 只在 allowlist 群内生效；不是全量 workspace 监听。 |
| 版本解释 | `为什么之前的 cn-shanghai 不用了？` | 当前版本、旧版本、覆盖原因和证据。 | 无法定位时先搜索主题，或用 `/versions <memory_id>`。 | 版本解释可看旧值；默认搜索不把旧值作为当前答案。 |
| 任务前 prefetch | `帮我准备今天上线前 checklist。` | compact context pack、相关 active 记忆、风险和缺失信息。 | 上下文不足时返回缺失项，不编造。 | 不返回全部 raw events，不代表 production live。 |

## 飞书卡片怎么看

UX-02 后，飞书里的记忆卡片分成 4 类。卡片第一屏给用户决策信息，审计字段放在底部或 payload 的 `audit_details` 中。

| 卡片 | 用户先看什么 | 按钮含义 | 失败 fallback |
|---|---|---|---|
| 搜索结果卡 | 当前 active 结论、证据 quote、版本状态、旧值是否已过滤。 | `解释版本` 会进入现有版本解释路径。 | 找不到时提示补主题或先创建候选，不返回旧值充当答案。 |
| 候选审核卡 | 新记忆、来源、证据、风险、是否冲突。 | reviewer / owner / admin 才能看到 `确认保存`、`拒绝候选`、`要求补证据`、`标记过期`；创建 candidate 的用户会按 owner 身份看到并可点击确认；点击后仍走 `handle_tool_request()` / `CopilotService`，按钮 value 不内嵌 `current_context`。 | 权限不足、permission 缺失或畸形时 fail closed，并隐藏未授权内容。 |
| 版本解释卡 | 当前版本、旧版本、覆盖原因和时间线。 | 本阶段不新增半成品按钮。 | 无法定位时先搜索主题，或用 `/versions <memory_id>`。 |
| 任务前上下文卡 | 本次任务要带入的 active 规则、风险、deadline/owner 和缺失信息。 | 本阶段不新增半成品按钮。 | 只展示 compact context pack；上下文不足时列缺失信息。 |

这些卡片仍属于 demo / sandbox / pre-production 验收面；当前完成的是真实飞书可点击卡片的受控路径，不代表生产部署、全量飞书空间接入、生产级 card action 长期运行，或真实 Feishu DM 到本项目 `fmc_*` / `memory.*` 链路已稳定长期运行。

## 人类接手后先做什么

1. 先读 [README.md](../README.md) 顶部任务区，确认当前阶段。
2. 再读 [docs/README.md](README.md)，找到你要看的文档分区。
3. 读 [productization/launch-polish-todo.md](productization/launch-polish-todo.md)，按顺序挑下一项。
4. 读 [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)，按任务类型选择验证命令。
5. 做完后更新 README、handoff、飞书看板、验证结果和 commit。

## 当前最重要的下一步

按优先级：

1. 在已完成一次受控真实 DM `fmc_memory_search` allow-path 证据基础上，扩大到 `prefetch` / `create_candidate` 等关键动作，并验证真实 DM 长期稳定性。
2. 在 limited ingestion 底座之上，接真实飞书任务、会议、Bitable API 拉取，并保留失败 fallback。
3. 继续修复 UX-06 暴露的解释缺口、闲聊误记和旧值泄漏，不删除失败样例。
4. 补审计、监控和运维面，让权限拒绝、ingestion 失败、websocket down、embedding unavailable 能被查询和告警。
5. 设计 productized live 长期运行方案，包括部署、监控、回滚、权限后台和审计 UI。

## 判断项目是否健康的标准

健康状态应该同时满足：

- Agent 可以自然调用记忆工具。
- 记忆有证据、有版本、有状态。
- 旧值不会作为当前答案泄露。
- 权限缺失或越权会拒绝。
- 真实飞书来源不会自动 active。
- 审计能追踪谁做了什么。
- 文档不会把 demo / dry-run / sandbox 说成 production live。

## 需要特别小心的边界

- 不要把旧 Bot 当主架构。
- 不要把测试群 sandbox 当生产接入。
- 不要把 Cognee fallback 当 Cognee 主路径成功。
- 不要把 embedding live gate 当长期 embedding 服务。
- 不要为了演示方便绕过 permission context。
- 不要让 card 或 Bitable 直接改 active memory。
