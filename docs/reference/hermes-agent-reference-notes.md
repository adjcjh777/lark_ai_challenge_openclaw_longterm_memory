# Hermes Agent 参考笔记

版本：2026-04-25  
本地参考源码：`.reference/hermes-agent/`  
当前参考快照：`023b1bf`  
上游仓库：https://github.com/NousResearch/hermes-agent

## 1. 使用边界

Hermes Agent 只作为架构参考，不作为当前项目的运行时依赖。初赛阶段不要把项目改造成 Hermes Agent，也不要引入它的 TUI、多模型 provider、Skills Hub、Telegram/Discord/Slack gateway 或 OpenClaw 迁移系统。

本项目要吸收的是它的机制：

- Memory Provider 生命周期。
- curated memory 和 session search 的分层。
- Skill / SKILL.md 作为 Agent 程序性记忆。
- Feishu gateway 的工程细节。
- cron / scheduler 对主动提醒的启发。
- memory 内容安全扫描。

## 2. 优先阅读文件

| 参考文件 | 参考点 | 对本项目的落点 |
|---|---|---|
| `.reference/hermes-agent/agent/memory_provider.py` | `initialize`、`prefetch`、`sync_turn`、`get_tool_schemas`、`handle_tool_call`、`on_memory_write` 生命周期 | `Memory Engine Provider Contract` |
| `.reference/hermes-agent/tools/memory_tool.py` | 有界 curated memory、写入去重、内容安全扫描、frozen snapshot 思路 | 记忆注入安全、白皮书安全章节、Benchmark 解释 |
| `.reference/hermes-agent/website/docs/developer-guide/memory-provider-plugin.md` | 外部 Memory Provider 插件结构和配置 schema | 复赛可做 Hermes/OpenClaw adapter |
| `.reference/hermes-agent/website/docs/user-guide/features/skills.md` | `SKILL.md` 格式、progressive disclosure、agent-managed skills | D11 的 `feishu-memory-engine` skill |
| `.reference/hermes-agent/website/docs/user-guide/features/memory.md` | Memory vs session search 分层 | D7-D9 benchmark 和文档证据链 |
| `.reference/hermes-agent/gateway/platforms/feishu.py` | 飞书 @mention gating、去重、allowlist、卡片事件、串行处理、fallback | D6 卡片和飞书安全边界 |
| `.reference/hermes-agent/cron/` | 定时任务和主动触达 | D10 遗忘预警 |

## 3. 融入方式

### 初赛

初赛只落地轻量适配，不做完整 Hermes 插件：

1. 在代码中保持 Memory Engine Core 独立。
2. 用 CLI/Bot 暴露 `remember`、`recall`、`versions`、`review_due`、`benchmark`。
3. 在 `agent_adapters/` 下写 Agent 调用契约和 SKILL.md。
4. 在白皮书中说明：飞书 Bot 面向人，OpenClaw/Hermes Skill 面向 Agent，二者共享同一套企业记忆核心。

### 复赛

复赛再考虑真实 Memory Provider / Skill 适配：

1. 将当前 CLI 包装成 Hermes 风格工具 schema。
2. 增加 `prefetch(query)`：在 Agent 回答前自动召回企业记忆。
3. 增加 `sync_turn(user, assistant)`：把重要 Agent 工作结果写入候选记忆。
4. 保持“先预览，再确认”的写入门控，避免 Agent 自动污染团队记忆。

## 4. 禁止事项

- 不提交 `.reference/hermes-agent/`。
- 不复制大段 Hermes 源码进本项目。
- 不把 Hermes 的多平台 gateway 当作初赛目标。
- 不让 Hermes 适配阻塞飞书 Bot、Benchmark、白皮书三大交付物。
- 不把外部 Agent 的个人记忆和团队企业记忆混为一谈。
