# Feishu Memory Copilot - 审计 UI 设计

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：审计查询界面、审计导出、审计 Dashboard

---

## 1. 设计目标

### 1.1 核心目标

1. **审计查询**：支持多维度查询审计事件
2. **审计导出**：支持 CSV/JSON 导出，用于合规审查
3. **审计 Dashboard**：可视化审计事件趋势和异常
4. **审计追溯**：支持按 request_id/trace_id 追溯完整链路

### 1.2 设计原则

- 查询高效（支持时间范围、actor、event_type、tenant）
- 导出灵活（CSV/JSON）
- 可视化直观（趋势图、异常检测）
- 安全合规（不记录敏感信息）

---

## 2. 审计查询界面需求

### 2.1 查询维度

| 维度 | 类型 | 说明 | 示例 |
|------|------|------|------|
| 时间范围 | 日期范围 | 开始/结束时间 | 2026-04-01 ~ 2026-04-28 |
| Actor | 文本 | 操作者 ID | u_001 |
| Event Type | 下拉 | 事件类型 | memory.search, candidate.confirmed |
| Tenant | 文本 | 租户 ID | tenant_a |
| Organization | 文本 | 组织 ID | org_a |
| Permission Decision | 下拉 | 权限决策 | allow, deny, redact |
| Target Type | 下拉 | 目标类型 | memory, candidate, evidence |
| Target ID | 文本 | 目标 ID | mem_001, c_001 |
| Request ID | 文本 | 请求 ID | req_20260428_001 |
| Trace ID | 文本 | 链路 ID | trace_20260428_001 |

### 2.2 查询界面

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Audit Query                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Time Range: [2026-04-01] to [2026-04-28]                      │
│                                                                 │
│  Actor:        [________________]                               │
│  Event Type:   [All ▼]                                         │
│  Tenant:       [________________]                               │
│  Organization: [________________]                               │
│  Decision:     [All ▼]                                         │
│  Target Type:  [All ▼]                                         │
│  Target ID:    [________________]                               │
│  Request ID:   [________________]                               │
│  Trace ID:     [________________]                               │
│                                                                 │
│  [Search]  [Reset]  [Export CSV]  [Export JSON]                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Results: 1,234 events (showing 1-50)                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Time       │ Actor │ Event Type    │ Decision │ Target │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  10:30:15   │ u_001 │ memory.search │ allow    │ mem_01 │   │
│  │  10:29:45   │ u_002 │ candidate.confirm │ allow │ c_001 │   │
│  │  10:28:30   │ u_003 │ memory.search │ deny     │ -      │   │
│  │  ...        │ ...   │ ...           │ ...      │ ...    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [← Previous]  Page 1 of 25  [Next →]                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 查询详情

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Audit Event Detail                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Audit ID:     audit_20260428_001                              │
│  Request ID:   req_20260428_001                                │
│  Trace ID:     trace_20260428_001                              │
│  Time:         2026-04-28 10:30:15                             │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Actor                                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  User ID:     u_001                                     │   │
│  │  Roles:       [reviewer, member]                        │   │
│  │  Tenant:      tenant_a                                  │   │
│  │  Organization: org_a                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Action                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Action:      memory.search                             │   │
│  │  Target Type: memory                                    │   │
│  │  Target ID:   mem_001                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Permission Decision                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Decision:    allow                                     │   │
│  │  Reason Code: same_org_team_visibility                  │   │
│  │  Visible:     [subject, current_value, summary]         │   │
│  │  Redacted:    []                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Source Context                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Entrypoint:  openclaw                                  │   │
│  │  Workspace:   project:feishu-memory-copilot             │   │
│  │  Chat ID:     oc_xxxxx (masked)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [View Trace Chain]  [Back to Query]                           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 链路追溯

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Trace Chain                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Trace ID: trace_20260428_001                                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  10:30:15  [1] memory.search                            │   │
│  │            │  Actor: u_001                              │   │
│  │            │  Decision: allow                           │   │
│  │            │  Duration: 120ms                           │   │
│  │            ▼                                            │   │
│  │  10:30:15  [2] permission.check                         │   │
│  │            │  Decision: allow                           │   │
│  │            │  Reason: same_org_team_visibility          │   │
│  │            ▼                                            │   │
│  │  10:30:15  [3] retrieval.execute                        │   │
│  │            │  Source: hybrid (cognee + sqlite)          │   │
│  │            │  Results: 3 memories                       │   │
│  │            ▼                                            │   │
│  │  10:30:15  [4] response.compose                         │   │
│  │               Visible fields: [subject, value, summary] │   │
│  │               Redacted fields: []                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [Back to Event]  [Export Trace]                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 审计导出需求

### 3.1 导出格式

| 格式 | 说明 | 适用场景 |
|------|------|----------|
| CSV | 逗号分隔，Excel 兼容 | 人工审查、数据分析 |
| JSON | 结构化数据 | 程序处理、API 集成 |
| JSON Lines | 每行一条 JSON | 大数据处理 |

### 3.2 导出字段

| 字段 | CSV | JSON | 说明 |
|------|-----|------|------|
| audit_id | ✓ | ✓ | 审计 ID |
| request_id | ✓ | ✓ | 请求 ID |
| trace_id | ✓ | ✓ | 链路 ID |
| actor_id | ✓ | ✓ | 操作者 |
| actor_roles | ✓ | ✓ | 角色列表 |
| tenant_id | ✓ | ✓ | 租户 |
| organization_id | ✓ | ✓ | 组织 |
| action | ✓ | ✓ | 动作 |
| target_type | ✓ | ✓ | 目标类型 |
| target_id | ✓ | ✓ | 目标 ID |
| permission_decision | ✓ | ✓ | 权限决策 |
| reason_code | ✓ | ✓ | 原因码 |
| visible_fields | ✓ | ✓ | 可见字段 |
| redacted_fields | ✓ | ✓ | 脱敏字段 |
| source_context | ✓ | ✓ | 来源上下文 |
| created_at | ✓ | ✓ | 时间 |

### 3.3 导出 API

```python
# memory_engine/copilot/audit_export.py

class AuditExportService:
    """审计导出服务"""

    def export_csv(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        filters: dict = None
    ) -> str:
        """导出 CSV"""
        pass

    def export_json(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        filters: dict = None
    ) -> list[dict]:
        """导出 JSON"""
        pass

    def export_jsonlines(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        filters: dict = None
    ) -> str:
        """导出 JSON Lines"""
        pass
```

### 3.4 导出限制

| 限制 | 值 | 说明 |
|------|-----|------|
| 最大导出行数 | 100,000 | 超过需分批 |
| 导出时间范围 | 90 天 | 超过需申请 |
| 并发导出数 | 3 | 避免资源争用 |
| 导出文件大小 | 100 MB | 超过需分批 |

---

## 4. 审计 Dashboard 需求

### 4.1 Overview Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Audit Overview (24h)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Total Events: 12,450  │  Deny Rate: 8.2%  │  Avg Latency: 120ms│
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Events by Hour                                                 │
│                                                                 │
│  Count                                                           │
│  1000|                                                          │
│   800|  *   *   *   *   *   *   *   *                           │
│   600|  *   *   *   *   *   *   *   *   *   *   *   *           │
│   400|  *   *   *   *   *   *   *   *   *   *   *   *           │
│   200|  *   *   *   *   *   *   *   *   *   *   *   *           │
│     0|__*___*___*___*___*___*___*___*___*___*___*___*___*___*__│
│       00  02  04  06  08  10  12  14  16  18  20  22           │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Permission Decisions                                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Allow    [████████████████████████████████████]  91.8% │   │
│  │  Deny     [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   6.5% │   │
│  │  Redact   [█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   1.7% │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Top Actions                                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  memory.search        ████████████████████  8,500       │   │
│  │  candidate.confirm    ████████████         2,800        │   │
│  │  candidate.reject     ████████             1,150        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Security Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Security Audit (7d)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Permission Denials: 523  │  Consecutive Deny Alerts: 3        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Deny Rate Trend (7d)                                           │
│                                                                 │
│  Rate %                                                         │
│   20%|                                                          │
│   15%|      *                                                   │
│   10%|  *   *   *                                               │
│    5%|  *   *   *   *   *                                       │
│    0%|__*___*___*___*___*___*___*___*___*___*___*___*___*___*__│
│       Mon Tue Wed Thu Fri Sat Sun                               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Top Deny Reasons                                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  tenant_mismatch           ████████████  45%            │   │
│  │  visibility_private        ████████      32%            │   │
│  │  missing_permission        █████         18%            │   │
│  │  other                     █             5%             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Suspicious Activities                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Time       │ Actor │ Event           │ Count │ Alert  │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  10:30      │ u_999 │ permission.deny │ 15    │ ⚠️     │   │
│  │  11:15      │ u_888 │ memory.search   │ 500   │ ⚠️     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Compliance Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Compliance Report (30d)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Data Deletion Requests: 12  │  Completed: 10  │  Pending: 2   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Deletion Requests                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Date       │ User   │ Reason      │ Status  │ Complete │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  2026-04-25 │ u_001  │ GDPR        │ Done    │ 2h       │   │
│  │  2026-04-26 │ u_002  │ User request│ Done    │ 1h       │   │
│  │  2026-04-27 │ u_003  │ Compliance  │ Pending │ -        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Data Retention                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Active Memories:     15,230  (retain: permanent)       │   │
│  │  Candidates:          2,450   (retain: 90 days)         │   │
│  │  Audit Events:        125,000 (retain: 90 days)         │   │
│  │  Deleted Data:        120     (retain: 30 days)         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Export History                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Date       │ User   │ Format │ Records │ Size    │ Time │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  2026-04-28 │ admin  │ CSV    │ 50,000  │ 12 MB   │ 5s   │   │
│  │  2026-04-27 │ auditor│ JSON   │ 25,000  │ 8 MB    │ 3s   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. API 接口

### 5.1 审计查询 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/audit/events | 查询审计事件 |
| GET | /api/audit/events/:id | 获取事件详情 |
| GET | /api/audit/trace/:trace_id | 获取链路追溯 |
| GET | /api/audit/summary | 获取统计摘要 |

### 5.2 审计导出 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/audit/export/csv | 导出 CSV |
| POST | /api/audit/export/json | 导出 JSON |
| GET | /api/audit/export/:export_id | 获取导出文件 |

### 5.3 审计 Dashboard API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/audit/dashboard/overview | Overview 数据 |
| GET | /api/audit/dashboard/security | Security 数据 |
| GET | /api/audit/dashboard/compliance | Compliance 数据 |

### 5.4 请求示例

```bash
# 查询审计事件
curl -X GET "http://localhost:8080/api/audit/events? \
  tenant_id=tenant_a& \
  start_time=2026-04-01T00:00:00Z& \
  end_time=2026-04-28T23:59:59Z& \
  event_type=memory.search& \
  decision=deny& \
  limit=50&offset=0" \
  -H "Authorization: Bearer <token>"

# 导出 CSV
curl -X POST "http://localhost:8080/api/audit/export/csv" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant_a",
    "start_time": "2026-04-01T00:00:00Z",
    "end_time": "2026-04-28T23:59:59Z",
    "filters": {
      "event_type": "memory.search"
    }
  }'
```

---

## 6. 实现优先级

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | 审计查询 API | 核心查询能力 |
| P0 | 审计查询界面 | 基础查询 UI |
| P1 | 审计导出 CSV/JSON | 合规要求 |
| P1 | 审计链路追溯 | 调试需求 |
| P2 | Overview Dashboard | 运维需求 |
| P2 | Security Dashboard | 安全需求 |
| P3 | Compliance Dashboard | 合规需求 |

---

## 7. 参考文档

- `docs/productization/contracts/audit-observability-contract.md` - 审计契约
- `docs/productization/monitoring-design.md` - 监控方案
- `docs/productization/permission-admin-design.md` - 权限后台
- `docs/productization/productized-live-architecture.md` - 架构图
