# PRD：Feishu Memory Copilot 完整产品路线

Metadata:
- Workflow: `$ralplan --consensus --direct .omx/specs/deep-interview-complete-product-roadmap.md`（仓库可追踪副本）
- Date: 2026-04-27
- Workspace: `/Users/junhaocheng/feishu_ai_challenge`
- Source spec: `.omx/specs/deep-interview-complete-product-roadmap.md`
- Consensus: Planner revision -> Architect `APPROVE` -> Critic `APPROVE`
- OpenClaw lock: `2026.4.24`
- Planning boundary: 原始 `$ralplan` 只产出计划、不实现代码；本仓库副本作为后续 `$ralph` / `$team` 的输入，执行时仍必须按 Phase gate 推进。

---

## 1. Requirements Summary

本路线把 Feishu Memory Copilot 从当前“Proof MVP / dry-run / benchmark / whitepaper 证明层”推进为 PRD 定义的完整产品闭环。完整产品不是先做大型企业后台，而是先形成一个可用、可复现、可治理、可审计的 OpenClaw-native Copilot：

1. OpenClaw Agent 真实调用 `memory.*` tools。
2. 飞书内有真实交互或审核面，用于搜索结果、候选确认、版本解释、提醒审核中的核心动作。
3. Copilot Core 作为长期记忆治理事实源，负责 candidate、confirm/reject、active、superseded、recall、explain_versions、heartbeat candidate。
4. 真实多租户权限必须落地：`tenant_id`、`organization_id`、`visibility_policy` 下不能越权召回。
5. 第一版不做完整企业后台、分布式架构、正式生产安全认证；历史迁移和主动推送轻量化。
6. README、Demo runbook、Benchmark Report、白皮书、录屏和截图讲同一个产品故事，不能把 schema demo、dry-run、seed/local bridge 说成真实飞书 live ingestion。

RALPLAN intake 时的仓库事实（历史快照，已被 2026-05-07 Phase 1/Phase 2 前置实现部分推进）：
- RALPLAN 启动前 README 顶部仍把下一步描述为 2026-05-06 提交材料、录屏、QA 和 scope freeze；当前仓库副本已将 README 顶部改为完整产品路线入口（`README.md:7-11`）。
- SQLite 基础表仍以 `scope_type/scope_id` 为主，`raw_events` 和 `memories` 尚无 `tenant_id`、`organization_id`、`visibility_policy`（`memory_engine/db.py:14-47`）。
- 2026-05-07 最新状态：`current_context.permission` 已进入 OpenClaw schema；`memory.search/create_candidate/confirm/reject/explain_versions/prefetch` 已在 `CopilotService` 统一权限门控；missing/malformed permission 已 fail closed；真实 Feishu document ingestion 已在 fetch 前 fail closed。对应提交：`b6b17b4`。
- 仍未完成：storage migration、audit table、healthcheck、OpenClaw runtime live bridge、Feishu review surface 和 limited Feishu ingestion。

---

## 2. RALPLAN-DR Summary

### 2.1 Principles

1. **Submission Freeze First**：2026-05-06 / 2026-05-07 初赛提交闭环不能被后续产品化尝试破坏。
2. **Contracts Before Live Data**：真实飞书 ingestion 必须晚于 storage、permission、evidence、review、audit 契约。
3. **Service Is Source of Truth**：`memory_engine/copilot/` 的 service / governance / permission 是事实源；Feishu UI、Bitable、card、OpenClaw payload 只能消费服务输出。
4. **Candidate Before Active**：真实飞书数据先进入 candidate，不能自动 active。
5. **Narrow Adapters, Stable Core**：OpenClaw 是主入口，Cognee 是窄 adapter 背后的记忆引擎，旧 CLI/Bot/Feishu handler 是 fallback/reference。

### 2.2 Decision Drivers

1. **初赛交付确定性**：2026-05-06/05-07 仍要保护可提交材料、录屏、Benchmark Report、白皮书和 README。
2. **企业记忆可信度**：完整产品必须回答“谁能看、从哪里来、为什么是当前版本、是否经过确认、能否追溯”。
3. **OpenClaw-native Product Proof**：必须证明 OpenClaw 通过稳定 schema 调用 Copilot service，而不是停留在 CLI-first/Bot-first demo。

### 2.3 Options And Decision Matrix

| Option | 路线 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A | Submission-only MVP | 风险低，最稳提交 | 产品路线不完整，OpenClaw-native 和治理价值不足 | 不采用；仅作为 Phase 0 freeze 策略 |
| B | Immediate Feishu Live Ingestion | 看起来 live，演示直观 | 权限/审计/review 未冻结，容易越权或误 active，初赛风险高 | 不采用 |
| C | Proof MVP -> Contracted Live Slice -> Controlled Productization | 同时保护提交和产品化；先契约后 live；可分阶段验证 | 前期多做 RFC/契约，真实 ingestion 推后 | **采用** |

---

## 3. ADR：Productization Route 001

### Decision

采用 **Proof MVP -> Contracted Live Slice -> Controlled Productization**。

阶段顺序固定为：

```text
Phase 0   Submission Freeze Preservation
Phase 0.5 Productization Baseline RFC
Phase 1   Storage + Permission Contract Freeze
Phase 2   OpenClaw Live Bridge
Phase 3   Feishu UI / Review Surface
Phase 4   Limited Feishu Ingestion
Phase 5   Heartbeat Controlled Reminder
Phase 6   Deployability + Healthcheck
Phase 7   Product QA
```

### Drivers

- 不让产品化探索破坏 2026-05-06 / 2026-05-07 初赛提交。
- 不在权限、证据、审计、review gate 未冻结时处理真实飞书数据。
- 保持 OpenClaw-native 主线，同时不让 Feishu UI/Bot/CLI 抢占 source of truth。
- 为 `$ralph` 单阶段闭环和 `$team` 后续并行提供清晰 gate。

### Alternatives Considered

- **Submission-only MVP**：Rejected；只能证明初赛材料，不能形成完整产品路线。
- **Immediate Feishu Live Ingestion**：Rejected；权限、review、audit 未冻结前风险过高。
- **Cognee reselection**：Rejected；违反当前项目约束，Cognee 继续作为 memory substrate。
- **Legacy Bot-first continuation**：Rejected；旧 Bot 只做 fallback/test surface，不做新主架构。

### Consequences

- Feishu live ingestion 被推迟到 Phase 4。
- Phase 1 前需要较完整的契约文件和 negative cases。
- `$team` 并行必须等 Contract Freeze Gate 通过。
- 所有文档必须区分：schema demo / dry-run / replay / OpenClaw live / Feishu live ingestion / productized live。

### Follow-ups

- 把 Phase 0.5 / Phase 1 的 RFC 和 contract artifact 作为后续执行前置输入。
- 在 OpenClaw payload 中冻结 permission context 进入方式。
- 给所有 tool/action 增加 fail-closed 权限矩阵。
- Product QA 前做 no-overclaim claim audit。

---

## 4. Product Vocabulary：不能混用的能力标签

| 标签 | 定义 | 是否可以称为 Feishu live ingestion |
|---|---|---|
| schema demo | 只展示 JSON schema 或样例 payload | 否 |
| dry-run | 不写真实外部系统，只输出本地日志/报告/card payload | 否 |
| replay | 用 seed/fixture 复现固定流程 | 否 |
| OpenClaw live bridge | OpenClaw 真实调用本地/seed Copilot service | 否 |
| limited Feishu ingestion | 指定飞书来源进入 candidate pipeline，不自动 active | 可以称为有限 ingestion，但必须标注 candidate-only |
| productized live | 部署、权限、审计、healthcheck、QA 全部过 gate 后的受控 live | 可以 |

---

## 5. Product Phases And Acceptance Criteria

### Phase 0：Submission Freeze Preservation

**目标**：保护 2026-05-06 / 2026-05-07 初赛提交闭环。

**范围**：
- 冻结三大交付物：白皮书、可运行 Demo、自证 Benchmark Report。
- 保持 README 顶部入口、Demo runbook、截图/录屏说明可提交。
- 只修提交 blocker，不新增未验证功能。
- 审查所有 live wording。

**Exit gate**：
- [ ] 2026-05-06 / 2026-05-07 初赛提交 artifacts 路径明确。
- [ ] Demo runbook 可复现。
- [ ] Benchmark Report 有命令、数据集、指标和结果。
- [ ] README/runbook/report/whitepaper 没有互相矛盾。
- [ ] 所有 live 用语有标签：schema demo / dry-run / replay / OpenClaw live / Feishu live ingestion。

### Phase 0.5：Productization Baseline RFC

**目标**：写产品化基线 RFC，不写生产代码，不宣称 live 完成。

**Contract artifacts**（Phase 1 已拆成可直接给 executor 使用的独立契约文件；本 PRD 第 6-7 节保留摘要）：
- [storage-contract.md](contracts/storage-contract.md)：冻结 tenant / organization / visibility-aware 存储字段、索引、迁移兼容和审计表边界。
- [permission-contract.md](contracts/permission-contract.md)：冻结 permission context、decision、redaction、fail-closed 和 action 权限矩阵。
- [openclaw-payload-contract.md](contracts/openclaw-payload-contract.md)：冻结首版 `current_context.permission` 兼容 payload，不立刻做 breaking schema。
- [audit-observability-contract.md](contracts/audit-observability-contract.md)：冻结 permission、review、ingestion、heartbeat 的 audit event 和指标。
- [migration-rfc.md](contracts/migration-rfc.md)：冻结 scope-first 到 tenant-aware 的兼容迁移策略。
- [negative-permission-test-plan.md](contracts/negative-permission-test-plan.md)：冻结后续 `tests/test_copilot_permissions.py` 可直接实现的越权反例。

**Exit gate**：
- [ ] RFC 明确只是路线/契约/验收基线。
- [ ] 不出现“Feishu live ingestion 已完成”的表述。
- [ ] Phase 0-7 的 gate、证据和风险边界已列出。

### Phase 1：Storage + Permission Contract Freeze

**目标**：在 `$team` 并行、OpenClaw live bridge、Feishu UI、真实 ingestion 之前冻结数据、权限、payload、审计契约。

**Phase 1 contract artifacts**：
- [Storage Contract](contracts/storage-contract.md)
- [Permission Contract](contracts/permission-contract.md)
- [OpenClaw Payload Contract](contracts/openclaw-payload-contract.md)
- [Audit & Observability Contract](contracts/audit-observability-contract.md)
- [Migration RFC](contracts/migration-rfc.md)
- [Negative Permission Test Plan](contracts/negative-permission-test-plan.md)

这些文件是后续代码实现的优先事实源；本 PRD 的第 6-7 节只保留摘要，若摘要与独立契约冲突，以 `docs/productization/contracts/` 下的文件为准。

**Contract Freeze Gate**：
- [x] Data model / migration RFC 完成。
- [x] `tenant_id` / `organization_id` / `visibility_policy` 冻结。
- [x] Permission context schema 冻结。
- [x] Service permission decision contract 冻结。
- [x] OpenClaw payload decision 冻结。
- [x] Negative permission cases 进入 test plan。
- [x] Audit fields 冻结。
- [x] Architect / Critic 对 contract freeze 无 blocker。
- [x] README/docs 没有把 Phase 2 写成 Feishu live ingestion。

2026-05-07 补充：Phase 2 权限前置实现已完成，见 [2026-05-07 handoff](../plans/2026-05-07-handoff.md)。这不等于 Phase 2 OpenClaw live bridge 已完成；下一步仍要做 OpenClaw/本地桥真实调用 seed/local Copilot service。

### Phase 2：OpenClaw Live Bridge

**目标**：OpenClaw 真实调用本地/seed Copilot service，返回 permission-aware output。

**不做**：真实 Feishu ingestion、自动 active、绕过 permission、把 OpenClaw adapter 写成 source of truth。

**Exit gate**：
- [x] `python3 scripts/check_openclaw_version.py` 通过。
- [ ] OpenClaw tool 调用 seed/local service 成功。
- [ ] response 包含 result、evidence、permission decision summary、trace/request id。
- [x] missing/malformed permission context fail closed。
- [x] Demo/README 文案明确这不是 Feishu live ingestion。

当前 Phase 2 状态：权限前置实现通过；OpenClaw live bridge 仍未完成。

### Phase 3：Feishu UI / Review Surface

**目标**：Feishu card/Bitable/review UI 展示 permission-aware candidate/memory，并通过 service 执行 confirm/reject。

**Exit gate**：
- [ ] Review surface 只消费 Copilot service 输出。
- [ ] approve/reject 调用 service，不直接改状态。
- [ ] 无 reviewer/owner 权限时无法 approve/reject。
- [ ] UI 文案区分 candidate / active / rejected / superseded。
- [ ] audit 记录 review action。

### Phase 4：Limited Feishu Ingestion

**目标**：指定飞书来源进入 candidate pipeline，不自动 active。

**前置**：Phase 1-3 全部通过。

**Exit gate**：
- [ ] 至少一条真实 Feishu source 进入 candidate。
- [ ] candidate 包含 evidence quote/source metadata。
- [ ] candidate 未自动 active。
- [ ] 无权限 actor 无法查看或 approve。
- [ ] audit 记录 ingestion 和 review decision。

### Phase 5：Heartbeat Controlled Reminder

**目标**：生成受控 reminder candidate 或 dry-run/card，不做复杂个性化推送。

**Exit gate**：
- [ ] reminder 有 reason、evidence、target actor、cooldown。
- [ ] permission deny 时不发送或脱敏。
- [ ] reminder 不自动 active。
- [ ] observability 记录 reminder decision。

### Phase 6：Deployability + Healthcheck

**目标**：产品可初始化、可健康检查、可诊断。

**Exit gate**：
- [ ] healthcheck 覆盖 OpenClaw version、service import、storage schema、Cognee adapter、embedding provider、permission contract。
- [ ] smoke test 覆盖 search、permission deny、candidate review。
- [ ] Cognee/embedding 不可用时降级或清楚报错。
- [ ] schema version visible in healthcheck。

### Phase 7：Product QA

**目标**：证明每个产品 claim 都有证据。

**Exit gate**：
- [ ] Claim audit 覆盖 README、白皮书、Benchmark Report、demo script、Feishu UI 文案、OpenClaw examples。
- [ ] Negative permission cases 通过。
- [ ] Candidate-only ingestion 通过。
- [ ] Review surface 不越权。
- [ ] Product QA report 写清 passed / failed / not tested / known risks / fallback。

---

## 6. Contracts

### 6.1 Storage Contract

`memory` 主体最低字段：
- `memory_id`
- `tenant_id`
- `organization_id`
- `workspace_id` 或等价 scope 字段
- `type`
- `subject`
- `current_value`
- `summary`
- `status`
- `version`
- `visibility_policy`
- `owner_id`（MVP 默认等同 `created_by`；后续 ACL 可独立扩展）
- `created_at`
- `updated_at`
- `created_by`
- `updated_by`

`candidate` 最低字段：
- `candidate_id`
- `tenant_id`
- `organization_id`
- `source_type`
- `source_id`
- `source_url`
- `source_timestamp`
- `suggested_subject`
- `suggested_value`
- `confidence`
- `status`
- `review_required`
- `review_reason`

`evidence` 最低字段：
- `evidence_id`
- `memory_id` 或 `candidate_id`
- `source_type`
- `source_event_id`
- `source_url`
- `quote`
- `actor_id`
- `actor_display`
- `event_time`
- `ingested_at`

`audit` 最低字段：
- `audit_id`
- `request_id`
- `trace_id`
- `actor_id`
- `actor_roles`
- `tenant_id`
- `organization_id`
- `action`
- `target_type`
- `target_id`
- `permission_decision`
- `reason_code`
- `visible_fields`
- `redacted_fields`
- `source_context`
- `created_at`

### 6.2 Required Scope Fields

必须真实参与权限判断：
- `tenant_id`
- `organization_id`
- `visibility_policy`

可补充：
- `workspace_id`
- `conversation_id`
- `document_id`
- `review_space_id`

### 6.3 Permission Context Schema

Phase 1 必须冻结 service 接收的 permission context。兼容建议：短期放入 `current_context.permission`，后续可升为顶层 `permission_context`；无论采用哪种，字段语义一致。

```json
{
  "request_id": "req_...",
  "actor": {
    "user_id": "u_...",
    "open_id": "ou_...",
    "tenant_id": "tenant_...",
    "organization_id": "org_...",
    "roles": ["member"]
  },
  "source_context": {
    "entrypoint": "openclaw",
    "chat_id": "optional",
    "document_id": "optional",
    "workspace_id": "optional"
  },
  "requested_action": "memory.search",
  "requested_visibility": "team",
  "timestamp": "2026-..."
}
```

规则：missing / malformed permission context 必须 fail closed。

### 6.4 Service Permission Decision Contract

允许：

```json
{
  "allowed": true,
  "decision": "allow",
  "reason_code": "same_org_team_visibility",
  "visible_fields": ["subject", "current_value", "summary", "evidence.quote"],
  "redacted_fields": [],
  "audit_required": true
}
```

拒绝：

```json
{
  "allowed": false,
  "decision": "deny",
  "reason_code": "tenant_mismatch",
  "visible_fields": [],
  "redacted_fields": ["current_value", "evidence"],
  "audit_required": true
}
```

### 6.5 OpenClaw Payload Contract Decision

Phase 1 必须选择并冻结以下其中一种：

1. **兼容过渡方案（推荐首版）**：继续使用 `current_context`，但冻结 `current_context.permission` 子结构；旧 examples 可以继续跑，真实产品路径要求 permission 子结构。
2. **顶层方案**：新增顶层 `permission_context`，每个 tool 都强制携带；更干净但 schema break 更大。

无论选择哪种，必须包含：`request_id`、actor user/open id、`tenant_id`、`organization_id`、roles、`source_context`、`requested_action`、`requested_visibility`、timestamp。

### 6.6 Service Action Permission Matrix

| Action | Required permission decision | Fail-closed behavior |
|---|---|---|
| `memory.search` | actor 可读取 requested visibility fields | 返回 `permission_denied`，不返回 memory/evidence |
| `memory.create_candidate` | actor 可在 tenant/org/source context 下提出候选 | 拒绝创建或返回 blocked response |
| `memory.confirm` | actor 有 reviewer/owner role | candidate 保持 candidate，不变 active |
| `memory.reject` | actor 有 reviewer/owner role | candidate 状态不变，写 deny audit |
| `memory.explain_versions` | actor 可查看 version/evidence fields | 脱敏或 deny old values/evidence |
| `memory.prefetch` | actor 可读取 context pack fields | 返回空/denied pack |
| `heartbeat` | actor/context 可接收 reminder candidate | withheld 或 redacted |

### 6.7 Audit / Observability Contract

- 每次 permission allow/deny 都要有 audit event 或结构化审计日志。
- 每次 confirm/reject 都要记录 actor、role、source_context、reason。
- 每次 ingestion gate 都要记录 source、candidate id、decision。
- denial log 不输出 raw private memory。
- redacted fields 可以记录字段名，不能记录明文秘密。

---

## 7. Migration Compatibility Requirements

- existing demo data gets default `tenant_id` / `organization_id` / `visibility_policy`。
- migration idempotent：重复执行不会重复加字段或破坏数据。
- old benchmarks remain runnable：Day1 fallback、existing `copilot_*` benchmarks 不因迁移直接失效。
- schema version visible in healthcheck。
- migration failure 提供 rollback/dry-run 说明。
- `.env`、logs、db、token、真实飞书数据不进入提交。

---

## 8. Pre-mortem

| Failure | Impact | Mitigation | Detection | Rollback |
|---|---|---|---|---|
| seed/local bridge 被误写成 Feishu live ingestion | 评审误解成熟度 | vocabulary RFC + Phase 7 claim audit | 文档称“已接入真实飞书”但无 Phase 4 evidence | 改文案，降级为 OpenClaw local bridge |
| 权限契约未冻结就 ingestion | 越权召回/证据暴露 | Contract Freeze Gate + fail-closed | candidate/memory 缺 tenant/org 或 audit | 关闭 ingestion，隔离 candidate |
| Feishu UI/Bitable 成为 source of truth | 状态机失控 | UI 只能调用 service | UI handler 直接写 active | 禁用 direct write，以 service 重建展示 |
| candidate 自动 active | 错误记忆污染 | candidate-only + governance tests | active 增加但无 review audit | 降级为 candidate/stale |
| Cognee/embedding 不可用 | Demo 崩溃 | 窄 adapter + fallback + healthcheck | search skipped/schema mismatch | repository fallback，重建本地数据 |
| Team 过早并行 | contract drift | Contract Freeze Gate | schema/payload 字段冲突 | 暂停 Team，回 Phase 1 |

---

## 9. Follow-up Staffing Guidance

### 9.1 `$ralph` 路径

适合在计划通过后逐阶段推进。每次只执行一个 phase，直到该 phase exit gate 通过，不自动跨越需要 Architect/Critic review 的 gate。

建议命令：

```text
$ralph .omx/plans/prd-complete-product-roadmap.md .omx/plans/test-spec-complete-product-roadmap.md
```

Ralph stop condition：当前 phase gate 通过、验证证据已收集、未解风险写入 handoff / Not-tested。

### 9.2 `$team` 路径

只能在 Phase 1 Contract Freeze Gate 通过后使用。建议 lane：

| Lane | Agent type | Owner files | Reasoning |
|---|---|---|---|
| Copilot Core | executor | `memory_engine/copilot/schemas.py`, `service.py`, `governance.py` | medium/high |
| Permission/Audit | security-reviewer + executor | `memory_engine/copilot/permissions.py`, audit storage/service tests | high |
| OpenClaw Adapter | executor | `agent_adapters/openclaw/memory_tools.schema.json`, examples | medium |
| Feishu Review Surface | executor/designer | card/Bitable/review surface files after Phase 3 | medium |
| Tests | test-engineer | `tests/test_copilot_*.py`, benchmark fixtures | medium/high |
| Verification | verifier | QA reports / no-overclaim audit | high |

Launch hint：

```text
$team .omx/plans/prd-complete-product-roadmap.md .omx/plans/test-spec-complete-product-roadmap.md
```

Team verification path：contract tests -> negative permission cases -> OpenClaw seed/local bridge -> Feishu review surface -> limited ingestion。

---

## 10. Applied Consensus Improvements

- 合并 Architect 建议：加入 Phase 1 artifact checklist、OpenClaw payload freeze decision、service action permission matrix、migration compatibility、audit exit criteria。
- 合并 Critic 建议：加入 decision matrix、phase-by-phase exit gates、no-overclaim vocabulary、Contract Freeze Gate before Team、test spec handoff要求。
- 保留硬约束：不实现代码、不升级 OpenClaw、不重选 Cognee、不把 dry-run/seed-local 写成 live。
