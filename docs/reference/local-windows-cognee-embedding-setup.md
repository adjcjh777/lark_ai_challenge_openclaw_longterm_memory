# Windows 备用环境：Cognee 本地 embedding 安装与验证

适用日期：2026-04-27 之后
适用范围：在 Windows 备用环境复现 Feishu Memory Copilot 的 Cognee 本地测试环境

## 先看这个

1. 今天不让 RightCode 负责 embedding（向量表示），RightCode 只继续负责大模型文本能力。
2. embedding 默认改成本机 Ollama 跑 `qwen3-embedding:0.6b-fp16`，这是一个 0.6B 参数、1024 维、约 1.2GB 的本地模型。
3. 你只需要安装 Ollama、拉模型、复制 `.env.example`，然后跑两个检查脚本。
4. 如果默认模型下载失败，再用备选 `bge-m3:567m`；不要自己换别的模型。
5. 遇到问题发我：`python scripts/check_embedding_provider.py` 的完整 JSON 输出。

## 为什么不用 `bge-m3:567m` 做默认

我们参考了 MTEB（Embedding 模型评测榜）和模型发布页。结论是：

| 模型 | 包体/参数 | 维度 | 多语言 MTEB | 中文 C-MTEB | 是否默认 |
|---|---:|---:|---:|---:|---|
| `qwen3-embedding:0.6b-fp16` | 0.6B，约 1.2GB | 1024 | 64.33 | 66.33 | 默认 |
| `bge-m3:567m` | 567M，约 1.2GB | 1024 | 59.56 | 未在同一表格列出 | 备选 |
| `qwen3-embedding:4b-fp16` | 4B，约 8GB | 2560 | 69.45 | 72.27 | 暂不默认 |

`qwen3-embedding:4b-fp16` 分数更高，但 8GB 模型在 16GB 机器上跑 Cognee 批处理会比较吃内存，也会让 Windows 备用环境复现更不稳。比赛 MVP 先选择 `qwen3-embedding:0.6b-fp16`：质量比 BGE-M3 更好，内存更稳，模型也能用 Ollama 直接下载。

## 你要安装什么

- Python 3.9 或更高版本。
- Git。
- Ollama。
- 本仓库依赖：`cognee==0.1.20`、`httpx==0.27.2` 已经写在 `pyproject.toml`。

不要安装 `latest` 版的 Cognee，也不要主动更新 OpenClaw。OpenClaw 固定为 `2026.4.24`。

## Windows 一键安装 Ollama embedding

在 PowerShell 里进入仓库目录：

```powershell
cd C:\path\to\feishu_ai_challenge
```

运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_embedding_ollama_windows.ps1
```

这个脚本会做三件事：

1. 如果没装 Ollama，用 `winget install Ollama.Ollama` 安装。
2. 启动本机 Ollama 服务。
3. 下载 `qwen3-embedding:0.6b-fp16` 并运行 embedding 检查。

成功时会看到类似：

```json
{
  "actual_dimensions": 1024,
  "endpoint": "http://localhost:11434",
  "expected_dimensions": 1024,
  "model": "ollama/qwen3-embedding:0.6b-fp16",
  "ok": true,
  "status": "ready"
}
```

## 配置 `.env`

复制模板：

```powershell
Copy-Item .env.example .env
```

打开 `.env`，只填这一项：

```text
LLM_API_KEY=你的 RightCode key
```

其余默认保持这样：

```text
LLM_PROVIDER=custom
LLM_MODEL=gpt-5.3-codex-high
LLM_ENDPOINT=https://right.codes/codex/v1

EMBEDDING_MODEL=ollama/qwen3-embedding:0.6b-fp16
EMBEDDING_ENDPOINT=http://localhost:11434
EMBEDDING_DIMENSIONS=1024
```

不要把 `.env` 发到群里，不要提交到 Git。

## 验证顺序

先验证 embedding，不要一上来跑 Cognee：

```powershell
python scripts\check_embedding_provider.py
```

再验证 Cognee dry-run：

```powershell
python scripts\spike_cognee_local.py --dry-run
```

最后跑真实 Cognee spike：

```powershell
python scripts\spike_cognee_local.py --reset-local-data
```

第一次跑真实 Cognee，或者切换过 embedding 模型时，都建议带 `--reset-local-data`。这个参数只删除项目内 `.data/cognee/` 的本地生成数据，不会删除代码、文档或飞书数据。

真实 spike 成功时，JSON 里应该能看到：

```json
"stages": [
  {"stage": "add", "ok": true},
  {"stage": "cognify", "ok": true},
  {"stage": "search", "ok": true}
]
```

## 如果默认模型下载失败

使用备选 BGE-M3：

```powershell
ollama pull bge-m3:567m
python scripts\check_embedding_provider.py --model ollama/bge-m3:567m --dimensions 1024
```

然后把 `.env` 改成：

```text
EMBEDDING_MODEL=ollama/bge-m3:567m
EMBEDDING_DIMENSIONS=1024
```

`bge-m3:567m` 是备选，不是默认。只有当 Qwen3 embedding 拉不下来或机器兼容性异常时才切换。

## 常见问题

### `Connection refused`

说明 Ollama 没启动。运行：

```powershell
ollama serve
```

另开一个 PowerShell，再运行：

```powershell
python scripts\check_embedding_provider.py
```

### `model not found`

说明模型没下载成功。运行：

```powershell
ollama pull qwen3-embedding:0.6b-fp16
```

### `dimension_mismatch`

检查 `.env` 里是否仍是：

```text
EMBEDDING_DIMENSIONS=1024
```

如果你切到了别的模型，把完整 JSON 输出发给我，不要自己继续改。

如果你刚从 OpenAI/RightCode embedding 切到 Ollama，运行：

```powershell
python scripts\spike_cognee_local.py --reset-local-data
```

因为旧的 `.data/cognee/` 里可能已经建过 3072 维的向量表，新模型是 1024 维，不清理会报维度不一致。

### Cognee 仍然报 RightCode embedding blocked

说明 `.env` 没有生效，或者 `EMBEDDING_MODEL` 还指向 RightCode/OpenAI。重新检查：

```powershell
python scripts\check_embedding_provider.py
python scripts\spike_cognee_local.py
```

## 文件对应关系

| 文件 | 用途 |
|---|---|
| `.env.example` | 本地配置模板，不含真实 key |
| `memory_engine/copilot/embedding-provider.lock` | 锁定默认 embedding provider/model/dimensions |
| `scripts/setup_embedding_ollama_windows.ps1` | Windows 安装和验证入口 |
| `scripts/check_embedding_provider.py` | 单独检查 embedding 服务是否可用 |
| `scripts/spike_cognee_local.py` | Cognee 真实 add/cognify/search spike |

## 今晚不用做

- 不用改 `memory_engine/repository.py`。
- 不用改 OpenClaw 配置。
- 不用安装 Cognee server 或 Docker。
- 不用把模型文件复制给别人，Ollama 会自己下载。
