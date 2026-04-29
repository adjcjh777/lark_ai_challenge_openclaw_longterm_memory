# TODO-1 Handoff: 真实飞书 DM 到 first-class memory.* tool routing

日期：2026-04-29
状态：已完成一次受控真实 DM allow-path live E2E；仍不宣称稳定长期路由
负责人：程俊豪

---

## 1. 做了什么

### 根因诊断

发现并解决了本地 Agent 工具路由和真实飞书 DM 验收中的关键问题：

1. **工具名包含点号 (`.`)**：OpenAI API 要求工具名匹配 `^[a-zA-Z0-9_-]+$`，但我们的工具名如 `memory.search` 包含点号，导致 API 拒绝工具注册。

2. **`tools.alsoAllow` 未配置**：OpenClaw 的 `tools.profile: "coding"` 只包含内置工具，插件工具需要通过 `tools.alsoAllow` 显式添加。

3. **Permission context 必须 fail closed**：Python runner 要求 Agent 提供完整的 `current_context.permission`；缺失、畸形、tenant/org/scope mismatch 都必须拒绝，不能自动生成宽松默认权限。

4. **MiMo / openai-completions 嵌套对象序列化**：2026-04-29 真实 DM 复测中，`mimo-v2.5` / `mimo-v2.5-pro` 可能把 `current_context` 对象序列化为 JSON 字符串。旧 schema 会在 OpenClaw 工具参数校验层报 `current_context: must be object`，无法进入插件和 `CopilotService`。

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

4. **Permission fail-closed**：后续权限 contract 已收紧；Agent / adapter 必须提供 `current_context.permission`，缺失或畸形时 runner 会拒绝，不再自动生成宽松默认值。

5. **JSON-string compatibility shim**：`memory_tools.schema.json` 的 `current_context` 改为 `$defs.current_context_payload`，允许对象或 JSON 字符串；OpenClaw 插件和 Python runner 都会把 JSON object string 解析回对象。解析失败或解析后缺少 permission 时仍 fail closed。

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
$ python3 -m unittest tests.test_copilot_tools tests.test_feishu_dm_routing -v
...
Ran 37 tests
OK
```

### 2.6 真实飞书 DM allow-path live E2E

时间：2026-04-29 11:04-11:07（Asia/Shanghai）

受控 DM 请求：

```text
请直接调用 fmc_memory_search 搜索 "Copilot live sandbox 验收口径"，
scope=project:feishu_ai_challenge，top_k=5。
current_context.permission 使用 demo tenant/org、reviewer actor、
request_id=req_feishu_dm_live_20260429_1104、
trace_id=trace_feishu_dm_live_20260429_1104。
```

本地证据：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw channels status --probe --json
rg -n 'req_feishu_dm_live_20260429_1104|trace_feishu_dm_live_20260429_1104|dispatch complete' \
  /tmp/openclaw/openclaw-2026-04-29.log ~/.openclaw/agents/main/sessions/<session>.jsonl
lark-cli im +chat-messages-list --profile feishu-ai-challenge --as user --chat-id <redacted-p2p-chat-id> --page-size 10 --sort desc
```

读回结果：

```text
OpenClaw gateway:
- received p2p DM
- dispatching to agent session
- direct fmc_memory_search tool call
- dispatch complete (queuedFinal=true, replies=1)

Tool bridge:
- ok=true
- returned_count=5
- bridge.tool=fmc_memory_search
- request_id=req_feishu_dm_live_20260429_1104
- trace_id=trace_feishu_dm_live_20260429_1104
- permission_decision=allow / scope_access_granted

Feishu reply:
- bot reply at 2026-04-29 11:07
- content includes "通过，命中 5 条"
- content includes request_id, trace_id, permission_decision
```

注意：真实 `chat_id`、`open_id`、Feishu message id 只保存在本机日志和 CLI 输出中，不写入仓库。

---

## 3. 边界

### 可以说

- ✅ 插件工具已成功注册到 OpenClaw Agent
- ✅ 本地 OpenClaw Agent 测试中可见并可调用 `fmc_memory_search`
- ✅ 本地链路通顺：Agent → plugin → Python runner → CopilotService
- ✅ Bridge metadata (request_id, trace_id, permission_decision) 正确保留
- ✅ 所有 7 个工具路径已验证
- ✅ 缺失 `current_context.permission` 时 fail closed，不回退到宽松默认权限
- ✅ 一次受控真实 Feishu DM 已进入 OpenClaw websocket，直接调用 `fmc_memory_search`，进入 `handle_tool_request()` / `CopilotService`，并在飞书 DM 中读回 allow-path 结果
- ✅ MiMo / openai-completions 把 `current_context` 序列化成 JSON 字符串时，插件和 runner 可解析； malformed 字符串仍 fail closed

### 不能说

- ❌ 不能说"生产部署已完成"——这只是本地开发环境验证
- ❌ 不能说"全量飞书接入"——只完成受控 DM 和测试群/本地底座，不是全量 workspace ingestion
- ❌ 不能说"真实 Feishu DM 已稳定路由到本项目工具"——当前只有一次受控 `fmc_memory_search` allow-path 证据，仍缺长期运行和更多工具动作验证
- ❌ 不能说"性能已优化"——未做性能测试

---

## 4. 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `agent_adapters/openclaw/memory_tools.schema.json` | 工具名从 `memory.xxx` 改为 `fmc_xxx`；`current_context` 使用 `current_context_payload`，兼容对象和 JSON object string |
| `agent_adapters/openclaw/plugin/index.js` | 添加 `OPENCLAW_TO_PYTHON` 翻译映射；把 JSON-string `current_context` 解析回对象后再调用 Python runner |
| `agent_adapters/openclaw/tool_registry.py` | 添加翻译层，更新验证逻辑；在每个工具 input schema 中嵌入 `$defs` 供 OpenClaw manifest 消费 |
| `agent_adapters/openclaw/feishu_memory_copilot.skill.md` | 更新工具名引用 |
| `agent_adapters/openclaw/examples/*.json` | 更新工具名引用 |
| `memory_engine/copilot/openclaw_tool_runner.py` | 在 Python runner 侧防御性解析 JSON-string `current_context`，解析失败仍按权限/验证 fail closed |
| `tests/test_openclaw_tool_registry.py` | 更新测试以处理名称翻译 |
| `tests/test_feishu_dm_routing.py` | 新增路由测试、JSON-string 兼容测试和 malformed fail-closed 测试 |
| `tests/test_copilot_tools.py` | 更新 schema contract 断言，确保工具都引用 `current_context_payload` |
| `scripts/check_feishu_dm_routing.py` | 新增诊断脚本 |
| `~/.openclaw/openclaw.json` | 添加 `tools.alsoAllow` 配置 |

---

## 5. 下一步

1. **固定评委/用户主路径脚本**：把 11:04 这类受控 DM 验收收敛成可复测脚本、用户提示和失败 fallback。
2. **扩展真实 DM 工具动作**：继续验证 `fmc_memory_prefetch`、`fmc_memory_create_candidate` 等关键动作；真实飞书来源仍只能进入 candidate。
3. **性能优化**：Python 子进程启动时间和 LLM fallback 会影响响应速度；11:04 复测中 `mimo-v2.5` 首次超时后 fallback 到 `mimo-v2.5-pro` 才完成。
4. **监控和告警**：添加工具调用成功率、permission deny、LLM timeout/fallback 和 Feishu reply latency 监控。
