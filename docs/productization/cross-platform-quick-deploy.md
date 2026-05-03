# Cross-platform Quick Deploy Runbook

日期：2026-05-03  
状态：demo / pre-production 快速部署入口；不是生产部署 runbook。

## 先看这个

这个文档解决一个具体问题：队友在另一台 **macOS / Linux / Windows** 机器上拿到仓库后，能否快速把 Feishu Memory Copilot 跑到本地 demo / pre-production 验收状态。

本 runbook 的完成标准是：

- 新机器能创建 Python 虚拟环境并安装本项目。
- 能初始化本地 SQLite demo/staging 数据库。
- 能跑 `check_cross_platform_quick_deploy.py`、`check_openclaw_version.py` 和 `check_demo_readiness.py`。
- 如果要验证 OpenClaw 主路径，OpenClaw 必须是锁定版本 `2026.4.24`。

它不能证明：

- 生产部署已完成。
- 全量接入 Feishu workspace。
- 真实 Feishu DM 长期稳定路由到本项目 `fmc_*` 工具。
- 长期 embedding / Cognee 服务已上线。
- productized live 长期运行已完成。

## 部署档位

| 档位 | 适用场景 | 必需条件 | 验证命令 |
|---|---|---|---|
| A. Local demo | 新机器最快本地复现、评委/队友自测 | Python、Git、SQLite stdlib | `python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json` |
| B. OpenClaw staging | 验证 OpenClaw-native 主路径和插件运行条件 | A + Node.js/npm + OpenClaw `2026.4.24` | `python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json` |
| C. Embedding staging | 验证真实 embedding provider 本地条件 | B + Ollama + embedding model | `python scripts/check_cross_platform_quick_deploy.py --profile embedding --json` |

建议默认先做到 **A**，再按机器权限和网络情况推进 **B/C**。

## 通用前置条件

| 组件 | 版本/要求 | 说明 |
|---|---|---|
| Python | 3.11+ 推荐；`pyproject.toml` 允许 3.9+ | 快速部署统一推荐 3.11，减少 Cognee / 本地依赖差异 |
| Git | 任意当前版本 | 克隆和更新仓库 |
| Node.js/npm | OpenClaw staging 必需 | 安装锁定版 OpenClaw CLI |
| OpenClaw | `2026.4.24` | 禁止 `openclaw update` 或 `npm install -g openclaw@latest` |
| Ollama | embedding staging 可选 | 只在真实 embedding gate 需要 |

## macOS

### 1. 安装系统依赖

```bash
brew install python@3.11 git node
npm i -g openclaw@2026.4.24 --no-fund --no-audit
```

如果只跑 local demo，可以先跳过 Node/OpenClaw；preflight 会给 warning，不会把 local demo 判失败。

### 2. 克隆并安装项目

```bash
git clone <repo-url> feishu_ai_challenge
cd feishu_ai_challenge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
cp .env.example .env
python -m memory_engine init-db
```

### 3. 验证

```bash
python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python scripts/check_openclaw_version.py
python scripts/check_demo_readiness.py --json
```

OpenClaw 主路径：

```bash
python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
```

Embedding 可选路径：

```bash
scripts/setup_embedding_ollama_macos.sh
python scripts/check_cross_platform_quick_deploy.py --profile embedding --json
```

## Linux

以下命令以 Ubuntu/Debian 为例；其他发行版按等价包名安装 Python 3.11、venv、Git、Node.js/npm。

### 1. 安装系统依赖

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip git nodejs npm
npm i -g openclaw@2026.4.24 --no-fund --no-audit
```

### 2. 克隆并安装项目

```bash
git clone <repo-url> feishu_ai_challenge
cd feishu_ai_challenge
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
cp .env.example .env
python -m memory_engine init-db
```

### 3. 验证

```bash
python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python scripts/check_openclaw_version.py
python scripts/check_demo_readiness.py --json
python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
```

Linux 暂无仓库内 Ollama 安装脚本；embedding staging 可以按 Ollama 官方安装方式装好 `ollama` 后再跑：

```bash
ollama pull qwen3-embedding:0.6b-fp16
python scripts/check_embedding_provider.py --model ollama/qwen3-embedding:0.6b-fp16 --dimensions 1024
python scripts/check_cross_platform_quick_deploy.py --profile embedding --json
```

## Windows

推荐使用 PowerShell 7 或 Windows PowerShell。以下命令在仓库根目录执行。

### 1. 安装系统依赖

```powershell
winget install --id Python.Python.3.11 --exact
winget install --id Git.Git --exact
winget install --id OpenJS.NodeJS --exact
npm i -g openclaw@2026.4.24 --no-fund --no-audit
```

如 PowerShell 禁止激活虚拟环境，先对当前用户放开脚本执行策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. 克隆并安装项目

```powershell
git clone <repo-url> feishu_ai_challenge
cd feishu_ai_challenge
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
Copy-Item .env.example .env
python -m memory_engine init-db
```

### 3. 验证

```powershell
python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python scripts/check_openclaw_version.py
python scripts/check_demo_readiness.py --json
python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
```

Embedding 可选路径：

```powershell
.\scripts\setup_embedding_ollama_windows.ps1
python scripts/check_cross_platform_quick_deploy.py --profile embedding --json
```

## Feishu / OpenClaw 真实联调前不要跳过的检查

跨平台 quick deploy 只证明新机器具备本地 demo / staging 条件。准备接真实 Feishu 或 OpenClaw websocket 时，继续按当前 productization gate 走：

```bash
python scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python scripts/prepare_feishu_live_evidence_run.py --planned-listener openclaw-websocket --json
```

真实扩样仍必须保留：

- 单监听：OpenClaw websocket、Copilot lark-cli sandbox、legacy listener 三选一。
- 权限 fail-closed：任何 `current_context.permission` 缺失或畸形都拒绝。
- review policy：真实飞书来源先进入 candidate / review policy，不能直接写 active。
- no-overclaim：任何 quick deploy 结果都不能写成生产部署或长期 live 已完成。

## 常见失败

| 失败 | 处理 |
|---|---|
| `python_stdlib_modules` 缺 `venv` | Linux 安装 `python3.11-venv`；Windows/macOS 重新安装完整 Python |
| `openclaw_locked_version` warning | local demo 可继续；OpenClaw staging 先安装 `npm i -g openclaw@2026.4.24 --no-fund --no-audit` |
| `openclaw_locked_version` fail | 本机 OpenClaw 版本不是锁定版，按锁定版本重装，不要运行 `openclaw update` |
| `node_npm` fail | 安装 Node.js/npm 后重开终端 |
| `ollama` warning | local demo / OpenClaw staging 可忽略；embedding staging 才需要安装 |
| `check_demo_readiness.py` fail | 先看 JSON 里的 failed step；不要把失败机器写成可演示部署 |

