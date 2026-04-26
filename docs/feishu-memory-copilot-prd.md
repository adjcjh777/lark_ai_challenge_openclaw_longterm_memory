# Feishu Memory Copilot PRD

日期：2026-04-26  
状态：Draft for implementation planning  
目标读者：项目负责人、队友、评委、后续重构执行者  
产品定位：OpenClaw-native enterprise memory copilot for Feishu collaboration

## 1. Executive Summary

### Problem Statement

企业项目协作中的关键上下文分散在飞书群聊、文档、会议纪要、任务和多维表格中。团队成员经常需要翻历史消息才能确认某个决策、负责人、截止时间或规则更新；当旧信息和新信息同时存在时，还容易误用过期结论。

当前项目早期实现已经证明 `remember -> recall -> conflict update -> benchmark` 可以本地跑通，但它偏向工具形态。新产品目标不是一个手动 `/remember` 工具，也不是普通聊天记录搜索，而是一个基于 OpenClaw Agent 的企业办公记忆 Copilot。

### Proposed Solution

Feishu Memory Copilot 是一个 OpenClaw-native 的企业办公记忆 Copilot。它以 OpenClaw Agent 为主要用户入口和工具编排层，以飞书群聊、文档、Bitable、lark-cli 和飞书 OpenAPI 作为办公集成层，以 Multi-Level Memory System 作为长期记忆核心。

系统从飞书协作场景中识别值得长期保留的企业级记忆，维护带证据、版本和状态的团队记忆，并通过 OpenClaw Agent 帮助用户快速找回历史决策、识别冲突更新、在任务执行前预取上下文，以及通过 heartbeat 原型主动提醒团队复核关键记忆。

### Success Criteria

MVP success criteria:

| Metric | MVP Target | Definition |
|---|---:|---|
| Recall@3 | >= 60% | 项目协作测试集中，Top 3 召回结果包含正确历史决策 |
| Conflict Update Accuracy | >= 70% | 对 `old -> new` 的冲突表达，系统能正确识别覆盖关系 |
| Evidence Coverage | >= 80% | 召回结果中至少 80% 带来源证据 |
| Candidate Precision | >= 60% | 系统识别出的候选记忆中，人工认为确实值得记的比例 |
| Agent Task Context Use Rate | >= 70% | 需要历史上下文的 Agent 任务中，Agent 实际调用 memory prefetch/search 的比例 |
| L1 Hot Recall p95 | <= 100ms | Hot Memory 查询 95 分位延迟 |
| Sensitive Reminder Leakage Rate | 0 | 主动提醒不得泄露 secret、token 或敏感内部链接 |
| OpenClaw E2E flows | >= 2 | 至少跑通 2 条 OpenClaw Agent 端到端工具调用流 |

Final target success criteria:

| Metric | Final Target |
|---|---:|
| Recall@3 | >= 85% |
| Conflict Update Accuracy | >= 90% |
| Evidence Coverage | >= 95% |
| Stale Leakage Rate | <= 5% |
| L1 Hot Recall p95 | <= 50ms |
| L2 Warm Recall p95 | <= 300ms |
| 主动提醒接受率 | >= 60% |
| 主动提醒误打扰率 | <= 20% |

### Product Decision

MVP 真实落地场景锁定为“项目协作记忆”，覆盖项目群聊、项目文档、历史决策、负责人、截止时间、流程规则、风险结论和部署参数。架构必须按可扩展企业记忆系统设计，预留会议、任务、客户、偏好、安全规则和多租户权限后台能力。

旧仓库实现不作为最终架构主干。它只作为参考资产：

- 数据模型经验。
- Benchmark 样例。
- 飞书卡片交互经验。
- Bitable 台账经验。
- 可复现 demo 兜底经验。

## 2. User Experience & Functionality

### User Personas

| Persona | Needs | Pain Points |
|---|---|---|
| 项目成员 | 快速确认历史决策、部署参数、负责人、截止时间 | 翻群聊、问同事、搜文档耗时 |
| 项目负责人 / PM | 了解团队之前定过什么、哪些结论被更新、哪些风险仍未关闭 | 上下文散落，重复讨论，旧信息污染决策 |
| 开发者 / Agent 用户 | 让 OpenClaw Agent 执行任务时自动获得项目上下文 | Agent 默认无长期项目记忆，每次都要重新解释背景 |
| 评委 / 管理者 | 判断系统是否真的提升效率，而不是普通搜索 | 需要看到状态机、证据链、Benchmark 和可运行 Demo |

### User Stories

#### Story 1: 历史决策召回

As a 项目成员, I want to 用自然语言询问 OpenClaw Agent 历史决策 so that 我不用翻群聊就能拿到当前有效结论。

Acceptance criteria:

- 用户问题不要求严格匹配关键词。
- Agent 必须调用 `memory.search` 或等价检索工具。
- Top 3 结果中包含正确记忆。
- 输出必须包含当前结论、来源证据、状态和版本。
- 如果存在旧版本，输出必须说明旧版本已被覆盖。

#### Story 2: 自动识别企业级记忆

As a 项目负责人, I want to 系统自动识别飞书群聊或文档里值得长期保存的信息 so that 团队不必手动记录每条重要规则。

Acceptance criteria:

- 系统能识别 decision、deadline、owner、workflow、risk、document 等记忆类型。
- 普通闲聊不应被保存为企业级记忆。
- 候选记忆必须绑定来源证据。
- 低置信或高风险候选必须进入人工确认。
- 用户确认后，candidate 变为 active。

#### Story 3: 用户手动记忆

As a 用户, I want to 显式要求 Copilot 记住某条信息 so that 我能主动沉淀确定重要的团队规则。

Acceptance criteria:

- 支持“记住”“请记一下”“以后都按”“这个规则固定下来”等表达。
- 手动记忆仍然必须经过 Memory Core，不能绕过证据、安全和冲突检查。
- 手动写入必须记录当前消息作为 evidence。
- 如果内容与旧记忆冲突，必须展示覆盖关系。

#### Story 4: 冲突更新识别

As a 项目成员, I want to 当团队规则更新时系统能识别旧值被覆盖 so that 后续不会误用旧信息。

Acceptance criteria:

- 支持“刚才说错了”“不对”“统一改成”“旧规则不用了”“按新版走”等覆盖表达。
- 旧版本进入 `superseded`，不得作为默认当前答案返回。
- 新版本进入 `active` 或人工确认队列。
- `memory.explain_versions` 能解释旧值为什么失效。
- Benchmark 必须检测 stale leakage。

#### Story 5: Agent 任务前上下文预取

As an OpenClaw Agent user, I want to Agent 执行项目任务前自动读取相关记忆 so that Agent 不是从零开始工作。

Acceptance criteria:

- 用户要求生成 checklist、计划、报告、答复或任务拆解时，Agent 应判断是否需要项目上下文。
- Agent 应调用 `memory.prefetch` 或 `memory.search`。
- 输出中必须使用 active memory，不得忽略已存在的关键规则。
- 如果上下文不足，Agent 应说明缺口，而不是编造。

#### Story 6: Heartbeat 主动提醒

As a 项目负责人, I want to Copilot 能通过 heartbeat 或 scheduled check 发现需要复核的关键记忆 so that 团队能在风险发生前处理过期信息和临近 deadline。

Acceptance criteria:

- MVP 至少支持 reminder candidate 生成。
- 提醒必须通过 importance、relevance、cooldown、scope permission 和敏感信息检查。
- MVP 可输出飞书卡片或 dry-run log。
- 主动提醒不得泄露敏感内容。

### MVP User Journeys

#### Journey 1: 历史决策召回

```text
1. 用户在飞书里询问 OpenClaw Agent：
   “这次生产部署 region 最后定的是哪个？”

2. OpenClaw Agent 判断这是历史上下文查询。

3. Agent 调用：
   memory.search(query="生产部署 region", scope="project:<id>", top_k=3)

4. Memory Orchestrator 按 L1 -> L2 -> L3 cascade 检索。

5. Memory Core 返回 active memory 和 evidence。

6. Agent 生成飞书卡片：
   当前结论、来源证据、版本号、是否覆盖旧值、查看版本链按钮。
```

#### Journey 2: 自动识别和手动写入企业级记忆

```text
自动识别：
1. 飞书群里出现：
   “以后评测报告周日 20:00 前完成，负责人是赵阳。”
2. Agent 或 ingestion pipeline 判断该消息包含长期价值。
3. 调用 memory.create_candidate。
4. Memory Core 生成 deadline + owner 类型候选记忆。
5. 用户确认后，candidate 变为 active。

手动记忆：
1. 用户说：
   “记住：生产部署必须加 --canary，region 用 ap-shanghai。”
2. Agent 判断这是显式记忆写入。
3. 调用 memory.create_candidate。
4. Memory Core 检查 evidence、敏感内容和冲突关系。
5. 无冲突则创建 candidate/active；有冲突则进入冲突更新流程。
```

#### Journey 3: 冲突更新

```text
1. 用户说：
   “刚才说错了，生产部署 region 统一改成 ap-shanghai。”

2. Agent 调用 memory.create_candidate。

3. Memory Core 查找同 scope、同 subject 的 active memory。

4. 系统识别 old -> new 覆盖关系。

5. 旧版本标记为 superseded，新版本进入 active 或确认队列。

6. 飞书卡片展示旧值、新值、来源和覆盖原因。
```

#### Journey 4: Agent 执行任务前预取

```text
1. 用户说：
   “帮我生成今天的部署 checklist。”

2. OpenClaw Agent 判断任务需要项目历史上下文。

3. Agent 调用：
   memory.prefetch(task="deployment_checklist", scope="project:<id>", current_context)

4. Memory Orchestrator 返回部署规则、审批要求、风险提醒。

5. Agent 基于 retrieved memory 生成 checklist。

6. 输出中标注使用了哪些记忆、来源是什么、哪些信息仍缺失。
```

#### Journey 5: Heartbeat 主动提醒

```text
1. OpenClaw heartbeat / scheduled check 触发。
2. Agent 调用 memory.proactive_check 或等价流程。
3. 系统扫描 review_due、重要但长期未 recall 的记忆、即将到期 deadline。
4. 生成 reminder candidate。
5. 通过门控后，发送飞书卡片或 dry-run log。
```

### Functional Requirements

#### FR1: Memory Search

Tool:

```text
memory.search(query, scope, top_k)
```

Requirements:

- 默认只搜索 `active` memory。
- 支持 Top K 返回，MVP 至少 Top 3。
- 返回 `memory_id`、`type`、`subject`、`current_value`、`status`、`version`、`layer`、`score`、`evidence`。
- 支持结构化过滤、关键词/全文检索、向量召回和 rerank。

#### FR2: Candidate Creation

Tool:

```text
memory.create_candidate(text, scope, source)
```

Sources:

```text
manual_user_instruction
feishu_message
feishu_doc
benchmark_fixture
openclaw_agent_context
```

Candidate output:

```text
type
subject
current_value
summary
confidence
importance
evidence
risk_flags
```

#### FR3: Manual Memory Capture

Requirements:

- 识别显式记忆表达。
- 手动记忆不能作为普通聊天处理。
- 如果用户明确要求记忆，系统必须返回保存状态。
- 手动写入不能绕过敏感信息检查。

#### FR4: Conflict Update

Requirements:

- 识别覆盖表达。
- 保留旧版本，不直接删除。
- 旧版本进入 Cold Memory 或历史版本路径。
- 新版本默认成为当前 active 或进入人工确认。
- 召回默认不返回 superseded 作为当前答案。

#### FR5: Evidence Management

Requirements:

- 每条 active memory 必须绑定 evidence。
- evidence 至少包含 `source_type`、`source_id`、`quote`、`created_at`、`actor_id`。
- Recall 和卡片输出必须展示 evidence 摘要。
- 敏感来源信息必须脱敏。

#### FR6: OpenClaw Tool Interface

MVP tools:

```text
memory.search
memory.create_candidate
memory.confirm
memory.reject
memory.explain_versions
memory.prefetch
```

Future tools:

```text
memory.search_hot
memory.search_recent
memory.search_deep
memory.promote
memory.review_due
memory.proactive_check
```

Requirements:

- 工具返回结构化 JSON。
- 工具错误必须可解释，例如 scope 缺失、权限不足、无匹配记忆。
- OpenClaw Agent 至少跑通 2 条端到端任务流，目标跑通 3 条。

#### FR7: Feishu Card Output

卡片必须展示：

```text
当前结论
类型
主题
状态
版本
来源
是否覆盖旧值
可执行按钮
```

MVP buttons:

```text
确认保存
拒绝候选
查看版本链
查看来源
标记需要复核
```

MVP 至少支持确认、拒绝、版本链中的两个。

### Non-Goals

MVP 不做：

- 完整泛企业知识库。
- 全量聊天记录语义搜索替代品。
- 分布式缓存。
- 完整多租户权限后台 UI。
- 全量企业文档长期归档。
- 生产级高可用部署。
- 完整 npm 包发布。
- 把 OpenClaw 当作记忆数据库或状态机。
- 无确认地自动写入高风险记忆。

## 3. AI System Requirements

### Agent Role

OpenClaw Agent 是 Memory Copilot 的原生运行入口，负责：

- 理解用户自然语言意图。
- 判断用户是在查询历史、写入记忆、更新规则，还是要求执行任务。
- 选择合适的 memory tools。
- 在执行任务前主动调用 memory prefetch。
- 将 Memory Core 的结构化结果组织成飞书回复或卡片。
- 在 heartbeat / scheduled check 中触发主动提醒检查。

OpenClaw Agent 不负责：

- 直接管理记忆数据库。
- 直接维护 active / superseded 状态机。
- 直接绕过 Memory Core 写入长期记忆。
- 直接删除旧版本。

### Tool Requirements

MVP required tools:

| Tool | Purpose | Required Output |
|---|---|---|
| `memory.search` | 查询 active memory | Top K memories with evidence and layer |
| `memory.create_candidate` | 生成候选记忆 | candidate memory with confidence/risk flags |
| `memory.confirm` | 确认候选 | updated memory status |
| `memory.reject` | 拒绝候选 | rejected status and reason |
| `memory.explain_versions` | 解释版本链 | active/superseded versions and evidence |
| `memory.prefetch` | 任务前预取上下文 | compact context pack |

Future tools:

| Tool | Purpose |
|---|---|
| `memory.search_hot` | 只查 L1 Hot Memory |
| `memory.search_recent` | 查 L2 Warm Memory |
| `memory.search_deep` | 触发 L3 Cold Memory 深度检索 |
| `memory.promote` | 提升重要记忆到 Hot Memory |
| `memory.review_due` | 查找需要复核的记忆 |
| `memory.proactive_check` | heartbeat 主动提醒判断 |

### Memory Intelligence Requirements

系统需要具备四类 AI 判断能力：

1. 记忆价值判断
   - 判断一段内容是否值得长期保存。
   - 区分企业级记忆和普通聊天噪声。

2. 类型分类
   - 判断是 decision、deadline、owner、workflow、risk、document 等类型。

3. 冲突检测
   - 判断新内容是否覆盖旧记忆。
   - 生成 old -> new 解释。

4. 任务前上下文预取
   - 判断 Agent 当前任务是否需要历史记忆支持。
   - 返回 compact context pack。

### Evaluation Strategy

MVP benchmark 至少包含：

```text
Historical Decision Recall
Candidate Memory Detection
Conflict Update
Multi-Level Memory Retrieval
OpenClaw Agent Prefetch
Heartbeat Reminder
Evidence & Security
```

Core metrics:

| Metric | MVP Target | Final Target |
|---|---:|---:|
| Recall@3 | >= 60% | >= 85% |
| Conflict Update Accuracy | >= 70% | >= 90% |
| Evidence Coverage | >= 80% | >= 95% |
| Candidate Precision | >= 60% | >= 80% |
| Candidate Recall | >= 50% | >= 75% |
| Stale Leakage Rate | <= 15% | <= 5% |
| Agent Task Context Use Rate | >= 70% | >= 90% |
| Prefetch Relevance@3 | >= 60% | >= 85% |
| Reminder Candidate Precision | >= 50% | TBD |
| Reminder Acceptance Rate | prototype only | >= 60% |
| Reminder Noise Rate | prototype only | <= 20% |
| Sensitive Reminder Leakage Rate | 0 | 0 |

### Benchmark Dataset Design

#### Dataset A: Historical Decision Recall

Validates:

- Recall@1 / Recall@3 / MRR。
- Evidence Coverage。
- Latency by memory layer。

Example:

```text
Input memory:
生产部署 region 统一使用 ap-shanghai，必须加 --canary。

Query:
这次部署 region 用哪个？

Expected:
Top 3 中包含 ap-shanghai 和 --canary。
```

#### Dataset B: Candidate Memory Detection

Includes:

- 值得记的决策、截止时间、负责人、流程规则、风险结论、文档约定。
- 不该记的闲聊、临时确认、情绪表达、重复寒暄、无长期价值过程消息。

Metrics:

- Candidate Precision。
- Candidate Recall。
- False Positive Rate。
- False Negative Rate。
- Risk Flag Accuracy。

#### Dataset C: Conflict Update

Validates:

- Conflict Update Accuracy。
- Current Answer Accuracy。
- Stale Leakage Rate。
- Version Trace Coverage。

Example:

```text
Old:
周报以后发给 A。

New:
不对，周报以后统一发给 B。

Query:
周报发给谁？

Expected:
返回 B，不返回 A 作为当前答案。
```

#### Dataset D: Multi-Level Memory Retrieval

Validates:

- L1 Hit Rate。
- L2 Fallback Success Rate。
- L3 Deep Search Success Rate。
- Layer Routing Accuracy。
- Hot/Warm/Cold latency。
- Promotion/Demotion behavior。

#### Dataset E: OpenClaw Agent Prefetch

Example tasks:

```text
帮我生成今天的部署 checklist。
帮我写一段给评委的项目进展说明。
帮我整理明天会议要确认的问题。
```

Metrics:

- Agent Task Context Use Rate。
- Prefetch Relevance@3。
- Missing Context Rate。
- Grounded Output Rate。

#### Dataset F: Heartbeat Reminder

Trigger examples:

- 重要 deadline 24 小时内到期。
- 高重要性 memory 超过 N 天未 recall。
- 当前群聊讨论主题与某条 active memory 高相似。
- 某条记忆 `review_due_at` 已到期。

Metrics:

- Reminder Candidate Precision。
- Reminder Acceptance Rate。
- Reminder Dismiss Rate。
- Reminder Cooldown Violation Rate。
- Sensitive Reminder Leakage Rate。

### Evaluation Pipeline

Benchmark runner should support:

```text
1. 初始化测试数据库和 memory indexes。
2. 注入 raw events、curated memories、candidate memories、conflict updates。
3. 构建 curated memory embedding。
4. 执行 L1/L2/L3 query cascade。
5. 执行 OpenClaw Agent task prefetch cases。
6. 执行 heartbeat reminder cases。
7. 输出 machine-readable JSON / CSV。
8. 生成 reviewer-readable Markdown report。
```

Required report sections:

```text
1. Dataset overview
2. Recall quality metrics
3. Candidate detection metrics
4. Conflict update metrics
5. Multi-level memory latency and layer routing
6. OpenClaw prefetch evaluation
7. Heartbeat reminder evaluation
8. Evidence coverage and stale leakage
9. Failure examples and error analysis
10. Current limitations and next iteration plan
```

### Failure Analysis Requirements

Every failed benchmark case must record:

```text
case_id
input_events
query_or_task
expected_result
actual_result
failed_metric
retrieved_layer
retrieved_memory_ids
rerank_score
failure_reason
recommended_fix
```

Failure reason categories:

```text
candidate_not_detected
wrong_subject_normalization
wrong_layer_routing
vector_miss
keyword_miss
stale_value_leaked
evidence_missing
agent_did_not_prefetch
reminder_too_noisy
permission_scope_error
```

## 4. Technical Specifications

### Architecture Overview

Architecture principle:

```text
OpenClaw Agent 负责理解任务、选择工具、编排记忆调用。
Memory Copilot Core 负责记忆状态、分层召回、冲突更新和证据链。
Feishu / lark-cli / OpenAPI 负责办公数据接入和动作执行。
旧仓库实现只作为参考资产，不作为最终架构主干。
```

High-level architecture:

```text
Feishu Workspace
群聊 / 文档 / 任务 / 会议 / Bitable
        |
        v
OpenClaw Feishu Plugin
接收飞书消息、线程上下文、用户身份、Agent 事件
        |
        v
OpenClaw Agent Runtime
理解意图、判断任务类型、选择记忆工具、组织回复
        |
        v
Memory Orchestrator
决定查哪一层记忆、是否需要 prefetch、是否触发冲突检测
        |
        v
Multi-Level Memory System
L0 Working Context
L1 Hot Memory
L2 Warm Memory
L3 Cold Memory
        |
        v
Memory Governance
candidate / active / superseded / rejected / stale / archived
        |
        v
Memory Store & Indexes
raw_events / memories / versions / evidence / recall_logs
全文索引 / 结构化索引 / 向量索引
        |
        v
Feishu Action Layer
lark-cli / Feishu OpenAPI
发送卡片、读取文档、写 Bitable、回写确认状态
```

### Multi-Level Memory Architecture

Feishu Memory Copilot uses L0-L3 memory hierarchy:

| Level | 类比 | 内容 | 访问方式 | Target Latency | Purpose |
|---|---|---|---|---:|---|
| L0 Working Context | 当前寄存器 | 当前对话、当前任务、当前用户、当前飞书线程 | OpenClaw runtime context | 极低 | 保证当前任务不断片 |
| L1 Hot Memory | CPU cache | 当前项目 active memory、高频查询、最近确认的重要规则 | 内存 hot set / hot index | p95 <= 100ms MVP | 快速回答常见项目问题 |
| L2 Warm Memory | 内存 | 最近 2-7 天记忆、候选记忆、近期文档摘要、未关闭风险 | SQLite + FTS / lightweight vector index | p95 <= 500ms MVP | 覆盖近期协作上下文 |
| L3 Cold Memory | 硬盘 | 历史 raw events、旧版本、归档文档、长期证据 | 深度检索 / 异步检索 / rerank | p95 <= 2s 或异步 | 追溯历史和补全证据 |

### Query Cascade

Recall must not directly scan all memory records. It must use retrieval cascade:

```text
1. 读取 L0 当前任务上下文。
2. 查询 L1 Hot Memory。
3. 如果 L1 置信度足够，直接返回。
4. 如果 L1 不足，查询 L2 Warm Memory。
5. 如果 L2 仍不足，触发 L3 Cold Memory deep search。
6. 合并候选结果。
7. Rerank。
8. 返回 Top K with evidence。
9. 将高价值命中结果 promotion 到 L1 或 L2。
```

### Memory Data Model

Each memory must support:

```text
memory_id
tenant_id / organization_id
scope
source_chat_id
source_doc_id
type
subject
current_value
summary
status
layer
importance
confidence
version
evidence
last_recalled_at
recall_count
created_at
updated_at
review_due_at
expires_at
visibility_policy
```

Core statuses:

```text
candidate
active
superseded
rejected
stale
archived
```

Core types:

```text
decision
deadline
owner
workflow
preference
risk
security
document
meeting
customer
```

MVP real implementation types:

```text
decision
deadline
owner
workflow
risk
document
```

### Curated Memory Embedding

MVP must support vector retrieval, but only for curated memory. It must not vectorize all raw events.

Embedding objects:

```text
memory.subject
memory.current_value
memory.summary
evidence.quote
```

Not vectorized in MVP:

```text
所有 raw events
所有历史聊天全文
所有未筛选文档全文
```

Rationale:

- 减少存储浪费。
- 降低噪声。
- 提高检索质量。
- 控制 10 天开发范围。

### Hybrid Retrieval

MVP recall must combine:

```text
Structured filtering:
scope / tenant_id / status / layer / type

Keyword or full-text retrieval:
subject / current_value / evidence quote

Vector retrieval:
semantic similarity

Rerank:
importance / recency / confidence / version freshness / layer
```

Default strategy:

```text
先过滤 scope 和 active status
再执行 keyword + vector hybrid recall
最后根据状态、版本、证据和层级 rerank
```

### Promotion and Demotion

Promotion conditions:

```text
被频繁召回
被用户确认重要
与当前任务高度相关
涉及 deadline / deployment / risk
刚发生冲突更新
```

Demotion conditions:

```text
长期未召回
项目阶段结束
旧版本被 superseded
用户标记过期
超过 hot ttl
```

MVP must:

- 记录 `layer` 变化。
- 记录 `promotion_reason` / `demotion_reason`。
- 旧版本被覆盖后不再留在 Hot Memory 默认召回路径。

### OpenClaw Prefetch

Tool:

```text
memory.prefetch(task, scope, current_context)
```

Trigger examples:

```text
用户要求生成计划、总结、checklist、回复、报告、任务拆解
用户问题中出现项目关键词
当前任务涉及 deployment、deadline、owner、risk、decision
当前飞书线程有明确项目 scope
```

Context pack example:

```json
{
  "scope": "project:feishu_memory_copilot",
  "task": "deployment_checklist",
  "memories": [
    {
      "type": "workflow",
      "subject": "生产部署",
      "current_value": "必须加 --canary，region 使用 ap-shanghai",
      "version": 2,
      "evidence": "飞书群聊 2026-04-25"
    }
  ],
  "missing_context": [
    "审批人未确认"
  ]
}
```

### Heartbeat Reminder Prototype

MVP must implement heartbeat reminder prototype.

Trigger methods:

```text
OpenClaw heartbeat
scheduled check
manual /review_due
Agent task start pre-check
```

Candidate sources:

```text
review_due_at <= now
important memory N 天未被 recall
deadline 即将到期
当前飞书线程主题与 active memory 高相似
```

Gates:

```text
importance >= threshold
relevance >= threshold
cooldown 未命中
scope 权限允许
敏感内容已脱敏
```

MVP output:

```text
reminder candidate
飞书卡片或 dry-run log
Bitable reminder record 可选
```

### Integration Points

| Integration | Role | MVP Approach | Future Approach |
|---|---|---|---|
| OpenClaw Agent | 主入口、工具编排、prefetch、heartbeat | Tool schema + adapter | Native plugin/service integration |
| OpenClaw Feishu Plugin | 飞书 channel | Use for design and runnable flow if feasible | Primary Feishu channel |
| lark-cli | 快速飞书操作层 | Messages, docs, Bitable, dry-run | Keep for debug/demo |
| Feishu OpenAPI | 稳定生产 API | Selectively use when needed | High-frequency production path |
| Bitable | 评委可见台账 | Optional sync / demo table | Admin and review surface |
| Benchmark runner | 验证系统质量 | Required | CI / regression gate |

### Security & Privacy

MVP must implement minimum scope-based permission boundary:

```text
每条 memory 绑定 tenant_id / organization_id
每条 memory 绑定 scope
每条 memory 记录 source_chat_id / source_doc_id
默认只在同 scope 内召回
跨 scope 召回默认禁止
敏感字段脱敏
```

Reserved for future multi-tenant admin console:

```text
企业级多租户管理
部门级权限
项目级授权
跨群共享策略
审计日志
管理员后台
billing / quota
```

Sensitive content rules:

- 不在卡片中展示完整 token、secret、内部链接。
- 高风险记忆进入确认或复核。
- 安全、权限、客户、合同、生产变更相关记忆不得无确认自动 active。
- Recall 和 reminder 均必须经过 scope permission check。

### MVP Implementation Boundary

MVP must do:

```text
Multi-Level Memory data model
L0/L1/L2/L3 最小实现或模拟
query cascade
curated memory embedding
hybrid retrieval
promotion / demotion 字段和日志
OpenClaw Agent prefetch
heartbeat reminder prototype
scope-based permission boundary
```

MVP explicitly does not do:

```text
分布式缓存
完整多租户权限后台 UI
全量 raw events 向量化
完整泛企业知识库
生产级高可用部署
复杂个人化提醒策略
```

## 5. Risks & Roadmap

### Phased Rollout

#### MVP: 10-day initial round

Goal:

```text
OpenClaw-native Memory Copilot MVP 能在项目协作场景中跑通：
历史决策召回
企业级记忆候选识别
手动记忆
冲突更新
Agent 任务前 prefetch
heartbeat reminder prototype
Benchmark report
```

Required deliverables:

- `docs/feishu-memory-copilot-prd.md`
- Memory tool schema for OpenClaw.
- Multi-Level Memory Core minimal implementation.
- Curated memory embedding and hybrid retrieval.
- Heartbeat reminder prototype.
- OpenClaw Agent demo flow.
- Feishu card demo or dry-run.
- Benchmark report with MVP metrics.

#### v1.1: Product hardening

Goals:

- Improve Recall@3 toward 85%。
- Improve conflict update accuracy toward 90%。
- Expand reminder evaluation with real user feedback。
- Add stronger permission and audit logs。
- Add Bitable admin/review views。
- Improve OpenClaw Feishu plugin integration beyond CLI/debug bridge。

#### v2.0: Enterprise expansion

Goals:

- Multi-tenant admin console。
- Department/project permission management。
- Meeting/task/customer memory types。
- Cross-scope sharing policy。
- Production OpenAPI gateway。
- More sophisticated heartbeat and personalization。

### 10-day Roadmap

| Day | Focus | Output |
|---|---|---|
| D1 | PRD + architecture freeze | Final PRD, schema decisions, demo scope |
| D2 | OpenClaw tool schema + Memory Core interfaces | `agent_adapters/openclaw/`, tool JSON/spec docs |
| D3 | Multi-Level Memory data model | L0/L1/L2/L3 fields, migration, repository boundary |
| D4 | Hybrid retrieval + curated embedding | embedding index, keyword/vector merge, rerank |
| D5 | Candidate detection + manual memory | `memory.create_candidate`, confirm/reject, risk flags |
| D6 | Conflict update + version chain | superseded logic, stale leakage tests |
| D7 | OpenClaw prefetch flow | Agent task context pack, checklist demo |
| D8 | Heartbeat reminder prototype | reminder candidates, gates, card/dry-run output |
| D9 | Benchmark expansion | recall, candidate, conflict, layer, prefetch, reminder metrics |
| D10 | Demo freeze + report | demo runbook, benchmark report, whitepaper inputs |

### Technical Risks

| Risk | Impact | Mitigation |
|---|---|---|
| OpenClaw runtime integration takes longer than expected | MVP slips into old CLI demo | Define tool schema first; keep CLI/dry-run only as fallback, not architecture trunk |
| Vector retrieval quality is low | Recall@3 below target | Use hybrid retrieval and structured filters; only embed curated memory |
| Candidate detection creates too many false positives | 用户觉得系统乱记 | Require candidate confirmation and Candidate Precision benchmark |
| Heartbeat reminders become noisy | 用户关闭提醒 | Use gates: importance, relevance, cooldown, permission, sensitivity |
| Conflict update misses old values | 旧信息污染当前决策 | Add stale leakage benchmark and version trace coverage |
| Scope permission model too weak | 企业安全风险 | Implement scope boundary now; reserve tenant/visibility fields |
| 10-day scope too broad | 三大交付物不闭环 | Prioritize OpenClaw E2E flows, hybrid recall, conflict update, benchmark |

### Dependency Risks

| Dependency | Risk | Mitigation |
|---|---|---|
| OpenClaw Feishu plugin | setup or runtime instability | Keep lark-cli/OpenAPI fallback for Feishu actions |
| lark-cli | profile/token/permission failures | Document profile setup and dry-run path |
| Feishu OpenAPI | permission approval delays | Use fixture and existing test group where possible |
| Embedding model | cost or local availability | Use lightweight/local embedding first; keep keyword fallback |
| Bitable | field schema/API instability | Bitable is review surface, not source of truth |

### Acceptance Criteria for MVP Freeze

MVP can freeze for demo when:

- `Recall@3 >= 60%` on project collaboration benchmark.
- `Conflict Update Accuracy >= 70%`.
- `Evidence Coverage >= 80%`.
- `Candidate Precision >= 60%`.
- L1 Hot Recall p95 <= 100ms on local benchmark.
- Sensitive reminder leakage is 0.
- At least 2 OpenClaw Agent E2E flows run:
  - Historical decision query.
  - Conflict update.
  - Agent task prefetch.
- Benchmark report includes failure analysis and current limitations.
- Demo can explain why this is not ordinary search:
  - Multi-level memory.
  - Active/superseded lifecycle.
  - Evidence chain.
  - OpenClaw Agent prefetch.
  - Heartbeat reminder prototype.

### Final Evaluation Narrative

答辩叙事应避免只说“我们做了一个搜索”。推荐表达：

```text
普通搜索只能找文本。
Feishu Memory Copilot 能判断哪条是当前有效记忆。

普通数据库只能存历史。
Feishu Memory Copilot 能维护 hot/warm/cold 多级记忆。

普通 Bot 只能被动回答。
Feishu Memory Copilot 能通过 OpenClaw Agent prefetch 和 heartbeat 主动帮助用户。

普通 RAG 容易把旧信息混进答案。
Feishu Memory Copilot 用 version chain 和 stale leakage 指标证明旧值不会污染当前决策。
```

