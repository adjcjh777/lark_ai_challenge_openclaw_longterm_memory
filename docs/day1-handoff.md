# Day 1 Handoff

日期：2026-04-24

## 给队友先看这个

今天先把“记忆引擎”的本地版本跑起来了。它现在可以做到：记住一条规则、按问题找回规则、遇到新规则时覆盖旧规则、用评测脚本检查结果是否正确。

你今晚不用看数据库和代码，主要帮忙确认 Demo 讲得通：评委能不能看懂“系统真的记住了，而且旧规则不会乱回来”。

做对的标准：

- 输入旧规则和新规则后，系统只返回新规则。
- 中间加一些无关内容后，系统还能找回正确记忆。
- 召回结果里能看到来源证据，也就是这条记忆从哪里来。
- 5 分钟内能讲清楚：记住、找回、抗干扰、覆盖旧规则。

如果卡住，把你输入的命令和系统返回内容发给我；不用自己改代码。

## 今日完成

- 本地 `remember` / `recall`：已实现，默认使用 `data/memory.sqlite`。
- SQLite schema：已实现 `raw_events`、`memories`、`memory_versions`、`memory_evidence`。
- 冲突更新：已实现同 scope/type/subject 下的覆盖更新，旧版本标记为 `superseded`，新版本为 `active`。
- Benchmark runner：已实现 `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`。
- Benchmark cases：已提供 10 条 Day 1 case，覆盖普通召回、干扰召回、矛盾更新、旧值泄漏和 evidence。
- 飞书准备：README 已记录 `lark-cli` 入口、Day 2 Bot 权限和环境变量。

## 队友今晚任务

1. 按 README 里的 Day 1 命令跑一遍 `remember` 和 `recall`，确认能记住并查回来。
2. 先输入“周报发给 A”，再输入“不对，周报发给 B”，确认最后只返回 B。
3. 看召回结果里有没有 `source_type`、`source_id`、`quote`。这三个字段表示“这条记忆从哪里来”。
4. 用自己的话写一版 5 分钟 Demo 讲法，重点讲：为什么它不是普通搜索。

## 队友任务补齐记录

2026-04-25 已补齐 D1 队友任务，详见 `docs/day1-teammate-completion.md`。

- 30 条记忆测试样例和 10 条矛盾更新 case 已写入 `benchmarks/day1_teammate_cases.json`。
- 100 条干扰聊天样例已写入 `data/day1_teammate_noise_messages.txt`。
- 5 分钟 Demo 讲法、白皮书一页目录和回复文案审查建议已写入 `docs/day1-teammate-completion.md`。
- 可用命令验证：`python3 -m memory_engine benchmark run benchmarks/day1_teammate_cases.json`。

今晚不用做：

- 不用改数据库结构。
- 不用接飞书机器人。
- 不用处理 OpenClaw 或 Hermes。

## 明天目标

- 接飞书长连接事件订阅。
- 支持 `/remember` 和 `/recall`。
- 使用 Bot 文本回复召回结果。
- 继续优先使用本机 `lark-cli`，OpenClaw 插件只在需要官方插件能力时安装和使用。
