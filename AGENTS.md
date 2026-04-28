# AGENTS.md

这个文件是给 Codex / 自动执行代理看的项目执行规则。
README 面向评委和新读者；AGENTS.md 面向代码修改、验证、提交和同步任务。

所有自动执行必须遵守这里的规则。

---

## 0. 当前项目一句话

本项目是飞书 AI 挑战赛 OpenClaw 赛道项目：**OpenClaw-native Feishu Memory Copilot**。

目标不是继续做旧的 CLI-first / Bot-first demo，而是把项目推进成一个可复现、可治理、可审计的企业级长程记忆 Copilot。

核心架构：

```text
OpenClaw Agent
  -> memory.* tools
  -> handle_tool_request()
  -> CopilotService
  -> permissions / governance / retrieval / audit
  -> SQLite / Cognee adapter / Feishu / Bitable
```

---

## 1. 当前事实源优先级

执行任何任务前，按以下顺序判断事实：

1. 用户当前最新指令。
2. 当前代码状态。
3. `README.md` 顶部当前状态。
4. `docs/productization/full-copilot-next-execution-doc.md`
5. `docs/productization/prd-completion-audit-and-gap-tasks.md`
6. 相关 productization contract / runbook / handoff。
7. 历史日期计划和归档文档。

如果历史文档和当前代码冲突，以当前代码和最新产品化文档为准。

---

## 2. 默认先读取哪些文件

每次开始新任务，默认先读：

```text
AGENTS.md
README.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/complete-product-roadmap-prd.md
docs/productization/complete-product-roadmap-test-spec.md
```

然后再按任务类型读取相关文件。

### 2.1 只在明确需要时读取

只有用户明确要求执行某个绝对日期任务时，才读取：

```text
docs/plans/YYYY-MM-DD-implementation-plan.md
docs/plans/YYYY-MM-DD-handoff.md
```

已在最新产品化文档中标记为完成的日期计划，只作为历史证据，不再作为默认执行入口。不要仅凭日期早晚判断任务是否完成。

### 2.2 归档文档使用规则

`docs/archive/` 里的内容只作为 reference / fallback。
不要把旧 day 文档当作当前主线。

### 2.3 产品化 / 交付物任务再读

如果任务涉及 productization、评委材料、handoff、真实 Feishu/OpenClaw 验收或上线边界，再读：

```text
docs/README.md
docs/human-product-guide.md
docs/productization/workflow-and-test-process.md
docs/productization/launch-polish-todo.md
docs/productization/contracts/
```

---

## 3. 当前主线和边界

当前主线：

```text
OpenClaw-native Feishu Memory Copilot
```

不要把新功能继续塞进旧 Bot handler。
新能力优先进入：

```text
memory_engine/copilot/
agent_adapters/openclaw/
docs/productization/
tests/test_copilot_*.py
benchmarks/copilot_*.json
```

旧实现只能作为 fallback：

```text
memory_engine/repository.py
memory_engine/feishu_runtime.py
legacy CLI commands
docs/archive/
benchmarks/day*.json
```

除非任务明确要求修 legacy，否则不要从大改旧实现开始。

---

## 4. 当前可以说和不能说

### 4.1 可以说

- 已完成 MVP / Demo / Pre-production 本地闭环。
- 已完成 OpenClaw tool schema 和本地 bridge。
- 已完成 `CopilotService` 权限门控、候选记忆、版本链、审计、检索。
- 已完成受控飞书测试群 live sandbox。
- 已完成 benchmark、demo readiness 和 healthcheck。
- 已完成 first-class OpenClaw tool registry 的本机证据。
- 已完成 Feishu websocket running 的本机 staging 证据。
- 已完成本机 storage migration dry-run / apply、索引检查和生产存储试点方案。

### 4.2 不能说

- 不能说生产部署已完成。
- 不能说全量接入飞书 workspace。
- 不能说多租户企业后台已完成。
- 不能说长期 embedding 服务已完成。
- 不能说真实 Feishu DM 已稳定路由到本项目 first-class `memory.*` 工具。
- 不能说 productized live 长期运行已完成。

任何文档、commit message、handoff、看板备注都必须遵守这个边界。

---

## 5. Copilot-first 开发规则

### 5.1 Schema 先行

OpenClaw 工具变更必须先看：

```text
agent_adapters/openclaw/memory_tools.schema.json
```

再实现：

```text
memory_engine/copilot/schemas.py
memory_engine/copilot/tools.py
memory_engine/copilot/service.py
```

### 5.2 服务层统一

所有新入口都应该进入：

```python
handle_tool_request()
CopilotService
```

不要让 Feishu、CLI、OpenClaw plugin 各自绕开服务层。

### 5.3 权限默认 fail closed

任何 `memory.*` 工具都必须带 `current_context.permission`。

缺失、畸形、scope 不匹配、tenant/org 不匹配，都必须拒绝。

相关文件：

```text
memory_engine/copilot/permissions.py
tests/test_copilot_permissions.py
```

### 5.4 真实飞书来源不能自动 active

真实飞书消息、文档、Bitable 来源只能进入 candidate。

不能自动变成 active memory。
必须经过 reviewer 确认。

相关文件：

```text
memory_engine/copilot/governance.py
memory_engine/copilot/feishu_live.py
memory_engine/document_ingestion.py
```

### 5.5 不向量化全部 raw events

默认只对 curated memory 做 embedding：

```text
subject
current_value
summary
evidence quote
```

不要把全部 raw events 直接向量化。

相关文件：

```text
memory_engine/copilot/retrieval.py
memory_engine/copilot/embeddings.py
```

---

## 6. Cognee 使用规则

Cognee 是当前选定的 memory / knowledge engine 方向。
不要改成 Mem0、Graphiti、MemOS、Letta、Zep、TiMem，除非用户明确要求重新选型。

使用原则：

1. 优先走本地 Python SDK spike。
2. 通过窄 adapter 接入。
3. 不要在业务代码里到处直接 `import cognee`。
4. 不要一开始就要求 Cognee server / Docker。
5. 企业记忆治理仍由本项目实现，不交给 Cognee 黑盒。

相关文件：

```text
memory_engine/copilot/cognee_adapter.py
tests/test_copilot_cognee_adapter.py
scripts/spike_cognee_local.py
```

---

## 7. OpenClaw 版本锁定

当前 OpenClaw 固定版本：

```text
2026.4.24
```

锁文件：

```text
agent_adapters/openclaw/openclaw-version.lock
```

每次 OpenClaw 相关开发或验收前运行：

```bash
python3 scripts/check_openclaw_version.py
```

禁止主动运行：

```bash
openclaw update
npm update -g openclaw
npm install -g openclaw@latest
```

如果版本漂移，只允许安装精确版本：

```bash
npm i -g openclaw@2026.4.24 --no-fund --no-audit
```

---

## 8. 依赖安装和锁定

如果任务需要新依赖，可以直接安装，不要停下来让用户手动处理。

但必须遵守：

1. 使用 exact version。
2. 写入可追踪文件。
3. 不使用 latest / beta / dev / floating range。
4. 不开启自动升级。
5. 在 commit message 或 handoff 中写清验证结果。

Python 依赖写入：

```text
pyproject.toml
```

OpenClaw / 本地模型 / 特殊工具写入对应 lock 文件或文档。

---

## 9. Ollama / 本地模型清理

涉及 embedding、Cognee、Ollama 的验证后，必须检查模型是否仍在运行：

```bash
ollama ps
```

如果看到本项目模型仍在运行，需要停止：

```bash
ollama stop qwen3-embedding:0.6b-fp16
```

或停止本次验证拉起的其他项目模型。

只关闭本项目使用的模型。
不要误停用户其他模型。

最终回复和 commit message 里必须说明清理状态。

---

## 10. Feishu live sandbox 规则

新的飞书测试群入口：

```bash
python3 -m memory_engine copilot-feishu listen
```

或：

```bash
scripts/start_copilot_feishu_live.sh
```

相关文件：

```text
memory_engine/copilot/feishu_live.py
memory_engine/feishu_listener_guard.py
scripts/check_feishu_listener_singleton.py
docs/productization/feishu-staging-runbook.md
```

规则：

1. OpenClaw Feishu websocket、Copilot lark-cli sandbox、legacy `feishu listen` 三选一。
2. 不要多个监听同时消费同一个 bot。
3. 启动前做 singleton preflight。
4. 真实群聊 ID、用户 ID、token 不写入仓库。
5. logs 目录是本地证据目录，不提交。

---

## 11. legacy Bot fallback 规则

旧 Bot 只作为 fallback，不是当前主架构。

旧 Bot 名称：

```text
Feishu Memory Engine bot
```

旧测试命令示例：

```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
```

只有改到旧 Bot / legacy runtime 时，才跑 legacy 测试。

---

## 12. 飞书任务看板同步规则

项目任务同步看板：

```text
https://jcneyh7qlo8i.feishu.cn/wiki/DlikwJHLGi2MjdkaC5LcZeIznAe?from=from_copylink
```

标题：

```text
飞书挑战赛任务跟进看板
```

用途：同步程俊豪个人项目进度和任务状态。

### 12.1 什么时候同步

以下情况需要同步：

- 开始新阶段。
- 完成阶段闭环。
- 更新产品化执行文档。
- 更新 handoff。
- 用户要求同步进度。
- README 顶部当前任务变化。

### 12.2 字段语义

| 字段 | 规则 |
|---|---|
| 任务描述 | 写清绝对日期、负责人、交付物 |
| 状态 | 只用：待启动、进行中、已完成、延期、暂停 |
| 优先级 | 只用：P0、P1、P2 |
| 指派给 | 程俊豪 |
| 任务截止日期 | 使用绝对日期 |
| 备注 | 写验收证据、文档路径、commit hash、剩余风险 |

### 12.3 操作流程

不要直接用 `lark-cli sheets +read/+write` 改数据区。
这个页面是 Wiki 包装的 Sheets，里面嵌入 Bitable block。

正确流程：

```bash
lark-cli wiki spaces get_node --params '{"token":"DlikwJHLGi2MjdkaC5LcZeIznAe"}'
```

然后读取 spreadsheet metainfo：

```bash
lark-cli api GET /open-apis/sheets/v2/spreadsheets/<spreadsheet_token>/metainfo
```

再从 `blockInfo.blockToken` 拆出：

```text
app_token
table_id
```

最后用：

```bash
lark-cli base +...
```

同步后必须读回确认：

```bash
lark-cli base +record-list
```

如果同步失败，不要声称已同步。
最终回复和 handoff 必须写清失败命令、错误摘要和本地替代入口。

---

## 13. 文档写作规则

README 面向评委和新读者，必须清楚回答：

1. 项目是什么。
2. 当前能跑什么。
3. 怎么快速验证。
4. 架构是什么。
5. 哪些已经完成。
6. 哪些不能 overclaim。
7. 答辩材料在哪里。

AGENTS.md 面向 Codex，必须清楚回答：

1. 先读什么。
2. 改哪里。
3. 不能改哪里。
4. 怎么验证。
5. 怎么提交。
6. 怎么同步看板。
7. 哪些话不能说。

写作要求：

- 用浅显中文。
- 先讲要做什么，再讲为什么。
- 技术词第一次出现要解释。
- 不要堆长段。
- 表格只放关键信息。
- 补充任务最多 5 条。
- 每条任务必须有文件位置和完成标准。
- 当前不做的事情直接写“本阶段不用做”。

---

## 14. 验证规则

### 14.1 所有提交前都跑

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

### 14.2 只改文档时

适用范围：

```text
README.md
AGENTS.md
docs/**/*.md
```

最低验证：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

如果文档改了验收命令、依赖锁、OpenClaw/Cognee 约束、benchmark 口径，再追加相关专项验证。

### 14.3 改 Python 代码、脚本、schema、benchmark runner 时

追加：

```bash
python3 -m compileall memory_engine scripts
```

### 14.4 改 Copilot schema / tools / service 时

追加：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
```

### 14.5 改权限、治理、候选记忆时

追加：

```bash
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance
```

### 14.6 改检索、召回、分层策略时

追加：

```bash
python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_benchmark
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
```

### 14.7 改 Cognee / embedding 时

追加：

```bash
python3 -m unittest tests.test_copilot_cognee_adapter
python3 scripts/spike_cognee_local.py --dry-run
ollama ps
```

必要时停止本项目模型，并在最终回复写清清理状态。

### 14.8 改 Feishu live sandbox 时

追加：

```bash
python3 -m unittest tests.test_copilot_feishu_live
python3 -m unittest tests.test_feishu_listener_guard
```

如改 websocket evidence：

```bash
python3 -m unittest tests.test_openclaw_feishu_websocket_evidence
```

### 14.9 改 Demo readiness / demo seed 时

追加：

```bash
python3 -m unittest tests.test_demo_readiness tests.test_demo_seed
python3 scripts/check_demo_readiness.py --json
```

### 14.10 改 storage migration 时

追加：

```bash
python3 -m unittest tests.test_copilot_storage_migration
python3 scripts/migrate_copilot_storage.py --dry-run --json
```

如需要验证 apply：

```bash
python3 scripts/migrate_copilot_storage.py --apply --json
```

### 14.11 改 legacy fallback 时

只有触达旧实现时才跑：

```bash
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json
python3 -m unittest tests.test_benchmark_day7 tests.test_document_ingestion tests.test_bitable_sync
python3 -m unittest tests.test_feishu_day3 tests.test_feishu_day5 tests.test_feishu_day6 tests.test_feishu_interactive_cards tests.test_feishu_runtime_logging
```

不要把 legacy 测试当作 OpenClaw-native Copilot 的主验收。

---

## 15. Git 提交规则

每完成一个可运行闭环、阶段交付或关键文档更新后，需要提交并推送。

提交前检查：

```bash
git status --short
```

确认不要提交：

```text
.env
.omx/
data/*.sqlite
logs/
reports/ 临时文件
缓存文件
真实群聊 ID / 用户 ID / token
```

只提交当前任务相关文件。
不要回退或覆盖无关改动。
不要使用 destructive git 命令。

### 15.1 commit message 格式

首行写“为什么做这次变更”。

正文写验证结果：

```text
Clarify README and AGENTS for Copilot-first execution

Reorganized README for judges and new readers, and reorganized AGENTS.md for Codex execution rules. Kept the current no-overclaim boundary and productization status.

Tested: python3 scripts/check_openclaw_version.py
Tested: git diff --check
Not-tested: Python runtime tests not needed for documentation-only change
```

提交后推送：

```bash
git push origin HEAD
```

如果推送失败，读取错误并处理可恢复问题。
不要强推，除非用户明确要求并说明风险。

---

## 16. 外部参考

飞书开发文档：

```text
https://open.feishu.cn/document/client-docs/intro
https://open.feishu.cn/document/course
https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/AI-assistant-code-generation-guide
https://open.feishu.cn/document/client-docs/h5/
https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu
```

飞书 OpenClaw 官方插件：

```text
https://github.com/larksuite/openclaw-lark
https://bytedance.larkoffice.com/docx/MFK7dDFLFoVlOGxWCv5cTXKmnMh
```

本地工具：

```text
lark-cli 已安装，可以直接使用
openclaw 版本固定为 2026.4.24
```
