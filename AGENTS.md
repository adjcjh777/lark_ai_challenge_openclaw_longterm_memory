# 飞书文档参考
## 开发指南 https://open.feishu.cn/document/client-docs/intro
## 开发教程 https://open.feishu.cn/document/course
## 服务端api https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/AI-assistant-code-generation-guide
## 客户端 api https://open.feishu.cn/document/client-docs/h5/
## 飞书 cli https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu
## 飞书 openclaw 官方插件 https://bytedance.larkoffice.com/docx/MFK7dDFLFoVlOGxWCv5cTXKmnMh

# 主控计划入口
## 新的项目主控执行文档是 `docs/feishu-memory-copilot-implementation-plan.md`。
## 后续每个新对话、新阶段任务或每日开发任务，必须先读取并遵循该 implementation plan 中的当前日期/阶段安排，再结合用户最新指令执行。
## 旧主控文档 `docs/archive/legacy-master/competition-master-execution-plan.md` 已降级为归档参考；不要再把它作为默认执行入口。
## 当前项目主线：从 CLI-first / Bot-first memory demo 切换为 OpenClaw-native Feishu Memory Copilot。OpenClaw Agent 是主入口和工具编排层，Memory Copilot Core 是长期记忆大脑，Feishu / lark-cli / Feishu OpenAPI 是办公数据和动作集成层，Bitable / card 是展示和交互层。
## 当前执行周期：2026-04-26 至 2026-05-02 完成 MVP 可演示闭环；2026-05-03 至 2026-05-07 完成 Benchmark、Demo、白皮书、答辩材料和初赛提交缓冲。
## 初赛优先级最高：先保证《Memory 定义与架构白皮书》、可运行 Demo、自证 Benchmark Report 三大交付物闭环，再做复赛加分项。
## 每日任务应按新主控计划拆分为：用户白天主线任务、队友晚上补位任务、范围边界、验收标准、以绝对日期命名的 implementation-plan 文档。不要再新增 `day1`、`day2` 这种日期不明确的主线计划文件。

# 每日任务上下文读取规则
## 执行某个日期任务时默认读取：`AGENTS.md`、`docs/feishu-memory-copilot-implementation-plan.md`、`docs/plans/YYYY-MM-DD-implementation-plan.md`。
## 如果存在上一日 handoff 或执行记录，再读取对应绝对日期文件；不要默认读取所有旧 day 文档。
## `docs/archive/legacy-day-docs/` 里的旧 day 文档只作为 reference / fallback。只有当新主控计划明确依赖旧能力时，才按需读取对应归档文档。
## 当前代码库是事实源；历史文档只作为背景、验收标准和风险参考。如果历史文档与代码不一致，以代码和最新 implementation plan 为准。
## 相关历史读取示例：改 Feishu card 时可按需读 `docs/archive/legacy-day-docs/day6-handoff.md`；做 Benchmark 时可按需读 `docs/archive/legacy-day-docs/day7-implementation-plan.md`；做 Bitable 时可按需读 `docs/reference/bitable-ledger-views.md`。

# 队友可读文档写作规则
## handoff、队友任务和看板备注必须用浅显中文；先讲要做什么，再讲为什么，不要先堆技术名词。
## 每份 handoff 必须包含“给队友先看这个”小节，用 3-5 条说明：今天做了什么、队友今晚从哪里开始、要交付什么、怎么判断做对、遇到问题发什么给我。
## 队友任务最多 5 条，每条都要有明确动作、文件/页面位置和完成标准；不要只写“检查/优化/研究”，必须写清检查什么、改哪里、什么算通过。
## 技术词第一次出现要顺手解释，例如：Benchmark（评测脚本）、candidate（待确认记忆）、Recall@3（前三条结果里能找到正确答案）。
## 给队友看的段落避免使用 P0/P1、FTS5、MRR、provider、gateway 等缩写；必须使用时加一句白话解释。
## 如果某件事不用队友做，直接写“今晚不用做”，避免他误以为要处理代码、权限或线上配置。

# 执行规则
## 本地已经安装了 lark_cli (https://github.com/larksuite/cli), 可以直接使用 `lark-cli` 命令，这是最重要的工具！！！！
## 飞书 openclaw 插件 （https://github.com/larksuite/openclaw-lark），如果需要的话可以直接安装并使用！！！！
## 在执行每次对话前，必须先确认当前日期和阶段任务安排，确保执行内容与 `docs/feishu-memory-copilot-implementation-plan.md` 和 `docs/plans/YYYY-MM-DD-implementation-plan.md` 一致。

## 飞书共享任务看板同步规则
### 项目任务同步看板是 `https://jcneyh7qlo8i.feishu.cn/wiki/DlikwJHLGi2MjdkaC5LcZeIznAe?from=from_copylink`，标题为“飞书挑战赛任务跟进看板”，用于同步程俊豪与赵阳的项目进度和任务指派。
### 每次开始新阶段、完成当日闭环、更新 handoff、或用户要求同步进度时，必须先读取 `docs/feishu-memory-copilot-implementation-plan.md`、当前绝对日期 implementation-plan、上一日 handoff/执行记录和当前代码状态，再更新该看板。
### 该链接是 Wiki 包装的 Sheets 页面，且页面内嵌 Bitable block。操作流程必须是：先用 `lark-cli wiki spaces get_node --params '{"token":"DlikwJHLGi2MjdkaC5LcZeIznAe"}'` 解析真实 `obj_token`；再用 `lark-cli api GET /open-apis/sheets/v2/spreadsheets/<spreadsheet_token>/metainfo` 读取 `blockInfo.blockToken`；将 `blockToken` 按 `_` 拆成 `app_token` 和 `table_id`；最后用 `lark-cli base +...` 操作记录。
### 不要直接用 `lark-cli sheets +read/+write` 修改该看板的数据区；这个页面的数据区是 Bitable block，Sheets 单元格 API 可能返回 `not found sheetId`。
### 看板字段语义固定：`任务描述` 写清 `YYYY-MM-DD`、负责人和交付物；`状态` 只用 `待启动`、`进行中`、`已完成`、`延期`、`暂停`；`优先级` 只用 `P0/P1/P2`；`指派给` 必须使用飞书人员字段；`任务截止日期` 使用绝对日期；`备注` 写验收证据、文档路径或剩余风险。
### 程俊豪任务更新规则：已按代码、文档和验证证据完成的任务，设置 `完成情况-程俊豪=true` 且 `状态=已完成`，这样会进入看板的已完成分组；未完成任务只指派、填截止日期和 P0/P1，不提前勾选。
### 赵阳任务更新规则：只分配明确、可独立执行的晚上补位任务，设置 `指派给=赵阳`、优先级、截止日期和备注；不要替赵阳勾选 `完成情况-赵阳`。赵阳完成后由他自己打勾。
### 同步看板时不得覆盖或改写无关历史记录；阶段任务应优先追加为新记录，只有精确匹配同一绝对日期/负责人/任务描述的记录时才更新该记录。
### 每次同步后必须用 `lark-cli base +record-list` 读回确认：程俊豪已完成项已勾选且状态为已完成；赵阳新任务未被代勾；任务数量、负责人和截止日期与新主控文档/最新日期计划一致。

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
### 启动监听测试程序时默认写入 `logs/feishu-bot/feishu-listen-<timestamp>.ndjson`；每条日志必须包含 `ts` 时间戳，便于复盘真实飞书测试群里的消息、卡片点击、fallback 和异常行为。
### `logs/` 是本地运行证据目录，已被 `.gitignore` 忽略；不要把真实监听日志、群聊 ID、用户 ID 或 token 提交到仓库。

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
