# lark_ai_challenge_openclaw_longterm_memory
飞书AI挑战赛-Openclaw企业级长程记忆方向

## Day 1 本地闭环

本仓库当前实现 `remember -> recall -> conflict update -> benchmark stub` 的本地最小闭环。Day 1 不接真实飞书 Bot、Bitable 写入、H5、embedding 或 OpenClaw 深度集成。

初始化 SQLite：

```bash
python3 -m memory_engine init-db
```

写入和召回：

```bash
python3 -m memory_engine remember --scope project:feishu_ai_challenge "生产部署必须加 --canary --region cn-shanghai"
python3 -m memory_engine recall --scope project:feishu_ai_challenge "生产部署参数"
python3 -m memory_engine remember --scope project:feishu_ai_challenge "不对，生产部署 region 改成 ap-shanghai"
python3 -m memory_engine recall --scope project:feishu_ai_challenge "生产部署 region"
```

运行 Day 1 benchmark：

```bash
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

默认数据库路径是 `data/memory.sqlite`，可用 `MEMORY_DB_PATH` 覆盖。仓库已忽略 `.env`、`.omx/` 和 `data/*.sqlite`。

如需安装为 `memory` 命令：

```bash
python3 -m pip install -e .
memory benchmark run benchmarks/day1_cases.json
```

## Day 2 飞书 Bot 最小闭环

本机已安装 `lark-cli`，Day 2 的真实事件监听和消息回复优先使用 `lark-cli`：

```bash
lark-cli --version
```

Day 2 最小 Bot 权限：

- `im:message.group_at_msg:readonly`
- `im:message.p2p_msg:readonly`
- `im:message:send_as_bot`

环境变量：

```bash
MEMORY_DB_PATH=data/memory.sqlite
MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge
FEISHU_BOT_MODE=reply
```

如果使用指定 lark-cli profile，可额外设置：

```bash
LARK_CLI_PROFILE=your_profile
```

本地 replay 不需要飞书凭证：

```bash
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

真实长连接监听使用 `lark-cli event +subscribe`：

```bash
scripts/start_feishu_bot.sh
```

调试时不真实回复飞书：

```bash
scripts/start_feishu_bot.sh --dry-run
```

Demo 输入：

```text
/remember 生产部署必须加 --canary --region cn-shanghai
/recall 生产部署参数
/remember 不对，生产部署 region 改成 ap-shanghai
/recall 生产部署 region
```

## Day 3 真实 Bot 稳定化

Day 3 增加稳定中文回复格式和 Demo 命令：

- `/help`：展示可用命令、参数示例和 Demo 推荐输入。
- `/health`：展示数据库路径、默认 scope、dry-run 状态和回复模式。
- `/remember`、`/recall`、`/versions` 回复统一包含：类型、主题、状态、版本、来源。
- 非文本、空消息、机器人自发消息、重复消息、未知命令都有明确处理。

真实测试群配置：

- 群名：内部测试群，真实名称不提交到公开仓库。
- `chat_id`：使用本地环境变量 `FEISHU_TEST_CHAT_ID`，真实值不提交。
- 群聊中请使用 `@Feishu Memory Engine bot /help` 这类 @Bot 命令；单聊可省略 @。

本地 Day 3 验证：

```bash
python3 -m unittest discover -s tests
rm -f /tmp/feishu_d3_replay.sqlite
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_help_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_health_event.json
```

## Day 4 Bitable 记忆台账

Day 4 增加 SQLite 到飞书多维表格的最小同步脚本。默认是本地 dry-run，不需要 Bitable 权限，也不会影响本地 `remember` / `recall` 核心能力。

查看表结构：

```bash
python3 -m memory_engine bitable schema
```

预览同步内容和将要执行的 `lark-cli` 命令：

```bash
python3 -m memory_engine bitable sync --benchmark-cases benchmarks/day1_cases.json
```

生成 Day 4 评委看板样例数据：

```bash
python3 scripts/seed_day4_demo_data.py --scope project:day4_demo
python3 -m memory_engine bitable sync --scope project:day4_demo --benchmark-cases benchmarks/day1_cases.json
```

有 Base 权限后写入真实 Bitable：

```bash
export BITABLE_BASE_TOKEN="app_xxx"
export BITABLE_LEDGER_TABLE="Memory Ledger"
export BITABLE_VERSIONS_TABLE="Memory Versions"
export BITABLE_BENCHMARK_TABLE="Benchmark Results"
export LARK_CLI_PROFILE="feishu-ai-challenge"
export LARK_CLI_AS="user"

python3 -m memory_engine bitable sync --write --benchmark-cases benchmarks/day1_cases.json
```

建表命令预览：

```bash
python3 -m memory_engine bitable setup-commands --base-token "$BITABLE_BASE_TOKEN" --profile feishu-ai-challenge --as-identity user
```

视图建议见 [Bitable 记忆台账与评委视图建议](docs/bitable-ledger-views.md)。

## 文档

- [比赛总控执行文档](docs/competition-master-execution-plan.md)
- [飞书 Memory Engine 调研与项目规划](docs/feishu-memory-engine-research-and-plan.md)
- [Hermes Agent 参考笔记](docs/hermes-agent-reference-notes.md)
- [Day 1 执行文档](docs/day1-execution-plan.md)
- [Day 1 Handoff](docs/day1-handoff.md)
- [Day 2 实现计划](docs/day2-implementation-plan.md)
- [Day 2 Handoff](docs/day2-handoff.md)
- [Day 3 实现计划](docs/day3-implementation-plan.md)
- [Day 3 Handoff](docs/day3-handoff.md)
- [Day 4 实现计划](docs/day4-implementation-plan.md)
- [Day 4 Handoff](docs/day4-handoff.md)
- [Day 3 安全风险决策](docs/day3-security-risk-decision.md)
- [Bitable 记忆台账与评委视图建议](docs/bitable-ledger-views.md)
- [Day 4 Bitable Demo 讲解词](docs/day4-bitable-demo-talk-track.md)
- [真实飞书 Demo Runbook](docs/demo-runbook.md)
- [队友 lark-cli 配置与 Day 2 测试指南](docs/teammate-lark-cli-setup.md)
- [项目原型图 Mermaid 源码](docs/diagrams/README.md)
