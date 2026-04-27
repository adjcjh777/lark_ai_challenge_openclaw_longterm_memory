# Day 5 Handoff

日期：2026-04-28

## 先看这个

1. 今天已经完成：系统可以从飞书文档或 Markdown 文件里抽取“可能值得记住”的内容，先放进候选列表，确认后才变成正式记忆。
2. 你今晚从这里开始：准备两份示例文档，一份写架构决策，一份写项目周会纪要。
3. 你今晚要交付：每份文档至少 5 条重要信息、15 条干扰内容，并记录 `/ingest_doc` 的测试结果。
4. 做对的标准：机器人回复里能看到候选记忆，确认其中一条后，`/recall` 能查到它，并显示来自哪份文档。
5. 遇到问题发我：发文档标题、`/ingest_doc` 命令、机器人回复截图或 `lark-cli docs +fetch` 报错。

## 今日目标

D5 目标是完成文档 ingestion 最小闭环。优先 P0，完成后继续 P1。

P0：

- 实现 `/ingest_doc <url_or_token>` 的本地 handler 或 CLI 命令。
- 读取飞书文档纯文本，或用 `lark-cli docs +fetch` 作为第一版入口。
- 从文档中抽取候选记忆，默认保存为 `candidate`。
- 记录 evidence：文档 token、标题、摘录 quote。

P1：

- 增加 `/confirm <candidate_id>` 和 `/reject <candidate_id>` 的最小实现。
- 支持从 Markdown 文件导入，便于无飞书权限时演示。
- 增加文档 ingestion fixture。

## 已完成代码能力

- 新增 `memory_engine/document_ingestion.py`：
  - 本地 Markdown 文件读取。
  - 飞书文档 token/url 解析。
  - `lark-cli docs +fetch <token>` 纯文本读取入口。
  - 基于文档行/段落抽取候选 quote。
- 扩展 `MemoryRepository`：
  - `add_candidate(...)` 写入 `candidate` 记忆、候选版本和文档 evidence。
  - `confirm_candidate(...)` 将候选提升为 `active`。
  - `reject_candidate(...)` 将候选标记为 `rejected`。
  - `recall(...)` 返回 `document_title`、`document_token` 和 quote。
- 扩展 CLI：
  - `python3 -m memory_engine ingest-doc <url_or_token>`
  - `python3 -m memory_engine confirm <candidate_id>`
  - `python3 -m memory_engine reject <candidate_id>`
- 扩展飞书 Bot：
  - `/ingest_doc <url_or_token>`
  - `/confirm <candidate_id>`
  - `/reject <candidate_id>`
  - `/recall` 对文档来源显示 `文档《标题》/ token_or_path`。
- 新增 fixture：
  - `tests/fixtures/day5_doc_ingestion_fixture.md`
  - 内含 7 条可抽取候选和多条干扰信息。
- 新增 Demo 文档：
  - `docs/archive/legacy-day-docs/demo-docs/day5-architecture-decisions.md`
  - `docs/archive/legacy-day-docs/demo-docs/day5-weekly-meeting-notes.md`
  - 每份文档包含 5 条可抽取记忆和 15 条干扰信息。
- 新增 Day5 ingestion benchmark：
  - `benchmarks/day5_ingestion_cases.json`
  - `python3 -m memory_engine benchmark ingest-doc benchmarks/day5_ingestion_cases.json`
- 新增测试：
  - `tests/test_document_ingestion.py`
  - `tests/test_feishu_day5.py`

## 演示命令

Markdown fallback 路径：

```bash
tmp_db=$(mktemp -t day5-memory.XXXXXX.sqlite)
python3 -m memory_engine --db-path "$tmp_db" ingest-doc --limit 7 tests/fixtures/day5_doc_ingestion_fixture.md
python3 -m memory_engine --db-path "$tmp_db" confirm <candidate_id>
python3 -m memory_engine --db-path "$tmp_db" recall 生产部署参数
rm -f "$tmp_db"
```

Day5 ingestion benchmark：

```bash
python3 -m memory_engine benchmark ingest-doc benchmarks/day5_ingestion_cases.json
```

飞书 Bot dry-run/replay 可发送：

```text
@Feishu Memory Engine bot /ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md
@Feishu Memory Engine bot /confirm mem_xxx
@Feishu Memory Engine bot /recall 生产部署参数
```

飞书文档权限就绪后可发送真实 token 或 URL：

```text
@Feishu Memory Engine bot /ingest_doc https://.../docx/<token>
```

底层会调用：

```bash
lark-cli docs +fetch --api-version v2 --doc <token> --doc-format markdown
```

## 真实飞书文档验证

2026-04-25 已用 `lark-cli docs +create --api-version v2 --as user --doc-format markdown` 创建两份真实飞书文档，并用真实 URL 跑通 `ingest-doc`。为避免把内部文档链接写入公开仓库，handoff 只记录标题和结果，不提交 URL/token。

真实验证结果：

- `Day5 Demo 架构决策文档`：
  - `source_type = document_feishu`
  - `candidate_count = 5`
  - 候选 quote 覆盖：生产部署、后端框架、数据存储、Benchmark、飞书 Bot 权限。
- `Day5 Demo 项目周会纪要`：
  - `source_type = document_feishu`
  - `candidate_count = 5`
  - 候选 quote 覆盖：评测报告截止、OpenClaw 演示负责人、周报偏好、真实 Bot 权限风险、Day6 决策卡片字段。
- 真实文档确认 + 召回验证：
  - 确认 `生产部署必须加 --canary --region cn-shanghai` 候选后，`recall 生产部署参数` 返回 `status = active`。
  - 召回来源包含 `source_type = document_feishu`、`document_title = Day5 Demo 架构决策文档`、原文 quote。

创建真实文档时遇到一次飞书下游瞬时错误：

```text
code = 10071
downstream_code = 233523001
```

重试后成功。当前结论：真实文档创建/读取链路可用，但演示时建议保留 Markdown fallback。

## 验证结果

已通过：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark ingest-doc benchmarks/day5_ingestion_cases.json
```

专项验证：

- `python3 -m unittest discover -s tests -p 'test_document_ingestion.py'`：3 tests OK。
- `python3 -m unittest discover -s tests -p 'test_feishu_day5.py'`：1 test OK。
- CLI demo：从 `tests/fixtures/day5_doc_ingestion_fixture.md` 抽取 7 条 candidate，确认生产部署候选后，`recall` 返回：
  - `source_type = document_markdown`
  - `document_title = Day5 架构决策文档`
  - `quote = 决定：生产部署必须加 --canary --region cn-shanghai。`
- Day5 ingestion benchmark：
  - `case_count = 2`
  - `case_pass_rate = 1.0`
  - `avg_candidate_count = 5.0`
  - `avg_quote_coverage = 1.0`
  - `avg_noise_rejection_rate = 1.0`
  - `document_evidence_coverage = 1.0`

Day 1 benchmark 仍为：

- `case_count = 10`
- `case_pass_rate = 1.0`
- `conflict_accuracy = 1.0`
- `evidence_coverage = 1.0`
- `stale_leakage_rate = 0.0`

## 历史补充任务

1. 准备 2 份示例飞书文档：一份叫“架构决策文档”，一份叫“项目周会纪要”。
2. 每份文档写 5 条重要信息，再混入 15 条普通说明或闲聊内容，模拟真实文档里有噪声。
3. 在测试群发送 `/ingest_doc <文档链接>`；如果权限失败，就记录错误，并改用 `tests/fixtures/day5_doc_ingestion_fixture.md` 继续演示。
4. 看机器人回复的候选列表是否好懂：哪条值得确认、从哪份文档来、下一步该点确认还是拒绝。
5. 给白皮书补一段白话说明：每条文档记忆都有标题、来源和原文摘录，所以评委能追溯证据。

今晚不用做：

- 不用修改文档抽取代码。
- 不用提交真实飞书文档链接、token 或内部文档截图。
- 不用做批量确认按钮，卡片按钮是后续任务。

## 未验证项

- 真实飞书文档 token 已用 CLI 验证通过；尚未在真实飞书群聊中通过 Bot 长连接发送 `/ingest_doc <url>` 做端到端群聊验证。
- 当前抽取器是启发式规则，适合 Demo 文档和初赛闭环；后续如需复杂文档块结构，应接入更强的解析或人工确认 UI。
- 候选确认目前按 `candidate_id` 手动执行，尚无批量确认或卡片按钮。
