# Day 7 Handoff

日期：2026-04-25  
目标日期：2026-04-30  
主题：Benchmark 扩容，抗干扰测试成型

说明：这是提前执行 D7。当前已优先完成 P0，并补齐 P1 中低成本加码项。

## 给队友先看这个

今天做的是评测脚本。它会先放入 50 条真正重要的记忆，再混入 1000 条无关聊天，然后问 50 个问题，检查系统还能不能找回正确记忆。

你今晚不用管代码怎么实现，主要帮忙把测试数据改得更像真实工作群。现在数据能跑通，但有些内容还偏“机器生成”，需要你把它改得自然一点。

做对的标准：

- 50 条关键记忆读起来像真实项目里的决定、流程、偏好或风险提醒。
- 1000 条干扰聊天读起来像真实群聊废话，不要太整齐。
- 50 个问题像真实同事会问的问题。
- 报告里能让评委看懂：不是所有聊天都算记忆，只有整理后的有效信息才会被召回。

如果卡住，把你觉得不自然的 3-5 条样例贴给我；不用自己改评测脚本。

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
python3 -m unittest discover -s tests -p 'test_benchmark_day7.py'
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md --csv-output reports/day7_anti_interference.csv --json-output reports/day7_anti_interference.json
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m unittest discover -s tests
```

## 提交前注意

- 不提交 `.env`。
- 不提交 `.omx/`。
- 不提交 `.reference/hermes-agent/`。
- 不提交 `data/memory.sqlite`。
- 不提交 `reports/day7_anti_interference.csv` 或 `reports/day7_anti_interference.json`。
- 当前工作区已有非本轮未跟踪文件 `docs/pr2-teammate-fix-notes.md`，本轮不纳入提交。

## 队友今晚任务

1. 打开 `benchmarks/day7_anti_interference.json`，把里面不自然的关键记忆改成真实群聊会出现的说法。数量先别改，保持 50 条关键记忆、1000 条干扰聊天、50 个问题。
2. 随机挑 20 个问题，看系统给出的前三条结果里有没有正确答案。这里的“前三条结果”就是评测里说的 Recall@3。
3. 打开 `docs/benchmark-report.md`，把“测试集设计”那一段写得更像给评委看的说明：我们为什么放 1000 条干扰、这些干扰模拟什么场景。
4. 检查报告有没有讲清楚这句话：聊天记录可以很多，但真正进入长期记忆的是被整理后的有效信息。

今晚不用做：

- 不用改 `memory_engine/benchmark.py`。
- 不用处理 CSV/JSON 报告输出。
- 不用研究 Hermes Agent 代码，只要帮忙把报告说清楚。

## 剩余风险

- D7 数据集目前偏合成化，适合证明评测脚本能跑通；后续应让队友补真实群聊风格。
- 当前召回仍为规则打分，复杂语义改写未覆盖；D8/D9 可结合失败样例再决定是否增强 subject 归一化。
- `docs/benchmark-report.md` 目前只覆盖 D7 抗干扰，D8/D9 需要继续追加矛盾更新和效能指标章节。
