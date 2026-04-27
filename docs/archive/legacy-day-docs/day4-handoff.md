# Day 4 Handoff

日期：2026-04-27

## 先看这个

1. 今天已经完成：本地记忆已经能同步到飞书多维表格，评委可以在表格里看到当前记忆、版本链和评测结果。
2. 你今晚从这里开始：打开真实 Bitable 看板，先看字段顺序和视图是否清楚。
3. 你今晚要交付：把需要给评委展示的视图截图整理出来，并把手动调整过的视图写到 `docs/day4-qa-notes.md`。
4. 做对的标准：评委不用看代码，也能在表格里看懂“这条记忆是什么、当前是否有效、历史版本是什么”。
5. 遇到问题发我：发 Bitable 截图、你点的视图名称、以及页面提示的错误。

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

如果表名被外部分工改成中文或实际 table id，可通过环境变量或命令参数覆盖。

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

## 真实 Bitable 写入验证

2026-04-25 已在真实 Base“飞书 ai 挑战赛”完成一次写入验证，Base token 保留在本地环境变量，不写入仓库。

已创建三张表：

- `Memory Ledger`
- `Memory Versions`
- `Benchmark Results`

已执行：

```bash
python3 -m memory_engine bitable sync --write --benchmark-cases benchmarks/day1_cases.json
```

写入结果：

- `Memory Ledger`：2 行。
- `Memory Versions`：4 行，包含 `active` 与 `superseded`。
- `Benchmark Results`：1 行，`case_count = 10`，`case_pass_rate = 1.0`，`conflict_accuracy = 1.0`，`stale_leakage_rate = 0.0`。

验证读取：

```bash
lark-cli base +record-list --table-id "Memory Ledger" --limit 5
lark-cli base +record-list --table-id "Memory Versions" --limit 5
lark-cli base +record-list --table-id "Benchmark Results" --limit 5
```

## 样例数据和评委视图增强

2026-04-25 追加完成一轮评委看板增强：

- 新增 `scripts/seed_day4_demo_data.py`。
- 本地写入 `project:day4_demo` 样例数据：
  - 20 条 active 记忆。
  - decision、workflow、preference、deadline、risk 各 4 条。
  - 3 条覆盖更新样例，形成 active/superseded 版本链。
- 同步命令新增 `--scope` 过滤，避免只为 Demo 补样例时重复同步其它 scope。
- 已同步到真实 Bitable：
  - `Memory Ledger`：追加 20 行。
  - `Memory Versions`：追加 23 行。
  - `Benchmark Results`：追加 1 行。
- 新增评委讲解词：`docs/day4-bitable-demo-talk-track.md`。

样例数据命令：

```bash
python3 scripts/seed_day4_demo_data.py --scope project:day4_demo
python3 -m memory_engine bitable sync --scope project:day4_demo --benchmark-cases benchmarks/day1_cases.json
python3 -m memory_engine bitable sync --write --scope project:day4_demo --benchmark-cases benchmarks/day1_cases.json
```

已创建真实视图：

- `Memory Ledger / Active Ledger`
- `Memory Ledger / By Type`
- `Memory Ledger / Recently Updated`
- `Memory Versions / Version Chain`
- `Memory Versions / By Version Status`
- `Benchmark Results / Latest Runs`

已配置成功：

- `Active Ledger`：筛选 `status = active`。
- `By Type`：按 `type` 分组。
- `Recently Updated`：按 `updated_at` 倒序。
- `Version Chain`：按 `memory_id` 分组，按 `version` 升序。
- `Latest Runs`：设置核心字段顺序。

平台限制：

- 部分视图配置接口返回 `OpenAPIUpdateViewSort limited`、`OpenAPIUpdateViewGroup limited` 或 `OpenAPISetVisibleFields limited`。
- 需要外部分工在真实 Bitable UI 中手动补齐：`By Version Status` 按 `status` 分组，`Latest Runs` 按 `updated_at` 倒序，个别视图字段顺序微调。

## 历史补充任务

1. 打开真实 Bitable 看板，确认 `memory_id`、`subject`、`current_value`、`status`、`version`、`updated_at` 这几个字段在前面，评委不用横向翻太久。
2. 在 Bitable 页面里手动补齐两个视图：`By Version Status` 按状态分组，`Latest Runs` 按更新时间倒序。
3. 按 `docs/day4-bitable-demo-talk-track.md` 讲一遍，标出最适合截图的 3-5 个页面。
4. 人工看 20 条样例是否像真实项目内容；不自然的文案先写到 `docs/day4-qa-notes.md`。

今晚不用做：

- 不用修改 Bitable 同步脚本。
- 不用重新生成数据库样例，除非当天明确安排。
- 不用把真实 Base token、表格链接或内部截图提交到仓库。

## 未验证项

- 当前同步策略是 append-only 批量创建，适合初赛 Demo 和评委看板；如果需要长期生产同步，后续应增加 record_id 映射表或按 `memory_id` 查找后更新。
- Bitable 视图已创建，但部分排序、分组和字段顺序受 OpenAPI 限制，尚需外部分工在真实 Base UI 中人工检查和微调。
