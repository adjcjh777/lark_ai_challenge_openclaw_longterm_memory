#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export LARK_CLI_PROFILE="${LARK_CLI_PROFILE:-feishu-ai-challenge}"
export MEMORY_DB_PATH="${MEMORY_DB_PATH:-data/memory.sqlite}"
export MEMORY_DEFAULT_SCOPE="${MEMORY_DEFAULT_SCOPE:-project:feishu_ai_challenge}"
export FEISHU_BOT_MODE="${FEISHU_BOT_MODE:-reply}"

if ! command -v lark-cli >/dev/null 2>&1; then
  echo "lark-cli not found in PATH" >&2
  exit 1
fi

echo "Starting Feishu Memory Bot"
echo "  profile: $LARK_CLI_PROFILE"
echo "  db: $MEMORY_DB_PATH"
echo "  scope: $MEMORY_DEFAULT_SCOPE"
echo "  mode: $FEISHU_BOT_MODE"
echo

python3 -m memory_engine init-db >/dev/null
exec python3 -m memory_engine feishu listen "$@"
