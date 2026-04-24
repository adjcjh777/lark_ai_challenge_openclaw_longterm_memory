# Day 1 Handoff

日期：2026-04-24

## 今日完成

- 本地 `remember` / `recall`：已实现，默认使用 `data/memory.sqlite`。
- SQLite schema：已实现 `raw_events`、`memories`、`memory_versions`、`memory_evidence`。
- 冲突更新：已实现同 scope/type/subject 下的覆盖更新，旧版本标记为 `superseded`，新版本为 `active`。
- Benchmark runner：已实现 `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`。
- Benchmark cases：已提供 10 条 Day 1 case，覆盖普通召回、干扰召回、矛盾更新、旧值泄漏和 evidence。
- 飞书准备：README 已记录 `lark-cli` 入口、Day 2 Bot 权限和环境变量。

## 今晚请测

1. 输入旧规则 -> 新规则，确认只返回新规则。
2. 加入干扰样例后，确认 recall 仍能命中目标记忆。
3. 检查 recall JSON 是否包含 evidence：`source_type`、`source_id`、`quote`。
4. 检查 Demo 文案是否能在 5 分钟内讲清楚：记忆写入、抗干扰召回、矛盾覆盖、证据链。

## 明天目标

- 接飞书长连接事件订阅。
- 支持 `/remember` 和 `/recall`。
- 使用 Bot 文本回复召回结果。
- 继续优先使用本机 `lark-cli`，OpenClaw 插件只在需要官方插件能力时安装和使用。

