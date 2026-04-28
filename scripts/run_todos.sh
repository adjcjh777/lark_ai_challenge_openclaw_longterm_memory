#!/bin/bash
# run_todos.sh — 从 docs/TODO.md 子任务文档自动执行所有 TODO
# 每个任务在独立的 tmux 窗口中运行，完成后自动关闭窗口
#
# 用法:
#   ./scripts/run_todos.sh                    # 执行所有 TODO
#   ./scripts/run_todos.sh --todo 1           # 只执行 TODO-1
#   ./scripts/run_todos.sh --todo 3,5         # 只执行 TODO-3 和 TODO-5
#   ./scripts/run_todos.sh --dry-run          # 只列出任务，不执行
#   ./scripts/run_todos.sh --budget 5.00      # 设置每个任务的最大花费

set -euo pipefail

# ============================================================
# 配置
# ============================================================
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TODOS_DIR="$PROJECT_DIR/docs/todos"
TODO_FILE="$PROJECT_DIR/docs/TODO.md"
LOG_DIR="$PROJECT_DIR/.claude-auto-logs"
REPORT_FILE="$LOG_DIR/execution-report.md"
SESSION_NAME="todo-runner"

# 默认配置
MAX_BUDGET_USD="${MAX_BUDGET_USD:-5.00}"
MAX_TURNS="${MAX_TURNS:-30}"
DRY_RUN=false
FILTER_TODOS=""
MODEL="${CLAUDE_MODEL:-}"

# ============================================================
# 如果不在 tmux 中，自动创建 tmux session 并重新执行
# ============================================================
if [ -z "${TMUX:-}" ]; then
  echo "未在 tmux 中，自动创建 session: $SESSION_NAME"
  # 传递所有原始参数
  exec tmux new-session -s "$SESSION_NAME" -n "main" \
    "cd '$PROJECT_DIR' && '$0' $*"
fi

# ============================================================
# 参数解析
# ============================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --todo)    FILTER_TODOS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --budget)  MAX_BUDGET_USD="$2"; shift 2 ;;
    --turns)   MAX_TURNS="$2"; shift 2 ;;
    --model)   MODEL="$2"; shift 2 ;;
    --help|-h)
      echo "用法: $0 [选项]"
      echo ""
      echo "选项:"
      echo "  --todo NUMS    只执行指定的 TODO（逗号分隔，如 1,3,5）"
      echo "  --dry-run      只列出任务，不执行"
      echo "  --budget USD   每个任务的最大花费（默认 $MAX_BUDGET_USD）"
      echo "  --turns N      每个任务的最大轮次（默认 $MAX_TURNS）"
      echo "  --model MODEL  指定 Claude 模型"
      echo "  --help         显示帮助"
      exit 0
      ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

# ============================================================
# 任务定义
# ============================================================
declare -a TASK_IDS=()
declare -a TASK_NAMES=()
declare -a TASK_DOCS=()
declare -a TASK_PROMPTS=()

TASK_IDS+=(1)
TASK_NAMES+=("打通飞书 DM 到 memory.* tool routing")
TASK_DOCS+=("TODO-1-feishu-dm-routing.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-1-feishu-dm-routing.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(2)
TASK_NAMES+=("接真实 Feishu API 拉取")
TASK_DOCS+=("TODO-2-feishu-api-pull.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-2-feishu-api-pull.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(3)
TASK_NAMES+=("扩大 Benchmark 规模")
TASK_DOCS+=("TODO-3-expand-benchmark.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-3-expand-benchmark.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(4)
TASK_NAMES+=("配置真实 Cognee 运行")
TASK_DOCS+=("TODO-4-real-cognee.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-4-real-cognee.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(5)
TASK_NAMES+=("配置真实 Embedding 服务")
TASK_DOCS+=("TODO-5-real-embedding.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-5-real-embedding.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(6)
TASK_NAMES+=("补充审计可观测性")
TASK_DOCS+=("TODO-6-audit-observability.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-6-audit-observability.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(7)
TASK_NAMES+=("扩充真实飞书记忆数据")
TASK_DOCS+=("TODO-7-expand-memory-data.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-7-expand-memory-data.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(8)
TASK_NAMES+=("设计 productized live 方案")
TASK_DOCS+=("TODO-8-productized-live.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-8-productized-live.md，执行第一个未完成的子任务。完成后在文档中勾选。")

TASK_IDS+=(10)
TASK_NAMES+=("添加 CI/CD 管道")
TASK_DOCS+=("TODO-10-cicd-pipeline.md")
TASK_PROMPTS+=("阅读 docs/todos/TODO-10-cicd-pipeline.md，执行第一个未完成的子任务。完成后在文档中勾选。")

# ============================================================
# 过滤任务
# ============================================================
if [[ -n "$FILTER_TODOS" ]]; then
  IFS=',' read -ra SELECTED <<< "$FILTER_TODOS"
  FILTERED_IDS=()
  FILTERED_NAMES=()
  FILTERED_DOCS=()
  FILTERED_PROMPTS=()
  for sel in "${SELECTED[@]}"; do
    sel=$(echo "$sel" | tr -d ' ')
    for i in "${!TASK_IDS[@]}"; do
      if [[ "${TASK_IDS[$i]}" == "$sel" ]]; then
        FILTERED_IDS+=("${TASK_IDS[$i]}")
        FILTERED_NAMES+=("${TASK_NAMES[$i]}")
        FILTERED_DOCS+=("${TASK_DOCS[$i]}")
        FILTERED_PROMPTS+=("${TASK_PROMPTS[$i]}")
      fi
    done
  done
  TASK_IDS=("${FILTERED_IDS[@]}")
  TASK_NAMES=("${FILTERED_NAMES[@]}")
  TASK_DOCS=("${FILTERED_DOCS[@]}")
  TASK_PROMPTS=("${FILTERED_PROMPTS[@]}")
fi

TOTAL=${#TASK_IDS[@]}

# ============================================================
# 辅助函数
# ============================================================
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ============================================================
# 主流程
# ============================================================
mkdir -p "$LOG_DIR"

# 设置 tmux：窗口关闭时不保留，自动切换到上一个窗口
tmux set-option -g remain-on-exit off 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Feishu Memory Copilot — 自动化 TODO 执行器        ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  项目目录: $PROJECT_DIR"
echo "║  任务数量: $TOTAL"
echo "║  每任务预算: \$${MAX_BUDGET_USD}"
echo "║  最大轮次: ${MAX_TURNS}"
echo "║  tmux session: $SESSION_NAME"
echo "║  Dry Run:  ${DRY_RUN}"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if [[ $TOTAL -eq 0 ]]; then
  echo "没有要执行的任务。"
  exit 0
fi

echo "待执行任务:"
for i in "${!TASK_IDS[@]}"; do
  echo "  TODO-${TASK_IDS[$i]}: ${TASK_NAMES[$i]}"
done
echo ""

if $DRY_RUN; then
  echo "[dry-run] 以上任务不会被执行。"
  exit 0
fi

# ============================================================
# 顺序执行（每个任务一个 tmux 窗口，完成后自动关闭）
# ============================================================
PASSED=0
FAILED=0
SKIPPED=0
START_ALL=$(date +%s)

cat > "$REPORT_FILE" << EOF
# 自动化执行报告

执行时间: $(date '+%Y-%m-%d %H:%M:%S')
项目目录: $PROJECT_DIR

| # | 任务 | 状态 | 耗时 | 费用 | 日志 |
|---|------|------|------|------|------|
EOF

for i in "${!TASK_IDS[@]}"; do
  TASK_ID="${TASK_IDS[$i]}"
  TASK_NAME="${TASK_NAMES[$i]}"
  TASK_DOC="${TASK_DOCS[$i]}"
  TASK_PROMPT="${TASK_PROMPTS[$i]}"
  LOG_FILE="$LOG_DIR/todo-${TASK_ID}.log"
  JSON_FILE="$LOG_DIR/todo-${TASK_ID}.json"
  SIGNAL="todo-${TASK_ID}-done"

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  log "TODO-${TASK_ID}: ${TASK_NAME}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # 检查子任务文档是否存在
  if [[ ! -f "$TODOS_DIR/$TASK_DOC" ]]; then
    log "⚠️  子任务文档不存在，跳过"
    SKIPPED=$((SKIPPED + 1))
    echo "| ${TASK_ID} | ${TASK_NAME} | ⏭️ 跳过 | - | - | 文档不存在 |" >> "$REPORT_FILE"
    continue
  fi

  # 检查是否所有子任务都已完成
  UNCHECKED=$(grep -c '\- \[ \]' "$TODOS_DIR/$TASK_DOC" 2>/dev/null || true)
  UNCHECKED=$(echo "$UNCHECKED" | tr -d '[:space:]')
  UNCHECKED=${UNCHECKED:-0}
  CHECKED=$(grep -c '\- \[x\]' "$TODOS_DIR/$TASK_DOC" 2>/dev/null || true)
  CHECKED=$(echo "$CHECKED" | tr -d '[:space:]')
  CHECKED=${CHECKED:-0}
  if [[ "$UNCHECKED" == "0" ]] && [[ "$CHECKED" != "0" ]]; then
    log "✅ 所有子任务已完成（${CHECKED} 个已勾选），跳过"
    SKIPPED=$((SKIPPED + 1))
    echo "| ${TASK_ID} | ${TASK_NAME} | ✅ 已完成 | - | - | - |" >> "$REPORT_FILE"
    continue
  fi

  log "🚀 在 tmux 窗口 [todo-${TASK_ID}] 中启动..."

  START_TIME=$(date +%s)

  # 构建 prompt 写入临时文件
  PROMPT_FILE=$(mktemp)
  cat > "$PROMPT_FILE" << PROMPT_EOF
你正在执行飞书 Memory Copilot 项目的自动化任务。

项目目录: $PROJECT_DIR
当前任务: TODO-${TASK_ID} — ${TASK_NAME}
子任务文档: docs/todos/${TASK_DOC}

执行规则:
1. 先阅读子任务文档，理解所有子任务
2. 执行第一个未完成的子任务（标记为 [ ] 的第一项）
3. 完成后，在子任务文档中将该项从 - [ ] 改为 - [x]
4. 运行相关验证命令确认结果
5. 如果遇到无法解决的依赖或外部条件不满足，记录问题但不要跳过

${TASK_PROMPT}
PROMPT_EOF

  # 构建 claude 命令
  CLAUDE_CMD="claude -p \"\$(cat '$PROMPT_FILE')\" \
    --allowedTools Bash Read Edit Write Glob Grep Agent \
    --permission-mode acceptEdits \
    --output-format json \
    --max-budget-usd '$MAX_BUDGET_USD' \
    --max-turns '$MAX_TURNS'"
  if [[ -n "$MODEL" ]]; then
    CLAUDE_CMD+=" --model '$MODEL'"
  fi

  # 在新 tmux 窗口中执行 claude，完成后发信号并自动退出
  tmux new-window -t "$SESSION_NAME" -n "todo-${TASK_ID}" \
    "{ $CLAUDE_CMD > '$JSON_FILE' 2>'$LOG_FILE'; EXIT_CODE=\$?; \
       if [ \$EXIT_CODE -eq 0 ]; then \
         echo '✅ TODO-${TASK_ID} 完成'; \
       else \
         echo '❌ TODO-${TASK_ID} 失败 (exit: '\$EXIT_CODE')'; \
       fi; \
       tmux wait-for -S '$SIGNAL'; \
       sleep 3; }"

  # 主窗口阻塞等待任务完成信号
  log "⏳ 等待 todo-${TASK_ID} 窗口完成..."
  tmux wait-for "$SIGNAL"

  END_TIME=$(date +%s)
  DURATION=$((END_TIME - START_TIME))

  # 检查结果
  if [[ -f "$JSON_FILE" ]] && jq -e '.result' "$JSON_FILE" >/dev/null 2>&1; then
    COST=$(jq -r '.total_cost_usd // "N/A"' "$JSON_FILE" 2>/dev/null || echo "N/A")
    log "✅ 完成 (${DURATION}s, \$${COST})"
    PASSED=$((PASSED + 1))
    echo "| ${TASK_ID} | ${TASK_NAME} | ✅ 成功 | ${DURATION}s | \$${COST} | [log](../.claude-auto-logs/todo-${TASK_ID}.json) |" >> "$REPORT_FILE"
  else
    COST="N/A"
    if [[ -f "$JSON_FILE" ]]; then
      COST=$(jq -r '.total_cost_usd // "N/A"' "$JSON_FILE" 2>/dev/null || echo "N/A")
    fi
    log "❌ 失败 (${DURATION}s)"
    log "   详见: $LOG_FILE"
    FAILED=$((FAILED + 1))
    echo "| ${TASK_ID} | ${TASK_NAME} | ❌ 失败 | ${DURATION}s | \$${COST} | [log](../.claude-auto-logs/todo-${TASK_ID}.json) |" >> "$REPORT_FILE"
  fi

  rm -f "$PROMPT_FILE"

  # 任务间等待
  sleep 2
done

# ============================================================
# 汇总
# ============================================================
END_ALL=$(date +%s)
TOTAL_DURATION=$((END_ALL - START_ALL))
TOTAL_MINUTES=$((TOTAL_DURATION / 60))

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    执行总结                              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  总任务:  $TOTAL"
echo "║  成功:    $PASSED"
echo "║  失败:    $FAILED"
echo "║  跳过:    $SKIPPED"
echo "║  总耗时:  ${TOTAL_MINUTES}m ${TOTAL_DURATION}s"
echo "║  报告:    $REPORT_FILE"
echo "╚══════════════════════════════════════════════════════════╝"

cat >> "$REPORT_FILE" << EOF

## 总结

- 总任务: $TOTAL
- 成功: $PASSED
- 失败: $FAILED
- 跳过: $SKIPPED
- 总耗时: ${TOTAL_MINUTES}m ${TOTAL_DURATION}s
EOF

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
