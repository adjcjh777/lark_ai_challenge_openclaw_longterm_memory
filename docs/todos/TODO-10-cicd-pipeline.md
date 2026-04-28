# TODO-10：添加 CI/CD 管道

日期：2026-04-28
负责人：程俊豪
优先级：P1
状态：进行中

---

## 1. 目标

为 Feishu Memory Copilot 项目添加 CI/CD 管道，实现自动化测试、代码质量检查、构建和部署，保证每次提交都经过验证，减少人工操作错误。

---

## 2. 当前状态分析

### 已完成

- `pyproject.toml` 已定义项目元数据和依赖：`cognee==0.1.20`、`httpx==0.27.2`。
- `.gitignore` 已忽略 `__pycache__/`、`*.pyc`、`node_modules/`、`data/*.sqlite`、`*.log`、`logs/`、`.env` 等。
- `scripts/` 目录已有 18 个脚本，覆盖 healthcheck、demo readiness、embedding gate、migration 等。
- 单元测试分布在 `tests/` 目录，覆盖 copilot permissions、healthcheck、tools、schemas、feishu_live 等。
- benchmark 测试覆盖 recall、candidate、conflict、layer、prefetch、heartbeat 六类。

### 未完成

- 无自动化部署流程（Staging / Production）。
- 无自动化版本号管理（基于 git tag）。

### 已完成（本次实现）

- CI/CD 配置文件：`.github/workflows/ci.yml`（GitHub Actions）。
- 自动化测试流水线：单元测试、集成测试、Benchmark 测试。
- 代码质量检查：ruff lint/format、mypy type check、compileall、git diff --check。
- 依赖安全扫描：pip-audit、license 检查。
- 构建流程：`python -m build` + 构建产物验证。
- 代码覆盖率：coverage.py 集成，阈值 70%。
- OpenClaw 特定检查：版本检查、schema 验证、插件 manifest 验证。
- `pyproject.toml` 已添加 `[dev]` 依赖组（ruff、mypy、coverage、pip-audit 等）。

---

## 3. 子任务清单

### 3.1 CI 基础设施搭建

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.1.1 选择 CI 平台 | GitHub Actions | `.github/workflows/` | CI 平台选定 |
| [x] 10.1.2 创建 CI 配置文件 | 定义 pipeline stages | `.github/workflows/ci.yml` | 配置文件存在 |
| [x] 10.1.3 配置 Python 环境 | 指定 Python 版本、安装依赖 | CI 配置文件 | Python 环境可复现 |
| [x] 10.1.4 配置缓存策略 | pip cache | CI 配置文件 | 缓存命中率 > 50% |

### 3.2 自动化测试

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.2.1 单元测试 stage | 运行 `python3 -m unittest discover tests/` | CI 配置文件 | 所有测试通过 |
| [x] 10.2.2 集成测试 stage | 运行 healthcheck、demo readiness | CI 配置文件 | 脚本 exit code = 0 |
| [x] 10.2.3 Benchmark 测试 stage | 运行六类 benchmark | CI 配置文件 | 所有 benchmark 通过 |
| [x] 10.2.4 测试结果报告 | coverage report 输出摘要 | CI 配置文件 | 报告可读 |
| [x] 10.2.5 测试失败通知 | GitHub Actions 自动标注失败 job | CI 配置文件 | 通知可达 |

### 3.3 代码质量检查

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.3.1 代码编译检查 | `python3 -m compileall memory_engine scripts` | CI 配置文件 | 编译无错误 |
| [x] 10.3.2 Lint 检查 | 使用 ruff | CI 配置文件、`pyproject.toml` | lint 无错误 |
| [x] 10.3.3 Type check | 使用 mypy | CI 配置文件、`pyproject.toml` | type check 无错误 |
| [x] 10.3.4 格式检查 | 使用 ruff format | CI 配置文件、`pyproject.toml` | 格式一致 |
| [x] 10.3.5 Git diff 检查 | `git diff --check` | CI 配置文件 | 无 whitespace 错误 |

### 3.4 依赖安全扫描

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.4.1 依赖漏洞扫描 | 使用 pip-audit | CI 配置文件 | 无高危漏洞 |
| [ ] 10.4.2 依赖版本锁定 | 生成 requirements.txt 或 poetry.lock | `requirements.txt` | 依赖版本固定 |
| [x] 10.4.3 License 检查 | 使用 pip-licenses 检查依赖兼容性 | CI 配置文件 | 无 license 冲突 |

### 3.5 构建流程

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.5.1 Python 包构建 | `python -m build` | CI 配置文件 | 构建成功 |
| [x] 10.5.2 构建产物验证 | 验证 wheel / sdist 可安装 | CI 配置文件 | 安装成功 |
| [ ] 10.5.3 版本号管理 | 自动化版本号（基于 git tag） | `pyproject.toml`、CI 配置文件 | 版本号正确 |

### 3.6 部署流程

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [ ] 10.6.1 Staging 部署 | 自动部署到 staging 环境 | CI 配置文件、部署脚本 | staging 可访问 |
| [ ] 10.6.2 生产部署 | 手动触发或 tag 触发生产部署 | CI 配置文件、部署脚本 | 生产可访问 |
| [ ] 10.6.3 部署后验证 | 部署后运行 healthcheck | CI 配置文件 | healthcheck 通过 |
| [ ] 10.6.4 部署回滚 | 部署失败时自动回滚 | CI 配置文件、部署脚本 | 回滚成功 |

### 3.7 OpenClaw 特定检查

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.7.1 OpenClaw 版本检查 | `python3 scripts/check_openclaw_version.py` | CI 配置文件 | 版本一致 |
| [x] 10.7.2 OpenClaw schema 验证 | 验证 `memory_tools.schema.json` 格式正确 | CI 配置文件 | schema 有效 |
| [x] 10.7.3 OpenClaw 插件验证 | 验证 `openclaw.plugin.json` manifest 格式正确 | CI 配置文件 | 插件 manifest 有效 |

### 3.8 代码覆盖率

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| [x] 10.8.1 集成覆盖率工具 | 使用 coverage.py | `pyproject.toml`、CI 配置文件 | 覆盖率可采集 |
| [x] 10.8.2 覆盖率报告 | 生成 XML 报告并上传 artifact | CI 配置文件 | 报告可读 |
| [x] 10.8.3 覆盖率阈值 | 设置最低覆盖率 70% | CI 配置文件 | 覆盖率达标 |

---

## 4. 依赖关系

| 依赖项 | 说明 |
|---|---|
| GitHub / GitLab 仓库 | 需要 CI 平台访问权限 |
| Python 3.9+ | 项目要求 |
| 现有测试套件 | `tests/` 目录已有测试 |
| 现有 benchmark 套件 | `benchmarks/` 目录已有 benchmark |
| 现有脚本 | `scripts/` 目录已有验证脚本 |

---

## 5. 风险和注意事项

1. **OpenClaw 版本锁定**：CI 必须使用 OpenClaw 2026.4.24，不要自动升级。
2. **真实凭证不进 CI**：飞书 app secret、lark-cli token 不写入 CI 配置。
3. **本地 SQLite 测试**：CI 中使用内存 SQLite 或临时文件，不依赖生产数据库。
4. **Ollama 模型不驻留**：CI 中如果测试 embedding，验证后必须清理。
5. **不冒称生产部署**：CI/CD 管道是开发流程，不是生产上线。
6. **保持 candidate-only**：CI 中的测试数据只进 candidate，不自动 active。

---

## 6. 验证命令

```bash
# 基础检查
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json

# 测试套件
python3 -m unittest discover tests/ -v

# Benchmark 套件
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json

# 代码质量
python3 -m compileall memory_engine scripts
git diff --check

# 本地模拟 CI
act -j test  # 如果使用 GitHub Actions + act
# 或
gitlab-runner exec docker test  # 如果使用 GitLab CI

# 依赖检查
pip-audit  # 或 safety check

# 覆盖率
coverage run -m unittest discover tests/
coverage report --fail-under=70
```

---

## 7. CI 配置示例（GitHub Actions）

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11']

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
        cache: 'pip'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev]"  # 需要 pyproject.toml 添加 dev 依赖

    - name: Compile check
      run: python3 -m compileall memory_engine scripts

    - name: Git diff check
      run: git diff --check

    - name: Unit tests
      run: python3 -m unittest discover tests/ -v

    - name: Healthcheck
      run: python3 scripts/check_copilot_health.py --json

    - name: Demo readiness
      run: python3 scripts/check_demo_readiness.py --json

    - name: Benchmark tests
      run: |
        python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
        python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
        python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
        python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
        python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
        python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```
