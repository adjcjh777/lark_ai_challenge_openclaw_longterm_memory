# Day 1 队友补位完成记录

日期：2026-04-25  
对应任务：D1 队友晚上任务补齐

## 给队友先看这个

今天已经把 D1 原本留给队友的测试样例、干扰聊天、矛盾更新 case、Demo 讲法和白皮书目录补齐。你后面不用再从零写 D1 材料，只需要在真实演示前读一遍脚本，看哪里不像人话。

判断做对的标准：

- 30 条记忆样例能覆盖决策、流程、偏好、截止时间、负责人、飞书接入、评测这几类内容。
- 100 条干扰聊天读起来像真实群聊里的杂音，不会被误认为正式规则。
- 10 条矛盾更新 case 都能体现“旧值被新值覆盖”。
- 5 分钟 Demo 能讲清楚：记住、找回、抗干扰、覆盖旧规则、证据链。

## 已补齐的文件

| 文件 | 内容 | 完成标准 |
|---|---|---|
| `benchmarks/day1_teammate_cases.json` | 30 条 recall case + 10 条 conflict_update case | 可用现有 benchmark runner 运行 |
| `data/day1_teammate_noise_messages.txt` | 100 条不应沉淀为长期记忆的干扰聊天 | 读起来像工作群杂音 |
| 本文件“白皮书一页目录”小节 | D1 白皮书目录草案 | 后续正式白皮书按总控文档落到 `docs/memory-definition-and-architecture-whitepaper.md` |
| `docs/day1-teammate-completion.md` | 本文件 | 记录 D1 队友任务已闭环 |

## 交付物要求自查

| 初赛交付物 | D1 队友补位结果 | 是否还要继续 |
|---|---|---|
| Memory 定义与架构白皮书 | 已整理白皮书一页目录，覆盖“为什么不是搜索”和状态机 | 后续 D12 按 `docs/memory-definition-and-architecture-whitepaper.md` 扩成正式稿 |
| 可运行 Demo | 已有 5 分钟讲法，能用 CLI 展示 remember / recall / conflict | 后续接飞书截图 |
| Benchmark Report | 已补 D1 扩展样例和干扰聊天，能支撑早期评测 | 后续 D7-D9 扩指标 |
| 提交材料 | README 和 handoff 已有入口 | 后续 D13/D14 打包 |

## 5 分钟 Demo 讲法

### 0:00-0:40 开场

我们做的不是普通聊天搜索，而是“企业协作记忆”。普通搜索只能把历史消息找出来，但它不知道哪条是当前有效规则，也不知道旧规则是不是已经被覆盖。Memory Engine 会把聊天或文档里的高价值信息整理成 active memory（当前有效记忆），并保留证据和版本链。

### 0:40-1:30 写入第一条记忆

运行：

```bash
python3 -m memory_engine remember --scope project:feishu_ai_challenge "生产部署必须加 --canary --region cn-shanghai"
python3 -m memory_engine recall --scope project:feishu_ai_challenge "生产部署参数"
```

讲解重点：

- 系统返回当前规则。
- 返回里有 `source_type`、`source_id`、`quote`，说明不是凭空生成。
- 这条记忆有状态和版本。

### 1:30-2:20 加入干扰后召回

运行：

```bash
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

讲解重点：

- case 里混入无关聊天。
- 系统仍然只召回 active memory。
- 干扰聊天进入 raw event 层，不默认成为长期记忆。

### 2:20-3:30 展示矛盾更新

运行：

```bash
python3 -m memory_engine remember --scope project:feishu_ai_challenge "不对，生产部署 region 改成 ap-shanghai"
python3 -m memory_engine recall --scope project:feishu_ai_challenge "生产部署 region"
```

讲解重点：

- `cn-shanghai` 变成旧版本。
- `ap-shanghai` 变成当前 active。
- 这就是它和搜索最大的区别：搜索会把新旧两条都找出来，Memory Engine 默认只返回当前有效版本。

### 3:30-4:20 看版本链

运行：

```bash
python3 -m memory_engine versions <上一步返回的 memory_id>
```

讲解重点：

- 旧值没有被删除，而是保留为 `superseded`。
- 评委能追溯为什么现在只用新值。

### 4:20-5:00 收束到比赛价值

一句话收尾：

> 我们把飞书里的零散协作信息，变成了可更新、可召回、可解释、可评测的团队记忆。

## 白皮书一页目录

1. 什么是企业级记忆：可表达、可验证、可更新、可召回的团队事实单元。
2. 为什么不是搜索：搜索不理解当前有效版本，也不管理冲突更新。
3. 系统架构：飞书消息/文档/CLI -> 抽取 -> Memory Engine -> SQLite/Bitable -> Bot/CLI/Demo。
4. 状态机：candidate（待确认）-> active（当前有效）-> superseded（已覆盖）-> stale（待复核）-> archived（归档）。
5. 核心机制：抗干扰、矛盾更新、版本链、证据链。
6. 飞书生态：Bot 负责交互，文档 ingestion 提供来源，Bitable 做评委可视化。
7. Benchmark：抗干扰、矛盾更新、效能指标三类测试。
8. 企业价值：减少重复沟通，避免旧规则误用，让团队知识有证据、有版本、有边界。

## 卡片/回复文案审查建议

虽然 D1 还没有飞书卡片，但后续 Bot 回复必须遵循这几条：

- 第一行先给结论，不先堆字段。
- 必须出现“当前有效”或“已被覆盖”，让评委一眼看懂状态。
- 证据要短，只放原文摘录，不放完整内部链接或 token。
- 旧值和新值要并排展示，例如 `旧规则 -> 新规则`。
- 未命中时要告诉用户下一步可以 `/remember`。

## D1 队友任务完成对照

| 原任务 | 完成情况 |
|---|---|
| 补 30 条记忆测试样例 | 已放入 `benchmarks/day1_teammate_cases.json` 的前 30 条 |
| 补 100 条干扰聊天样例 | 已放入 `data/day1_teammate_noise_messages.txt` |
| 设计 10 条矛盾更新 case | 已放入 `benchmarks/day1_teammate_cases.json` 的后 10 条 |
| 写 Demo 脚本第一版 | 已写入本文件“5 分钟 Demo 讲法” |
| 审查卡片文案是否让评委一眼看懂 | 已写入“卡片/回复文案审查建议” |
| 提炼白皮书目录成 1 页 | 已写入“白皮书一页目录” |
