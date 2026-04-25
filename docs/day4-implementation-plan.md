# Day 4 实现计划：Bitable 记忆台账和评委可视化

日期：2026-04-27  
阶段：Day 4  
目标：在 Day 1 本地 Memory Engine 和 Day 2/Day 3 飞书 Bot 闭环基础上，补齐面向评委的 Bitable 记忆台账，让系统既能本地稳定运行，也能在有权限时把 active/superseded 记忆、版本链和 Benchmark 汇总同步到飞书多维表格。

## 1. Day 3 当前基线

仓库当前已完成：

- 本地 CLI：`init-db`、`remember`、`recall`、`versions`、`benchmark run`。
- SQLite schema：`raw_events`、`memories`、`memory_versions`、`memory_evidence`。
- 飞书 Bot 最小闭环：`feishu replay`、`feishu listen`。
- Bot 命令：`/remember`、`/recall`、`/versions`、`/help`、`/health`。
- 真实 Bot 稳定化：非文本、空消息、机器人自发消息、重复消息、未知命令都有明确处理。
- Day 1 benchmark 当前可通过，能证明冲突更新、旧值不泄露和证据覆盖。

已验证基线：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

当前缺口：

- 评委无法直接看到结构化台账，只能看 CLI/Bot 输出。
- `active` / `superseded` 版本链还没有同步到 Bitable。
- Benchmark 结果还没有沉淀到一个可视化看板。
- 真实 Bitable 权限可能不稳定，所以必须先保证 dry-run。

## 2. Day 4 不变原则

Day 4 只做 Bitable 记忆台账和最小同步，不把外部写入放进核心记忆路径。

### 2.1 P0 必做

1. 设计三张表：
   - `Memory Ledger`
   - `Memory Versions`
   - `Benchmark Results`
2. 实现本地 SQLite 到 Bitable 的最小同步脚本。
3. 同步字段至少包含：
   - `memory_id`
   - `scope`
   - `type`
   - `subject`
   - `current_value`
   - `status`
   - `version`
   - `source`
   - `updated_at`
4. 默认 dry-run，不依赖 Bitable 权限。
5. 更新 README 或 handoff，记录 Bitable 配置步骤。

### 2.2 P1 可做

1. 增加 Bitable 视图建议文档，覆盖按 `status`、`type`、`updated_at` 分组或排序。
2. 支持将 Benchmark 汇总结果写入 `Benchmark Results`。
3. 增加同步失败重试和错误摘要。
4. 输出队友晚上可以直接执行的字段检查、讲解词和造数任务。

### 2.3 Day 4 不做

- 不做生产级双向同步。
- 不做按 `memory_id` 查找后更新已有 Bitable record。
- 不做自动创建复杂视图、仪表盘和权限角色。
- 不做 Bitable 到 SQLite 的反向导入。
- 不把 Bitable 写入接到 `/remember` 或 `/recall` 同步路径。
- 不新增依赖。

原因：Day 4 的目标是评委可视化和可演示，不是做完整数据集成平台。核心能力仍必须在无 Bitable 权限时正常运行。

## 3. Bitable 表设计

### 3.1 `Memory Ledger`

用途：当前有效记忆台账，一行对应一个 `memory_id` 的当前状态。

字段：

| 字段 | 类型建议 | 来源 | 说明 |
|---|---|---|---|
| `memory_id` | text | `memories.id` | 记忆主键 |
| `scope` | text | `scope_type:scope_id` | 项目、群或用户范围 |
| `type` | text | `memories.type` | decision/workflow/preference/deadline/risk |
| `subject` | text | `memories.subject` | 主题 |
| `current_value` | text | `memories.current_value` | 当前有效结论 |
| `status` | text | `memories.status` | 当前状态 |
| `version` | number | active version | 当前版本号 |
| `source` | text | evidence/raw event | 来源类型和来源 id |
| `updated_at` | datetime | `memories.updated_at` | 最近更新时间 |
| `reason` | text | `memories.reason` | 规则抽取原因或说明 |
| `confidence` | number | `memories.confidence` | 置信度 |
| `importance` | number | `memories.importance` | 重要性 |
| `recall_count` | number | `memories.recall_count` | 召回次数 |

### 3.2 `Memory Versions`

用途：版本链，一行对应一个 `memory_versions.id`。

字段：

| 字段 | 类型建议 | 来源 | 说明 |
|---|---|---|---|
| `version_id` | text | `memory_versions.id` | 版本主键 |
| `memory_id` | text | `memory_versions.memory_id` | 所属记忆 |
| `scope` | text | joined memory scope | 范围 |
| `type` | text | joined memory type | 类型 |
| `subject` | text | joined memory subject | 主题 |
| `current_value` | text | `memory_versions.value` | 该版本的结论 |
| `status` | text | `memory_versions.status` | active/superseded |
| `version` | number | `memory_versions.version_no` | 版本号 |
| `source` | text | evidence/raw event | 来源 |
| `updated_at` | datetime | `memory_versions.created_at` | 版本创建时间 |
| `created_by` | text | `memory_versions.created_by` | 创建人 |
| `supersedes_version_id` | text | `memory_versions.supersedes_version_id` | 覆盖了哪个旧版本 |

### 3.3 `Benchmark Results`

用途：一次 Benchmark 运行的汇总指标，一行对应一次运行。

字段：

| 字段 | 类型建议 | 来源 | 说明 |
|---|---|---|---|
| `run_id` | text | sync runtime | 评测运行 id |
| `benchmark_name` | text | CLI 参数或文件名 | 评测名称 |
| `source` | text | benchmark 文件路径 | 数据来源 |
| `case_count` | number | benchmark summary | case 数量 |
| `case_pass_rate` | number | benchmark summary | 通过率 |
| `conflict_accuracy` | number | benchmark summary | 冲突更新准确率 |
| `stale_leakage_rate` | number | benchmark summary | 旧值泄露率 |
| `evidence_coverage` | number | benchmark summary | 证据覆盖率 |
| `avg_latency_ms` | number | benchmark summary | 平均召回延迟 |
| `updated_at` | datetime | sync runtime | 写入时间 |
| `summary_json` | text | benchmark summary | 原始汇总 JSON |

## 4. 推荐实现路线

### 4.1 新增模块

建议新增：

```text
memory_engine/bitable_sync.py
```

职责：

| 能力 | 说明 |
|---|---|
| `collect_sync_payload` | 从 SQLite 和可选 Benchmark 输入构造三张表 payload |
| `ledger_rows` | 导出当前记忆台账 |
| `version_rows` | 导出版本链 |
| `benchmark_rows` | 运行 benchmark 或读取 benchmark JSON，生成汇总行 |
| `sync_payload` | dry-run 或调用 lark-cli 批量写入 |
| `setup_commands` | 输出建表命令预览 |
| `table_schema_spec` | 输出字段结构给 README、handoff 和队友使用 |

### 4.2 CLI 新增

新增 `bitable` 子命令：

```bash
python3 -m memory_engine bitable schema
python3 -m memory_engine bitable setup-commands
python3 -m memory_engine bitable sync
```

`sync` 默认 dry-run。只有显式传 `--write` 才写 Bitable。

### 4.3 lark-cli 写入策略

使用 `lark-cli base +record-batch-create`：

```bash
lark-cli base +record-batch-create \
  --base-token "$BITABLE_BASE_TOKEN" \
  --table-id "Memory Ledger" \
  --json @batch-create.json
```

批量 JSON 结构：

```json
{
  "fields": ["memory_id", "scope", "type"],
  "rows": [
    ["mem_xxx", "project:feishu_ai_challenge", "workflow"]
  ]
}
```

同步策略：

- 单批最多 200 行。
- 每张表独立写入。
- 每批失败后重试。
- 汇总错误摘要，便于定位权限、字段名或 table id 问题。

### 4.4 配置入口

支持环境变量：

```bash
BITABLE_BASE_TOKEN=app_xxx
BITABLE_LEDGER_TABLE="Memory Ledger"
BITABLE_VERSIONS_TABLE="Memory Versions"
BITABLE_BENCHMARK_TABLE="Benchmark Results"
LARK_CLI_PROFILE=feishu-ai-challenge
LARK_CLI_AS=user
```

同时支持 CLI 参数覆盖：

```bash
python3 -m memory_engine bitable sync \
  --base-token "$BITABLE_BASE_TOKEN" \
  --ledger-table "Memory Ledger" \
  --versions-table "Memory Versions" \
  --benchmark-table "Benchmark Results" \
  --profile feishu-ai-challenge \
  --as-identity user
```

## 5. 本地 dry-run 契约

无 Bitable 权限时，以下命令必须可运行：

```bash
python3 -m memory_engine bitable schema
python3 -m memory_engine bitable sync --benchmark-cases benchmarks/day1_cases.json
```

dry-run 输出应包含：

- `ok: true`
- `dry_run: true`
- 三张表对应行数
- 将要执行的 `lark-cli` 命令预览
- `errors: []`

这证明同步逻辑可构造 payload，但不会触发外部写入。

## 6. 视图和 Demo 讲解

视图建议单独沉淀到：

```text
docs/bitable-ledger-views.md
```

建议视图：

| 表 | 视图 | 用途 |
|---|---|---|
| `Memory Ledger` | `Active Ledger` | 筛选 `status = active`，展示当前有效记忆 |
| `Memory Ledger` | `By Type` | 按 `type` 分组，展示记忆覆盖范围 |
| `Memory Ledger` | `Recently Updated` | 按 `updated_at` 倒序，展示刚同步的变更 |
| `Memory Versions` | `Version Chain` | 按 `memory_id` 分组，按 `version` 升序 |
| `Memory Versions` | `By Version Status` | 展示 active/superseded |
| `Benchmark Results` | `Latest Runs` | 展示最近评测汇总 |

评委讲解主线：

1. `Memory Ledger` 证明系统沉淀的是结构化当前有效记忆，不是聊天日志。
2. `Memory Versions` 证明系统能追踪旧规则如何被新规则覆盖。
3. `Benchmark Results` 证明系统能用指标自证，而不是只靠一次演示。

## 7. 测试计划

### 7.1 单元测试

新增 `tests/test_bitable_sync.py`：

- 创建临时 SQLite。
- 写入一条记忆和一次覆盖更新。
- 验证 `Memory Ledger` 只有一条当前记忆。
- 验证 `Memory Versions` 同时包含 `active` 和 `superseded`。
- 验证 dry-run 不调用真实 lark-cli。
- 验证 Benchmark summary 可生成 `Benchmark Results` 行。

### 7.2 回归验证

提交前运行：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine bitable schema
python3 -m memory_engine bitable sync --benchmark-cases benchmarks/day1_cases.json
```

### 7.3 真实 Bitable 验证

有权限后运行：

```bash
python3 -m memory_engine bitable sync --write --benchmark-cases benchmarks/day1_cases.json
```

验收：

- `Memory Ledger` 能看到 active 记忆。
- `Memory Versions` 能看到 active/superseded 版本。
- `Benchmark Results` 能看到最新 benchmark 汇总。

## 8. 风险和取舍

| 风险 | 处理 |
|---|---|
| Bitable 权限不可用 | 默认 dry-run，不阻塞本地核心能力 |
| 字段名和表名不一致 | 支持环境变量和 CLI 参数覆盖 |
| 重复同步产生重复记录 | 初赛接受 append-only；后续可做 record_id 映射 |
| lark-cli 写入失败 | 增加 retry 和 error summary |
| 真实视图配置需要人工检查 | handoff 交给队友晚上核对字段顺序和视图 |

## 9. 队友晚上任务

1. 在真实 Bitable 中检查字段命名和展示顺序。
2. 按 `docs/bitable-ledger-views.md` 创建视图。
3. 输出一份“评委看 Bitable 时的讲解词”。
4. 造 20 条记忆样例，覆盖 decision、workflow、preference、deadline、risk。
5. 至少造 3 条覆盖更新样例，用来展示 `superseded`。

## 10. 完成标准

Day 4 完成时必须满足：

- 本地无 Bitable 权限时，`remember`、`recall`、`benchmark` 不受影响。
- dry-run 能输出三张表 payload 和写入命令预览。
- 有权限时可用 `--write` 写入 Bitable。
- README 或 handoff 记录配置步骤。
- handoff 记录未验证项和队友任务。
- 所有本地验证命令通过。
