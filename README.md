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

## Day 2 飞书准备项

本机已安装 `lark-cli`，应优先作为 Day 2 飞书能力入口：

```bash
lark-cli --version
```

Day 2 最小 Bot 权限：

- `im:message.group_at_msg:readonly`
- `im:message.p2p_msg:readonly`
- `im:message:send_as_bot`

环境变量：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
MEMORY_DB_PATH=data/memory.sqlite
```

## 文档

- [飞书 Memory Engine 调研与项目规划](docs/feishu-memory-engine-research-and-plan.md)
- [Day 1 执行文档](docs/day1-execution-plan.md)
- [Day 1 Handoff](docs/day1-handoff.md)
- [Day 2 实现计划](docs/day2-implementation-plan.md)
- [项目原型图 Mermaid 源码](docs/diagrams/README.md)
