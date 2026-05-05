# Agent 自动部署检查任务单

状态：demo / pre-production 自动检查与隔离部署任务单；不是生产部署 runbook。

用途：让 Agent 在读到 README 里的部署 prompt 后，可以自动判断当前机器是否具备运行 Feishu Memory Copilot 的条件，并在不破坏当前工作区和本机 OpenClaw 配置的前提下完成检查、隔离部署和验收报告。

## 给 Agent 的一行 prompt

请在仓库根目录执行：先读取 `AGENTS.md`、`README.md` 和本文件；默认只做只读检查，不升级 OpenClaw、不安装或启用插件、不启动真实飞书 listener；如需完整部署，请优先使用临时目录或全新 clone 做隔离部署，最后输出已运行命令、通过/失败项、边界声明和下一步人工动作。

## 边界

可以自动声称：

- 本机或隔离 clone 具备 local demo / OpenClaw staging 的运行条件。
- 本地 replay、healthcheck、readiness、harness 检查通过。
- OpenClaw 版本符合锁定版本 `2026.4.24`。

不能自动声称：

- 生产部署完成。
- 全量 Feishu workspace ingestion 已完成。
- 长期真实 Feishu DM / 群聊 / workspace event 稳定路由已完成。
- 长期 embedding / Cognee 服务已上线。

## 默认安全规则

- 不运行 `openclaw update`。
- 不运行 `npm install -g openclaw@latest`。
- 不在当前机器上自动执行 `openclaw plugins install`、`openclaw plugins enable`、`openclaw channels start` 或任何会改变 OpenClaw 配置的命令。
- 不启动 `scripts/start_copilot_feishu_live.sh`，除非用户明确给出受控测试群、reviewer 和单监听授权。
- 不把 `.env`、真实 token、真实 chat id、真实 open id 写入 git。
- 当前工作区只做检查；真正部署优先放在临时目录、全新 clone 或用户指定的干净目录。

## 执行顺序

### 1. 读取事实源

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,260p' README.md
sed -n '1,260p' docs/productization/agent-auto-deploy-checklist.md
sed -n '1,260p' docs/productization/cross-platform-quick-deploy.md
```

### 2. 当前工作区只读检查

这些命令不会安装依赖、不会启用 OpenClaw 插件、不会启动 listener：

```bash
git status --short
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python3 scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
COPILOT_AUTO_INIT_COGNEE=0 python3 scripts/check_demo_readiness.py --json --demo-json-output /tmp/feishu_memory_demo_replay.json
git diff --check
```

如果 `openclaw-staging` 失败，但 `local-demo` 通过，应报告为“本地 demo 可运行，OpenClaw staging 条件未满足”，不要自动改 OpenClaw。

Agent 执行 `check_demo_readiness.py` 时应设置 180 秒超时；如果超时或外部观测 / Cognee SDK 在本机环境里反复报错，应停止该项并报告为“readiness check blocked by local optional dependency”，不要继续启动 listener 或修改 OpenClaw。

### 3. 隔离部署（需要用户允许）

只有用户要求“帮我在新目录完整部署”时，才执行本段。建议使用临时目录或用户指定目录：

```bash
DEPLOY_DIR="$(mktemp -d /tmp/feishu-memory-copilot-deploy.XXXXXX)"
git clone https://github.com/adjcjh777/lark_ai_challenge_openclaw_longterm_memory.git "$DEPLOY_DIR"
cd "$DEPLOY_DIR"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
cp .env.example .env
python -m memory_engine init-db
python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python scripts/check_openclaw_version.py
COPILOT_AUTO_INIT_COGNEE=0 python scripts/check_demo_readiness.py --json --demo-json-output /tmp/feishu_memory_demo_replay.json
```

如果用户明确授权 OpenClaw staging，并且本机 OpenClaw 已经是 `2026.4.24`，可以继续只读验证：

```bash
python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
```

不要自动安装或启用插件。插件安装和启用必须单独向用户确认，因为它会改变本机 OpenClaw 状态。

### 4. OpenClaw plugin 操作（必须人工授权）

只有用户明确说“可以修改本机 OpenClaw 插件状态”时，才执行：

```bash
openclaw plugins install --link --dangerously-force-unsafe-install ./agent_adapters/openclaw/plugin
openclaw plugins enable feishu-memory-copilot
openclaw plugins inspect feishu-memory-copilot --json
python scripts/check_feishu_dm_routing.py --json
```

如果这些命令失败，不要改用 `openclaw update`，也不要安装 latest。先报告失败原因。

### 5. 飞书 sandbox 操作（必须人工授权）

只有用户明确提供受控测试群和 reviewer，并确认当前只启用一个 listener 时，才执行：

```bash
python scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
export LARK_CLI_PROFILE=feishu-ai-challenge
export COPILOT_FEISHU_ALLOWED_CHAT_IDS="<controlled_test_chat_id>"
export COPILOT_FEISHU_REVIEWER_OPEN_IDS="<reviewer_open_id>"
bash scripts/start_copilot_feishu_live.sh
```

如果由 OpenClaw websocket 接管飞书事件，则不要启动本仓库 listener，只做：

```bash
python scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw channels status --probe --json
```

## 验收报告格式

Agent 最后输出：

```text
部署检查结论：
- local-demo: pass/fail
- openclaw-staging: pass/fail/not-run
- demo-readiness: pass/fail
- OpenClaw version: 2026.4.24/pass 或具体失败原因
- 是否修改当前工作区：yes/no，列出文件
- 是否修改本机 OpenClaw 状态：yes/no，列出命令
- 是否启动飞书 listener：yes/no
- 边界：demo/pre-production only，不代表生产部署或长期 live 完成
- 下一步：需要用户授权的动作
```

## 常见处理

| 情况 | Agent 行为 |
|---|---|
| Python 版本低于 3.9 | 停止部署，建议安装 Python 3.11+。 |
| local-demo 通过，openclaw-staging 失败 | 报告 OpenClaw 条件不足，不自动安装或升级。 |
| OpenClaw 不是 `2026.4.24` | 停止 OpenClaw staging，不运行 update，不安装 latest。 |
| `.env` 缺失 | 当前工作区只报告；隔离部署中可以从 `.env.example` 创建。 |
| demo readiness 写报告 | 默认写到 `/tmp/feishu_memory_demo_replay.json`，不要污染当前仓库。 |
| 需要真实飞书联调 | 先确认单 listener、受控群、reviewer 和 no-overclaim 边界。 |
