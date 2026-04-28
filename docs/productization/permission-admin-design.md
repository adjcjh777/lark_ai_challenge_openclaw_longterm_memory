# Feishu Memory Copilot - 权限后台设计

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：多租户数据隔离、角色权限管理、审批流程、数据删除和遗忘

---

## 1. 设计目标

### 1.1 核心目标

1. **多租户隔离**：确保租户间数据完全隔离
2. **角色权限**：细粒度的权限控制
3. **审批流程**：候选记忆的审核机制
4. **数据删除**：支持用户数据删除和遗忘权
5. **审计追踪**：所有权限操作可追溯

### 1.2 设计原则

- Permission fail-closed（默认拒绝）
- 最小权限原则
- 职责分离
- 可审计、可追溯

---

## 2. 多租户数据隔离

### 2.1 隔离层级

```text
┌─────────────────────────────────────────────────────────────┐
│                     Tenant (租户)                            │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                 Organization (组织)                    │ │
│  │                                                       │ │
│  │  ┌─────────────────────────────────────────────────┐ │ │
│  │  │           Workspace (工作区)                     │ │ │
│  │  │                                                 │ │ │
│  │  │  ┌───────────────────────────────────────────┐ │ │ │
│  │  │  │              Scope (范围)                  │ │ │ │
│  │  │  │                                           │ │ │ │
│  │  │  │  - Project (项目)                         │ │ │ │
│  │  │  │  - Chat (群聊)                            │ │ │ │
│  │  │  │  - Document (文档)                        │ │ │ │
│  │  │  │  - User (用户)                            │ │ │ │
│  │  │  └───────────────────────────────────────────┘ │ │ │
│  │  └─────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 隔离字段

| 字段 | 类型 | 说明 | 索引 |
|------|------|------|------|
| tenant_id | text | 租户 ID | PK, INDEX |
| organization_id | text | 组织 ID | INDEX |
| workspace_id | text | 工作区 ID（可选） | INDEX |
| scope_type | text | 范围类型 | INDEX |
| scope_id | text | 范围 ID | INDEX |

### 2.3 隔离规则

```sql
-- 查询时必须过滤 tenant_id
SELECT * FROM memories
WHERE tenant_id = :tenant_id
  AND organization_id = :organization_id
  AND status = 'active';

-- 写入时必须带 tenant_id
INSERT INTO memories (tenant_id, organization_id, ...)
VALUES (:tenant_id, :organization_id, ...);

-- 更新时必须过滤 tenant_id
UPDATE memories
SET ...
WHERE tenant_id = :tenant_id
  AND memory_id = :memory_id;

-- 删除时必须过滤 tenant_id
DELETE FROM memories
WHERE tenant_id = :tenant_id
  AND memory_id = :memory_id;
```

### 2.4 隔离验证

```python
# tests/test_tenant_isolation.py

def test_tenant_data_isolation():
    """验证租户间数据隔离"""
    # 租户 A 创建数据
    create_memory(tenant_id="tenant_a", ...)

    # 租户 B 无法访问租户 A 的数据
    results = search_memory(tenant_id="tenant_b", ...)
    assert not any(r.tenant_id == "tenant_a" for r in results)

def test_organization_isolation():
    """验证组织间数据隔离"""
    # 同一租户下，组织 A 的数据对组织 B 不可见
    create_memory(tenant_id="tenant_a", organization_id="org_a", ...)
    results = search_memory(tenant_id="tenant_a", organization_id="org_b", ...)
    assert len(results) == 0
```

---

## 3. 角色权限管理

### 3.1 角色定义

| 角色 | 说明 | 权限 |
|------|------|------|
| **Super Admin** | 系统管理员 | 所有权限，包括租户管理 |
| **Tenant Admin** | 租户管理员 | 管理租户内所有组织和用户 |
| **Organization Admin** | 组织管理员 | 管理组织内所有工作区和用户 |
| **Reviewer** | 审核员 | 审核候选记忆（confirm/reject） |
| **Member** | 普通成员 | 搜索、创建候选、查看版本 |
| **Viewer** | 只读用户 | 只读搜索 |

### 3.2 权限矩阵

| 操作 | Super Admin | Tenant Admin | Org Admin | Reviewer | Member | Viewer |
|------|-------------|--------------|-----------|----------|--------|--------|
| memory.search | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| memory.create_candidate | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| memory.confirm | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| memory.reject | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| memory.explain_versions | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| memory.prefetch | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 管理用户 | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| 管理租户 | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 查看审计 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| 导出数据 | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |

### 3.3 权限存储

```sql
-- 用户表
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 角色表
CREATE TABLE roles (
    role_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    permissions JSON NOT NULL,
    created_at INTEGER NOT NULL
);

-- 用户角色关联表
CREATE TABLE user_roles (
    user_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    scope_type TEXT,  -- 可选：限定在特定 scope
    scope_id TEXT,
    granted_by TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    expires_at INTEGER,  -- 可选：过期时间
    PRIMARY KEY (user_id, role_id)
);
```

### 3.4 权限 API

```python
# memory_engine/copilot/permission_admin.py

class PermissionAdmin:
    """权限管理服务"""

    def create_role(self, tenant_id: str, name: str, permissions: list) -> Role:
        """创建角色"""
        pass

    def update_role(self, role_id: str, permissions: list) -> Role:
        """更新角色"""
        pass

    def delete_role(self, role_id: str) -> bool:
        """删除角色"""
        pass

    def assign_role(self, user_id: str, role_id: str, granted_by: str) -> bool:
        """分配角色"""
        pass

    def revoke_role(self, user_id: str, role_id: str) -> bool:
        """撤销角色"""
        pass

    def get_user_roles(self, user_id: str) -> list[Role]:
        """获取用户角色"""
        pass

    def check_permission(self, user_id: str, action: str, resource: dict) -> bool:
        """检查权限"""
        pass
```

---

## 4. 审批流程设计

### 4.1 候选记忆生命周期

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Candidate Lifecycle                          │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Created  │ -> │ Pending  │ -> │ Reviewed │ -> │ Final    ││
│  │          │    │ Review   │    │          │    │          ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
│       │               │               │               │       │
│       │               │               │               │       │
│       ▼               ▼               ▼               ▼       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │candidate │    │candidate │    │confirmed │    │active    ││
│  │          │    │          │    │rejected  │    │archived  ││
│  │          │    │          │    │blocked   │    │stale     ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 审批规则

| 规则 | 说明 |
|------|------|
| 审批人必须是 Reviewer 或 Admin | 权限检查 |
| 审批人不能是创建人 | 职责分离（可选） |
| 审批必须记录原因 | 审计要求 |
| 审批不可撤销 | 一旦 confirm/reject，状态不可回退 |

### 4.3 审批 API

```python
# memory_engine/copilot/approval.py

class ApprovalService:
    """审批服务"""

    def confirm_candidate(
        self,
        candidate_id: str,
        reviewer_id: str,
        reason: str
    ) -> Memory:
        """确认候选记忆"""
        pass

    def reject_candidate(
        self,
        candidate_id: str,
        reviewer_id: str,
        reason: str
    ) -> Candidate:
        """拒绝候选记忆"""
        pass

    def get_pending_candidates(
        self,
        tenant_id: str,
        organization_id: str
    ) -> list[Candidate]:
        """获取待审核候选"""
        pass

    def get_approval_history(
        self,
        candidate_id: str
    ) -> list[ApprovalRecord]:
        """获取审批历史"""
        pass
```

### 4.4 审批通知

```python
# 审批通知模板
CONFIRM_NOTIFICATION = """
✅ 候选记忆已确认

候选 ID: {candidate_id}
主题: {subject}
审核人: {reviewer_name}
审核时间: {reviewed_at}
原因: {reason}

记忆已生效，可被搜索召回。
"""

REJECT_NOTIFICATION = """
❌ 候选拒绝

候选 ID: {candidate_id}
主题: {subject}
审核人: {reviewer_name}
审核时间: {reviewed_at}
原因: {reason}

候选已归档，不会被搜索召回。
"""
```

---

## 5. 数据删除和遗忘

### 5.1 删除场景

| 场景 | 说明 | 处理方式 |
|------|------|----------|
| 用户主动删除 | 用户要求删除自己的记忆 | 软删除 + 审计 |
| 租户管理员删除 | 管理员删除租户数据 | 软删除 + 审计 |
| 合规删除 | 法律要求删除 | 硬删除 + 审计 |
| 数据保留过期 | 超过保留期 | 自动清理 |

### 5.2 删除流程

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Data Deletion Flow                           │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Request  │ -> │ Validate │ -> │ Anonymize│ -> │ Confirm  ││
│  │ Delete   │    │ Identity │    │ Data     │    │ Delete   ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
│       │               │               │               │       │
│       ▼               ▼               ▼               ▼       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Audit    │    │ Permission│    │ Backup   │    │ Notify   ││
│  │ Log      │    │ Check    │    │ Data     │    │ User     ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 删除 API

```python
# memory_engine/copilot/data_deletion.py

class DataDeletionService:
    """数据删除服务"""

    def request_deletion(
        self,
        user_id: str,
        tenant_id: str,
        reason: str
    ) -> DeletionRequest:
        """请求删除数据"""
        pass

    def anonymize_memory(self, memory_id: str) -> bool:
        """匿名化记忆数据"""
        pass

    def soft_delete(self, memory_id: str, deleted_by: str) -> bool:
        """软删除记忆"""
        pass

    def hard_delete(self, memory_id: str, deleted_by: str, reason: str) -> bool:
        """硬删除记忆（合规要求）"""
        pass

    def export_user_data(self, user_id: str) -> dict:
        """导出用户数据（GDPR 右）"""
        pass

    def get_deletion_history(
        self,
        tenant_id: str
    ) -> list[DeletionRecord]:
        """获取删除历史"""
        pass
```

### 5.4 匿名化规则

| 字段 | 匿名化方式 | 说明 |
|------|------------|------|
| subject | 哈希 | 保留唯一性 |
| current_value | 删除 | 完全移除 |
| summary | 删除 | 完全移除 |
| evidence.quote | 删除 | 完全移除 |
| actor_id | 哈希 | 保留统计 |
| created_by | 哈希 | 保留统计 |

### 5.5 保留策略

| 数据类型 | 保留周期 | 说明 |
|----------|----------|------|
| Active Memory | 永久 | 直到用户删除 |
| Candidate | 90 天 | 未处理自动归档 |
| Audit Events | 90 天 | 合规要求 |
| Deleted Data | 30 天 | 软删除保留期 |
| Backup Data | 365 天 | 灾备要求 |

---

## 6. 权限后台 UI

### 6.1 用户管理页面

```text
┌─────────────────────────────────────────────────────────────────┐
│                     User Management                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Search: [________________] [Search]                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  User ID    │ Name      │ Organization │ Roles    │ Actions │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  u_001      │ 张三      │ 组织 A       │ Admin    │ [Edit] │   │
│  │  u_002      │ 李四      │ 组织 A       │ Reviewer │ [Edit] │   │
│  │  u_003      │ 王五      │ 组织 B       │ Member   │ [Edit] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [Add User]  [Export]  [Import]                                │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 角色管理页面

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Role Management                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Role: [Reviewer ▼]                                            │
│                                                                 │
│  Permissions:                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ☑ memory.search                                        │   │
│  │  ☑ memory.create_candidate                              │   │
│  │  ☑ memory.confirm                                       │   │
│  │  ☑ memory.reject                                        │   │
│  │  ☑ memory.explain_versions                              │   │
│  │  ☑ memory.prefetch                                      │   │
│  │  ☐ 管理用户                                             │   │
│  │  ☐ 管理租户                                             │   │
│  │  ☐ 查看审计                                             │   │
│  │  ☐ 导出数据                                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [Save]  [Delete Role]                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 审批队列页面

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Approval Queue                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Filter: [All ▼] [Today ▼] [My Queue ▼]                       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Candidate ID │ Subject       │ Source  │ Created │ Actions │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  c_001        │ 项目进度      │ Message │ 2h ago  │ [✓][✗] │   │
│  │  c_002        │ 决策记录      │ Doc     │ 5h ago  │ [✓][✗] │   │
│  │  c_003        │ 会议纪要      │ Meeting │ 1d ago  │ [✓][✗] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Pending: 3  │  Confirmed Today: 12  │  Rejected Today: 5      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 审计追踪

### 7.1 审计事件

| 事件类型 | 说明 | 必须记录 |
|----------|------|----------|
| user.created | 创建用户 | ✓ |
| user.updated | 更新用户 | ✓ |
| user.deleted | 删除用户 | ✓ |
| role.created | 创建角色 | ✓ |
| role.updated | 更新角色 | ✓ |
| role.assigned | 分配角色 | ✓ |
| role.revoked | 撤销角色 | ✓ |
| candidate.confirmed | 确认候选 | ✓ |
| candidate.rejected | 拒绝候选 | ✓ |
| data.anonymized | 匿名化数据 | ✓ |
| data.deleted | 删除数据 | ✓ |

### 7.2 审计日志格式

```json
{
  "audit_id": "audit_20260428_001",
  "event_type": "candidate.confirmed",
  "actor_id": "u_001",
  "actor_roles": ["reviewer"],
  "tenant_id": "tenant_a",
  "organization_id": "org_a",
  "target_type": "candidate",
  "target_id": "c_001",
  "action": "confirm",
  "reason": "内容准确，已验证",
  "metadata": {
    "candidate_subject": "项目进度",
    "source_type": "message"
  },
  "created_at": 1682700000
}
```

---

## 8. API 接口

### 8.1 用户管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/users | 获取用户列表 |
| POST | /api/users | 创建用户 |
| GET | /api/users/:id | 获取用户详情 |
| PUT | /api/users/:id | 更新用户 |
| DELETE | /api/users/:id | 删除用户 |

### 8.2 角色管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/roles | 获取角色列表 |
| POST | /api/roles | 创建角色 |
| GET | /api/roles/:id | 获取角色详情 |
| PUT | /api/roles/:id | 更新角色 |
| DELETE | /api/roles/:id | 删除角色 |
| POST | /api/roles/:id/assign | 分配角色 |
| POST | /api/roles/:id/revoke | 撤销角色 |

### 8.3 审批管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/approvals/pending | 获取待审批列表 |
| POST | /api/approvals/:id/confirm | 确认候选 |
| POST | /api/approvals/:id/reject | 拒绝候选 |
| GET | /api/approvals/:id/history | 获取审批历史 |

### 8.4 数据删除

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/data/delete | 请求删除数据 |
| GET | /api/data/export | 导出用户数据 |
| GET | /api/data/deletion-history | 获取删除历史 |

---

## 9. 实现优先级

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | 多租户数据隔离 | 核心安全要求 |
| P0 | 基础角色权限 | Member/Reviewer/Admin |
| P0 | 候选审批流程 | 核心业务流程 |
| P1 | 用户管理 UI | 管理界面 |
| P1 | 角色管理 UI | 管理界面 |
| P1 | 数据删除 API | 合规要求 |
| P2 | 审计 UI | 运维需求 |
| P2 | 高级权限（ACL） | 扩展需求 |

---

## 10. 参考文档

- `docs/productization/contracts/permission-contract.md` - 权限契约
- `docs/productization/contracts/audit-observability-contract.md` - 审计契约
- `docs/productization/audit-ui-design.md` - 审计 UI 设计
- `docs/productization/productized-live-architecture.md` - 架构图
