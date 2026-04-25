# Day 4 Handoff

日期：2026-04-27

## 今日目标

D4 目标是完成 Bitable 记忆台账和评委可视化。优先 P0，完成后继续 P1。

P0：

- 设计 Bitable 表结构：`Memory Ledger`、`Memory Versions`、`Benchmark Results`。
- 实现“本地 SQLite -> Bitable 同步”的最小脚本。
- 同步字段至少包括：`memory_id`、`scope`、`type`、`subject`、`current_value`、`status`、`version`、`source`、`updated_at`。
- 增加本地 dry-run，避免没有 Bitable 权限时阻塞。

P1：

- 增加 Bitable 视图建议文档。
- 支持将 Benchmark 汇总结果写入 `Benchmark Results`。
- 增加同步失败重试和错误摘要。

## 已完成代码能力

- 新增 `memory_engine/bitable_sync.py`：
  - 从 SQLite 导出 `Memory Ledger` 行。
  - 从 SQLite 导出 `Memory Versions` 行，包含 `active` / `superseded`。
  - 从 benchmark JSON 或 benchmark cases 生成 `Benchmark Results` 汇总行。
  - 默认 dry-run，输出将要执行的 `lark-cli base +record-batch-create` 命令和行数。
  - 使用 `lark-cli` 写入时支持每批最多 200 行、失败重试和错误摘要。
- 新增 CLI：
  - `python3 -m memory_engine bitable schema`
  - `python3 -m memory_engine bitable setup-commands`
  - `python3 -m memory_engine bitable sync`
- 新增测试：`tests/test_bitable_sync.py`。

## Bitable 配置步骤

1. 在飞书多维表格中准备一个 Base，记下 Base token。
2. 创建三张表，表名建议保持：
   - `Memory Ledger`
   - `Memory Versions`
   - `Benchmark Results`
3. 查看字段设计：

```bash
python3 -m memory_engine bitable schema
```

4. 生成建表命令预览：

```bash
python3 -m memory_engine bitable setup-commands --base-token "$BITABLE_BASE_TOKEN" --profile feishu-ai-challenge --as-identity user
```

5. 本地 dry-run 同步，不写入飞书：

```bash
python3 -m memory_engine bitable sync --benchmark-cases benchmarks/day1_cases.json
```

6. 有权限后执行真实写入：

```bash
export BITABLE_BASE_TOKEN="app_xxx"
export BITABLE_LEDGER_TABLE="Memory Ledger"
export BITABLE_VERSIONS_TABLE="Memory Versions"
export BITABLE_BENCHMARK_TABLE="Benchmark Results"
export LARK_CLI_PROFILE="feishu-ai-challenge"
export LARK_CLI_AS="user"

python3 -m memory_engine bitable sync --write --benchmark-cases benchmarks/day1_cases.json
```

如果表名被队友改成中文或实际 table id，可通过环境变量或命令参数覆盖。

## 视图建议

详见 `docs/bitable-ledger-views.md`。建议至少配置：

- `Memory Ledger / Active Ledger`：筛选 `status = active`，按 `updated_at` 倒序。
- `Memory Ledger / By Type`：按 `type` 分组。
- `Memory Versions / Version Chain`：按 `memory_id` 分组，再按 `version` 升序。
- `Benchmark Results / Latest Runs`：按 `updated_at` 倒序。

## 本地验证

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine bitable schema
python3 -m memory_engine bitable sync --benchmark-cases benchmarks/day1_cases.json
```

## 队友今晚任务

1. 在飞书多维表格里检查字段命名和展示顺序，优先保证 `memory_id`、`subject`、`current_value`、`status`、`version`、`updated_at` 在前排可见。
2. 按 `docs/bitable-ledger-views.md` 创建或调整视图。
3. 输出一份“评委看 Bitable 时的讲解词”，可直接基于 `docs/bitable-ledger-views.md` 的讲解词改写。
4. 造 20 条不同类型的记忆样例，覆盖 decision、workflow、preference、deadline、risk，并至少包含 3 条覆盖更新。

## 未验证项

- 当前环境未在真实 Bitable 中执行 `--write` 写入，真实写入取决于 Base token、字段结构、表权限和 lark-cli profile。
- 当前同步策略是 append-only 批量创建，适合初赛 Demo 和评委看板；如果需要长期生产同步，后续应增加 record_id 映射表或按 `memory_id` 查找后更新。
- Bitable 视图尚需队友在真实 Base 中人工检查展示顺序。
