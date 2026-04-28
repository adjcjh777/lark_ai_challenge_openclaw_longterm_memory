# TODO-1: 打通真实飞书 DM 到 first-class memory.* tool routing

日期：2026-04-28
状态：部分完成（本地 Agent `fmc_*` 工具路由已补；真实飞书 DM live E2E 待验收）
负责人：程俊豪

---

## 1. 目标

让真实飞书 DM 进入 OpenClaw Agent 后，Agent 自然选择本项目的 OpenClaw-facing `fmc_memory_search`、`fmc_memory_create_candidate` 等 first-class 工具，再由插件翻译到 Python 侧 `memory.search`、`memory.create_candidate`，而不是走 OpenClaw 内置的 `memory_search`。

**最终完成标准**：真实飞书 DM → OpenClaw Agent → `fmc_memory_search` 等项目工具 → `memory.search` 等 Python 侧工具 → `handle_tool_request()` → `CopilotService` → 返回结果，回复中保留 `request_id`、`trace_id`、`permission_decision`。

## 当前事实口径

截至 2026-04-29，本 TODO 的前置工程链路已经补齐：插件工具使用 `fmc_*` 名称注册，`scripts/check_feishu_dm_routing.py` 和 `tests/test_feishu_dm_routing.py` 能验证本地 Agent 可见 `fmc_*` 工具、插件到 Python runner 的翻译、bridge metadata 和 `CopilotService` 调用链路。

但真实飞书 DM live E2E 还不能写成完成：当前仓库没有读回“真实飞书 DM 触发 OpenClaw Agent 后选择 `fmc_memory_search` / `fmc_memory_prefetch` 等本项目工具”的最终证据。后续必须用真实 DM、gateway 日志和 tool call 输出补齐这一步。

---

## 2. 当前状态分析

### 2.1 已完成的部分

| 组件 | 状态 | 证据 |
|---|---|---|
| `feishu-memory-copilot` 插件已安装并启用 | 完成 | `openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 toolNames |
| 插件注册了 7 个 first-class 工具 | 完成 | `agent_adapters/openclaw/plugin/index.js` 通过 `api.registerTool()` 注册 |
| Python runner 调用 `handle_tool_request()` | 完成 | `memory_engine/copilot/openclaw_tool_runner.py` 通过 stdin/stdout JSON 调用 |
| OpenClaw Feishu websocket running | 完成 | `openclaw channels status --probe --json` 显示 running，gateway 日志有 `dispatching to agent` |
| 真实 DM 进入 OpenClaw Agent dispatch | 完成 | gateway 日志记录 `received message` → `dispatching to agent` → `dispatch complete` |

### 2.2 已补齐的中间层

- OpenClaw-facing 工具名已改为 `fmc_*`，避免 OpenAI / OpenClaw 工具名点号限制。
- 插件已把 `fmc_*` 翻译到 Python 侧 `memory.*`。
- `tools.alsoAllow` 和本地 Agent 工具可见性已有诊断脚本覆盖。
- 本地 Agent 调用 `fmc_memory_search`、Python runner、bridge metadata 和权限上下文已有自动化测试覆盖。

### 2.3 未完成的部分

**核心问题**：还缺真实飞书 DM 场景下的最终读回证据，证明 OpenClaw Agent 收到真实飞书 DM 后选择的是本项目 `fmc_memory_search` 等工具，而非内置 `memory_search`。

**可能原因**（需要实际验证）：

1. **OpenClaw 内置 memory 工具优先级更高**：OpenClaw 2026.4.24 可能内置了 `memory_search` 等工具，Agent 在 tool dispatch 时优先选择内置工具。
2. **Agent prompt / system message 引导不足**：Agent 的 system prompt 可能没有明确引导它使用 `memory.search` 而非 `memory_search`。
3. **工具名称冲突或相似**：`memory_search`（内置）和 `memory.search`（插件）名称相似，Agent 可能混淆。
4. **插件工具未在 Agent tool list 中暴露**：插件已注册，但 OpenClaw Agent runtime 可能未将插件工具加入 Agent 的可用工具列表。
5. **Skill 文件未被 Agent 加载**：`feishu_memory_copilot.skill.md` 已存在，但 Agent 可能未读取它来指导 tool selection。

### 2.4 历史问题路径

```text
真实飞书 DM
  → OpenClaw Feishu websocket (running)
  → OpenClaw Agent dispatch
  → Agent 选择内置 memory_search ← 历史 websocket staging 证据中记录的问题
  → OpenClaw 内置实现（不经过本项目 CopilotService）
  → 返回结果（无 request_id/trace_id/permission_decision）
```

### 2.5 目标数据流

```text
真实飞书 DM
  → OpenClaw Feishu websocket (running)
  → OpenClaw Agent dispatch
  → Agent 选择 fmc_memory_search（本项目 first-class tool）
  → plugin/index.js → runPythonTool()
  → memory_engine.copilot.openclaw_tool_runner → memory.search → handle_tool_request()
  → CopilotService → permissions/governance/retrieval/audit
  → 返回结果（含 request_id/trace_id/permission_decision）
```

---

## 3. 子任务清单

### 子任务 1：诊断 OpenClaw Agent tool dispatch 机制

**目标**：理解 OpenClaw Agent 为什么选择了内置 `memory_search` 而非插件 `memory.search`。

**输入**：
- OpenClaw 2026.4.24 运行实例
- 已安装的 `feishu-memory-copilot` 插件
- `openclaw --help`、`openclaw agent --help`、`openclaw tools --help` 等 CLI 输出

**执行步骤**：
1. 检查 OpenClaw 内置工具列表：`openclaw tools list --json`，确认是否存在内置 `memory_search`
2. 检查 Agent 配置：`openclaw agent config --json`，查看 tool dispatch 规则
3. 检查 Agent system prompt：`openclaw agent prompt --json`，查看是否有 memory 工具相关引导
4. 发送测试 DM 并捕获 Agent 的 tool call 日志：`openclaw logs --follow --json` 中搜索 `tool_call` 或 `memory`
5. 对比内置 `memory_search` 和插件 `memory.search` 的 schema 差异

**输出**：
- 明确的根因判断（以下之一）：
  - 内置工具优先级问题
  - Agent prompt 引导不足
  - 插件工具未暴露给 Agent
  - 工具名称冲突
  - 其他

**验证方法**：
- 能清楚解释 Agent 选择内置工具的原因
- 文档化 OpenClaw tool dispatch 的完整决策链

**预估时间**：2-4 小时

---

### 子任务 2：禁用或覆盖 OpenClaw 内置 memory 工具

**目标**：让 OpenClaw Agent 不再使用内置 `memory_search`，转而使用插件注册的 `memory.search`。

**输入**：
- 子任务 1 的根因分析结果
- OpenClaw 配置文件和 CLI 文档

**可能方案**（根据子任务 1 结果选择）：

**方案 A：OpenClaw 配置禁用内置工具**
```bash
# 如果 OpenClaw 支持禁用内置工具
openclaw tools disable memory_search
openclaw tools disable memory_create
# 或通过配置文件
```

**方案 B：Agent prompt 中优先引导**
- 在 `feishu_memory_copilot.skill.md` 中强化引导语
- 或在 OpenClaw Agent 配置中设置 system prompt 偏好

**方案 C：重命名插件工具避免冲突**
- 将 `memory.search` 改为 `feishu_memory.search` 或其他不冲突的名称
- 同步更新 `memory_tools.schema.json`、`tools.py`、`openclaw_tool_runner.py`

**方案 D：通过 OpenClaw plugin API 设置工具优先级**
- 如果 OpenClaw plugin SDK 支持设置工具优先级或覆盖内置工具

**输出**：
- OpenClaw Agent 使用 `memory.search` 而非 `memory_search`
- 内置工具被禁用或被插件工具覆盖

**验证方法**：
```bash
# 发送测试 DM，检查 Agent tool call
openclaw logs --follow --json | grep -E "tool_call|memory"

# 或通过 Agent 运行日志确认
openclaw agent run --message "生产部署 region 是什么？" --json
```

**预估时间**：4-8 小时

---

### 子任务 3：强化 Skill 文件引导 Agent 工具选择

**目标**：确保 `feishu_memory_copilot.skill.md` 被 OpenClaw Agent 加载，并有效引导 Agent 选择正确的工具。

**输入**：
- 当前 `agent_adapters/openclaw/feishu_memory_copilot.skill.md`
- OpenClaw skill 加载机制文档

**执行步骤**：
1. 确认 OpenClaw Agent 是否加载 `.skill.md` 文件：检查 Agent config 或文档
2. 如果未加载，探索正确的 skill 注册方式（可能需要在 `openclaw.plugin.json` 中声明）
3. 更新 skill 文件内容，明确排除内置 `memory_search`：
   ```markdown
   ## 重要：不要使用内置 memory_search

   本项目已注册 first-class memory 工具，优先级高于 OpenClaw 内置工具：
   - 使用 `memory.search` 而非 `memory_search`
   - 使用 `memory.create_candidate` 而非 `memory_create`
   - 所有记忆操作必须通过本项目工具，以确保权限门控和审计
   ```
4. 验证 skill 文件格式符合 OpenClaw 规范

**输出**：
- Agent 加载了更新后的 skill 文件
- Agent 在处理记忆相关请求时优先选择插件工具

**验证方法**：
```bash
# 检查 Agent 是否加载了 skill
openclaw agent skills --json

# 发送测试 DM 验证工具选择
openclaw agent run --message "记住：测试规则" --json | jq '.tool_calls'
```

**预估时间**：2-4 小时

---

### 子任务 4：验证端到端路由链路

**目标**：确认真实飞书 DM → OpenClaw Agent → `memory.search` → `handle_tool_request()` → `CopilotService` 完整链路通顺。

**输入**：
- 子任务 2 和 3 的修改结果
- 真实飞书测试群或 DM

**执行步骤**：
1. 确保 OpenClaw Feishu websocket running：
   ```bash
   openclaw channels status --probe --json
   ```
2. 发送真实飞书 DM（测试搜索）：
   ```
   @Bot 生产部署 region 是什么？
   ```
3. 检查 OpenClaw gateway 日志中的 tool call：
   ```bash
   openclaw logs --follow --json | grep -E "memory\.search|tool_call"
   ```
4. 检查 Python runner 是否被调用：
   - 查看 `openclaw_tool_runner.py` 的 stderr 输出
   - 或在 runner 中添加临时日志
5. 验证返回结果包含：
   - `bridge.entrypoint == "openclaw_tool"`
   - `bridge.tool == "memory.search"`
   - `bridge.permission_decision.decision == "allow"`
   - `bridge.request_id` 非空
   - `bridge.trace_id` 非空

6. 测试其他工具路径：
   - 创建候选：`@Bot /remember 规则：测试`
   - 预取上下文：`@Bot /prefetch 生成 checklist`
   - 帮助：`@Bot /help`

**输出**：
- 所有测试消息的 tool call 指向 `memory.search` 等插件工具
- 返回结果包含完整的 bridge metadata

**验证方法**：
```bash
# 完整验证脚本
python3 scripts/check_feishu_dm_routing.py --json --timeout 60
```

**预估时间**：4-6 小时

---

### 子任务 5：保留 request_id/trace_id/permission_decision

**目标**：确认路由到插件工具后，返回给用户的回复中保留了审计所需的元数据。

**输入**：
- 子任务 4 的端到端测试结果
- `memory_engine/copilot/tools.py` 中的 `_with_bridge_metadata()`

**执行步骤**：
1. 检查 `handle_tool_request()` 返回的 bridge metadata 是否完整
2. 检查 OpenClaw Agent 是否将 bridge metadata 传递给用户回复
3. 如果 Agent 剥离了 metadata，需要在 skill 文件中引导 Agent 保留：
   ```markdown
   ## 回复格式

   回复用户时，必须在末尾包含以下审计信息：
   - request_id：用于追踪本次请求
   - trace_id：用于追踪检索链路
   - permission_decision：权限决策结果
   ```
4. 验证用户收到的飞书消息包含上述信息

**输出**：
- 用户收到的飞书回复包含 `request_id`、`trace_id`、`permission_decision`

**验证方法**：
```bash
# 检查 Agent 回复中的 bridge metadata
openclaw agent run --message "测试" --json | jq '.response | contains("request_id")'
```

**预估时间**：2-3 小时

---

### 子任务 6：编写路由测试

**目标**：新增测试覆盖 Feishu DM → 插件工具的路由路径。

**输入**：
- 子任务 4 和 5 的验证结果
- 现有测试：`tests/test_openclaw_tool_registry.py`、`tests/test_openclaw_runtime_evidence.py`

**新增测试**：

```python
# tests/test_feishu_dm_routing.py

class FeishuDMRoutingTest(unittest.TestCase):
    def test_plugin_tool_is_registered_with_correct_names(self):
        """验证插件注册的工具名称与 schema 一致。"""

    def test_runner_receives_correct_envelope_from_plugin(self):
        """验证 plugin/index.js 发送给 runner 的 envelope 格式正确。"""

    def test_runner_returns_bridge_metadata_for_all_tools(self):
        """验证所有 7 个工具都返回 bridge metadata。"""

    def test_search_result_contains_permission_decision(self):
        """验证 memory.search 返回包含 permission_decision。"""

    def test_candidate_result_preserves_request_trace_ids(self):
        """验证 memory.create_candidate 返回保留 request_id/trace_id。"""
```

**输出**：
- 新增 `tests/test_feishu_dm_routing.py`
- 所有测试通过

**验证方法**：
```bash
python3 -m unittest tests.test_feishu_dm_routing -v
```

**预估时间**：2-3 小时

---

### 子任务 7：编写路由诊断脚本

**目标**：新增可重复运行的诊断脚本，检查 Feishu DM routing 状态。

**输入**：
- 子任务 4 的验证逻辑
- 现有脚本：`scripts/check_openclaw_feishu_websocket.py`

**新增脚本**：

```python
# scripts/check_feishu_dm_routing.py

def check_feishu_dm_routing() -> dict:
    """检查真实飞书 DM 是否路由到本项目 memory.* 工具。

    检查项：
    1. OpenClaw Feishu websocket running
    2. feishu-memory-copilot 插件已安装并启用
    3. 插件工具在 Agent tool list 中可见
    4. 内置 memory_search 已禁用或被覆盖
    5. 测试 DM 的 tool call 指向 memory.search
    """
```

**输出**：
- 新增 `scripts/check_feishu_dm_routing.py`
- 支持 `--json` 和 `--timeout` 参数

**验证方法**：
```bash
python3 scripts/check_feishu_dm_routing.py --json --timeout 60
```

**预估时间**：2-3 小时

---

### 子任务 8：更新 handoff 文档

**目标**：记录本 TODO 的完成状态和验收证据。

**输入**：
- 所有子任务的完成结果
- 现有 handoff：`docs/productization/handoffs/openclaw-feishu-websocket-handoff.md`

**输出**：
- 新增 `docs/productization/handoffs/feishu-dm-routing-handoff.md`

**文档内容**：
- 做了什么
- 验收证据（命令和输出摘要）
- 边界（可以说/不能说）
- 下一步

**验证方法**：
- 文档与实际代码和测试一致

**预估时间**：1-2 小时

---

## 4. 依赖关系

```text
子任务 1（诊断）
  ↓
子任务 2（禁用/覆盖内置工具）← 依赖子任务 1 的根因
  ↓
子任务 3（强化 skill 引导）← 可与子任务 2 并行
  ↓
子任务 4（端到端验证）← 依赖子任务 2 和 3
  ↓
子任务 5（保留 metadata）← 依赖子任务 4
  ↓
子任务 6（编写测试）← 依赖子任务 4 和 5
  ↓
子任务 7（诊断脚本）← 可与子任务 6 并行
  ↓
子任务 8（handoff 文档）← 依赖所有子任务
```

**关键依赖**：
- 子任务 1 是阻塞项，必须先完成才能确定后续方案
- 子任务 2 和 3 可能需要多次迭代
- 子任务 4 是核心验收点

---

## 5. 风险和注意事项

### 5.1 高风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| OpenClaw 不支持禁用内置工具 | 无法阻止 Agent 使用内置 memory_search | 使用方案 B（prompt 引导）或方案 C（重命名） |
| 插件工具优先级无法调整 | Agent 始终优先选择内置工具 | 联系 OpenClaw 团队或查看是否有 API |
| 工具名称冲突导致行为不确定 | Agent 随机选择内置或插件工具 | 使用方案 C（重命名为不冲突的名称） |

### 5.2 中风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| Agent 不加载 skill 文件 | prompt 引导无效 | 探索正确的 skill 注册方式 |
| bridge metadata 被 Agent 剥离 | 用户看不到 request_id/trace_id | 在 skill 文件中明确引导 Agent 保留 |
| 性能下降（Python 子进程调用） | 响应时间增加 | 优化 runner 启动时间或使用长连接 |

### 5.3 注意事项

1. **不要破坏现有插件注册**：修改时确保 `openclaw plugins inspect` 仍能读回 7 个 toolNames
2. **保持 CopilotService 不变**：路由层的修改不应影响核心服务逻辑
3. **保持权限门控**：路由修改后仍需确保 `current_context.permission` 正确传递
4. **不要 overclaim**：即使路由成功，也不能说"生产部署已完成"或"全量飞书接入"
5. **记录所有 OpenClaw CLI 输出**：诊断过程中记录完整输出，用于 handoff 文档

---

## 6. 验证命令

### 6.1 基础环境检查

```bash
# 检查 OpenClaw 版本
python3 scripts/check_openclaw_version.py

# 检查插件状态
openclaw plugins inspect feishu-memory-copilot --json

# 检查 websocket 状态
openclaw channels status --probe --json

# 检查单监听
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
```

### 6.2 工具路由诊断

```bash
# 列出 OpenClaw 所有可用工具
openclaw tools list --json

# 检查 Agent 配置
openclaw agent config --json

# 检查 Agent 加载的 skills
openclaw agent skills --json
```

### 6.3 端到端验证

```bash
# 发送测试 DM 并检查 tool call
openclaw agent run --message "生产部署 region 是什么？" --json | jq '.tool_calls'

# 检查 gateway 日志中的 tool dispatch
openclaw logs --follow --json | grep -E "memory\.search|memory_search|tool_call"

# 路由诊断脚本
python3 scripts/check_feishu_dm_routing.py --json --timeout 60
```

### 6.4 测试套件

```bash
# 工具注册测试
python3 -m unittest tests.test_openclaw_tool_registry -v

# 运行时证据测试
python3 -m unittest tests.test_openclaw_runtime_evidence -v

# 路由测试（新增）
python3 -m unittest tests.test_feishu_dm_routing -v

# 完整健康检查
python3 scripts/check_copilot_health.py --json
```

### 6.5 完成标准检查清单

```bash
# 所有以下命令应返回成功
python3 scripts/check_openclaw_version.py
openclaw plugins inspect feishu-memory-copilot --json | jq '.enabled'
openclaw channels status --probe --json | jq '.channel_running'
python3 scripts/check_feishu_dm_routing.py --json | jq '.ok'
python3 -m unittest tests.test_feishu_dm_routing -v
```

---

## 7. 预估总时间

| 子任务 | 预估时间 | 阻塞项 |
|---|---|---|
| 1. 诊断 dispatch 机制 | 2-4h | 无 |
| 2. 禁用/覆盖内置工具 | 4-8h | 子任务 1 |
| 3. 强化 skill 引导 | 2-4h | 无 |
| 4. 端到端验证 | 4-6h | 子任务 2, 3 |
| 5. 保留 metadata | 2-3h | 子任务 4 |
| 6. 编写测试 | 2-3h | 子任务 4, 5 |
| 7. 诊断脚本 | 2-3h | 子任务 4 |
| 8. handoff 文档 | 1-2h | 全部 |
| **总计** | **19-33h** | - |

建议按 3-5 个工作日规划，预留 buffer 应对 OpenClaw 内部机制的不确定性。
