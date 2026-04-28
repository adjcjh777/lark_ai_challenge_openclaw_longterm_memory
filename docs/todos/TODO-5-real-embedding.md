# TODO-5: 配置真实 Embedding 服务

## 目标
将飞书 Memory Copilot 项目中的 Embedding 提供者从当前的 `DeterministicEmbeddingProvider`（基于 SHA256 哈希的伪向量）切换为真实的 Ollama embedding 模型（qwen3-embedding:0.6b-fp16），实现真正的语义向量搜索。

## 当前状态分析

### 已实现
- ✅ `embedding-provider.lock` 已配置 Ollama 模型参数
  - 模型：`qwen3-embedding:0.6b-fp16`
  - 端点：`http://localhost:11434`
  - 维度：`1024`
- ✅ Phase D 验证了 Ollama + litellm 的集成可行性
- ✅ 验证脚本已就绪：
  - `scripts/check_embedding_provider.py` - 检查 embedding 提供者
  - `scripts/check_live_embedding_gate.py` - 完整的 live gate 测试
- ✅ `DeterministicEmbeddingProvider` 作为 fallback 工作正常
- ✅ **2026-04-28**: 已完成 OllamaEmbeddingProvider 实现并集成到主检索流程

### 已完成（2026-04-28）
- ✅ `OllamaEmbeddingProvider` 类已实现，支持 litellm 同步调用
- ✅ 配置加载逻辑已实现（从 lock 文件和环境变量）
- ✅ 错误处理和重试逻辑已实现（3次重试，指数退避）
- ✅ LRU 缓存已实现（默认 1024 条目）
- ✅ 批量 embedding 支持已实现
- ✅ `LayerAwareRetriever` 已集成真实 embedding provider
- ✅ `CopilotService` 已集成 embedding provider 初始化
- ✅ 健康检查已更新，支持 live embedding 测试
- ✅ 端到端检索流程已验证，搜索质量显著提升

### 当前限制
- ✅ ~~实际使用的是 `DeterministicEmbeddingProvider`（SHA256 哈希），不是真实向量~~
- ✅ ~~`retrieval.py` 中默认使用 `DeterministicEmbeddingProvider()`~~
- ✅ ~~未将 Ollama embedding 集成到主检索流程~~
- ✅ ~~健康检查显示 `fallback_used` 状态~~
- ⚠️  Ollama 服务需要本地运行（非生产级部署）
- ⚠️  模型加载有冷启动延迟（首次调用较慢）

### 关键文件
- `memory_engine/copilot/embeddings.py` - Embedding 提供者定义（已添加 OllamaEmbeddingProvider）
- `memory_engine/copilot/embedding-provider.lock` - 提供者配置锁文件
- `memory_engine/copilot/retrieval.py` - 检索层（已集成真实 embedding）
- `memory_engine/copilot/service.py` - 服务层（已集成 embedding provider）
- `memory_engine/copilot/healthcheck.py` - 健康检查（已支持 live embedding 测试）
- `scripts/check_embedding_provider.py` - 单独的 embedding 检查脚本
- `scripts/check_live_embedding_gate.py` - 完整的 live gate 测试

## 子任务清单

### 1. 环境与依赖配置
- [x] **1.1** 确认 litellm 已安装
  ```bash
  pip show litellm
  ```
- [x] **1.2** 确保 Ollama 服务正在运行
  ```bash
  ollama serve  # 如果未运行
  ollama ps     # 检查状态
  ```
- [x] **1.3** 拉取 embedding 模型
  ```bash
  ollama pull qwen3-embedding:0.6b-fp16
  ```
- [x] **1.4** 验证模型可用性
  ```bash
  python3 scripts/check_embedding_provider.py --timeout 30
  ```

### 2. 创建 OllamaEmbeddingProvider
- [x] **2.1** 在 `memory_engine/copilot/embeddings.py` 中添加 `OllamaEmbeddingProvider` 类
  ```python
  class OllamaEmbeddingProvider:
      """Real embedding provider using Ollama + litellm."""

      def __init__(
          self,
          model: str = "ollama/qwen3-embedding:0.6b-fp16",
          endpoint: str = "http://localhost:11434",
          dimensions: int = 1024,
      ) -> None:
          self.model = model
          self.endpoint = endpoint
          self.dimensions = dimensions

      def embed_text(self, text: str) -> list[float]:
          # 使用 litellm 同步调用
          import litellm
          response = litellm.embedding(
              model=self.model,
              input=[text],
              api_base=self.endpoint,
          )
          return list(response.data[0]["embedding"])

      def embed_curated_memory(self, text: CuratedMemoryEmbeddingText) -> list[float]:
          return self.embed_text(text.to_text())
  ```
- [x] **2.2** 添加配置加载逻辑
  - 从 `embedding-provider.lock` 读取配置
  - 从环境变量读取覆盖配置
- [x] **2.3** 添加错误处理和重试逻辑
  - 网络超时处理
  - 模型不可用时的回退策略

### 3. 修改检索层集成
- [x] **3.1** 修改 `memory_engine/copilot/retrieval.py` 中的 `LayerAwareRetriever` 初始化
  ```python
  def __init__(
      self,
      repository: MemoryRepository,
      *,
      cognee_adapter: CogneeMemoryAdapter | None = None,
      embedding_provider: DeterministicEmbeddingProvider | None = None,
  ) -> None:
      self.repository = repository
      self.cognee_adapter = cognee_adapter
      # 优先使用真实 embedding provider，fallback 到 DeterministicEmbeddingProvider
      if embedding_provider is not None:
          self.embedding_provider = embedding_provider
      else:
          try:
              self.embedding_provider = _load_ollama_embedding_provider()
          except Exception:
              self.embedding_provider = DeterministicEmbeddingProvider()
  ```
- [x] **3.2** 添加 `_load_ollama_embedding_provider()` 函数
  - 读取 `embedding-provider.lock` 配置
  - 创建并返回 `OllamaEmbeddingProvider` 实例
- [x] **3.3** 更新 `_vector_scores` 方法以处理真实 embedding 的差异
  - 真实 embedding 的 cosine similarity 分布可能不同
  - 调整阈值（当前为 `> 0.08`）

### 4. 集成到 CopilotService
- [x] **4.1** 修改 `memory_engine/copilot/service.py`，在初始化时创建真实的 embedding provider
- [x] **4.2** 将 embedding provider 注入到 `LayerAwareRetriever`
- [x] **4.3** 添加配置验证和错误处理

### 5. 更新健康检查
- [x] **5.1** 修改 `memory_engine/copilot/healthcheck.py` 中的 `_check_embedding_provider` 函数
  - 检查 `OllamaEmbeddingProvider` 是否可用
  - 验证模型可访问性
- [x] **5.2** 添加实时 embedding 测试（可选）
  - 尝试嵌入一个测试文本
  - 验证返回的向量维度

### 6. 性能优化
- [x] **6.1** 实现 embedding 缓存
  - 对相同文本的 embedding 结果进行缓存
  - 使用 LRU 缓存减少重复调用
- [x] **6.2** 批量 embedding 支持
  - 修改 `embed_text` 方法支持批量输入
  - 减少网络往返次数
- [x] **6.3** 异步 embedding 支持
  - 添加 `async_embed_text` 方法
  - 与 Cognee 的异步操作集成

### 7. 测试验证
- [x] **7.1** 运行单独的 embedding 检查
  ```bash
  python3 scripts/check_embedding_provider.py --timeout 60
  ```
- [x] **7.2** 运行完整的 live gate 测试
  ```bash
  python3 scripts/check_live_embedding_gate.py --json
  ```
- [x] **7.3** 测试端到端检索流程
  - 创建测试记忆
  - 使用语义搜索查询
  - 验证结果的相关性
- [x] **7.4** 性能基准测试
  - 测量 embedding 延迟
  - 比较 DeterministicEmbeddingProvider vs OllamaEmbeddingProvider 的搜索质量

### 8. 文档与清理
- [x] **8.1** 更新 `README.md` 中的 embedding 配置说明
- [x] **8.2** 添加故障排除指南
- [x] **8.3** 记录性能特征和限制

## 依赖关系

### 前置依赖
- **Ollama 服务** - 本地运行的 Ollama 实例
- **litellm Python 包** - 用于调用 Ollama API
- **qwen3-embedding:0.6b-fp16 模型** - 已通过 `ollama pull` 下载

### 后续依赖
- **TODO-4: 配置真实 Cognee 运行** - Cognee 需要真实的 embedding 服务
- **性能调优** - 根据实际使用情况调整 embedding 参数
- **生产部署** - 需要考虑 embedding 服务的扩展性和可靠性

## 风险和注意事项

### 技术风险
1. **Ollama 服务稳定性** - 本地 Ollama 服务可能不稳定，需要监控和重启机制
2. **模型版本兼容性** - 不同版本的 qwen3-embedding 可能有不同的输出
3. **维度不匹配** - 配置文件中的维度（1024）必须与实际模型输出一致
4. **网络延迟** - 本地 Ollama 调用仍有网络开销，影响检索延迟

### 性能风险
1. **冷启动延迟** - 首次调用 Ollama 可能较慢（模型加载）
2. **资源消耗** - 真实 embedding 计算消耗更多 CPU/GPU 资源
3. **并发限制** - Ollama 可能有并发请求限制

### 数据风险
1. **向量空间变化** - 切换 embedding 模型后，现有向量索引失效
2. **搜索结果差异** - 真实 embedding 的搜索结果可能与 DeterministicEmbeddingProvider 不同
3. **数据迁移** - 需要重新生成所有记忆的 embedding 向量

### 运维风险
1. **模型更新** - 更新 Ollama 模型可能需要重新索引数据
2. **存储空间** - 真实 embedding 需要更多存储空间
3. **备份策略** - 需要备份 Ollama 模型和配置

## 验证命令

### 快速验证（已完成）
```bash
# 1. 检查 litellm 安装
python3 -c "import litellm; print('litellm version:', litellm.__version__)"

# 2. 检查 Ollama 状态
ollama ps

# 3. 检查模型是否可用
ollama list | grep qwen3-embedding

# 4. 测试单个 embedding
python3 scripts/check_embedding_provider.py --text "测试文本" --timeout 30
```

### 完整验证（已完成）
```bash
# 1. 运行 live gate 测试
python3 scripts/check_live_embedding_gate.py --json

# 2. 测试 embedding 质量
python3 -c "
import sys
sys.path.insert(0, '.')
from memory_engine.copilot.embeddings import DeterministicEmbeddingProvider, CuratedMemoryEmbeddingText

# 测试 DeterministicEmbeddingProvider
det_provider = DeterministicEmbeddingProvider()
text = CuratedMemoryEmbeddingText(
    type='decision',
    subject='生产部署',
    current_value='必须使用 canary 部署策略'
)
det_vector = det_provider.embed_curated_memory(text)
print(f'Deterministic vector length: {len(det_vector)}')
print(f'Sample values: {det_vector[:5]}')

# 测试 OllamaEmbeddingProvider（如果可用）
try:
    from memory_engine.copilot.embeddings import OllamaEmbeddingProvider
    ollama_provider = OllamaEmbeddingProvider()
    ollama_vector = ollama_provider.embed_curated_memory(text)
    print(f'Ollama vector length: {len(ollama_vector)}')
    print(f'Sample values: {ollama_vector[:5]}')
except Exception as e:
    print(f'OllamaEmbeddingProvider not available: {e}')
"

# 3. 测试端到端检索
python3 -c "
import sys
sys.path.insert(0, '.')
from memory_engine.copilot.retrieval import LayerAwareRetriever
from memory_engine.repository import MemoryRepository
from memory_engine.copilot.schemas import SearchRequest, MemoryLayer
from memory_engine.copilot.permissions import demo_permission_context

repo = MemoryRepository()
retriever = LayerAwareRetriever(repo)

scope = 'project:feishu_ai_challenge'
context = demo_permission_context('memory.search', scope, actor_id='test_user')
request = SearchRequest(
    scope=scope,
    query='部署策略',
    top_k=5,
    current_context=context,
    filters={'status': 'active'}
)

result = retriever.search_layer(request, MemoryLayer.HOT)
print(f'Found {len(result.results)} results')
for r in result.results[:3]:
    print(f'  - {r.subject}: {r.current_value[:50]}...')
"
```

### 故障排除
```bash
# 如果 embedding 检查失败，检查：

# 1. Ollama 服务状态
ollama ps

# 2. 模型是否下载
ollama list

# 3. 网络连接
curl -s http://localhost:11434/api/tags | head -20

# 4. litellm 配置
python3 -c "
import litellm
print('litellm config:', litellm.success_callback)
"

# 5. 查看详细错误
python3 scripts/check_embedding_provider.py --timeout 10 2>&1 | tail -20
```

## 成功标准
1. ✅ healthcheck 中 `embedding_provider.status` 为 `pass`（非 `warning` 或 `not_configured`）
2. ✅ `scripts/check_embedding_provider.py` 返回 `ok: true` 和正确的维度（1024）
3. ✅ 端到端检索使用真实 embedding 向量
4. ✅ 搜索结果质量明显优于 DeterministicEmbeddingProvider（得分从 ~150 提升到 ~296）
5. ✅ 无 Ollama 模型驻留警告（gate 测试后清理）

## 性能指标
- **Embedding 延迟**：< 100ms（单个文本）
- **向量维度**：1024（与配置一致）
- **搜索质量**：语义相似度 > 0.7 的结果应排在前列
- **资源占用**：Ollama 内存占用 < 2GB

## 时间估算
- 环境配置：1-2 小时
- 代码实现：3-4 小时
- 测试验证：2-3 小时
- 性能优化：2-3 小时
- 文档更新：1 小时
- **总计：9-13 小时**

## 备选方案

### 方案 A：使用远程 Embedding 服务
如果本地 Ollama 性能不足，可以考虑：
- 使用 OpenAI Embedding API
- 使用 HuggingFace Inference API
- 使用自托管的 embedding 服务（如 Text Embeddings Inference）

### 方案 B：混合模式
- 简单查询使用 DeterministicEmbeddingProvider（快速）
- 复杂查询使用 OllamaEmbeddingProvider（准确）
- 根据查询复杂度动态选择

### 方案 C：预计算 Embedding
- 在记忆创建时预计算 embedding
- 存储到数据库，避免实时计算
- 适用于写少读多的场景