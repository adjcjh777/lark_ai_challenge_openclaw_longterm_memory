# PR #2 修改说明：Day 1 数据集与白皮书补位

日期：2026-04-25

这次 PR 的方向是对的：补了 simple / conflict / noise 数据集，也开始写《Memory 定义与架构白皮书》初稿，和你负责的补位任务匹配。但目前先不要合并，因为新增材料还不能直接支撑 Day 1 / 初赛 Benchmark 验收。

## 这次为什么没有合并

当前主线要求不是“有数据就行”，而是数据要能被仓库现有 runner 跑起来，并且能产出可信指标。PR 里的新增文件目前更像原始语料或未来扩展草稿，还没到“可验收 benchmark 数据集”的状态。

本地验证结果：

```bash
python3 -m compileall memory_engine scripts
# 通过

python3 -m memory_engine benchmark run benchmarks/day1_cases.json
# 通过，现有 Day 1 baseline 10/10 没被破坏
```

额外试跑新增数据集：

```text
data/simple_memory_cases_70.json
- 70 条里通过 53 条
- 17 条失败
- pass_rate = 0.7571

data/conflict_cases_50.json
- 50 条里通过 20 条
- 30 条失败
- pass_rate = 0.4
- forbidden_values 没有被当前 runner 识别，所以旧值泄漏检查实际没有生效
```

另外：

```bash
python3 -m pytest
```

当前本地环境没有安装 `pytest`，所以这条没有作为阻塞你 PR 的原因。

## 必须修改的点

### 1. 统一 conflict 数据集 schema

现在 `data/conflict_cases_50.json` 里使用的是：

```json
{
  "type": "multi_conflict_update",
  "forbidden_values": [
    "旧规则 A",
    "旧规则 B"
  ]
}
```

但当前 `memory_engine.benchmark` runner 只识别：

```json
{
  "type": "conflict_update",
  "forbidden_value": "旧规则"
}
```

因此现在 runner 不会把这些 case 计入 conflict 指标，也不会真正检查多个旧值是否泄漏。

你有两个可选修法，选一个即可：

1. **保守修法，推荐先做**：把数据改成现有 runner 能识别的格式。
   - `type` 改成 `conflict_update`
   - 如果只有一个旧值，用 `forbidden_value`
   - 如果有多个旧值，先拆成多个 case，或只保留最关键的旧值做 `forbidden_value`

2. **扩展修法**：同步修改 `memory_engine/benchmark.py`。
   - 支持 `forbidden_values: list[str]`
   - 让 `conflict_accuracy` 同时统计 `conflict_update` 和 `multi_conflict_update`
   - 旧值泄漏率要检查所有 forbidden values，而不是只检查一个字符串

如果你不想改代码，建议走第 1 种。

### 2. 让新增 benchmark 数据能跑出可信通过率

`data/simple_memory_cases_70.json` 现在 70 条只通过 53 条。失败原因大概率不是数据 JSON 语法错，而是样例表达、query、expected_active_value 和当前规则抽取能力不匹配。

需要你做的事：

- 逐条看失败 case。
- 优先修 `expected_active_value`，让它和当前系统实际会召回的 active value 对齐。
- 如果某条 case 明显超出 Day 1 能力范围，比如需要复杂语义理解或尚未实现的类型能力，就先移到 raw/corpus 文件，不要放进可验收 benchmark。
- 修完后重新跑，目标是作为 benchmark 的文件至少能达到接近 100% 通过；如果不能 100%，要在文档里说明哪些是挑战样例，不计入 Day 1 验收。

建议临时用这个脚本看失败项：

```bash
python3 - <<'PY'
from memory_engine.benchmark import run_benchmark

for path in [
    "data/simple_memory_cases_70.json",
    "data/conflict_cases_50.json",
]:
    result = run_benchmark(path)
    print(path, result["summary"])
    for item in result["results"]:
        if not item["passed"]:
            print(item["case_id"], "expected=", item["expected"], "actual=", item["actual"])
PY
```

### 3. 区分“可验收 benchmark”和“原始语料”

如果这些文件暂时只是给后续 D7 Benchmark 扩容用的原始素材，不要放得像已经可跑的验收集。

建议目录命名：

```text
data/raw/simple_memory_cases_70.json
data/raw/conflict_cases_50.json
data/raw/noise_chat_samples_200.json
```

或者保留在 `data/`，但新增一个说明文件：

```text
data/README.md
```

里面写清楚：

- 哪些文件是 raw corpus。
- 哪些文件能直接被 `memory_engine benchmark run` 跑。
- 当前通过率是多少。
- 是否计入 Benchmark Report。

### 4. 修正白皮书日期和入口位置

`docs/memory-definition-and-architecture-whitepaper/version_0.md` 里写的是：

```text
日期：2026-04-26
```

但这个 PR 是 2026-04-25 提交和 review 的。请改成真实产出日期，或者明确写成“Day 3 草稿”。

另外总控文档里要求最终白皮书入口是：

```text
docs/memory-definition-and-architecture-whitepaper.md
```

现在 PR 放在：

```text
docs/memory-definition-and-architecture-whitepaper/version_0.md
```

这不是大问题，但要二选一处理：

1. 直接把最终入口整理成 `docs/memory-definition-and-architecture-whitepaper.md`。
2. 保留版本目录，但新增入口文件 `docs/memory-definition-and-architecture-whitepaper.md`，里面链接到 `version_0.md` 并说明这是 v0 草稿。

## 建议你这次 PR 的最小改法

为了尽快合并，建议不要一次性扩展 runner，先把 PR 收敛成“队友补位材料包”：

1. 把新增数据分成两类：
   - 可运行 benchmark：能被现有 runner 跑通。
   - raw corpus：暂时只作为后续扩容素材。
2. conflict case 先改成现有 runner 契约。
3. 修到新增 benchmark 文件通过率接近 100%。
4. 白皮书修日期，并补一个最终入口或说明。
5. 在 PR 描述里补上验证结果。

## 合并前验收命令

请在修改后至少跑：

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

如果你保留了新增 benchmark 文件作为“可运行数据集”，也要跑：

```bash
python3 - <<'PY'
from memory_engine.benchmark import run_benchmark
import json

for path in [
    "data/simple_memory_cases_70.json",
    "data/conflict_cases_50.json",
]:
    result = run_benchmark(path)
    print(path)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    failed = [item["case_id"] for item in result["results"] if not item["passed"]]
    print("failed_count:", len(failed))
    print("failed:", failed[:30])
PY
```

PR 描述里请贴：

```text
Tested: python3 -m compileall memory_engine scripts
Tested: python3 -m memory_engine benchmark run benchmarks/day1_cases.json
Tested: 新增 benchmark 数据集通过率：...
Not-tested: pytest，原因：本地环境缺少 pytest（如果你那边也没有）
```

## 这次 PR 做得好的地方

- 数据规模方向是对的，后面做 Benchmark Report 需要这些素材。
- conflict case 覆盖了多轮更新，这是我们项目区别于普通搜索/向量库的关键点。
- noise chat 样例很有用，可以作为 D7 抗干扰测试的基础。
- 白皮书已经抓住了“不是搜索，而是有状态、有版本、有证据的企业记忆”这个主线。

这次主要问题不是方向错，而是还没有和当前工程契约对齐。把 schema、通过率、文档入口这三件事修好，就可以重新 review。
