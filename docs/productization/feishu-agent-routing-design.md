# Feishu Agent Tool Routing 设计

日期：2026-04-28
状态：方案设计（本地 Agent `fmc_*` 工具路由已补，真实飞书 DM live E2E 仍待验收）
适用范围：Feishu Agent Tool Routing 问题分析、routing 方案、fallback 方案

---

## 1. 问题分析

### 1.1 当前问题

**历史核心问题**：2026-04-28 websocket staging 证据中，真实 Feishu DM 触发的是 OpenClaw 内置 `memory_search`，而不是本项目 first-class 工具。

**当前边界**：后续已补本地 Agent `fmc_*` 工具调用验证，`fmc_*` 会翻译到 Python 侧 `memory.*` 并进入 `CopilotService`；但还缺真实飞书 DM live E2E 证据，不能写成真实 DM 已稳定路由到本项目工具。

### 1.2 问题详情

| 问题 | 说明 | 影响 |
|------|------|------|
| 工具路由错误 | 飞书消息进入 OpenClaw 内置工具 | 无法使用本项目的权限、审计、检索逻辑 |
| Permission 缺失 | 内置工具不带 current_context.permission | 无法执行 fail-closed 权限检查 |
| Audit 缺失 | 内置工具不写审计日志 | 无法追踪操作和审计 |
| 检索质量差异 | 内置工具使用简单检索 | 无法使用 hybrid retrieval |

### 1.3 技术原因

```text
当前流程（错误）：
User DM (@Bot question)
  -> OpenClaw Gateway
  -> Agent Runtime
  -> OpenClaw 内置 memory_search（不经过 CopilotService，该路径是历史 staging 问题）
  -> 返回结果

期望流程（正确）：
User DM (@Bot question)
  -> OpenClaw Gateway
  -> Agent Runtime
  -> Tool Router
  -> fmc_memory_search（OpenClaw-facing tool）
  -> memory.search（Python-side tool，经过 handle_tool_request -> CopilotService）
  -> 返回结果
```

---

## 2. Routing 方案设计

### 2.1 方案 1：OpenClaw Plugin Registry（推荐）

**原理**：通过 OpenClaw Plugin 系统注册本项目工具，覆盖内置工具。

**实现步骤**：

```python
# agent_adapters/openclaw/plugin/index.js

const { ToolRegistry } = require('openclaw-plugin-sdk');

// 注册本项目工具
ToolRegistry.register({
  name: 'memory.search',
  description: 'Search enterprise memories with permission control',
  handler: async (params) => {
    // 调用 CopilotService
    return await callCopilotService('memory.search', params);
  }
});

// 覆盖内置工具
ToolRegistry.override('memory_search', 'memory.search');
```

**优点**：
- 不修改 OpenClaw 核心代码
- 通过插件系统自然覆盖
- 保持 OpenClaw 版本锁定

**缺点**：
- 依赖 OpenClaw Plugin API 稳定性
- 需要验证覆盖逻辑

### 2.2 方案 2：Tool Router 配置

**原理**：在 OpenClaw Agent Runtime 配置 Tool Router，指定工具路由规则。

**实现步骤**：

```yaml
# openclaw-config.yaml

agent:
  tool_router:
    rules:
      - match:
          tool_name: "memory.*"
        route_to:
          plugin: "feishu-memory-copilot"
          handler: "handle_tool_request"
      - match:
          tool_name: "memory_search"
        route_to:
          plugin: "feishu-memory-copilot"
          handler: "handle_tool_request"
    fallback:
      route_to:
        builtin: true
```

**优点**：
- 配置化，灵活
- 支持 fallback 规则
- 可动态调整

**缺点**：
- 依赖 OpenClaw Tool Router 功能
- 配置复杂度高

### 2.3 方案 3：Gateway Webhook 拦截

**原理**：在 OpenClaw Gateway 层拦截飞书消息，直接路由到本项目服务。

**实现步骤**：

```python
# memory_engine/copilot/feishu_gateway_interceptor.py

class FeishuGatewayInterceptor:
    """飞书 Gateway 拦截器"""

    def intercept(self, event):
        """拦截飞书事件"""
        # 解析消息内容
        message = self.parse_message(event)

        # 如果是 @Bot 消息，直接路由到 CopilotService
        if self.is_bot_mention(message):
            return self.route_to_copilot(message)

        # 否则交给 OpenClaw 处理
        return self.forward_to_openclaw(event)
```

**优点**：
- 完全控制路由逻辑
- 不依赖 OpenClaw 内部机制
- 可实现复杂路由规则

**缺点**：
- 需要修改 Gateway 层
- 维护成本高
- 可能与 OpenClaw 更新冲突

### 2.4 方案对比

| 方案 | 复杂度 | 维护成本 | 灵活性 | 推荐度 |
|------|--------|----------|--------|--------|
| Plugin Registry | 中 | 低 | 中 | ⭐⭐⭐⭐⭐ |
| Tool Router 配置 | 低 | 中 | 高 | ⭐⭐⭐⭐ |
| Gateway 拦截 | 高 | 高 | 高 | ⭐⭐⭐ |

**推荐方案**：方案 1（Plugin Registry）

---

## 3. Plugin Registry 实现细节

### 3.1 插件结构

```
agent_adapters/openclaw/plugin/
├── index.js              # 插件入口
├── package.json          # 依赖配置
├── tools/
│   ├── memory_search.js      # memory.search 工具
│   ├── memory_create.js      # memory.create_candidate 工具
│   ├── memory_confirm.js     # memory.confirm 工具
│   ├── memory_reject.js      # memory.reject 工具
│   ├── memory_explain.js     # memory.explain_versions 工具
│   ├── memory_prefetch.js    # memory.prefetch 工具
│   └── heartbeat_review.js   # heartbeat.review_due 工具
├── permission/
│   └── context.js            # Permission Context 构建
└── audit/
    └── logger.js             # Audit Logger
```

### 3.2 工具注册

```javascript
// agent_adapters/openclaw/plugin/index.js

const { Plugin, ToolRegistry, PermissionChecker, AuditLogger } = require('openclaw-plugin-sdk');
const { callCopilotService } = require('./copilot_client');

class FeishuMemoryCopilotPlugin extends Plugin {
  name = 'feishu-memory-copilot';
  version = '1.0.0';

  async onInit() {
    // 注册工具
    this.registerTools();

    // 注册权限检查器
    this.registerPermissionChecker();

    // 注册审计日志器
    this.registerAuditLogger();
  }

  registerTools() {
    // memory.search
    ToolRegistry.register({
      name: 'memory.search',
      description: 'Search enterprise memories with permission control',
      parameters: {
        query: { type: 'string', required: true },
        scope_type: { type: 'string', required: false },
        scope_id: { type: 'string', required: false },
        top_k: { type: 'number', required: false, default: 5 }
      },
      handler: async (params, context) => {
        return await this.handleTool('memory.search', params, context);
      }
    });

    // 覆盖内置 memory_search
    ToolRegistry.override('memory_search', 'memory.search');

    // 其他工具类似注册...
  }

  async handleTool(action, params, context) {
    // 1. 构建 Permission Context
    const permissionContext = this.buildPermissionContext(context);

    // 2. 调用 CopilotService
    const result = await callCopilotService(action, {
      ...params,
      current_context: {
        permission: permissionContext
      }
    });

    // 3. 记录审计日志
    await this.auditLogger.log({
      action,
      params,
      result,
      permissionContext
    });

    return result;
  }

  buildPermissionContext(context) {
    return {
      request_id: context.request_id || this.generateRequestId(),
      trace_id: context.trace_id || this.generateTraceId(),
      actor: {
        user_id: context.user_id,
        open_id: context.open_id,
        tenant_id: context.tenant_id,
        organization_id: context.organization_id,
        roles: context.roles || ['member']
      },
      source_context: {
        entrypoint: 'openclaw',
        workspace_id: context.workspace_id,
        chat_id: context.chat_id,
        document_id: context.document_id
      },
      requested_action: context.action,
      requested_visibility: context.visibility || 'team',
      timestamp: new Date().toISOString()
    };
  }
}

module.exports = FeishuMemoryCopilotPlugin;
```

### 3.3 飞书事件解析

```javascript
// agent_adapters/openclaw/plugin/feishu_event_parser.js

class FeishuEventParser {
  parse(event) {
    // 解析飞书事件
    const { header, event: eventData } = event;

    // 提取用户信息
    const sender = eventData.sender;
    const message = eventData.message;

    return {
      // 用户信息
      user_id: sender.sender_id.user_id,
      open_id: sender.sender_id.open_id,
      tenant_id: sender.tenant_id,

      // 消息信息
      chat_id: message.chat_id,
      chat_type: message.chat_type,
      message_type: message.message_type,
      content: this.parseContent(message.content),

      // 元数据
      event_type: header.event_type,
      create_time: message.create_time,
      message_id: message.message_id
    };
  }

  parseContent(content) {
    try {
      return JSON.parse(content);
    } catch {
      return { text: content };
    }
  }
}

module.exports = FeishuEventParser;
```

---

## 4. Fallback 方案设计

### 4.1 Fallback 场景

| 场景 | 说明 | Fallback 策略 |
|------|------|---------------|
| Plugin 加载失败 | 插件初始化错误 | 使用内置工具 + 审计告警 |
| CopilotService 不可用 | 服务连接失败 | 返回错误 + 审计告警 |
| Permission Context 缺失 | 飞书事件解析失败 | deny + 审计告警 |
| 超时 | 请求处理超时 | 重试 1 次 + fallback |
| 数据库不可用 | PostgreSQL 连接失败 | 返回错误 + 审计告警 |

### 4.2 Fallback 实现

```javascript
// agent_adapters/openclaw/plugin/fallback_handler.js

class FallbackHandler {
  constructor(auditLogger) {
    this.auditLogger = auditLogger;
  }

  async handleWithFallback(action, params, context) {
    try {
      // 尝试主路径
      return await this.handlePrimary(action, params, context);
    } catch (error) {
      console.error(`Primary handler failed: ${error.message}`);

      // 记录审计告警
      await this.auditLogger.logAlert({
        type: 'fallback_triggered',
        action,
        error: error.message,
        context
      });

      // 尝试 fallback
      return await this.handleFallback(action, params, context, error);
    }
  }

  async handlePrimary(action, params, context) {
    // 主路径：调用 CopilotService
    const permissionContext = this.buildPermissionContext(context);

    const result = await callCopilotService(action, {
      ...params,
      current_context: {
        permission: permissionContext
      }
    });

    return result;
  }

  async handleFallback(action, params, context, originalError) {
    // Fallback 1：使用内置工具（如果有）
    if (this.hasBuiltinTool(action)) {
      console.log(`Falling back to builtin tool: ${action}`);
      return await this.handleBuiltin(action, params, context);
    }

    // Fallback 2：返回错误
    return {
      success: false,
      error: {
        code: 'FALLBACK_TRIGGERED',
        message: `Primary handler failed: ${originalError.message}`,
        fallback_used: true
      }
    };
  }

  hasBuiltinTool(action) {
    const builtinTools = ['memory_search'];
    return builtinTools.includes(action);
  }

  async handleBuiltin(action, params, context) {
    // 调用 OpenClaw 内置工具
    // 注意：这会跳过权限检查和审计
    const openclaw = require('openclaw');
    return await openclaw.tools.invoke(action, params);
  }

  buildPermissionContext(context) {
    // ... 同 Plugin 实现
  }
}

module.exports = FallbackHandler;
```

### 4.3 Fallback 告警

```javascript
// agent_adapters/openclaw/plugin/fallback_alert.js

class FallbackAlert {
  constructor(webhookUrl) {
    this.webhookUrl = webhookUrl;
  }

  async sendAlert(alert) {
    const message = {
      msg_type: 'interactive',
      card: {
        header: {
          title: {
            tag: 'plain_text',
            content: '⚠️ Tool Routing Fallback Triggered'
          },
          template: 'orange'
        },
        elements: [
          {
            tag: 'div',
            text: {
              tag: 'lark_md',
              content: `
**Action**: ${alert.action}
**Error**: ${alert.error}
**Time**: ${new Date().toISOString()}
**Context**: ${JSON.stringify(alert.context, null, 2)}
              `
            }
          }
        ]
      }
    };

    await fetch(this.webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message)
    });
  }
}

module.exports = FallbackAlert;
```

---

## 5. 测试方案

### 5.1 单元测试

```python
# tests/test_feishu_agent_routing.py

def test_tool_override():
    """验证工具覆盖"""
    # 注册插件
    plugin = FeishuMemoryCopilotPlugin()
    plugin.onInit()

    # 验证工具注册
    tools = ToolRegistry.list()
    assert 'memory.search' in tools
    assert 'memory_search' in tools  # 内置工具被覆盖

def test_permission_context_build():
    """验证 Permission Context 构建"""
    context = {
        'user_id': 'u_001',
        'open_id': 'ou_001',
        'tenant_id': 'tenant_a',
        'organization_id': 'org_a',
        'roles': ['member']
    }

    permission_context = buildPermissionContext(context)

    assert permission_context['actor']['user_id'] == 'u_001'
    assert permission_context['actor']['tenant_id'] == 'tenant_a'
    assert permission_context['source_context']['entrypoint'] == 'openclaw'

def test_fallback_handler():
    """验证 Fallback 处理"""
    handler = FallbackHandler(audit_logger)

    # 模拟主路径失败
    with mock.patch('callCopilotService', side_effect=ConnectionError):
        result = handler.handleWithFallback('memory.search', {}, {})

    assert result['success'] == False
    assert result['error']['fallback_used'] == True
```

### 5.2 集成测试

```python
# tests/test_feishu_routing_integration.py

def test_feishu_dm_routing():
    """验证飞书 DM 路由到 CopilotService"""
    # 模拟飞书事件
    event = {
        'header': {'event_type': 'im.message.receive_v1'},
        'event': {
            'sender': {
                'sender_id': {'user_id': 'u_001', 'open_id': 'ou_001'},
                'tenant_id': 'tenant_a'
            },
            'message': {
                'chat_id': 'oc_001',
                'chat_type': 'p2p',
                'message_type': 'text',
                'content': '{"text": "@Bot 查询项目进度"}'
            }
        }
    }

    # 处理事件
    result = process_feishu_event(event)

    # 验证路由到 CopilotService
    assert result['handler'] == 'CopilotService'
    assert result['action'] == 'memory.search'
    assert result['permission_checked'] == True
    assert result['audit_logged'] == True

def test_permission_deny_routing():
    """验证权限拒绝路由"""
    event = {
        # ... 模拟无权限事件
    }

    result = process_feishu_event(event)

    assert result['handler'] == 'CopilotService'
    assert result['permission_decision'] == 'deny'
    assert result['audit_logged'] == True
```

### 5.3 端到端测试

```python
# tests/test_e2e_routing.py

def test_e2e_feishu_search():
    """端到端飞书搜索测试"""
    # 1. 启动 OpenClaw
    # 2. 发送飞书消息
    # 3. 验证 CopilotService 被调用
    # 4. 验证权限检查
    # 5. 验证审计日志
    # 6. 验证返回结果
    pass
```

---

## 6. 部署步骤

### 6.1 插件部署

```bash
# 1. 安装插件
openclaw plugins install agent_adapters/openclaw/plugin/

# 2. 验证插件
openclaw plugins inspect feishu-memory-copilot --json

# 3. 重启 OpenClaw
openclaw gateway restart
openclaw agent restart

# 4. 验证工具注册
openclaw tools list --json | jq '.[] | select(.name | startswith("memory"))'
```

### 6.2 验证路由

```bash
# 1. 发送测试消息
# 在飞书测试群发送 @Bot 查询项目进度

# 2. 检查日志
tail -f logs/openclaw.log | grep "memory.search"

# 3. 检查审计日志
python3 scripts/query_audit_events.py --json --limit 10

# 4. 验证 CopilotService 被调用
grep "CopilotService" logs/*.log
```

---

## 7. 监控和告警

### 7.1 监控指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `routing_fallback_total` | counter | Fallback 触发次数 | > 0 |
| `routing_bypass_total` | counter | 绕过 CopilotService 次数 | > 0 |
| `routing_success_total` | counter | 路由成功次数 | - |
| `routing_failure_total` | counter | 路由失败次数 | - |

### 7.2 告警规则

```yaml
# prometheus-alerts.yml
groups:
  - name: routing
    rules:
      - alert: RoutingFallbackTriggered
        expr: routing_fallback_total > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Tool routing fallback triggered"
          description: "A fallback was triggered, indicating potential routing issue"

      - alert: RoutingBypassDetected
        expr: routing_bypass_total > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "CopilotService bypass detected"
          description: "A request bypassed CopilotService, missing permission and audit checks"
```

---

## 8. 实现优先级

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | Plugin Registry 实现 | 核心路由修复 |
| P0 | Permission Context 构建 | 权限检查 |
| P0 | Audit Logger | 审计日志 |
| P1 | Fallback Handler | 降级处理 |
| P1 | 单元测试 | 代码质量 |
| P2 | 集成测试 | 端到端验证 |
| P2 | 监控告警 | 运维需求 |

---

## 9. 参考文档

- `agent_adapters/openclaw/plugin/` - 插件目录
- `memory_engine/copilot/feishu_live.py` - 飞书事件处理
- `memory_engine/copilot/service.py` - CopilotService
- `docs/productization/contracts/permission-contract.md` - 权限契约
- `docs/productization/contracts/audit-observability-contract.md` - 审计契约
