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
## 当前项目主线：从 CLI-first / Bot-first memory demo 切换为 OpenClaw-native Feishu Memory Copilot。OpenClaw Agent 是主入口和工具编排层，Cognee 是开源知识/记忆引擎核心，Memory Copilot Core 是企业记忆治理层，Feishu / lark-cli / Feishu OpenAPI 是办公数据和动作集成层，Bitable / card 是展示和交互层。
## 当前执行周期：2026-04-26 至 2026-05-02 完成 MVP 可演示闭环；2026-05-03 至 2026-05-07 完成 Benchmark、Demo、白皮书、答辩材料和初赛提交缓冲。
## 初赛优先级最高：先保证《Memory 定义与架构白皮书》、可运行 Demo、自证 Benchmark Report 三大交付物闭环，再做复赛加分项。
## 每日任务应按新主控计划拆分为：用户白天主线任务、队友晚上补位任务、范围边界、验收标准、以绝对日期命名的 implementation-plan 文档。不要再新增 `day1`、`day2` 这种日期不明确的主线计划文件。
## 如果当天 `docs/plans/YYYY-MM-DD-implementation-plan.md` 不存在，先根据新主控计划创建该日期计划，再开始代码实现。

# 每日任务上下文读取规则
## 执行某个日期任务时默认读取：`AGENTS.md`、`docs/feishu-memory-copilot-implementation-plan.md`、`docs/plans/YYYY-MM-DD-implementation-plan.md`。
## 如果存在上一日 handoff 或执行记录，再读取对应绝对日期文件；不要默认读取所有旧 day 文档。
## `docs/archive/legacy-day-docs/` 里的旧 day 文档只作为 reference / fallback。只有当新主控计划明确依赖旧能力时，才按需读取对应归档文档。
## 当前代码库是事实源；历史文档只作为背景、验收标准和风险参考。如果历史文档与代码不一致，以代码和最新 implementation plan 为准。
## 相关历史读取示例：改 Feishu card 时可按需读 `docs/archive/legacy-day-docs/day6-handoff.md`；做 Benchmark 时可按需读 `docs/archive/legacy-day-docs/day7-implementation-plan.md`；做 Bitable 时可按需读 `docs/reference/bitable-ledger-views.md`。

# Copilot-first 开发边界
## 新功能优先进入 `memory_engine/copilot/` 和 `agent_adapters/openclaw/`；不要从大改 `memory_engine/repository.py`、`memory_engine/feishu_runtime.py` 或旧 CLI 命令开始。
## OpenClaw tools schema 先行：先冻结 `agent_adapters/openclaw/memory_tools.schema.json`，再实现 `memory_engine/copilot/schemas.py`、`tools.py`、`service.py`。
## 正式写代码前的技术调研结论必须落到 `docs/feishu-memory-copilot-implementation-plan.md` 和后续 `docs/plans/YYYY-MM-DD-implementation-plan.md`，不能只留在聊天记录里；调研结论进入计划后，后续按计划执行并用代码状态校准。
## Cognee 是当前选定的 memory 系统核心：优先复用其本地知识/记忆引擎能力和 `remember / recall / improve / forget`、低层 `add / cognify / search` 流程；不要改成 Mem0、Graphiti、MemOS、Letta、Zep 或 TiMem，除非用户明确重新做选型。
## Cognee 接入优先走本地 Python SDK spike 和窄 adapter；MVP 第一阶段不要先起 Cognee server / Docker，不要让业务代码到处直接 `import cognee`。
## Memory Copilot Core 负责企业记忆治理；candidate / active / superseded / rejected / stale / archived 状态机、证据链、版本解释、权限门控、OpenClaw tools、Feishu card 和 Benchmark 仍由本项目实现，不能交给 Cognee 或任何外部 API 黑盒。
## CLI、Feishu Bot、Benchmark、Bitable、lark-cli 都是入口或展示/验证层，后续应调用同一套 Copilot Core。
## 旧 Day1-Day7 实现只能作为 reference / fallback。复用旧能力时通过 adapter 或 service 层包起来，不把新业务逻辑继续塞进旧 handler。
## 默认不向量化全部 raw events；embedding 只针对 curated memory 的 subject、current_value、summary 和 evidence quote。
## Heartbeat 主动提醒进入 MVP，但先做 reminder candidate + card/dry-run，不做复杂个性化推送。

# OpenClaw 版本锁定
## 本项目 OpenClaw 开发版本固定为 `2026.4.24`（本机 `openclaw --version` 显示 `OpenClaw 2026.4.24 (cbcfdf6)`）。
## 版本锁文件是 `agent_adapters/openclaw/openclaw-version.lock`；后续 OpenClaw adapter、tool schema、skill、demo flow 和 runtime 联调都必须基于该版本。
## 不要运行 `openclaw update`、`npm update -g openclaw`、`npm install -g openclaw@latest`，也不要切换 stable / beta / dev channel，除非用户明确要求重新升级并重新锁定版本。
## 如果本机版本漂移或需要重装，只允许使用 exact version：`npm i -g openclaw@2026.4.24 --no-fund --no-audit`。
## 每次开始 OpenClaw 相关开发或验收前，运行 `python3 scripts/check_openclaw_version.py`，确认当前 CLI 版本与锁文件一致。

# 依赖安装与版本锁定
## 如果执行计划需要的 CLI、SDK、插件或 Python/npm 依赖尚未安装，可以直接安装，不要停下来让用户手动处理。
## 安装任何新依赖后，必须立即锁定 exact version，并把版本写入项目内可追踪文件，例如 lock 文件、requirements/pyproject、package lock、脚本校验文件、AGENTS.md 或当日 implementation plan；不要只留在聊天记录里。
## 新安装的依赖默认禁止自动升级：不要使用 latest、beta、dev channel、floating range 或自动更新命令；如工具支持 auto-update 开关，安装后必须关闭自动更新或在项目脚本/环境说明中固定禁用方式。
## 后续恢复、重装或 CI/本机验收只允许使用已锁定版本；除非用户明确要求升级，否则不要主动更新已锁定依赖。
## 如果某个工具无法锁 exact version，必须在当日计划或 commit message 的 `Not-tested:` / `Constraint:` 中写清原因、当前版本、安装命令和风险。

# 本地模型与 Ollama 清理规则
## Cognee / embedding 测试使用的本地模型必须按项目锁定文件执行；当前默认模型见 `memory_engine/copilot/embedding-provider.lock`。
## 每次运行 `scripts/check_embedding_provider.py`、`scripts/spike_cognee_local.py` 或任何会拉起 Ollama embedding 的验证后，必须执行 `ollama ps` 检查是否仍有本项目模型驻留。
## 如果 `ollama ps` 显示 `qwen3-embedding:0.6b-fp16`、`bge-m3:567m` 或其他本项目测试拉起的模型仍在运行，验证结束后必须执行 `ollama stop <model>` 关闭，避免持续占用 Mac mini GPU/内存。
## 只关闭本项目测试拉起或明确由本项目使用的 Ollama 模型；不要误停用户或队友正在运行的无关模型。
## 最终回复的验证结果里要写清 Ollama 清理状态，例如：`ollama ps` 已确认无本项目模型驻留，或说明仍保留运行的具体原因。

# 队友可读文档写作规则
## 日期 implementation plan、handoff、队友任务和看板备注必须用浅显中文；先讲要做什么，再讲为什么，不要先堆技术名词。
## 每份日期计划或 handoff 必须包含“给队友先看这个”小节，用 3-5 条说明：今天做了什么、队友今晚从哪里开始、要交付什么、怎么判断做对、遇到问题发什么给我。
## 队友任务最多 5 条，每条都要有明确动作、文件/页面位置和完成标准；不要只写“检查/优化/研究”，必须写清检查什么、改哪里、什么算通过。
## 技术词第一次出现要顺手解释，例如：Benchmark（评测脚本）、candidate（待确认记忆）、Recall@3（前三条结果里能找到正确答案）。
## 给队友看的段落避免使用 P0/P1、FTS5、MRR、provider、gateway 等缩写；必须使用时加一句白话解释。
## 如果某件事不用队友做，直接写“今晚不用做”，避免他误以为要处理代码、权限或线上配置。

# 执行规则
## 本地已经安装了 lark-cli (https://github.com/larksuite/cli), 可以直接使用 `lark-cli` 命令，这是最重要的工具！！！！
## 飞书 openclaw 插件 （https://github.com/larksuite/openclaw-lark），如果需要的话可以直接安装并使用！！！！
## 在执行每次对话前，必须先确认当前日期和阶段任务安排，确保执行内容与 `docs/feishu-memory-copilot-implementation-plan.md` 和 `docs/plans/YYYY-MM-DD-implementation-plan.md` 一致。

## 飞书共享任务看板同步规则
### 项目任务同步看板是 `https://jcneyh7qlo8i.feishu.cn/wiki/DlikwJHLGi2MjdkaC5LcZeIznAe?from=from_copylink`，标题为“飞书挑战赛任务跟进看板”，用于同步程俊豪与赵阳的项目进度和任务指派。
### 每次开始新阶段、完成当日闭环、更新日期计划、更新 handoff、或用户要求同步进度时，必须先读取 `docs/feishu-memory-copilot-implementation-plan.md`、当前绝对日期 implementation-plan、上一日 handoff/执行记录和当前代码状态，再更新该看板。
### 该链接是 Wiki 包装的 Sheets 页面，且页面内嵌 Bitable block。操作流程必须是：先用 `lark-cli wiki spaces get_node --params '{"token":"DlikwJHLGi2MjdkaC5LcZeIznAe"}'` 解析真实 `obj_token`；再用 `lark-cli api GET /open-apis/sheets/v2/spreadsheets/<spreadsheet_token>/metainfo` 读取 `blockInfo.blockToken`；将 `blockToken` 按 `_` 拆成 `app_token` 和 `table_id`；最后用 `lark-cli base +...` 操作记录。
### 不要直接用 `lark-cli sheets +read/+write` 修改该看板的数据区；这个页面的数据区是 Bitable block，Sheets 单元格 API 可能返回 `not found sheetId`。
### 看板字段语义固定：`任务描述` 写清 `YYYY-MM-DD`、负责人和交付物；`状态` 只用 `待启动`、`进行中`、`已完成`、`延期`、`暂停`；`优先级` 只用 `P0/P1/P2`；`指派给` 必须使用飞书人员字段；`任务截止日期` 使用绝对日期；`备注` 写验收证据、文档路径或剩余风险。
### 程俊豪任务更新规则：已按代码、文档和验证证据完成的任务，设置 `完成情况-程俊豪=true` 且 `状态=已完成`，这样会进入看板的已完成分组；未完成任务只指派、填截止日期和 P0/P1，不提前勾选。
### 赵阳任务更新规则：只分配明确、可独立执行的晚上补位任务，设置 `指派给=赵阳`、优先级、截止日期和备注；不要替赵阳勾选 `完成情况-赵阳`。赵阳完成后由他自己打勾。
### 同步看板时不得覆盖或改写无关历史记录；阶段任务应优先追加为新记录，只有精确匹配同一绝对日期/负责人/任务描述的记录时才更新该记录。
### 每次同步后必须用 `lark-cli base +record-list` 读回确认：程俊豪已完成项已勾选且状态为已完成；赵阳新任务未被代勾；任务数量、负责人和截止日期与新主控文档/最新日期计划一致。

## 飞书 Bot 测试约定（legacy fallback）
### 新主线的主入口是 OpenClaw Agent；当前飞书 Bot 是旧实现的可复现测试面和 fallback，不得把 Bot handler 当作新 Copilot 主架构。
### 本项目机器人在飞书里的显示名仍是 `Feishu Memory Engine bot`，真实群聊测试旧 Bot 路径时继续使用这个名字，例如：
```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
```
### 单聊旧 Bot 时可以省略 @ 名称，直接发送 `/remember`、`/recall` 或 `/versions`。
### 启动监听测试程序时默认写入 `logs/feishu-bot/feishu-listen-<timestamp>.ndjson`；每条日志必须包含 `ts` 时间戳，便于复盘真实飞书测试群里的消息、卡片点击、fallback 和异常行为。
### `logs/` 是本地运行证据目录，已被 `.gitignore` 忽略；不要把真实监听日志、群聊 ID、用户 ID 或 token 提交到仓库。

## 版本维护与推送规则
### 每完成一个可运行闭环、阶段交付或关键文档更新后，必须执行本地验证、提交并推送到远程仓库。
### 提交前必须检查 `git status --short`，确认 `.env`、`.omx/`、数据库文件、缓存文件和临时报告不会进入提交。
### 提交前基础验证
### 每次关键文档、代码或配置变更提交前至少运行：
```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```
### 这三条分别验证 OpenClaw 版本锁、Python 语法/导入基线、旧本地 memory 闭环回归；`day1_cases.json` 仍是保底基线，但不再代表新 Copilot PRD 的全部验收。
### Cognee / Copilot 新主线相关变更，按触达范围追加专项验证；对应测试或 benchmark 文件尚未创建时，在 commit message 的 `Not-tested:` 中说明缺口，不要假装已覆盖：
```bash
# OpenClaw schema、工具 handler、Cognee adapter、Copilot schema
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools

# retrieval、Cognee recall/search adapter、L0-L3 分层召回
python3 -m unittest tests.test_copilot_retrieval
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json

# candidate、confirm/reject、conflict update、version chain、stale leakage
python3 -m unittest tests.test_copilot_governance
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json

# prefetch、heartbeat reminder、敏感信息门控
python3 -m unittest tests.test_copilot_prefetch tests.test_copilot_heartbeat
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```
### 阶段闭环、提交材料、白皮书或 Demo freeze 前，使用主控计划中的最终验收命令：`python3 -m unittest discover tests`，再跑 `day1_cases`、`day7_anti_interference` 和所有已存在的 `copilot_*_cases.json`。
### 只提交与当前任务相关的文件；不要回退或覆盖他人已有改动。
### `AGENTS.md` 是项目执行契约，必须进入版本控制；如果被 ignore 规则影响，使用 `git add -f AGENTS.md` 明确纳入本次提交。
### commit message 采用“为什么做这次变更”作为首行，并在正文中记录验证情况，例如：
```text
Keep verification aligned with the Cognee-backed Copilot core

Updated the repo execution contract so commits still keep the old local memory baseline, while Cognee/Copilot changes add scope-specific schema, retrieval, governance, prefetch, heartbeat, and benchmark checks.

Tested: python3 scripts/check_openclaw_version.py
Tested: python3 -m compileall memory_engine scripts
Tested: python3 -m memory_engine benchmark run benchmarks/day1_cases.json
Not-tested: copilot_* benchmark files not created yet
```
### 提交后推送当前分支到 `origin`：
```bash
git push origin HEAD
```
### 如果推送失败，先读取错误信息并处理可恢复问题；不要使用 destructive git 命令。
