# 飞书文档参考
## 开发指南 https://open.feishu.cn/document/client-docs/intro
## 开发教程 https://open.feishu.cn/document/course
## 服务端api https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/AI-assistant-code-generation-guide
## 客户端 api https://open.feishu.cn/document/client-docs/h5/
## 飞书 cli https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu
## 飞书 openclaw 官方插件 https://bytedance.larkoffice.com/docx/MFK7dDFLFoVlOGxWCv5cTXKmnMh

# 总控计划入口
## 比赛总控执行文档是 `docs/competition-master-execution-plan.md`。
## 后续每个新对话、新阶段任务或每日开发任务，必须先读取并遵循该文档中的当前日期/阶段安排，再结合用户最新指令执行。
## 当前项目基线：Day 1 本地 Memory Engine、Day 2 飞书 Bot、Day 3 Bot 稳定化、Day 4 Bitable 看板、Day 5 文档 ingestion 已完成或已提前验收；后续优先从总控文档的 D6 及之后任务推进。
## 初赛优先级最高：先保证《Memory 定义与架构白皮书》、可运行 Demo、自证 Benchmark Report 三大交付物闭环，再做复赛加分项。
## 每日任务应按总控文档拆分为：用户白天主线任务、队友晚上补位任务、P0/P1 范围、验收标准、implementation-plan文档和 handoff 文档。

# 每日任务上下文读取规则
## 执行 D{n} 时默认读取：`AGENTS.md`、`docs/competition-master-execution-plan.md` 的 D{n}、`docs/day{n-1}-handoff.md`、存在时的 `docs/day{n}-implementation-plan.md`。
## 不要默认读取所有旧日期文档。只有当 D{n} 明确依赖更早某天能力时，才按需读取对应 day 的 handoff / implementation-plan。
## 当前代码库是事实源；历史文档只作为背景、验收标准和风险参考。如果历史文档与代码不一致，以代码和最新 handoff 为准。
## 相关历史读取示例：D6 改 Bot 卡片时读 D3；D7-D9 做 Benchmark 时读 D1 和相关 benchmark 文档；D11 做 Agent/OpenClaw/Hermes adapter 时读 Hermes 参考笔记和 CLI 相关代码。

# 执行规则
## 本地已经安装了 lark_cli (https://github.com/larksuite/cli), 可以直接使用 `lark-cli` 命令，这是最重要的工具！！！！
## 飞书 openclaw 插件 （https://github.com/larksuite/openclaw-lark），如果需要的话可以直接安装并使用！！！！
## 在执行每次对话前，必须先确认当前日期和阶段任务安排，确保执行内容与总控计划一致。

## 飞书 Bot 测试约定
### 本项目机器人在飞书里的显示名是 `Feishu Memory Engine bot`。
### 后续所有群聊测试命令都使用这个名字，例如：
```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
```
### 单聊机器人时可以省略 @ 名称，直接发送 `/remember`、`/recall` 或 `/versions`。

## 版本维护与推送规则
### 每完成一个可运行闭环、阶段交付或关键文档更新后，必须执行本地验证、提交并推送到远程仓库。
### 提交前必须检查 `git status --short`，确认 `.env`、`.omx/`、数据库文件、缓存文件和临时报告不会进入提交。
### 代码变更提交前至少运行：
```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```
### 只提交与当前任务相关的文件；不要回退或覆盖他人已有改动。
### commit message 采用“为什么做这次变更”作为首行，并在正文中记录验证情况，例如：
```text
Deliver local Day 1 memory engine loop

Implemented the local remember/recall/conflict/benchmark path so the project has a runnable baseline before Feishu Bot integration.

Tested: python3 -m compileall memory_engine scripts
Tested: python3 -m memory_engine benchmark run benchmarks/day1_cases.json
Not-tested: real Feishu Bot / Bitable integration, planned for Day 2
```
### 提交后推送当前分支到 `origin`：
```bash
git push origin HEAD
```
### 如果推送失败，先读取错误信息并处理可恢复问题；不要使用 destructive git 命令。
