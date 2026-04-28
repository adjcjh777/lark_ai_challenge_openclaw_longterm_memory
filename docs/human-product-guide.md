# Feishu Memory Copilot 人类阅读指南

日期：2026-04-28
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
- OpenClaw Agent runtime 已有受控证据；`memory.*` first-class 原生工具注册也已有本机插件证据。
- 飞书测试群 live sandbox 已接入 Copilot path，但不是生产 live。
- Cognee / Ollama live embedding gate 已通过，但不是长期 embedding 服务。

不能说已经完成：

- 生产部署。
- 全量接入 Feishu workspace。
- OpenClaw Feishu websocket 已 running。
- 完整多租户后台。
- 审计 UI、管理员配置和长期运维。
- 长期 embedding 服务。

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

当前仓库已经实现了中间的 Copilot Core、schema、benchmark、demo、受控接入证据和 OpenClaw first-class 工具注册；上线前还要补 Feishu websocket running、真实权限和生产运维。

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
记住：生产部署必须加 --canary，region 用 ap-shanghai。
```

系统应该调用 `memory.create_candidate`，生成 candidate。真实飞书来源不会自动 active。

### 确认候选

reviewer 说：

```text
/confirm <candidate_id>
```

系统通过 `memory.confirm` 把 candidate 变成 active，并写 audit record。

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

## 人类接手后先做什么

1. 先读 [README.md](../README.md) 顶部任务区，确认当前阶段。
2. 再读 [docs/README.md](README.md)，找到你要看的文档分区。
3. 读 [productization/launch-polish-todo.md](productization/launch-polish-todo.md)，按顺序挑下一项。
4. 读 [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)，按任务类型选择验证命令。
5. 做完后更新 README、handoff、飞书看板、验证结果和 commit。

## 当前最重要的下一步

按优先级：

1. 补 OpenClaw Feishu websocket running 证据。
2. 把 demo 权限模型升级为真实飞书权限映射。
3. 做生产存储、索引、迁移和审计查询方案。
4. 扩大真实 Feishu ingestion，但继续坚持 candidate-only。
5. 把真实飞书消息进入 OpenClaw Agent 再自然选择 memory tool 的端到端证据补齐。

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
