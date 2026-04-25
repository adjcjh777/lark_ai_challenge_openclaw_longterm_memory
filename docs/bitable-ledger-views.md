# Bitable 记忆台账与评委视图建议

日期：2026-04-27  
适用阶段：D4 Bitable 记忆台账和评委可视化

## 表结构

### Memory Ledger

用途：展示每条记忆的当前有效状态，一行对应一个 `memory_id`。

字段顺序：

1. `memory_id`
2. `scope`
3. `type`
4. `subject`
5. `current_value`
6. `status`
7. `version`
8. `source`
9. `updated_at`
10. `reason`
11. `confidence`
12. `importance`
13. `recall_count`

### Memory Versions

用途：展示版本链，一行对应一个版本。评委能看到旧版本如何变成 `superseded`，新版本如何成为 `active`。

字段顺序：

1. `version_id`
2. `memory_id`
3. `scope`
4. `type`
5. `subject`
6. `current_value`
7. `status`
8. `version`
9. `source`
10. `updated_at`
11. `created_by`
12. `supersedes_version_id`

### Benchmark Results

用途：展示每次 Benchmark 的汇总指标，一行对应一次运行。

字段顺序：

1. `run_id`
2. `benchmark_name`
3. `source`
4. `case_count`
5. `case_pass_rate`
6. `conflict_accuracy`
7. `stale_leakage_rate`
8. `evidence_coverage`
9. `avg_latency_ms`
10. `updated_at`
11. `summary_json`

## 视图建议

### Memory Ledger

- `Active Ledger`：筛选 `status = active`，按 `updated_at` 倒序。用于 Demo 主视图。
- `By Status`：按 `status` 分组，优先展示 active，再展示待人工处理或后续扩展状态。
- `By Type`：按 `type` 分组，评委能看到 decision、workflow、preference、deadline、risk 等覆盖范围。
- `Recently Updated`：按 `updated_at` 倒序，适合展示“刚刚在 Bot 里更新后 Bitable 同步”的效果。

### Memory Versions

- `Version Chain`：按 `memory_id` 分组，再按 `version` 升序。用于解释覆盖更新。
- `By Version Status`：按 `status` 分组，展示 `active` 与 `superseded`。
- `Recent Version Changes`：按 `updated_at` 倒序，用于演示最新变更证据。

### Benchmark Results

- `Latest Runs`：按 `updated_at` 倒序，展示最近一次评测。
- `Pass Rate Review`：显示 `case_pass_rate`、`conflict_accuracy`、`stale_leakage_rate`、`evidence_coverage`。
- `Latency Review`：按 `avg_latency_ms` 排序，观察性能退化。

## 真实 Base 当前视图状态

2026-04-25 已在真实 Base 创建以下视图：

- `Memory Ledger / Active Ledger`：已设置 `status = active` 筛选。
- `Memory Ledger / By Type`：已按 `type` 分组。
- `Memory Ledger / Recently Updated`：已按 `updated_at` 倒序。
- `Memory Versions / Version Chain`：已按 `memory_id` 分组，并按 `version` 升序。
- `Memory Versions / By Version Status`：视图已创建；分组接口返回平台限制，需队友在 UI 中手动按 `status` 分组。
- `Benchmark Results / Latest Runs`：视图已创建并设置核心字段顺序；排序接口返回平台限制，需队友在 UI 中手动按 `updated_at` 倒序。

接口限制记录：部分视图配置调用返回 `OpenAPIUpdateViewSort limited`、`OpenAPIUpdateViewGroup limited` 或 `OpenAPISetVisibleFields limited`，数据写入和视图创建不受影响。

## 评委讲解词

1. 先看 `Memory Ledger`：这里不是普通聊天记录，而是系统抽象出来的当前有效记忆。
2. 指向 `status` 和 `version`：同一主题发生更新后，台账只保留当前有效结论，避免旧规则继续被召回。
3. 切到 `Memory Versions`：这里能看到旧版本已被标记为 `superseded`，新版本是 `active`，这就是企业协作里“决策变更可追溯”的核心价值。
4. 切到 `Benchmark Results`：这里用数据证明系统没有只做 Demo，而是能通过冲突更新、旧值泄露率、证据覆盖率和延迟指标做自证。

## 队友造数要求

请造 20 条不同类型的记忆样例，覆盖：

- `decision`：例如技术选型、上线策略、接口约定。
- `workflow`：例如部署流程、审批步骤、事故响应。
- `preference`：例如团队偏好、默认文案、优先工具。
- `deadline`：例如交付日期、评审时间、报名截止。
- `risk`：例如权限风险、数据泄露风险、依赖不稳定。

建议每类 4 条，并至少包含 3 条“旧规则 -> 新规则”的覆盖更新样例。
