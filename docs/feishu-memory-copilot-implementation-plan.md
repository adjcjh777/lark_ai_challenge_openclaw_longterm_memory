# Feishu Memory Copilot Implementation Plan

日期：2026-04-26
适用周期：2026-04-26 至 2026-05-07
状态：Active master implementation plan
依据文档：`AGENTS.md`、`docs/archive/legacy-master/competition-master-execution-plan.md`、`docs/feishu-memory-copilot-prd.md`、`docs/copilot-product-question-log.md`、当前仓库代码结构

## 1. 执行目标

本轮重构的目标是把项目从 CLI-first memory demo 转成 OpenClaw-native Feishu Memory Copilot：OpenClaw Agent 作为主入口和工具编排层，Cognee 作为开源知识/记忆引擎核心，Memory Copilot Core 作为企业记忆治理层，飞书、lark-cli、Feishu OpenAPI 作为办公数据和动作集成层，Bitable 和 card 作为展示与交互层。

MVP 必须在 2026-04-26 到 2026-05-02 这一周内完成可演示闭环，至少覆盖历史决策召回、候选记忆生成、冲突更新、版本解释、Agent 任务前预取和 heartbeat reminder prototype。

2026-05-03 到 2026-05-05 已完成初赛证明层：Benchmark Report、Demo runbook、README 快速开始和《Memory 定义与架构白皮书》初稿。2026-05-06 起主线升级为完整产品推进路线：先保护初赛提交闭环，再做 Productization Baseline RFC 和 Storage + Permission Contract Freeze，后续再进入 OpenClaw live bridge、Feishu review surface、limited Feishu ingestion、heartbeat、deployability 和 Product QA。初赛三大交付物仍必须保留并可提交：《Memory 定义与架构白皮书》、可运行 Demo、自证 Benchmark Report；但它们不再替代完整产品路线。

当前日期和阶段确认：

- 今天是 2026-04-27。
- 总控文档原时间线中 2026-04-26 对应 D3，但 PRD 已经把路线调整为从 2026-04-26 起一周完成 Feishu Memory Copilot MVP。
- 后续执行以 PRD 的 OpenClaw-native Copilot 架构为主线；旧 Day1-Day7 产物只作为参考资产和兜底能力。
- 2026-04-27 起项目改为程俊豪单人执行；原先拆出去的评测样例、文案、QA、截图和材料检查全部并入程俊豪的“我的补充任务”。

### 1.1 OpenClaw 版本基线

OpenClaw CLI 已升级并固定为 `2026.4.24`（`openclaw --version` 显示 `OpenClaw 2026.4.24 (cbcfdf6)`）。后续 OpenClaw adapter、tool schema、skill、examples、demo flow 和 runtime 联调全部基于该版本开发，不再随 npm `latest` 自动漂移。

版本锁文件：`agent_adapters/openclaw/openclaw-version.lock`。

固定规则：

1. 后续不要运行 `openclaw update`、`npm update -g openclaw` 或 `npm install -g openclaw@latest`。
2. 如需恢复本机版本，只使用 exact version：`npm i -g openclaw@2026.4.24 --no-fund --no-audit`。
3. OpenClaw 相关开发和验收前运行：`python3 scripts/check_openclaw_version.py`。
4. 若未来必须升级 OpenClaw，必须先更新锁文件、AGENTS、主控计划和当日计划，再重新跑基础验证。

### 1.1.1 完整产品路线基线

2026-04-27 的 `$deep-interview` 和 `$ralplan` 已把后续目标从“零散 Demo / 提交材料收尾”提升为“PRD 定义下的完整产品”。批准后的产品化计划已经落到仓库可追踪文档：

- `docs/productization/complete-product-roadmap-prd.md`
- `docs/productization/complete-product-roadmap-test-spec.md`

路线采用 **Proof MVP -> Contracted Live Slice -> Controlled Productization**：

1. **Phase 0 Submission Freeze Preservation**：保护 2026-05-06 / 2026-05-07 初赛提交闭环，README、Demo、Benchmark Report、白皮书、录屏/截图不被产品化探索破坏。
2. **Phase 0.5 Productization Baseline RFC**：把 dry-run、replay、OpenClaw live bridge、limited Feishu ingestion、productized live 的区别写清楚；只做文档和验收基线，不写代码。
3. **Phase 1 Storage + Permission Contract Freeze**：先冻结 `tenant_id`、`organization_id`、`visibility_policy`、permission context、service permission decision、OpenClaw payload、audit fields 和 negative permission cases。Phase 1 通过前不启动 `$team` 并行实现。
4. **Phase 2 OpenClaw Live Bridge**：OpenClaw 真实调用本地/seed Copilot service，但不能称为 Feishu live ingestion。
5. **Phase 3 Feishu UI / Review Surface**：Feishu card、Bitable 和文档页只消费 Copilot service 的 permission-aware output，不做 source of truth。
6. **Phase 4 Limited Feishu Ingestion**：指定飞书来源只进入 candidate pipeline，不自动 active。
7. **Phase 5-7**：heartbeat controlled reminder、deployability/healthcheck、Product QA 和 no-overclaim claim audit。

硬规则：真实多租户权限不能再只停留在字段预留；missing permission context 必须 fail closed；`memory.confirm`、`memory.reject`、`memory.explain_versions`、`memory.prefetch`、heartbeat 等动作都要进入 service-action permission matrix。

### 1.1.2 Cognee / RightCode 本地接入基线

2026-04-27 本地 spike 采用 `cognee==0.1.20`，并锁定 `httpx==0.27.2` 以避开 Cognee 依赖链中 OpenAI SDK 与 `httpx 0.28.x` 的兼容问题。Cognee 数据目录固定为项目内 `.data/cognee/`，不得提交。

RightCode custom provider 当前用于 LLM 文本模型验证：`gpt-5.3-codex-high` 的最小 chat completion 已验证可返回结果。RightCode 不提供可用 embedding；当前 RightCode `/embeddings` 对 `text-embedding-3-large` 返回 `PermissionDeniedError: Your request was blocked.`，所以 embedding 改为本地 Ollama。

本地 embedding 基线锁定在 `memory_engine/copilot/embedding-provider.lock`：默认 `qwen3-embedding:0.6b-fp16`，LiteLLM 名称 `ollama/qwen3-embedding:0.6b-fp16`，endpoint `http://localhost:11434`，维度 `1024`。选择理由：Qwen3-Embedding 模型卡给出的 multilingual MTEB 为 64.33、C-MTEB 为 66.33，高于同体量 BGE-M3 的 multilingual MTEB 59.56；官方 Ollama 包体约 1.2GB，适合 16GB Mac mini 和 Windows 备用环境复现。`bge-m3:567m` 只作为备选，`qwen3-embedding:4b-fp16` 虽然质量更高但官方 F16 包体约 8GB，MVP 不作为默认。

2026-04-27 复测结论：清理旧 `.data/cognee/` 里 3072 维向量表后，`LLM_PROVIDER=custom` + RightCode `gpt-5.3-codex-high` + Ollama `qwen3-embedding:0.6b-fp16` 已跑通 Cognee `add -> cognify -> search` 真实闭环。复现时优先运行 `scripts/check_embedding_provider.py`，再运行 `scripts/spike_cognee_local.py --reset-local-data`。

## 1.2 每日任务启动 Prompt

本节是每天开新对话时的复制粘贴入口，已经按 2026-04-27 之后的单人执行状态和 2026-05-06 起的完整产品路线更新。每天启动任务前，Agent 必须先判断“今天是哪一天、这一天计划是否已经完成、当前代码和看板处于什么状态”，再决定继续执行、补齐遗漏，还是只做计划/看板修正。

如果任务目标是继续推进完整产品，而不是只修提交材料，请优先读取：

1. `docs/productization/complete-product-roadmap-prd.md`
2. `docs/productization/complete-product-roadmap-test-spec.md`
3. 当前日期的 `docs/plans/YYYY-MM-DD-implementation-plan.md`

当前阶段的安全顺序是：Phase 0/0.5 文档和提交保护 -> Phase 1 契约冻结 -> Phase 2 OpenClaw live bridge -> Phase 3 Feishu review surface -> Phase 4 limited Feishu ingestion。不要跳过 Phase 1 直接接真实飞书数据。

当前适用规则：

- 项目从 2026-04-27 起按程俊豪单人执行；不再创建、指派或等待非本人任务。
- 原先拆出去的评测样例、文案、QA、截图和材料检查，全部转为“我的补充任务”或后续自查任务。
- README 顶部任务区、日期计划、handoff 和飞书共享看板必须保持同一口径。
- 飞书共享看板可直接用 `lark-cli` 更新；只维护程俊豪任务，不覆盖无关历史记录。
- 验证命令按改动类型选择：所有提交前至少运行 `python3 scripts/check_openclaw_version.py` 和 `git diff --check`；只有触达代码、脚本、schema、benchmark runner、测试数据或 legacy fallback 时，才追加对应专项验证。

### 直接启动今天任务

每天开工时优先复制这一段。如果系统日期正确，Agent 应自动定位当天的 `docs/plans/YYYY-MM-DD-implementation-plan.md`；如果当天任务已完成，Agent 不应重复实现，而应先报告完成证据和下一项可执行任务。

```text
工作目录：/Users/junhaocheng/feishu_ai_challenge

请开始执行今天的 Feishu Memory Copilot 任务。先判断今天计划是否已经完成，再决定继续执行、补齐遗漏或更新计划/看板。

必须先读取并遵循：
1. AGENTS.md
2. docs/feishu-memory-copilot-implementation-plan.md
3. 按当前日期定位的 docs/plans/YYYY-MM-DD-implementation-plan.md
4. 如果存在上一日 handoff 或当天 handoff，也读取对应 docs/plans/YYYY-MM-DD-handoff.md
5. README.md 顶部“今天先做这个：我的任务”
6. git status --short
7. 当前代码结构，尤其是 memory_engine/、memory_engine/copilot/、agent_adapters/openclaw/、benchmarks/、tests/、docs/

启动前先做状态确认：
- 复述今天的绝对日期、阶段、当日目标、“今日做到什么程度”、“今日不做”和“我的补充任务”。
- 检查 OpenClaw 版本锁，运行：python3 scripts/check_openclaw_version.py
- 检查工作树状态，不要覆盖用户或历史未跟踪文件。
- 检查飞书共享看板是否需要创建或更新今天的程俊豪主线任务和“我的补充任务”；如需同步，直接按 AGENTS.md 用 lark-cli 更新并读回确认。
- 如果发现今天任务已完成，不要重复写代码；先总结已完成证据，并只处理用户最新要求或计划中仍未闭环的事项。

执行要求：
- 严格按当天计划里的“今日执行清单（按顺序）”推进。
- 只做当天计划范围内的任务，不扩展到“今日不做”的事项。
- 新功能优先进入 memory_engine/copilot/ 和 agent_adapters/openclaw/。
- 不要从大改 memory_engine/repository.py、memory_engine/feishu_runtime.py 或旧 CLI/Bot handler 开始。
- 如果补充任务、handoff 或 README 顶部任务发生变化，同步更新文档和飞书共享看板。
- 每完成一个可运行闭环、阶段交付或关键文档更新后，按 AGENTS.md 选择验证命令、提交并推送。

验证规则：
- 所有提交前至少运行：
  python3 scripts/check_openclaw_version.py
  git diff --check
- 如果改了 Python 代码、脚本、OpenClaw schema、benchmark runner、测试数据或 fixture，追加：
  python3 -m compileall memory_engine scripts
- 如果改了 Copilot schema/tools/retrieval/benchmark，追加当天计划指定的 unittest 或 copilot_* benchmark。
- 只有触达 legacy fallback、旧 Bot、旧 CLI、本地 repository、文档摄取、Bitable 同步或历史 benchmark runner 时，才追加：
  python3 -m memory_engine benchmark run benchmarks/day1_cases.json
- 如果运行 Cognee / embedding / Ollama 相关验证，结束前必须执行 ollama ps，并停止本项目拉起的驻留模型。

最终回复请包含：
- 今天完成了什么
- 新增/修改文件
- 验证结果
- 飞书共享看板同步结果
- Ollama 清理状态（如本次未运行 embedding，也说明未拉起模型）
- 仍未实现或仍有风险的事项
- 下一步应该从哪个文件继续
```

### 指定日期启动任务

如果要补做某一天，或当天系统日期不准，复制下面这段并把 `YYYY-MM-DD` 改成目标日期，例如 `2026-04-28`。

```text
工作目录：/Users/junhaocheng/feishu_ai_challenge
目标日期：YYYY-MM-DD

请执行目标日期对应的 Feishu Memory Copilot 每日任务。先判断该日期任务是否已经完成，再决定继续执行、补齐遗漏或只更新计划/看板。

必须先读取并遵循：
1. AGENTS.md
2. docs/feishu-memory-copilot-implementation-plan.md
3. docs/plans/YYYY-MM-DD-implementation-plan.md
4. 如果存在上一日 handoff 或该日期 handoff，也读取对应 docs/plans/YYYY-MM-DD-handoff.md
5. README.md 顶部“今天先做这个：我的任务”
6. git status --short
7. 当前代码结构，尤其是 memory_engine/、memory_engine/copilot/、agent_adapters/openclaw/、benchmarks/、tests/、docs/

执行要求：
- 先复述目标日期的阶段、当日目标、“今日做到什么程度”、“今日不做”和“我的补充任务”。
- 运行 python3 scripts/check_openclaw_version.py，确认 OpenClaw 仍固定为 2026.4.24。
- 如果代码现状与日期计划不一致，以当前代码为事实源；不要擅自扩大范围，必要时先更新该日期计划或 handoff 记录偏差。
- 如果该日期任务已完成，不要重复实现；只补遗漏的验证、文档、看板或用户最新指定事项。
- 严格按该日期计划里的“今日执行清单（按顺序）”推进。
- 新功能优先进入 memory_engine/copilot/ 和 agent_adapters/openclaw/。
- 不要从大改 memory_engine/repository.py、memory_engine/feishu_runtime.py 或旧 CLI/Bot handler 开始。
- 若补充任务、README 顶部入口或看板任务发生变化，必须同步更新。
- 完成后按 AGENTS.md 选择验证命令、提交并推送。

验证规则：
- 所有提交前至少运行：
  python3 scripts/check_openclaw_version.py
  git diff --check
- 触达代码、脚本、schema、benchmark runner、测试数据或 fixture 时追加 compileall 和当天计划里的专项测试。
- 触达 legacy fallback 或旧 benchmark runner 时才追加 day1 benchmark。
- 运行 Cognee / embedding / Ollama 后，必须检查并清理本项目驻留模型。

最终回复请包含：
- 目标日期任务完成情况
- 新增/修改文件
- 验证结果
- 飞书共享看板同步结果
- 未完成风险或降级说明
- 下一步应该从哪个文件继续
```

### 只做计划复核或计划修正

如果当天不想让 Agent 直接改代码，只想检查计划是否足够细，可以复制这一段。

```text
工作目录：/Users/junhaocheng/feishu_ai_challenge

请只复核今天的每日 implementation plan，不要开始实现代码。

必须先读取：
1. AGENTS.md
2. docs/feishu-memory-copilot-implementation-plan.md
3. 按当前日期定位的 docs/plans/YYYY-MM-DD-implementation-plan.md
4. README.md 顶部“今天先做这个：我的任务”
5. git status --short

请检查：
- 当日目标是否具体，是否能在当天闭环。
- “今日做到什么程度”是否可验收。
- “今日执行清单”是否写到文件路径、模块边界和完成标准。
- 验证命令是否按改动类型选择，避免把 day1 legacy benchmark 当成所有任务的默认主验收。
- “我的补充任务”是否能由程俊豪独立执行，是否仍残留非本人负责或等待他人完成的说法。
- README 顶部任务、日期计划、handoff 和飞书共享看板是否需要同步。
- “今日不做”是否足够防止范围扩散。

如需修改，只更新文档和必要的看板说明，不写实现代码。完成后至少运行：
python3 scripts/check_openclaw_version.py
git diff --check

如果计划修正改变了 benchmark 口径、依赖锁、OpenClaw/Cognee 约束或验证命令，再追加对应专项验证。最后按 AGENTS.md 提交并推送。
```

## 2. 架构落地原则

1. 先新增 `memory_engine/copilot/`，不直接破坏旧实现。
2. 旧实现继续作为 reference / fallback，包括 SQLite 经验、benchmark 样例、Feishu Bot / card 经验、Bitable 台账经验、文档 ingestion 经验和 Day1 本地闭环验证经验。
3. OpenClaw tools schema 先行，先冻结工具契约，再实现内部模块。
4. Cognee 是当前选定的 memory 系统核心；通过窄 adapter 调用其本地知识/记忆引擎能力，不把 Cognee API 散落在产品代码里。
5. Memory Copilot Core 自研企业记忆治理：candidate / active / superseded / rejected / stale / archived、evidence、version、permission、OpenClaw tools、Feishu review surface 和 Benchmark 都归本项目负责。
6. Memory Core 不写死在 CLI、Bot handler 或 lark-cli 调用里。
7. 所有入口：OpenClaw、CLI、Bot、Benchmark 后续都应调用同一套 Copilot Core。
8. 向量检索只针对 curated memory，不向量化全部 raw events。
9. Heartbeat 主动提醒进入 MVP，但先做 reminder candidate + card/dry-run，不做复杂个性化推送。
10. 不做分布式缓存。
11. 不做完整多租户权限后台 UI，但数据模型预留 `tenant_id`、`organization_id`、`visibility_policy`。
12. 旧模块不一次性迁移或删除；MVP 稳定后再决定哪些旧路径迁移、废弃或保留为兼容入口。

## 3. 目标目录结构

本轮 MVP 目标结构如下。每日执行应优先读取本主控计划和 `docs/plans/YYYY-MM-DD-implementation-plan.md`，再按日期计划创建或修改对应代码文件。

```text
memory_engine/
  copilot/
    __init__.py
    schemas.py
    service.py
    orchestrator.py
    cognee_adapter.py
    retrieval.py
    embeddings.py
    governance.py
    heartbeat.py
    permissions.py
    tools.py

agent_adapters/
  openclaw/
    memory_tools.schema.json
    feishu_memory_copilot.skill.md
    examples/
      historical_decision_search.json
      conflict_update_flow.json
      task_prefetch_flow.json

tests/
  test_copilot_schemas.py
  test_copilot_tools.py
  test_copilot_retrieval.py
  test_copilot_governance.py
  test_copilot_prefetch.py
  test_copilot_heartbeat.py

benchmarks/
  copilot_recall_cases.json
  copilot_candidate_cases.json
  copilot_conflict_cases.json
  copilot_layer_cases.json
  copilot_prefetch_cases.json
  copilot_heartbeat_cases.json
```

模块边界：

| 文件 | 职责 | 不应承担 |
|---|---|---|
| `memory_engine/copilot/schemas.py` | 定义工具输入输出、memory、evidence、candidate、context pack、reminder candidate 的 dataclass / typed schema | 不直接访问 SQLite，不调用 lark-cli |
| `memory_engine/copilot/service.py` | Copilot Core 应用服务，承接 search、create_candidate、confirm、reject、versions、prefetch | 不解析 OpenClaw runtime，不生成飞书卡片，不把 Cognee API 泄漏给入口层 |
| `memory_engine/copilot/orchestrator.py` | 决定 L0-L3 query cascade、prefetch、冲突更新和 heartbeat 的编排顺序 | 不直接做底层 SQL，不直接拼 Cognee 原始返回 |
| `memory_engine/copilot/cognee_adapter.py` | 封装 Cognee 本地 memory engine，负责 dataset 命名、remember/recall 或 add/cognify/search 调用、结果规范化 | 不维护 Copilot 状态机，不直接生成 Feishu 文案 |
| `memory_engine/copilot/retrieval.py` | 结构化过滤、关键词/全文召回、向量召回、merge、rerank、Top K | 不改变记忆状态 |
| `memory_engine/copilot/embeddings.py` | curated memory embedding 构建、轻量相似度计算、embedding cache | 不 embed raw events |
| `memory_engine/copilot/governance.py` | candidate / active / superseded / rejected / stale / archived 状态机、冲突判断、版本链 | 不生成 UI |
| `memory_engine/copilot/heartbeat.py` | review_due、deadline、长期未 recall、当前线程相关提醒的候选生成和门控 | 不直接发送真实飞书消息 |
| `memory_engine/copilot/permissions.py` | scope、tenant、organization、visibility policy、敏感信息脱敏 | 不决定业务召回排序 |
| `memory_engine/copilot/tools.py` | OpenClaw tool handler 与统一错误格式，对接 `service.py` | 不绕过 service 直接写库 |
| `agent_adapters/openclaw/memory_tools.schema.json` | OpenClaw 可调用工具的 JSON schema | 不塞业务规则 |
| `agent_adapters/openclaw/feishu_memory_copilot.skill.md` | 给 OpenClaw Agent 的使用说明和 progressive disclosure 示例 | 不重复实现 Python 逻辑 |

## 4. OpenClaw 工具接口计划

统一错误格式：

```json
{
  "ok": false,
  "error": {
    "code": "scope_required",
    "message": "scope is required",
    "retryable": false,
    "details": {}
  }
}
```

MVP 错误码：

| code | 含义 | 典型处理 |
|---|---|---|
| `scope_required` | 缺少 scope | Agent 补传当前项目或飞书线程 scope |
| `permission_denied` | 当前用户或线程无权限访问该 scope | Agent 不展示记忆内容，只提示权限不足 |
| `memory_not_found` | 未找到 memory 或 candidate | Agent 说明无匹配并建议创建候选 |
| `candidate_not_confirmable` | candidate 已 active / rejected / archived | Agent 展示当前状态 |
| `validation_error` | 输入字段不合法 | Agent 修正工具调用参数 |
| `sensitive_content_blocked` | 内容包含 secret / token / 高风险敏感信息 | 进入人工复核或脱敏 |
| `internal_error` | 未分类异常 | 记录日志，返回可读失败原因 |

### 4.1 `memory.search`

用途：查询当前有效的 curated memory，默认只返回 `active`。

输入字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `query` | string | 是 | 用户自然语言问题 |
| `scope` | string | 是 | 例如 `project:feishu_ai_challenge`、`chat:<chat_id>` |
| `top_k` | integer | 否 | 默认 3，MVP 最大 10 |
| `filters` | object | 否 | `type`、`layer`、`status`，默认 `status=active` |
| `current_context` | object | 否 | L0 当前会话、飞书线程、任务上下文 |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 是否成功 |
| `query` | string | 原始 query |
| `scope` | string | 实际检索 scope |
| `results` | array | Top K memory |
| `results[].memory_id` | string | memory id |
| `results[].type` | string | decision / deadline / owner / workflow / risk / document |
| `results[].subject` | string | 主题 |
| `results[].current_value` | string | 当前有效值 |
| `results[].status` | string | 默认 active |
| `results[].version` | integer | 当前版本 |
| `results[].layer` | string | L1 / L2 / L3 |
| `results[].score` | number | rerank 后分数 |
| `results[].evidence` | object | `source_type`、`source_id`、`quote`、`created_at`、`actor_id` |
| `trace` | object | cascade、召回来源、merge/rerank 摘要 |

内部模块：

- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/permissions.py`
- 旧 `memory_engine/repository.py` 作为第一阶段 storage adapter / fallback

MVP 验收方式：

- `tests/test_copilot_tools.py` 验证工具输入输出和错误格式。
- `tests/test_copilot_retrieval.py` 验证默认只返回 active，superseded 不作为当前答案。
- `benchmarks/copilot_recall_cases.json` 达到 Recall@3 >= 60%、Evidence Coverage >= 80%。

### 4.2 `memory.create_candidate`

用途：从用户显式记忆、飞书消息、文档、OpenClaw 当前上下文或 benchmark fixture 中生成候选记忆。

输入字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 待判断内容 |
| `scope` | string | 是 | 记忆归属 scope |
| `source` | object | 是 | `source_type`、`source_id`、`actor_id`、`created_at`、`quote` |
| `current_context` | object | 否 | 当前线程、任务、已有 L0 context |
| `auto_confirm` | boolean | 否 | MVP 默认 false；低风险手动记忆可配置为 true，但仍过 governance |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 是否成功 |
| `candidate` | object | 候选记忆 |
| `candidate.memory_id` | string | candidate id |
| `candidate.type` | string | 类型 |
| `candidate.subject` | string | 主题 |
| `candidate.current_value` | string | 值 |
| `candidate.summary` | string | 摘要 |
| `candidate.confidence` | number | 置信度 |
| `candidate.importance` | number | 重要性 |
| `candidate.status` | string | candidate / active |
| `candidate.evidence` | object | 强制证据 |
| `risk_flags` | array | `sensitive`、`conflict`、`low_confidence` 等 |
| `conflict` | object/null | old -> new 覆盖关系 |

内部模块：

- `service.py`
- `governance.py`
- `permissions.py`
- `retrieval.py`，用于同 scope 同 subject 冲突查找
- 旧 `document_ingestion.py` 可作为文档候选提取 fallback

MVP 验收方式：

- `tests/test_copilot_governance.py` 验证候选必须带 evidence。
- `benchmarks/copilot_candidate_cases.json` 达到 Candidate Precision >= 60%。
- 高风险内容不得无确认自动 active。

### 4.3 `memory.confirm`

用途：把 candidate 确认为 active，必要时把旧 active 版本转为 superseded。

输入字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `candidate_id` | string | 是 | 待确认 candidate |
| `scope` | string | 是 | 权限校验 |
| `actor_id` | string | 是 | 确认人 |
| `reason` | string | 否 | 确认理由 |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 是否成功 |
| `memory_id` | string | active memory id |
| `status` | string | active |
| `version` | integer | 当前版本号 |
| `superseded` | object/null | 被覆盖的旧版本 |
| `evidence` | object | 确认证据和原始来源证据 |

内部模块：

- `tools.py`
- `service.py`
- `governance.py`
- `permissions.py`

MVP 验收方式：

- 单测验证 candidate -> active。
- 冲突 candidate confirm 后旧版本进入 superseded。
- Bitable / card 层能展示确认后的状态和版本。

### 4.4 `memory.reject`

用途：拒绝 candidate，保留审计记录，默认不进入 recall。

输入字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `candidate_id` | string | 是 | 待拒绝 candidate |
| `scope` | string | 是 | 权限校验 |
| `actor_id` | string | 是 | 拒绝人 |
| `reason` | string | 否 | 拒绝理由 |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 是否成功 |
| `memory_id` | string | candidate id |
| `status` | string | rejected |
| `reason` | string | 拒绝理由 |

内部模块：

- `service.py`
- `governance.py`
- `permissions.py`

MVP 验收方式：

- `tests/test_copilot_governance.py` 验证 rejected 不进入 search / prefetch。
- `memory.search` 对同 query 不返回 rejected。

### 4.5 `memory.explain_versions`

用途：解释某条 memory 的版本链、覆盖关系和证据来源。

输入字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `memory_id` | string | 是 | memory id |
| `scope` | string | 是 | 权限校验 |
| `include_archived` | boolean | 否 | 默认 false |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 是否成功 |
| `memory_id` | string | memory id |
| `active_version` | object | 当前版本 |
| `versions` | array | 所有可见版本 |
| `versions[].status` | string | active / superseded / stale / archived |
| `versions[].value` | string | 版本值 |
| `versions[].supersedes_version_id` | string/null | 覆盖关系 |
| `versions[].evidence` | object | 来源证据 |
| `explanation` | string | 给 Agent 使用的简短解释 |

内部模块：

- `service.py`
- `governance.py`
- `permissions.py`
- 旧 `repository.versions()` 可作为初版 adapter

MVP 验收方式：

- `benchmarks/copilot_conflict_cases.json` 验证 Version Trace Coverage。
- 冲突更新后，默认 search 返回新值，explain_versions 能看到旧值被 superseded。

### 4.6 `memory.prefetch`

用途：OpenClaw Agent 执行任务前预取项目上下文，返回 compact context pack。

输入字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task` | string | 是 | 例如 `deployment_checklist`、`weekly_report` |
| `scope` | string | 是 | 项目或线程 scope |
| `current_context` | object | 是 | L0 当前消息、任务类型、用户意图、线程主题 |
| `top_k` | integer | 否 | 默认 5 |

输出字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 是否成功 |
| `context_pack` | object | Agent 可直接使用的上下文包 |
| `context_pack.memories` | array | active memory 列表 |
| `context_pack.missing_context` | array | 尚缺信息 |
| `context_pack.risks` | array | 可能影响任务的风险 |
| `context_pack.evidence_summary` | array | 来源摘要 |
| `trace` | object | prefetch 触发原因和召回路径 |

内部模块：

- `service.py`
- `orchestrator.py`
- `retrieval.py`
- `permissions.py`

MVP 验收方式：

- `tests/test_copilot_prefetch.py` 覆盖 checklist / report / meeting prep 三类任务。
- `benchmarks/copilot_prefetch_cases.json` 达到 Agent Task Context Use Rate >= 70%、Prefetch Relevance@3 >= 60%。

### 4.7 未来预留工具

| 工具 | 用途 | MVP 处理 |
|---|---|---|
| `memory.search_hot` | 只查 L1 Hot Memory | 暂不暴露，先由 `memory.search` trace 展示 L1 命中 |
| `memory.search_recent` | 查 L2 Warm Memory | 暂不暴露 |
| `memory.search_deep` | 触发 L3 Cold Memory 深度检索 | 暂不暴露，可在 no match 时由 orchestrator 内部调用 |
| `memory.promote` | 手动提升重要记忆到 Hot Memory | 预留 schema |
| `memory.review_due` | 查找需要复核的记忆 | D7 heartbeat 可先内部实现，后续工具化 |
| `memory.proactive_check` | heartbeat 主动提醒判断 | MVP 内部 prototype，初赛后再稳定为工具 |

## 5. Multi-Level Memory 实施计划

### 5.1 L0-L3 定义

| Level | 名称 | 内容 | MVP 落点 | 默认召回策略 |
|---|---|---|---|---|
| L0 | Agent Working Context | 当前 OpenClaw session、当前飞书线程、当前任务上下文、当前用户意图 | `schemas.WorkingContext`，由 OpenClaw adapter / CLI dry-run 传入 | 只作为 query expansion 和 rerank 信号，不长期存储 |
| L1 | Hot Memory | 当前项目、当前群聊、当前任务最相关 active memory | 单机 hot set + SQLite `layer='L1'` 标记 | 优先查，p95 <= 100ms |
| L2 | Warm Memory | 最近 2-7 天项目记忆、candidate、近期文档抽取、未关闭风险 | SQLite + FTS / lightweight vector index，`layer='L2'` | L1 不足时查 |
| L3 | Cold Memory | 历史版本、raw events、旧 evidence、归档文档 | SQLite raw_events / versions / archived docs，`layer='L3'` | 只在追溯、解释版本或 L1/L2 不足时查 |

### 5.2 Query Cascade

```text
L0 current_context
  -> scope / permission check
  -> L1 hot memory search
  -> if enough confidence: return candidate set
  -> L2 warm memory search
  -> if still insufficient: L3 cold search
  -> merge
  -> rerank
  -> enforce evidence
  -> Top K
  -> promotion / demotion side effects
```

关键要求：

- cascade 不能直接扫描所有 memory records。
- 默认 `memory.search` 只返回 `active`。
- L3 raw events 只用于追溯和补证据，不作为默认答案直接返回。
- Top K 每条结果必须带 evidence；缺 evidence 的结果降权或被过滤。

### 5.3 Promotion Policy

提升到更热层的条件：

- 被频繁 recall，例如 24 小时内 recall_count >= 3。
- 用户确认重要，例如 card 点击“标记重要”或 confirm reason 包含长期规则。
- 与当前任务高度相关，例如 prefetch 使用后 Agent 输出引用该记忆。
- 涉及 deadline、deployment、risk、security。
- 刚发生冲突更新，避免旧值再次污染任务。

MVP 实现：

- 在 memory row 上增加或模拟 `layer`、`promotion_reason`、`last_promoted_at`。
- 第一版可以通过 adapter 字段或迁移脚本扩展 SQLite；不直接重写旧 repository。

### 5.4 Demotion Policy

降级到更冷层的条件：

- 长期未 recall，超过 hot TTL。
- 项目阶段结束。
- 旧版本被 superseded。
- 用户标记过期。
- 超过 `expires_at` 或 `review_due_at` 未通过复核。

MVP 实现：

- active memory 可从 L1 降到 L2。
- superseded 版本默认进入 L3 / cold。
- rejected 不参与 recall。
- archived 只用于审计和版本解释。

### 5.5 Stale / Superseded 处理

- `superseded`：明确被新版本覆盖，默认 recall 不返回；`memory.explain_versions` 可返回。
- `stale`：当前信息可能过期，默认 search 可不返回或低权返回，必须标注需要复核。
- `archived`：长期归档，只在 deep search / explain_versions 中按权限返回。
- `candidate`：只出现在确认队列和 governance review，不进入默认 search。
- 旧版本不删除；状态转移和 evidence 保留。

### 5.6 Evidence 强制要求

每条 active memory 必须至少有一个 evidence：

```text
source_type
source_id
quote
created_at
actor_id
source_chat_id / source_doc_id 可选
```

MVP 验收：

- Evidence Coverage >= 80%。
- 无 evidence 的 active memory 不允许进入 OpenClaw card / prefetch context pack，除非明确标注为 legacy fallback 且不计入正式 benchmark。

## 6. Retrieval / Embedding 实施计划

### 6.1 Curated Memory Embedding 范围

只 embed curated memory：

- `memory.subject`
- `memory.current_value`
- `memory.summary`
- `evidence.quote`

不 embed：

- 全量 raw events。
- 全量历史聊天全文。
- 未筛选文档全文。
- 被 rejected 的 candidate。

原因：

- 控制噪声。
- 控制 10 天开发范围。
- 减少敏感信息扩散。
- 让召回以 active memory 状态机为主，而不是把所有聊天塞进向量库。

### 6.2 Hybrid Retrieval 顺序

MVP 检索顺序固定为：

1. scope / status / layer / type 结构化过滤。
2. keyword / FTS 召回，优先匹配 subject、current_value、evidence quote。
3. vector similarity 召回，只在 curated memory embedding 上执行。
4. merge，按 memory_id 去重，保留不同召回通道分数。
5. rerank，综合 importance、recency、confidence、version freshness、layer、evidence completeness。

MVP 可用本地轻量实现：

- 关键词可先复用旧 `repository._score_recall()` 的 subject 经验，再升级为 FTS。
- 向量可先用本地轻量 embedding 或 deterministic pseudo embedding 做 contract test，确保接口稳定。
- 不要求复杂向量数据库或分布式向量服务。
- 如果 embedding 暂时不可用，keyword + structured filter 必须仍能跑通 benchmark fallback。

### 6.3 Rerank 规则

建议基础公式：

```text
score = keyword_score
      + vector_score
      + importance_bonus
      + confidence_bonus
      + recency_bonus
      + layer_bonus
      + evidence_bonus
      - stale_penalty
      - superseded_penalty
```

硬规则：

- `rejected` 永不返回。
- `superseded` 默认不返回；只有 explain_versions / deep trace 返回。
- evidence 缺失的结果不能作为正式 Top 1。
- scope permission check 在 rerank 前后都要执行一次，避免 merge 时混入越权结果。

### 6.4 MemPalace 借鉴的转换接入边界

2026-04-27 调研结论：MemPalace 可借鉴的是“原文证据 + 短索引 + 分层召回 + 可解释评测”的工程思想，不接入为新运行依赖。Cognee 仍是本项目选定的 memory substrate，Copilot Core 仍自管企业记忆状态、证据、版本、权限和飞书审核面。

转换规则：

- MemPalace 的 drawer 思路转换为本项目的 raw evidence / source quote：原文只做证据源和版本追溯，不作为默认 `memory.search` 当前答案。
- MemPalace 的 closet 思路转换为 `RecallIndexEntry`：为 curated memory 构造短索引文本，包含 `subject`、`type`、`current_value`、`summary`、`evidence.quote` 和 evidence pointer。
- MemPalace 的 closet-first search 思路转换为“索引加分不硬过滤”：structured / keyword / vector / Cognee 都是召回通道，最终由 Copilot rerank 和 evidence gate 决定 Top K。
- MemPalace 的 layer / wake-up 思路转换为本项目 L0/L1/L2/L3 和 `memory.prefetch`，不得暴露 Palace / Wing / Room / Drawer 术语给评委或 OpenClaw 用户。
- MemPalace 的 benchmark 表达方式可借鉴：明确区分 Recall@3、Evidence Coverage、Current Answer Accuracy、Stale Leakage Rate，不把检索召回率和端到端问答准确率混写。

按日期落地：

| 日期 | 转换目标 | 文件落点 | 验收重点 |
|---|---|---|---|
| 2026-04-29 | 将 closet 转成 `RecallIndexEntry` 和 hybrid rerank | `retrieval.py`、`embeddings.py`、`benchmark.py` | trace 能展示 structured / keyword_index / vector / cognee / rerank；不 embed raw events |
| 2026-04-30 | 将 drawer 转成 evidence gate 和 candidate source | `schemas.py`、`governance.py`、`service.py` | 无 evidence 不可 active；candidate 不进入默认 search |
| 2026-05-01 | 将 temporal graph 思路转成版本链和 cold evidence | `governance.py`、`retrieval.py`、`feishu_cards.py` | old -> new 可解释；旧值 superseded 后不泄漏 |
| 2026-05-02 | 将 wake-up / diary 思路转成 prefetch 和 agent run summary candidate | `orchestrator.py`、`heartbeat.py`、`agent_adapters/openclaw/examples/` | Agent 任务前主动拿 context pack；会话总结只进候选或 dry-run |

## 7. Governance 实施计划

### 7.1 状态定义

| 状态 | 含义 | 默认是否 recall | 可见入口 |
|---|---|---:|---|
| `candidate` | 待确认候选记忆 | 否 | candidate card、review queue |
| `active` | 当前有效记忆 | 是 | search、prefetch、card、benchmark |
| `superseded` | 被新版本覆盖 | 否 | explain_versions、audit |
| `rejected` | 用户拒绝或系统判定不应保存 | 否 | audit |
| `stale` | 可能过期，需复核 | 默认否或低权标注 | review_due、heartbeat |
| `archived` | 历史归档 | 否 | deep search、audit |

### 7.2 自动候选识别

候选来源：

- 飞书群聊中出现长期规则、决策、负责人、截止时间、风险结论。
- 飞书文档或 Markdown ingestion 抽取出的结构化结论。
- OpenClaw Agent 当前任务中发现用户显式要求记住。
- benchmark fixture 注入。

候选必须输出：

- type。
- subject。
- current_value。
- summary。
- confidence。
- importance。
- evidence。
- risk_flags。

低置信或高风险候选必须停留在 `candidate`，通过 card 或 dry-run 展示给用户确认。

### 7.3 用户手动记忆

显式表达包括：

- “记住”
- “请记一下”
- “以后都按”
- “这个规则固定下来”
- “统一改成”

处理原则：

- 手动记忆也必须经过 Memory Core。
- 手动写入必须记录当前消息作为 evidence。
- 不能绕过敏感信息检查。
- 如果与旧 active memory 冲突，必须进入冲突更新流程。

### 7.4 冲突更新

冲突表达包括：

- “刚才说错了”
- “不对”
- “统一改成”
- “旧规则不用了”
- “以后不要用”
- “按新版走”

处理流程：

```text
create_candidate
  -> find same scope + same normalized subject active memory
  -> detect old -> new conflict
  -> create candidate with conflict metadata
  -> confirm
  -> old active version -> superseded / L3 cold
  -> new version -> active
  -> search 默认只返回 new
  -> explain_versions 可追溯 old/new/evidence
```

旧版本不删除，只进入 `superseded` / cold。

### 7.5 Version Explainability

`memory.explain_versions` 必须回答：

- 当前有效值是什么。
- 旧值是什么。
- 旧值为什么失效。
- 覆盖来自哪条飞书消息、文档或 benchmark event。
- 谁确认了更新。
- 是否存在 stale / archived 风险。

## 8. Heartbeat 主动提醒计划

MVP 必须做 heartbeat reminder prototype，但先做 reminder candidate + card/dry-run，不做复杂个性化推送。

### 8.1 触发方式

- OpenClaw heartbeat。
- scheduled check。
- manual `review_due` / `memory.review_due`。
- Agent task start pre-check。

MVP 先实现：

- `memory_engine/copilot/heartbeat.py` 中的 `generate_reminder_candidates(now, scope, current_context)`。
- CLI / test dry-run 可调用该函数。
- OpenClaw adapter 文档说明 heartbeat 如何调用。

### 8.2 候选来源

| 来源 | 示例 | MVP 处理 |
|---|---|---|
| `review_due_at <= now` | 某条部署规则到复核时间 | 生成 reminder candidate |
| important memory N 天未 recall | 重要风险 5 天未被查过 | 进入候选，过 cooldown 再提醒 |
| deadline 即将到期 | 周报 24 小时内到期 | 高优先级候选 |
| 当前线程主题与 active memory 高相似 | 群里重新讨论部署 region | relevance 达阈值才提醒 |

### 8.3 门控

提醒必须经过：

- importance >= threshold。
- relevance >= threshold。
- cooldown 未命中。
- scope permission 允许。
- sensitive redaction 完成。

敏感内容规则：

- token、secret、完整内部链接不得出现在卡片正文。
- 高风险 security / production / customer 类记忆默认需要人工确认。
- `Sensitive Reminder Leakage Rate` 必须等于 0。

### 8.4 输出

MVP 输出：

- reminder candidate。
- 飞书卡片或 dry-run log。
- Bitable reminder record 可选，不作为第一周阻塞项。

候选字段：

```text
reminder_id
memory_id
scope
trigger_type
title
message
importance
relevance
cooldown_until
redacted_evidence
recommended_action
```

## 9. 调研结论转执行任务总表

本节把 2026-04-26 正式写代码前的“最高优先级 + 下一优先级前两项”调研转成后续执行队列。后续实现不能重新漂回“只做 Cognee API wrapper”或“旧 CLI-first demo”；每一项都必须落到具体文件、测试和日期计划。

| 调研项 | 结论 | 落地日期 | 主要文件入口 | 验收证据 |
|---|---|---|---|---|
| Cognee 本地最小可跑方案 | MVP 先走本地 Python SDK，不先起 Cognee server / Docker；`.data/cognee/` 放项目内本地数据 | 2026-04-26 至 2026-04-27 | `scripts/spike_cognee_local.py`、`.gitignore`、`memory_engine/copilot/cognee_adapter.py` | spike 能跑 `remember -> recall` 和 `add -> cognify -> search` 中至少一条真实闭环；不可用时有 dry-run/fallback |
| Cognee Adapter 边界设计 | 只允许 `cognee_adapter.py` 直接接触 Cognee；状态机、evidence、version、permission 和 benchmark 全部由 Copilot Core 自管 | 2026-04-27 | `memory_engine/copilot/cognee_adapter.py`、`tests/test_copilot_cognee_adapter.py` | adapter contract tests 覆盖 dataset 命名、evidence metadata、不可用 fallback、状态不被 Cognee 改写 |
| OpenClaw tool schema / runtime 调用方式 | schema 和 examples 先冻结；runtime 不稳定时用 examples + CLI/dry-run 证明工具契约 | 2026-04-26 至 2026-05-02 | `agent_adapters/openclaw/memory_tools.schema.json`、`agent_adapters/openclaw/feishu_memory_copilot.skill.md`、`agent_adapters/openclaw/examples/*.json` | 6 个 MVP tools 有输入/输出 schema；至少 2 条 demo flow 有可复制输入输出 |
| 旧模块复用映射 | 旧 repository 是 ledger/fallback；benchmark/document/cards/bitable/runtime 都只能作为 adapter、review surface 或 fallback | 2026-04-27 至 2026-05-02 | `memory_engine/repository.py`、`benchmark.py`、`document_ingestion.py`、`feishu_cards.py`、`bitable_sync.py`、`feishu_runtime.py` | 新代码优先进入 `memory_engine/copilot/`；旧模块不再新增主业务逻辑 |
| Benchmark 指标与样例设计 | 先做 `copilot_recall/candidate/conflict` 三个样例集，再补 layer/prefetch/heartbeat；失败必须分类 | 2026-04-27 至 2026-05-03 | `benchmarks/copilot_*_cases.json`、`memory_engine/benchmark.py`、`docs/benchmark-report.md` | Recall@3、Conflict Update Accuracy、Evidence Coverage、Candidate Precision、context use、L1 p95、sensitive/stale leakage 可计算 |
| Feishu Card / Bitable 审核流 | card 和 Bitable 只展示和审核 Copilot service 输出，不作为 source of truth | 2026-05-01 至 2026-05-03 | `memory_engine/feishu_cards.py`、`memory_engine/bitable_sync.py`、`docs/reference/bitable-ledger-views.md` | candidate review card、version card、dry-run Bitable payload 能展示 evidence、版本链和 stale/superseded 过滤 |

### 9.1 实现前置顺序

1. 先冻结 OpenClaw schema 和 Copilot-owned schemas。
2. 再跑 Cognee 本地 spike，确认 SDK / 本地目录 / fallback 形态。
3. 然后实现 `CogneeAdapter` contract，不让产品代码直接依赖 Cognee。
4. 再实现 `service.py` / `tools.py`，旧 repository 只作为 fallback。
5. 每新增一个工具，就同步补对应 benchmark case 和 dry-run example。
6. Card / Bitable 在 service 输出稳定后接入，只做审核展示。

## 10. 7 天 MVP 开发排期

### D1，2026-04-26：调研落盘 + OpenClaw tool schema + copilot package skeleton

当日目标：

- 完成本计划文档。
- 把正式写代码前的 P0/P1 调研结论写入总控计划和后续每日计划。
- 冻结 OpenClaw MVP tool schema。
- 明确 Cognee MVP 先走本地 Python SDK spike，不先起 server / Docker。
- 新增 `memory_engine/copilot/` 空骨架和 schema stub。
- 不改旧 `repository.py` 和 Feishu handler。

需要改/新增的文件：

- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-26-implementation-plan.md`
- `docs/plans/2026-04-27-implementation-plan.md`
- 后续日期计划：`docs/plans/2026-04-28-implementation-plan.md` 至 `docs/plans/2026-05-07-implementation-plan.md`
- `AGENTS.md`，如需补执行契约
- `agent_adapters/openclaw/memory_tools.schema.json`
- `agent_adapters/openclaw/feishu_memory_copilot.skill.md`
- `agent_adapters/openclaw/examples/*.json`
- `memory_engine/copilot/__init__.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/tools.py`
- `scripts/spike_cognee_local.py` 草案可以只写计划，不在当天强行实现

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`
- 新增 `tests/test_copilot_schemas.py`

验收标准：

- 总控计划包含 P0/P1 调研转执行任务总表。
- 后续每日计划能看出 Cognee spike、adapter contract、OpenClaw schema/examples、benchmark 样例、Card/Bitable review 的落地日期。
- schema 能描述 6 个 MVP 工具。
- Copilot package 可 import。
- 旧 Day1 benchmark 仍通过。

我的补充任务：

- 打开 `docs/plans/2026-04-27-implementation-plan.md` 和 `docs/plans/2026-04-28-implementation-plan.md`，检查明后两天任务是否能看懂。
- 打开 `agent_adapters/openclaw/memory_tools.schema.json` 草案，检查工具字段是否能让非本项目 Agent 理解。
- 用浅显中文改 `feishu_memory_copilot.skill.md` 的触发示例，保证评委能看懂“什么时候该调用记忆工具”。
- 不改核心 Python 代码。

### D2，2026-04-27：Cognee local spike + adapter contract + schemas

当日目标：

- 跑通或 dry-run 化 Cognee 本地最小 spike，确认 `.data/cognee/`、SDK 调用和不可用 fallback。
- 定义 `CogneeAdapter` 窄接口和 contract tests。
- 实现 Copilot-owned `schemas.py`，先锁 `Evidence`、`MemoryResult`、`CandidateMemory`、`RecallTrace`、`ToolError`。
- 启动 `CopilotService.search()` 和 `tools.memory_search()` 的最小 fallback 路径。
- 旧 `MemoryRepository.recall_candidates()` 作为 storage adapter / fallback。
- search 返回统一 JSON 和错误格式；不要求当天完成 hybrid retrieval。

需要改/新增的文件：

- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `scripts/spike_cognee_local.py`
- `.gitignore`，确保 `.data/` 或 `.data/cognee/` 不进入提交
- `tests/test_copilot_tools.py`
- `tests/test_copilot_retrieval.py`
- `tests/test_copilot_cognee_adapter.py`

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 scripts/spike_cognee_local.py --dry-run`，如果真实 Cognee 尚未安装
- `python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_cognee_adapter`
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`

验收标准：

- Cognee spike 明确记录真实运行结果或不可用原因。
- `CogneeAdapter` 只返回 Copilot-owned schema，不泄漏 Cognee 原始对象到 service。
- Cognee 不可用时能退回旧 `MemoryRepository` 或 dry-run。
- `memory.search` 对 active memory 返回 Top K with evidence 的最小路径成型。
- 缺 scope、无权限、无结果时返回统一错误。
- 默认不返回 candidate / rejected / superseded。

我的补充任务：

- 准备 10 条真实项目协作 query，写入 `benchmarks/copilot_recall_cases.json` 草稿。
- 每条 query 标注正确答案和必须出现的 evidence 关键词。
- 检查 `scripts/spike_cognee_local.py` 的输出说明是否能让人知道“真实跑通 / dry-run / blocked”的区别。
- 不处理数据库、权限或 token。

### D3，2026-04-28：`memory.search` service contract + L0/L1/L2/L3 query cascade

当日目标：

- 完整实现 `CopilotService.search()` 和 `tools.memory_search()`。
- 实现 L0 Working Context schema。
- 实现 L1/L2/L3 layer 字段和 query cascade。
- 在不大改旧 schema 的前提下，先通过 adapter / lightweight migration 支持 layer。
- 让 search trace 展示 repository fallback / Cognee adapter / dry-run 的来源。

需要改/新增的文件：

- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `tests/test_copilot_retrieval.py`
- `tests/test_copilot_tools.py`
- `benchmarks/copilot_layer_cases.json`
- `benchmarks/copilot_recall_cases.json`

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m unittest tests.test_copilot_tools tests.test_copilot_retrieval`
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`

验收标准：

- `memory.search` 输出包含 `memory_id`、`type`、`subject`、`current_value`、`status`、`version`、`score`、`evidence`、`trace`。
- query cascade trace 能显示 L1 -> L2 -> L3。
- L1 命中 p95 <= 100ms 的本地测试路径成型。
- L3 raw events 不直接作为默认答案。
- `benchmarks/copilot_recall_cases.json` 至少有 5 条可读样例。

我的补充任务：

- 给 `benchmarks/copilot_layer_cases.json` 补 15 条 layer 场景：热记忆、近 7 天记忆、旧版本、归档证据。
- 用中文备注每条为什么属于 Hot / Warm / Cold。
- 顺手检查 `copilot_recall_cases.json` 是否像真实飞书项目群问题。

### D4，2026-04-29：hybrid retrieval + curated memory embedding

当日目标：

- 实现 structured filter + keyword/FTS + vector similarity + merge + rerank。
- embedding 只覆盖 curated memory 字段。
- embedding 不成为单点依赖，关键词 fallback 必须可用。
- 扩展 benchmark runner 到 `copilot_recall_cases.json` 的最小可跑版本。

需要改/新增的文件：

- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/embeddings.py`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/benchmark.py`
- `tests/test_copilot_retrieval.py`
- `benchmarks/copilot_recall_cases.json`

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m unittest tests.test_copilot_retrieval`
- `python3 -m unittest tests.test_copilot_cognee_adapter`，如果 adapter 已开始接真实 Cognee
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`
- 如实现 benchmark runner 扩展：`python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json`

验收标准：

- Hybrid retrieval trace 能看到 structured / keyword / vector / rerank。
- 不向量化 raw events。
- Recall@3 >= 60% 的第一版目标可测。
- Cognee 召回结果缺 provenance 时，Copilot 用自己的 evidence 补齐。

我的补充任务：

- 人工检查 recall 失败样例，标注失败分类：keyword_miss、vector_miss、wrong_subject_normalization、evidence_missing。
- 把失败分类补进 benchmark case 的备注。

### D5，2026-04-30：create_candidate + manual memory + evidence + governance + candidate benchmark

当日目标：

- 实现 `memory.create_candidate`、`memory.confirm`、`memory.reject`。
- 手动记忆和自动候选统一走 governance。
- evidence 成为 active 的强约束。
- 创建并跑通 `copilot_candidate_cases.json` 的最小 runner 或单测替代路径。

需要改/新增的文件：

- `memory_engine/copilot/governance.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `memory_engine/document_ingestion.py` 只在需要转成 candidate source adapter 时小步改造
- `memory_engine/benchmark.py`
- `tests/test_copilot_governance.py`
- `benchmarks/copilot_candidate_cases.json`

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m unittest tests.test_copilot_governance tests.test_copilot_tools`
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`
- 如 runner 已实现：`python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json`

验收标准：

- 手动“记住”不绕过 safety / evidence / conflict check。
- candidate 默认不进入 search。
- confirm 后进入 active；reject 后不召回。
- Candidate Precision >= 60% 的 benchmark 数据集成型。
- 文档 ingestion 只生成 candidate source，不直接绕过 Copilot service。

我的补充任务：

- 补 30 条候选识别样例：15 条应该记、15 条不应该记。
- 每条用白话写“为什么值得记 / 为什么不值得记”。
- 检查候选卡片文案是否能看出“待确认记忆”的含义。

### D6，2026-05-01：conflict update + versions + stale leakage + review surface design

当日目标：

- 实现冲突更新 old -> new 的 Copilot governance 路径。
- `memory.explain_versions` 输出可解释版本链。
- stale / superseded 不泄漏到默认 recall。
- 定义 candidate review card、version card 和 Bitable review tables 的 typed 输出字段。

需要改/新增的文件：

- `memory_engine/copilot/governance.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `memory_engine/benchmark.py`
- `tests/test_copilot_governance.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_bitable_sync.py`
- `benchmarks/copilot_conflict_cases.json`

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m unittest tests.test_copilot_governance`
- `python3 -m unittest tests.test_copilot_tools`
- `python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync`
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json`
- 只有触达 legacy fallback、旧 Bot、旧 CLI、本地 repository 或历史 benchmark runner 时，才追加 `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`

验收标准：

- Conflict Update Accuracy >= 70%。
- 旧版本进入 superseded / cold。
- 默认 recall 不返回旧值作为当前答案。
- explain_versions 能解释旧值为什么失效。
- Feishu card / Bitable 只消费 Copilot service 输出，不直接改状态。
- Bitable 设计包含 Memory Ledger、Versions、Candidate Review、Benchmark Results、Reminder Candidates。

我的补充任务：

- 设计 20 组更像真人表达的冲突样例，例如“刚才说错了”“统一改成”“以后别用这个”。
- 检查版本链文案是否能让非技术评委看懂。
- 检查 Candidate Review 表字段是否能支持后续人工复核。

### D7，2026-05-02：`memory.prefetch` + heartbeat reminder prototype + OpenClaw demo/card dry-run flow

当日目标：

- 实现 `memory.prefetch` context pack。
- 实现 heartbeat reminder candidate prototype。
- 完成至少 2 条 OpenClaw Agent E2E demo flow：历史决策查询、任务前 prefetch；目标第三条为冲突更新。
- 完成 candidate review card / version card / reminder card 的 dry-run 演示路径。

需要改/新增的文件：

- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/heartbeat.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `agent_adapters/openclaw/examples/*.json`
- `tests/test_copilot_prefetch.py`
- `tests/test_copilot_heartbeat.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_bitable_sync.py`
- `benchmarks/copilot_prefetch_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`

测试：

- `python3 scripts/check_openclaw_version.py`
- `python3 -m unittest tests.test_copilot_prefetch tests.test_copilot_heartbeat`
- `python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync`
- `python3 -m compileall memory_engine scripts`
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`

验收标准：

- Agent Task Context Use Rate >= 70%。
- heartbeat 能输出 reminder candidate。
- Sensitive Reminder Leakage Rate = 0。
- OpenClaw demo flow 有可复制输入输出样例。
- card / Bitable 写入失败时有 dry-run payload，可展示 evidence、version chain 和 stale/superseded 过滤。

我的补充任务：

- 按 `agent_adapters/openclaw/examples/` 走一遍 demo 样例，记录哪里不像真实办公 Copilot。
- 准备 5 分钟 Demo 讲解词：先讲用户痛点，再讲 Agent 自动调用记忆工具。
- 检查 reminder 文案中是否有 token、secret 或完整内部链接。

## 11. 2026-05-03 到 2026-05-07 初赛证明层与完整产品启动计划

2026-05-03 至 2026-05-05 已完成初赛证明层：Benchmark Report、Demo runbook、README 快速开始和《Memory 定义与架构白皮书》初稿。2026-05-06 起不再只按“提交材料收尾”理解任务，而是进入 **完整产品 Phase 0 / 0.5 / Phase 1**：先保护初赛提交闭环，再把产品化契约冻结下来。

### 2026-05-03：Benchmark expansion（已完成）

- 扩展 `benchmarks/copilot_*_cases.json`。
- 将 recall、candidate、conflict、layer、prefetch、heartbeat 指标统一到 runner。
- 指标覆盖 Recall@3、Conflict Update Accuracy、Evidence Coverage、Candidate Precision、Agent Task Context Use Rate、L1 Hot Recall p95、Sensitive Reminder Leakage Rate、Stale Leakage Rate。
- 产出 `docs/benchmark-report.md`，包含失败分类和 recommended fix。

验收命令按当日 handoff 和当前仓库已有 runner 执行。

### 2026-05-04：Demo runbook + README（已完成）

- 更新 `docs/demo-runbook.md`。
- 更新 `README.md` 快速开始，突出 Feishu Memory Copilot、OpenClaw tools、可复现 benchmark。
- 固定 demo seed 数据和 dry-run/replay 路径。
- OpenClaw runtime 若不稳定，保留 schema demo / CLI / dry-run 兜底，但叙事不退回 CLI-first。

### 2026-05-05：白皮书（已完成）

- 创建或重写 `docs/memory-definition-and-architecture-whitepaper.md`。
- 覆盖记忆定义、状态机、证据链、OpenClaw 入口、飞书生态、安全权限、Benchmark 证明。
- 明确本阶段不宣称完整企业后台、生产安全认证或真实飞书全量 ingestion 已完成。

### 2026-05-06：Phase 0 / Phase 0.5（提交冻结保护 + 产品化基线 RFC）

主计划：`docs/plans/2026-05-06-implementation-plan.md`。

今天要做：

- 保护 README、Demo runbook、Benchmark Report、白皮书和提交材料路径，避免产品化探索破坏初赛闭环。
- 将 `$ralplan` 批准的完整产品 PRD/Test Spec 固化到：
  - `docs/productization/complete-product-roadmap-prd.md`
  - `docs/productization/complete-product-roadmap-test-spec.md`
- 更新 README 顶部入口，让打开 GitHub 第一屏就能进入完整产品当前任务。
- 做 no-overclaim 检查：不能把 schema demo、dry-run、replay、OpenClaw seed/local bridge 写成 Feishu live ingestion。
- 更新飞书共享看板中的 2026-05-06 程俊豪任务。

今天不做：

- 不写 Phase 1 权限/迁移代码。
- 不接真实飞书 ingestion。
- 不启动 `$team` 并行。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

### 2026-05-07：Phase 1 准备（Storage + Permission Contract Freeze）+ 初赛提交缓冲

主计划：`docs/plans/2026-05-07-implementation-plan.md`。

今天要做：

- 先确认初赛提交材料仍可提交；如有提交 blocker，先修 blocker。
- 如果提交闭环安全，开始冻结 Phase 1 契约：storage、permission、OpenClaw payload、audit、migration、negative permission cases。
- 明确首版 OpenClaw payload 兼容方案：优先 `current_context.permission`，除非明确需要顶层 `permission_context`。
- 明确所有 action 的 fail-closed 行为：`memory.search`、`memory.create_candidate`、`memory.confirm`、`memory.reject`、`memory.explain_versions`、`memory.prefetch`、heartbeat。
- 更新飞书共享看板中的 2026-05-07 程俊豪 Phase 1 任务。

今天不做：

- 不直接修改数据库迁移代码，除非用户明确进入实现阶段。
- 不接真实飞书 ingestion。
- 不启动 `$team`；Contract Freeze Gate 未通过前禁止并行大实现。

最终验收命令按改动类型选择。文档-only 至少运行：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

如触达代码、schema、tests，再追加：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
```

阶段闭环前的完整验证仍以当前仓库已实现 runner 为准；缺失项写入 Not-tested，不得假装通过。

## 12. Benchmark 和测试计划

### 12.1 PRD 指标映射

| PRD 指标 | MVP 目标 | 主要 benchmark | 主要测试 |
|---|---:|---|---|
| Recall@3 | >= 60% | `benchmarks/copilot_recall_cases.json` | `tests/test_copilot_retrieval.py` |
| Conflict Update Accuracy | >= 70% | `benchmarks/copilot_conflict_cases.json` | `tests/test_copilot_governance.py` |
| Evidence Coverage | >= 80% | recall / candidate / conflict 全部统计 | `tests/test_copilot_tools.py` |
| Candidate Precision | >= 60% | `benchmarks/copilot_candidate_cases.json` | `tests/test_copilot_governance.py` |
| Agent Task Context Use Rate | >= 70% | `benchmarks/copilot_prefetch_cases.json` | `tests/test_copilot_prefetch.py` |
| L1 Hot Recall p95 | <= 100ms | `benchmarks/copilot_layer_cases.json` | `tests/test_copilot_retrieval.py` |
| Sensitive Reminder Leakage Rate | 0 | `benchmarks/copilot_heartbeat_cases.json` | `tests/test_copilot_heartbeat.py` |
| Stale Leakage Rate | 0 | `benchmarks/copilot_conflict_cases.json`、`benchmarks/copilot_prefetch_cases.json` | `tests/test_copilot_governance.py`、`tests/test_copilot_retrieval.py` |

### 12.2 单元测试清单

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_copilot_schemas.py` | schema 必填字段、默认值、状态枚举、错误格式 |
| `tests/test_copilot_tools.py` | 6 个 MVP tools 的输入输出 contract、错误码 |
| `tests/test_copilot_retrieval.py` | L0-L3 cascade、active-only、hybrid retrieval、rerank、evidence 强制 |
| `tests/test_copilot_governance.py` | candidate / active / superseded / rejected / stale / archived 状态转移 |
| `tests/test_copilot_prefetch.py` | task context pack、missing context、Agent 使用率统计 |
| `tests/test_copilot_heartbeat.py` | reminder candidate、importance/relevance/cooldown/permission/sensitive gates |

保留现有测试：

- `tests/test_benchmark_day7.py`
- `tests/test_document_ingestion.py`
- `tests/test_feishu_day3.py`
- `tests/test_feishu_day5.py`
- `tests/test_feishu_day6.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_feishu_runtime_logging.py`
- `tests/test_bitable_sync.py`

### 12.3 Benchmark 文件清单

| 文件 | 目的 |
|---|---|
| `benchmarks/day1_cases.json` | 保留旧本地闭环基线 |
| `benchmarks/day7_anti_interference.json` | 保留抗干扰资产 |
| `benchmarks/copilot_recall_cases.json` | 历史决策召回 |
| `benchmarks/copilot_candidate_cases.json` | 自动候选识别 |
| `benchmarks/copilot_conflict_cases.json` | 冲突更新和 stale leakage |
| `benchmarks/copilot_layer_cases.json` | L1/L2/L3 分层召回和延迟 |
| `benchmarks/copilot_prefetch_cases.json` | OpenClaw Agent task prefetch |
| `benchmarks/copilot_heartbeat_cases.json` | heartbeat reminder candidate 和敏感泄漏 |

### 12.4 失败分类

每个失败 case 必须记录：

```text
case_id
input_events
query_or_task
expected_result
actual_result
expected_memory_ids
expected_status
forbidden_values
failed_metric
retrieved_layer
retrieved_memory_ids
rerank_score
failure_reason
recommended_fix
```

失败分类枚举：

- `candidate_not_detected`
- `wrong_subject_normalization`
- `wrong_layer_routing`
- `vector_miss`
- `keyword_miss`
- `stale_value_leaked`
- `evidence_missing`
- `agent_did_not_prefetch`
- `reminder_too_noisy`
- `permission_scope_error`

### 12.5 每日验证命令

每天最少运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

新增 Copilot 测试后追加：

```bash
python3 -m unittest tests.test_copilot_schemas
python3 -m unittest tests.test_copilot_tools
python3 -m unittest tests.test_copilot_retrieval
python3 -m unittest tests.test_copilot_governance
python3 -m unittest tests.test_copilot_prefetch
python3 -m unittest tests.test_copilot_heartbeat
```

### 12.6 最终验收命令

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest discover tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

注意：在对应 benchmark runner 未实现前，`copilot_*` 命令可以先作为计划中的验收入口；当天实现哪个 benchmark，就把哪个纳入强制验证。

## 13. 旧代码复用和废弃策略

| 模块 | 当前价值 | MVP 处理 | 稳定后再决定 |
|---|---|---|---|
| Cognee | 开源知识/记忆引擎核心，适合本地部署和调试，提供 graph + vector memory substrate | 通过 `memory_engine/copilot/cognee_adapter.py` 接入；作为长期 memory core 的主要底层，不承担企业状态机 | 稳定后评估是否扩展 ontology、memify、HTTP server 或可视化能力 |
| `memory_engine/repository.py` | 已有 SQLite remember / recall / versions / candidate confirm / reject / evidence 经验 | 不直接大改；作为 Copilot ledger / storage adapter / fallback，保留 evidence、versions、recall_logs 等项目自研证明 | 拆出 repository interface，补 tenant/layer/visibility 字段，逐步迁移 |
| `memory_engine/benchmark.py` | 已有 Day1、Day5、Day7 benchmark runner 和报告生成 | 复用 runner 结构，新增 copilot benchmark 分支 | 统一指标输出，支持多 benchmark suite |
| `memory_engine/cli.py` | 可复现兜底入口，已有 remember / recall / versions / ingest-doc / bitable / feishu | 不作为主架构；后续 CLI 命令调用 Copilot Core | 保留为 demo / debug bridge |
| `memory_engine/feishu_runtime.py` | 已有 Feishu event replay/listen、命令处理、日志、card publish | 不把新 Copilot Core 写进 handler；先通过 adapter 调 `service.py` | 将 `/remember` `/recall` 等旧命令迁到 Copilot tools |
| `memory_engine/feishu_cards.py` | 已有 card 字段、候选确认按钮、版本链按钮经验 | 复用展示经验；card 只消费 Copilot service 输出 | 拆出 Copilot card renderer |
| `memory_engine/document_ingestion.py` | 已有 Markdown / lark-cli docs fetch、candidate quote 抽取 | 作为 `memory.create_candidate` 的文档来源 fallback | 抽取成 ingestion adapter，不直接写 repository |
| `memory_engine/bitable_sync.py` | 已有 Memory Ledger / Versions / Benchmark Results 同步 | 作为可选 review surface，不作为 source of truth | 增加 reminder record 和 Copilot metrics 表 |
| `tests/` | 已有 Bot、Card、Bitable、文档 ingestion、D7 benchmark 测试 | 保留；新增 copilot 测试，不删除旧测试 | 旧入口迁移后更新测试断言 |
| `benchmarks/` | 已有 Day1、D5、D7 数据资产 | 保留；新增 `copilot_*` 数据集 | 合并报告生成和失败分析 |

明确要求：

- 不直接删除旧模块。
- 不一次性大改旧路径。
- 先通过 adapter 或 service 层复用旧能力，并通过 `cognee_adapter.py` 接入 Cognee。
- 新功能优先进入 `memory_engine/copilot/`。
- 等 MVP 稳定后再决定哪些旧路径迁移或废弃。

### 13.1 Feishu Card / Bitable 审核面待办

Card 和 Bitable 是 review surface，不是 source of truth。它们只能消费 `CopilotService` / `tools.py` 的输出；确认、拒绝、版本解释等状态变化必须回到 Copilot Core。

候选记忆卡片字段：

| 字段 | 来源 | 说明 |
|---|---|---|
| 当前结论 | `CandidateMemory.current_value` | 展示候选将保存的值 |
| 类型 | `CandidateMemory.type` | decision / deadline / owner / workflow / risk / document |
| 主题 | `CandidateMemory.subject` | 用于人审判断是否归一化正确 |
| 状态 | `CandidateMemory.status` | MVP 多数为 candidate |
| 版本 | `CandidateMemory.version` 或 conflict metadata | 展示是否会生成新版 |
| 来源 evidence | `Evidence` | 至少包含 source_type、source_id、quote、created_at、actor_id |
| 是否覆盖旧值 | `conflict.old_memory_id` / `supersedes_version_id` | 有冲突时必须醒目标注 |
| 风险标记 | `risk_flags` | sensitive、conflict、low_confidence、permission_scope_error |

MVP buttons：

| Button | MVP 处理 | 后端入口 |
|---|---|---|
| 确认保存 | 必做 | `memory.confirm` |
| 拒绝候选 | 必做 | `memory.reject` |
| 查看版本链 | 可先 dry-run，D6/D7 尽量接通 | `memory.explain_versions` |
| 查看来源 | 可先 dry-run，展示 evidence quote / source id | Copilot service evidence 输出 |
| 标记需要复核 | 可先 dry-run，后续映射 `stale` / review queue | governance review_due |

Bitable 表字段设计：

| 表 | MVP 字段 | 说明 |
|---|---|---|
| Memory Ledger | memory_id、tenant_id、organization_id、scope、type、subject、current_value、status、version、visibility_policy、updated_at、evidence_count、risk_flags | 当前台账视图，不直接作为写入源 |
| Versions | version_id、memory_id、version_no、status、value、supersedes_version_id、source_type、source_id、quote、created_at、created_by | 版本链和旧值追溯 |
| Candidate Review | candidate_id、scope、type、subject、current_value、confidence、importance、status、risk_flags、conflict_old_memory_id、evidence_quote、recommended_action | 人工审核队列 |
| Benchmark Results | run_id、benchmark_name、case_count、Recall@3、Conflict Update Accuracy、Evidence Coverage、Candidate Precision、Agent Task Context Use Rate、L1 Hot Recall p95、Sensitive Reminder Leakage Rate、Stale Leakage Rate、failure_summary | 评测证明面 |
| Reminder Candidates | reminder_id、memory_id、scope、trigger_type、title、message、importance、relevance、cooldown_until、redacted_evidence、recommended_action、status | heartbeat dry-run / 后续提醒审核 |

Dry-run 兜底：

- 真实飞书卡片发送失败时，输出 card JSON payload 和错误摘要。
- 真实 Bitable 写入失败时，输出 table schema、rows preview 和 lark-cli 命令，不改本地 source of truth。
- Demo 中展示 stale / superseded 不泄漏时，只展示 active 当前值；旧值只通过 `memory.explain_versions` 或 Versions 表按权限查看。

## 14. 风险和取舍

| 风险 | 影响 | Mitigation |
|---|---|---|
| 10 天周期过短 | OpenClaw、retrieval、heartbeat、benchmark 和白皮书可能不能全部打磨 | 先完成 2026-04-26 到 2026-05-02 MVP 闭环；2026-05-03 到 2026-05-07 只收尾三大交付物；复杂个性化提醒、完整多租户后台、分布式缓存全部延后 |
| OpenClaw runtime 集成风险 | 可能滑回旧 CLI/Bot demo | schema 先行，`agent_adapters/openclaw/` 先交付；真实 runtime 不稳时用 examples + CLI/dry-run 证明工具契约，但产品叙事仍是 OpenClaw-native |
| Cognee 接入变成黑盒包装 | 评委认为只是接了外部 memory API | Cognee 只作为本地开源 memory substrate；状态机、证据链、版本解释、权限、OpenClaw tools、Feishu card 和 Benchmark 全部由本项目实现并展示 |
| Cognee API 或本地后端调试不稳 | MVP 进度被底层集成拖住 | 先实现窄 adapter 和 repository fallback；D2/D3 只锁接口和最小 recall/search，复杂 ontology、memify、HTTP server 后置 |
| embedding 质量风险 | Recall@3 不达标 | 使用 hybrid retrieval；结构化过滤和 keyword/FTS 作为稳态兜底；只 embed curated memory；失败分类记录 `vector_miss` |
| heartbeat 太吵的风险 | 用户觉得系统乱插话 | MVP 只生成 reminder candidate；必须通过 importance、relevance、cooldown、permission、sensitive gates；Sensitive Reminder Leakage Rate 必须为 0 |
| 旧实现拖累架构的风险 | 新 Core 被旧 CLI/Bot handler 绑死 | 新功能只进 `memory_engine/copilot/`；旧 repository 只当 storage adapter；所有入口后续调用同一套 service |
| 飞书权限 / lark-cli profile 风险 | 真实飞书消息、文档、Bitable 写入失败 | 保留 fixture、replay、dry-run；文档明确 profile setup；lark-cli 是操作层，不是核心状态机 |
| Benchmark 达不到指标的风险 | 初赛证明力不足 | 缩小 P0 场景到项目协作记忆；强化 subject normalization、evidence、规则检索；每日跑基础验证和专项 benchmark |
| 权限模型太弱 | 企业级可信度不足 | MVP 预留 `tenant_id`、`organization_id`、`visibility_policy`，默认同 scope 召回，跨 scope 禁止 |
| 自动候选误记 | 系统显得不可靠 | 高风险和低置信候选进入人工确认；Candidate Precision 进入硬指标 |
| 旧值泄漏 | 用户误用过期信息 | 默认 recall 只返回 active；superseded/stale leakage 进入 benchmark；版本解释工具单独返回旧值 |

## 15. 执行顺序和下一步代码入口

本主控计划只定义执行顺序和边界；具体代码实现按 `docs/plans/YYYY-MM-DD-implementation-plan.md` 的日期任务推进。

下一步如果用户明确要求“开始执行”，建议从以下文件开始：

1. `agent_adapters/openclaw/memory_tools.schema.json`：先冻结工具 schema。
2. `memory_engine/copilot/schemas.py`：定义工具输入输出和 memory 状态模型。
3. `memory_engine/copilot/cognee_adapter.py`：定义 Cognee 本地 memory engine 的窄接口和 fallback 行为。
4. `memory_engine/copilot/tools.py`：实现 OpenClaw 工具 handler 的薄封装。
5. `memory_engine/copilot/service.py`：把 `memory.search` 先接到 Cognee adapter + 旧 repository fallback。
6. `tests/test_copilot_schemas.py`、`tests/test_copilot_tools.py` 和后续 adapter contract test：先锁 contract，再扩展 retrieval 和 governance。

不要从 `memory_engine/repository.py` 或 `memory_engine/feishu_runtime.py` 开始大改；这两个文件只在 adapter 确认需要时做小步扩展。
