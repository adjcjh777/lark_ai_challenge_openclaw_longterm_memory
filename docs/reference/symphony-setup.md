# Symphony Setup

日期：2026-04-29  
范围：把 OpenAI Symphony Elixir prototype 接到本仓库，用 Linear issue 驱动 Codex app-server 在隔离 workspace 中执行任务。

官方参考：

- https://github.com/openai/symphony/blob/main/elixir/README.md
- https://github.com/openai/symphony/blob/main/SPEC.md

## 1. 当前接入方式

本仓库不 vendoring Symphony 源码。`WORKFLOW.md` 是 repo-owned policy contract；Symphony runtime 仍从 `openai/symphony` 单独 clone 后运行。

已落地文件：

```text
WORKFLOW.md
scripts/check_symphony_setup.py
tests/test_symphony_setup.py
docs/reference/symphony-setup.md
.env.example
```

`WORKFLOW.md` 会让 Symphony：

1. 从 Linear 轮询候选 issue。
2. 为每个 issue 创建独立 workspace。
3. 在 workspace 中 clone 本仓库。
4. 安装 Python dev 依赖。
5. 运行 `check_openclaw_version` 和 `check_agent_harness`。
6. 启动 `codex app-server`。
7. 把 issue 内容、仓库规则、验证门和 Linear 状态流转规则传给 Codex。

## 2. 本地环境变量

复制 `.env.example` 到 `.env` 后补齐：

```bash
LINEAR_API_KEY=lin_api_xxx
SYMPHONY_LINEAR_PROJECT_SLUG=feishu-ai-challenge-785b3bb0a19d
SYMPHONY_WORKSPACE_ROOT=/Users/junhaocheng/.symphony/workspaces/feishu_ai_challenge
SOURCE_REPO_URL=https://github.com/adjcjh777/lark_ai_challenge_openclaw_longterm_memory.git
CODEX_BIN=codex
```

Linear project slug 获取方式：在 Linear 项目页右键复制项目 URL，URL 里项目部分就是 slug。本项目当前 slug 是 `feishu-ai-challenge-785b3bb0a19d`，来自：

```text
https://linear.app/feishu-ai-challenge/project/feishu-ai-challenge-785b3bb0a19d/overview
```

当前 OpenAI Symphony Elixir build 启动时会把 `tracker.project_slug` 里的 `$SYMPHONY_LINEAR_PROJECT_SLUG` 当成字面量读取，所以 `WORKFLOW.md` 已固定使用：

```yaml
project_slug: feishu-ai-challenge-785b3bb0a19d
```

`.env` 里的 `SYMPHONY_LINEAR_PROJECT_SLUG` 仍保留为人工参考。官方 README 说明 Symphony 示例依赖 `Rework`、`Human Review`、`Merging` 这类非标准状态；如果你的 Linear workflow 没有这些状态，要先在 Team Settings -> Workflow 中创建，或同步修改 `WORKFLOW.md`。

## 3. 安装 Symphony runtime

官方推荐使用 `mise` 管理 Elixir/Erlang 版本：

```bash
brew install mise
git clone https://github.com/openai/symphony /Users/junhaocheng/.symphony/src/openai-symphony
cd /Users/junhaocheng/.symphony/src/openai-symphony/elixir
mise trust
mise install
mise exec -- mix setup
mise exec -- mix build
```

如果 `mise install` 要求安装 Erlang/Elixir，按提示执行。不要把 Symphony runtime clone 到本仓库里；workspace 和 logs 目录应放在 `.symphony/` 或其他本地未跟踪目录。

## 4. 启动服务

在一个终端加载环境变量：

```bash
set -a
source /Users/junhaocheng/feishu_ai_challenge/.env
set +a
```

启动 Symphony：

```bash
cd /Users/junhaocheng/.symphony/src/openai-symphony/elixir
mise exec -- ./bin/symphony /Users/junhaocheng/feishu_ai_challenge/WORKFLOW.md \
  --logs-root /Users/junhaocheng/.symphony/logs/feishu_ai_challenge \
  --port 4040 \
  --i-understand-that-this-will-be-running-without-the-usual-guardrails
```

打开 dashboard：

```text
http://localhost:4040
```

如果不需要 dashboard，可以去掉 `--port 4040`。

## 5. 启动前检查

在本仓库先跑：

```bash
python3 scripts/check_symphony_setup.py
python3 -m unittest tests.test_symphony_setup
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

在 Symphony runtime 目录先跑：

```bash
cd /Users/junhaocheng/.symphony/src/openai-symphony/elixir
mise exec -- mix test
```

官方 `make e2e` 会创建临时 Linear 资源并启动真实 `codex app-server`，只在你明确想做外部 E2E 时运行。

## 6. 当前边界

- 这只是把 Symphony 接入本仓库的 orchestration harness，不代表生产部署完成。
- 这不改变 Feishu Memory Copilot 的主线架构。
- 这不替代飞书看板；Linear 只是 Symphony 的 issue tracker 输入。
- 真实 Feishu 来源仍 candidate-only，不自动 active。
- 真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` 工具的 live E2E 证据仍未完成。

## 7. 后续可选项

官方 README 提到可以复制 `commit`、`push`、`pull`、`land`、`linear` skills 到 repo。本次没有复制这些 skills；当前 `WORKFLOW.md` 用文字规则约束 Codex。如果后续要让 Symphony 更稳定地处理 PR、Linear workpad 和 merge flow，再把这些 skills 作为单独任务接入。
