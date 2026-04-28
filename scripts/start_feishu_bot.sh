#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export LARK_CLI_PROFILE="${LARK_CLI_PROFILE:-feishu-ai-challenge}"
export MEMORY_DB_PATH="${MEMORY_DB_PATH:-data/memory.sqlite}"
export MEMORY_DEFAULT_SCOPE="${MEMORY_DEFAULT_SCOPE:-project:feishu_ai_challenge}"
export FEISHU_BOT_MODE="${FEISHU_BOT_MODE:-reply}"
export FEISHU_CARD_MODE="${FEISHU_CARD_MODE:-interactive}"
export FEISHU_CARD_RETRY_COUNT="${FEISHU_CARD_RETRY_COUNT:-3}"
export FEISHU_CARD_TIMEOUT_SECONDS="${FEISHU_CARD_TIMEOUT_SECONDS:-2}"
export FEISHU_LOG_DIR="${FEISHU_LOG_DIR:-logs/feishu-bot}"

if ! command -v lark-cli >/dev/null 2>&1; then
  echo "lark-cli not found in PATH" >&2
  exit 1
fi

echo "Starting Feishu Memory Bot"
echo "  profile: $LARK_CLI_PROFILE"
echo "  db: $MEMORY_DB_PATH"
echo "  scope: $MEMORY_DEFAULT_SCOPE"
echo "  mode: $FEISHU_BOT_MODE"
echo "  card mode: $FEISHU_CARD_MODE"
echo "  card retry/per-attempt-timeout: $FEISHU_CARD_RETRY_COUNT / ${FEISHU_CARD_TIMEOUT_SECONDS}s"
echo "  log dir: $FEISHU_LOG_DIR"
echo

python3 scripts/check_feishu_listener_singleton.py --planned-listener legacy-lark-cli
python3 -m memory_engine init-db >/dev/null
exec python3 -m memory_engine feishu listen "$@"
