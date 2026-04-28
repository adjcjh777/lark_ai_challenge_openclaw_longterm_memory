# TODO-4: 配置真实 Cognee 运行

## 目标
将飞书 Memory Copilot 项目中的 Cognee 适配器从当前的"配置可检查但未真实运行"状态，升级为能够连接并使用真实 Cognee SDK 进行记忆存储、检索和推理的完整集成。

## 当前状态分析

### 已实现
- ✅ `CogneeMemoryAdapter` 类已完整实现（`memory_engine/copilot/cognee_adapter.py`）
- ✅ 支持 `add`、`cognify`、`search`、`remember`、`recall`、`improve`、`forget` 等核心操作
- ✅ 本地 spike 测试脚本已就绪（`scripts/spike_cognee_local.py`）
- ✅ Phase D 验证了 Cognee + Ollama 的本地集成可行性

### 当前限制
- ❌ `CogneeMemoryAdapter.client` 默认为 `None`，导致 `is_configured` 返回 `False`
- ❌ healthcheck 显示 `fallback_used` 状态，表示使用 repository 回退而非真实 Cognee
- ❌ 未注入真实的 Cognee SDK 客户端到适配器中
- ❌ 环境变量配置（如 `EMBEDDING_MODEL`、`LLM_PROVIDER`）未持久化

### 关键文件
- `memory_engine/copilot/cognee_adapter.py` - Cognee 适配器核心
- `scripts/spike_cognee_local.py` - 本地 spike 测试脚本
- `memory_engine/copilot/healthcheck.py` - 健康检查（`_check_cognee_adapter` 函数）
- `memory_engine/copilot/retrieval.py` - 检索层（使用 Cognee 作为可选通道）

## 子任务清单

### 1. 环境与依赖配置
- [x] **1.1** 确认 Cognee SDK 已安装
  ```bash
  pip show cognee
  ```
- [x] **1.2** 配置 `.env` 或 `.env.local` 文件，添加必要环境变量：
  ```env
  # LLM 配置（Cognee 推理需要）
  LLM_PROVIDER=custom
  LLM_API_KEY=your_rightcode_api_key_here  # 或 OPENAI_API_KEY
  LLM_ENDPOINT=https://right.codes/codex/v1

  # Embedding 配置（已由 embedding-provider.lock 定义，但 Cognee 需要环境变量）
  EMBEDDING_MODEL=ollama/qwen3-embedding:0.6b-fp16
  EMBEDDING_ENDPOINT=http://localhost:11434
  EMBEDDING_DIMENSIONS=1024
  ```
- [x] **1.3** 确保 Ollama 服务正在运行并已拉取模型
  ```bash
  ollama serve  # 如果未运行
  ollama pull qwen3-embedding:0.6b-fp16
  ```

### 2. 修改 Cognee 适配器注入逻辑
- [x] **2.1** 在 `CogneeMemoryAdapter` 初始化时自动加载 Cognee 客户端
  - 修改 `cognee_adapter.py` 中的 `load_cognee_client()` 调用时机
  - 或在服务层（`service.py`）初始化时注入客户端
- [x] **2.2** 添加配置验证逻辑
  - 检查必要环境变量是否存在
  - 验证 Cognee SDK 可用性
  - 提供清晰的错误信息

### 3. 集成到 CopilotService
- [x] **3.1** 修改 `memory_engine/copilot/service.py`，在初始化时创建并注入 Cognee 客户端
- [x] **3.2** 确保 `CogneeMemoryAdapter` 实例在服务生命周期内保持配置状态
- [x] **3.3** 更新 healthcheck 逻辑，区分"已配置"和"回退"状态

### 4. 验证真实 Cognee 运行
- [ ] **4.1** 运行本地 spike 测试（不带 `--dry-run`）
  ```bash
  python3 scripts/spike_cognee_local.py --scope project:feishu_ai_challenge --query "生产部署参数"
  ```
- [ ] **4.2** 验证 healthcheck 显示 `pass` 而非 `fallback_used`
  ```bash
  python3 -c "from memory_engine.copilot.healthcheck import run_copilot_healthcheck; import json; print(json.dumps(run_copilot_healthcheck()['checks']['cognee_adapter'], indent=2))"
  ```
- [ ] **4.3** 测试端到端记忆流程
  - 创建候选记忆
  - 确认记忆（触发 Cognee add + cognify）
  - 搜索记忆（使用 Cognee 检索通道）

### 5. 清理与文档
- [x] **5.1** 更新 `README.md` 中的 Cognee 配置说明
- [x] **5.2** 添加环境变量示例到 `.env.example`
- [x] **5.3** 记录已知限制和故障排除步骤

## 依赖关系

### 前置依赖
- **TODO-5: 配置真实 Embedding 服务** - Cognee 需要真实的 embedding 模型来生成向量
- **Ollama 服务** - 本地运行的 Ollama 实例，提供 embedding 和 LLM 能力
- **Cognee SDK** - Python 包 `cognee` 已安装

### 后续依赖
- **性能测试** - 真实 Cognee 运行后，需要测试检索延迟和准确性
- **生产部署** - 需要考虑 Cognee 的持久化存储和备份策略

## 风险和注意事项

### 技术风险
1. **Cognee SDK 版本兼容性** - 不同版本的 Cognee SDK API 可能有差异
2. **环境变量管理** - 多个环境变量需要协调配置，容易遗漏
3. **本地 vs 生产** - 本地测试通过后，生产环境可能需要不同的配置

### 运维风险
1. **Ollama 服务稳定性** - 本地 Ollama 服务需要持续运行
2. **存储空间** - Cognee 会创建本地数据库文件（SQLite、LanceDB、NetworkX 图）
3. **资源消耗** - 真实 embedding 计算会消耗更多 CPU/内存

### 数据风险
1. **数据迁移** - 从 fallback 切换到真实 Cognee 后，现有记忆需要重新索引
2. **数据一致性** - 确保 SQLite（repository）和 Cognee 存储的数据一致

## 验证命令

### 快速验证
```bash
# 1. 检查 Cognee SDK 可用性
python3 -c "import cognee; print('Cognee SDK available')"

# 2. 检查环境变量
python3 -c "import os; print('LLM_PROVIDER:', os.getenv('LLM_PROVIDER')); print('EMBEDDING_MODEL:', os.getenv('EMBEDDING_MODEL'))"

# 3. 运行 dry-run 测试
python3 scripts/spike_cognee_local.py --dry-run

# 4. 运行真实 spike 测试
python3 scripts/spike_cognee_local.py --scope project:feishu_ai_challenge --query "测试查询"
```

### 完整验证
```bash
# 1. 运行 healthcheck
python3 -c "
from memory_engine.copilot.healthcheck import run_copilot_healthcheck
import json
report = run_copilot_healthcheck()
cognee_check = report['checks']['cognee_adapter']
print(json.dumps(cognee_check, indent=2, ensure_ascii=False))
print('Status:', cognee_check['status'])
"

# 2. 测试端到端流程
python3 -c "
from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.permissions import demo_permission_context

service = CopilotService()
scope = 'project:feishu_ai_challenge'
context = demo_permission_context('memory.search', scope, actor_id='test_user')

# 搜索记忆（应使用真实 Cognee）
results = service.search(scope=scope, query='测试', current_context=context)
print('Search results:', len(results.get('results', [])))
"
```

### 故障排除
```bash
# 如果 healthcheck 显示 fallback_used，检查：
# 1. Cognee SDK 是否安装
pip show cognee

# 2. 环境变量是否设置
env | grep -E "LLM_|EMBEDDING_"

# 3. Ollama 是否运行
ollama ps

# 4. 查看详细错误
python3 scripts/spike_cognee_local.py 2>&1 | head -50
```

## 成功标准
1. ✅ healthcheck 中 `cognee_adapter.status` 为 `pass`（非 `fallback_used`）
2. ✅ spike 测试成功完成 add → cognify → search 流程
3. ✅ 端到端记忆搜索返回来自 Cognee 的结果
4. ✅ 无环境变量缺失或配置错误警告

## 时间估算
- 环境配置：1-2 小时
- 代码修改：2-3 小时
- 测试验证：1-2 小时
- 文档更新：0.5-1 小时
- **总计：4.5-8 小时**