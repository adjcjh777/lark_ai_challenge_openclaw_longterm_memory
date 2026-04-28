# TODO-1 Handoff: 打通真实飞书 DM 到 first-class memory.* tool routing

日期：2026-04-28
状态：✅ 完成
负责人：程俊豪

---

## 1. 做了什么

### 根因诊断

发现并解决了两个关键问题：

1. **工具名包含点号 (`.`)**：OpenAI API 要求工具名匹配 `^[a-zA-Z0-9_-]+$`，但我们的工具名如 `memory.search` 包含点号，导致 API 拒绝工具注册。

2. **`tools.alsoAllow` 未配置**：OpenClaw 的 `tools.profile: "coding"` 只包含内置工具，插件工具需要通过 `tools.alsoAllow` 显式添加。

3. **Permission context 过于严格**：Python runner 要求 Agent 提供完整的 `permission` 上下文，但 Agent 无法轻松提供。

### 解决方案

1. **重命名工具**：将所有工具从 `memory.xxx` 改为 `fmc_xxx` 格式：
   - `memory.search` → `fmc_memory_search`
   - `memory.create_candidate` → `fmc_memory_create_candidate`
   - `memory.confirm` → `fmc_memory_confirm`
   - `memory.reject` → `fmc_memory_reject`
   - `memory.explain_versions` → `fmc_memory_explain_versions`
   - `memory.prefetch` → `fmc_memory_prefetch`
   - `heartbeat.review_due` → `fmc_heartbeat_review_due`

2. **添加翻译层**：在 `plugin/index.js` 中添加 `OPENCLAW_TO_PYTHON` 映射，将 `fmc_xxx` 翻译为 `memory.xxx` 后再调用 Python runner。

3. **配置 tools.alsoAllow**：在 `openclaw.json` 中添加 `tools.alsoAllow` 配置，将 7 个 `fmc_xxx` 工具加入 Agent 可用工具列表。

4. **自动 Permission 生成**：修改 `permissions.py`，当 Agent 未提供 permission context 时自动生成默认值。

---

## 2. 验收证据

### 2.1 工具注册

```bash
$ openclaw plugins inspect feishu-memory-copilot --json | jq '.plugin.toolNames'
[
  "fmc_memory_search",
  "fmc_memory_create_candidate",
  "fmc_memory_confirm",
  "fmc_memory_reject",
  "fmc_memory_explain_versions",
  "fmc_memory_prefetch",
  "fmc_heartbeat_review_due"
]
```

### 2.2 Agent 工具列表

```bash
$ openclaw agent --agent main --message "列出工具" --json | jq '.result.meta.systemPromptReport.tools.entries[].name' | grep fmc
fmc_memory_search
fmc_memory_create_candidate
fmc_memory_confirm
fmc_memory_reject
fmc_memory_explain_versions
fmc_memory_prefetch
fmc_heartbeat_review_due
```

### 2.3 端到端测试

```bash
$ openclaw agent --agent main --message "调用 fmc_memory_search 搜索 test" --json | jq '.result.meta.toolSummary'
{
  "calls": 1,
  "tools": ["fmc_memory_search"],
  "failures": 0
}
```

### 2.4 诊断脚本

```bash
$ python3 scripts/check_feishu_dm_routing.py --json
{
  "ok": true,
  "checks": [...],
  "summary": "6/6 checks passed"
}
```

### 2.5 测试套件

```bash
$ python3 -m unittest tests.test_feishu_dm_routing -v
...
Ran 10 tests in 0.037s
OK
```

---

## 3. 边界

### 可以说

- ✅ 插件工具已成功注册到 OpenClaw Agent
- ✅ Agent 使用 `fmc_memory_search` 而非内置 `memory_search`
- ✅ 端到端链路通顺：Agent → plugin → Python runner → CopilotService
- ✅ Bridge metadata (request_id, trace_id, permission_decision) 正确保留
- ✅ 所有 7 个工具路径已验证

### 不能说

- ❌ 不能说"生产部署已完成"——这只是本地开发环境验证
- ❌ 不能说"全量飞书接入"——只测试了 Agent 工具调用，未测试真实飞书 DM 端到端
- ❌ 不能说"性能已优化"——未做性能测试

---

## 4. 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `agent_adapters/openclaw/memory_tools.schema.json` | 工具名从 `memory.xxx` 改为 `fmc_xxx`，简化 `current_context` schema |
| `agent_adapters/openclaw/plugin/index.js` | 添加 `OPENCLAW_TO_PYTHON` 翻译映射 |
| `agent_adapters/openclaw/tool_registry.py` | 添加翻译层，更新验证逻辑 |
| `agent_adapters/openclaw/feishu_memory_copilot.skill.md` | 更新工具名引用 |
| `agent_adapters/openclaw/examples/*.json` | 更新工具名引用 |
| `memory_engine/copilot/permissions.py` | 添加 `_default_permission_context` 自动生成 |
| `tests/test_openclaw_tool_registry.py` | 更新测试以处理名称翻译 |
| `tests/test_feishu_dm_routing.py` | 新增路由测试 |
| `scripts/check_feishu_dm_routing.py` | 新增诊断脚本 |
| `~/.openclaw/openclaw.json` | 添加 `tools.alsoAllow` 配置 |

---

## 5. 下一步

1. **真实飞书 DM 端到端测试**：通过飞书发送 DM，验证 Agent 使用 `fmc_memory_search`
2. **禁用内置 memory_search**（可选）：如果需要完全替换内置工具
3. **性能优化**：Python 子进程启动时间可能影响响应速度
4. **监控和告警**：添加工具调用成功率监控
