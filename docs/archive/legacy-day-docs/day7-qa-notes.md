# Day 7 QA Notes

日期：2026-04-25
主题：企业对话数据质量复核

## 先看这个

这份文件记录 D7 企业对话数据的人工复核结果。代码质量门禁已经通过，今晚主要看数据是否像真实飞书工作群、case 是否有证据、报告是否讲得清楚。

## 抽查范围

- `datasets/enterprise_dialogues.jsonl`
  - 抽查 15 个 thread。
  - 看对话是否自然，是否有真实的前因后果。
  - 看 active / superseded 的 evidence message 是否能支撑结论。
- `benchmarks/dialogue_memory_cases.json`
  - 抽查 30 条 case：10 条 recall、10 条 conflict_update、10 条 temporary_noise。
  - 看 query 是否像真实同事会问的问题。
  - 看 expected / forbidden 是否能从 source thread 中找到依据。
- `datasets/noise_messages.txt`
  - 抽查 50 条。
  - 标出太像正式决策、太模板化、或可能被误沉淀的句子。
- `docs/benchmark-report.md`
  - 检查“D7 企业对话数据质量评估”是否能让评委看懂。

## 复核记录

| 项目 | 抽查数量 | 结论 | 需要修改的样例 |
|---|---:|---|---|
| enterprise dialogues |  |  |  |
| dialogue memory cases |  |  |  |
| noise messages |  |  |  |
| benchmark report wording |  |  |  |

## 问题清单

| 文件 | 位置 | 问题 | 建议 |
|---|---|---|---|
|  |  |  |  |

## 通过标准

- 至少 15 个 thread 读起来像真实工作群。
- conflict_update case 能看出旧值被新值覆盖。
- temporary_noise case 不会把临时消息误写成长期记忆。
- 报告能讲清楚：raw chat 很多，长期记忆只保存经过整理的有效信息。
