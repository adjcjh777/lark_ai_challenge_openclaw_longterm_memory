# Day 7 Handoff

日期：2026-04-25
目标日期：2026-04-30
主题：Benchmark 扩容，抗干扰测试成型

说明：这是提前执行 D7。当前已优先完成 P0，并补齐 P1 中低成本加码项。

## 先看这个

今天做的是评测脚本和企业对话数据评估。第一版脚本会先放入 50 条真正重要的记忆，再混入 1000 条无关聊天，然后问 50 个问题，检查系统还能不能找回正确记忆；新补的数据则是 60 个更像真实飞书群聊的 thread，用来替代偏合成的样例。

你今晚不用管核心代码怎么实现，主要帮忙审查新数据和报告表达。现在数据质量门禁已经通过，但还没接入正式 runner；你要帮忙确认它读起来像真实工作群，并且评委能看懂这批数据为什么能证明“长期记忆不是普通聊天搜索”。

做对的标准：

- `datasets/enterprise_dialogues.jsonl` 里的 60 个 thread 读起来像真实项目里的决定、流程、偏好、风险、安全规则或文档规则。
- `benchmarks/dialogue_memory_cases.json` 里的 150 个问题像真实同事会问的问题，其中 40 个冲突更新 case 能看出旧值被新值覆盖。
- `datasets/noise_messages.txt` 里的干扰消息像真实群聊废话，不要太整齐，也不要看起来像正式决策。
- 报告里能让评委看懂：不是所有聊天都算记忆，只有整理后的有效信息才会被召回。

如果卡住，把你觉得不自然的 3-5 条样例贴给我；不用自己改 `memory_engine/` 核心代码。

## 已完成

P0：

- 扩展 `benchmark run`，支持 D7 anti-interference spec：
  - 批量注入 curated memories。
  - 批量生成并注入 raw/noise events。
  - 批量执行 recall queries。
- 新增 `benchmarks/day7_anti_interference.json`：
  - 50 条关键记忆。
  - 1000 条干扰对话。
  - 50 条查询。
- 输出指标：
  - Recall@1。
  - Recall@3。
  - MRR。
  - 平均延迟与 P95 延迟。
- 生成 `docs/benchmark-report.md` 初稿，包含指标表。
- 报告解释 raw events、curated memories、recall logs 三层分离，并参考 Hermes persistent memory / session search 叙事说明长期记忆不是把所有聊天塞进 prompt。

P1：

- 干扰规模已提升到 1000 条。
- 增加按 type 和 subject 的分项指标。
- 支持 JSON/CSV/Markdown 输出：
  - `--json-output`
  - `--csv-output`
  - `--markdown-output`
- 在 benchmark 临时库中尝试建立 FTS5 raw event 索引，仅用于失败样例诊断；不替代 active memory 状态机。
- 新增企业对话数据质量评估：
  - `datasets/enterprise_dialogues.jsonl`：60 个真实群聊风格 thread、500 条消息、82 个 memory labels。
  - `datasets/noise_messages.txt`：1000 条不应沉淀为长期记忆的干扰消息。
  - `benchmarks/dialogue_memory_cases.json`：150 条 case，包含 90 recall、40 conflict_update、20 temporary_noise。
  - `scripts/validate_enterprise_data.py`：13 类数据质量检查，当前全部通过。

## 关键文件

- `memory_engine/repository.py`
  - 新增 `recall_candidates(..., limit=3)`，保留 `recall(...)` 兼容旧调用。
- `memory_engine/benchmark.py`
  - Day1 list-of-cases runner 保持兼容。
  - 新增 D7 anti-interference runner、三层统计、分项指标、报告与 CSV 输出。
- `memory_engine/cli.py`
  - `benchmark run` 增加可选输出路径参数。
- `benchmarks/day7_anti_interference.json`
  - D7 抗干扰数据集。
- `tests/test_benchmark_day7.py`
  - 覆盖三层数据、Recall/MRR、Markdown 和 CSV 输出。
- `docs/benchmark-report.md`
  - D7 Benchmark Report 初稿。
- `datasets/enterprise_dialogues.jsonl`
  - 企业对话 thread 数据，含 evidence message 和 supersedes 链。
- `datasets/noise_messages.txt`
  - 不应沉淀为长期记忆的干扰消息池。
- `benchmarks/dialogue_memory_cases.json`
  - 基于企业对话数据生成的 recall / conflict / temporary noise case。
- `scripts/validate_enterprise_data.py`
  - 企业对话数据质量门禁。

## 运行方式

基础一键运行：

```bash
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json
```

生成报告和机器可读结果：

```bash
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json \
  --markdown-output docs/benchmark-report.md \
  --csv-output reports/day7_anti_interference.csv \
  --json-output reports/day7_anti_interference.json
```

`reports/*.csv` 和 `reports/*.json` 已被 `.gitignore` 忽略，只作为本地机器可读运行证据。

## 本轮指标

- raw events：1050
- curated memories：50
- recall logs：50
- Recall@1：1.0000
- Recall@3：1.0000
- MRR：1.0000
- 平均延迟：约 0.688 ms
- P95 延迟：约 1.122 ms

说明：延迟数值会随本机瞬时负载轻微波动，报告中记录的是本轮生成 `docs/benchmark-report.md` 时的结果。

## 验证结果

已通过：

```bash
python3 scripts/validate_enterprise_data.py
python3 -m unittest discover -s tests -p 'test_benchmark_day7.py'
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md --csv-output reports/day7_anti_interference.csv --json-output reports/day7_anti_interference.json
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m unittest discover -s tests
```

企业对话数据质量摘要：

- JSONL：60 threads。
- 消息：500 条，单 thread 8-12 条。
- memory labels：82 个，其中 active 62、superseded 20。
- memory type：decision、workflow、preference、deadline、risk、permission、security、demo、benchmark、document 共 10 类全覆盖。
- benchmark cases：150 条，其中 recall 90、conflict_update 40、temporary_noise 20。
- difficulty：easy 43、medium 41、hard 66。
- `python3 -m memory_engine benchmark run benchmarks/dialogue_memory_cases.json` 当前会得到 `case_pass_rate=0.0`，原因是新 case 通过 `source_thread_id` 指向 JSONL thread，现有 runner 尚未把 thread labels 注入临时库；这属于 runner adapter 待实现，不是数据质量失败。

## 提交前注意

- 不提交 `.env`。
- 不提交 `.omx/`。
- 不提交 `.reference/hermes-agent/`。
- 不提交 `data/memory.sqlite`。
- 不提交 `reports/day7_anti_interference.csv` 或 `reports/day7_anti_interference.json`。
- 当前工作区已有非本轮未跟踪文件 `docs/archive/legacy-day-docs/pr2-collaboration-fix-notes.md`，本轮不纳入提交。

## 历史补充任务

1. 打开 `datasets/enterprise_dialogues.jsonl`，抽查 15 个 thread，看对话是否像真实飞书工作群；重点检查“刚才说错了”“统一改成”“以后都按这个”等冲突表达是否自然。
2. 打开 `benchmarks/dialogue_memory_cases.json`，抽查 30 条 case：10 条 recall、10 条 conflict_update、10 条 temporary_noise。每条检查 query、expected_active_value、forbidden_value 是否能从 source thread 里找到证据。
3. 打开 `datasets/noise_messages.txt`，抽查 50 条，标出太像正式决策、太模板化、或可能被误沉淀为长期记忆的句子。
4. 打开 `docs/benchmark-report.md` 的“D7 企业对话数据质量评估”，把评委可能看不懂的技术词改成白话，特别是 `supersedes`、`active memory`、`temporary_noise`。
5. 把检查记录写到 `docs/day7-qa-notes.md`，不用改核心代码；如果要改数据，只改 `datasets/` 或 `benchmarks/dialogue_memory_cases.json`。

今晚不用做：

- 不用改 `memory_engine/benchmark.py`。
- 不用处理 CSV/JSON 报告输出。
- 不用研究 Hermes Agent 代码，只要帮忙把报告说清楚。

## 剩余风险

- D7 数据集目前偏合成化，适合证明评测脚本能跑通；后续应让外部分工补真实群聊风格。
- 新企业对话数据质量已通过，但还需要 runner adapter 才能变成真实引擎指标。
- 当前召回仍为规则打分，复杂语义改写未覆盖；D8/D9 可结合企业对话失败样例再决定是否增强 subject 归一化。
- `docs/benchmark-report.md` 目前只覆盖 D7 抗干扰，D8/D9 需要继续追加矛盾更新和效能指标章节。
