#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export LARK_CLI_PROFILE="${LARK_CLI_PROFILE:-feishu-ai-challenge}"
export MEMORY_DB_PATH="${MEMORY_DB_PATH:-data/memory.sqlite}"
export MEMORY_DEFAULT_SCOPE="${MEMORY_DEFAULT_SCOPE:-project:feishu_ai_challenge}"
export COPILOT_FEISHU_SCOPE="${COPILOT_FEISHU_SCOPE:-$MEMORY_DEFAULT_SCOPE}"
export COPILOT_FEISHU_DEFAULT_ROLES="${COPILOT_FEISHU_DEFAULT_ROLES:-member}"
export COPILOT_FEISHU_ALLOWED_CHAT_QUERY="${COPILOT_FEISHU_ALLOWED_CHAT_QUERY:-Feishu Memory Engine 测试群}"
export COPILOT_FEISHU_ALLOWED_CHAT_IDS="${COPILOT_FEISHU_ALLOWED_CHAT_IDS:-}"
export COPILOT_FEISHU_REVIEWER_OPEN_IDS="${COPILOT_FEISHU_REVIEWER_OPEN_IDS:-}"
export FEISHU_BOT_MODE="${FEISHU_BOT_MODE:-reply}"
export FEISHU_CARD_MODE="${FEISHU_CARD_MODE:-text}"
export FEISHU_CARD_RETRY_COUNT="${FEISHU_CARD_RETRY_COUNT:-3}"
export FEISHU_CARD_TIMEOUT_SECONDS="${FEISHU_CARD_TIMEOUT_SECONDS:-2}"
export FEISHU_LOG_DIR="${FEISHU_LOG_DIR:-logs/feishu-copilot-live}"

if ! command -v lark-cli >/dev/null 2>&1; then
  echo "lark-cli not found in PATH" >&2
  exit 1
fi

if [[ -z "$COPILOT_FEISHU_ALLOWED_CHAT_IDS" && -n "$COPILOT_FEISHU_ALLOWED_CHAT_QUERY" ]]; then
  resolved_chat_id="$(
    lark-cli im +chat-search \
      --profile "$LARK_CLI_PROFILE" \
      --as user \
      --query "$COPILOT_FEISHU_ALLOWED_CHAT_QUERY" \
      --page-size 5 \
      --jq '.data.chats[0].chat_id' 2>/dev/null \
      | tr -d '[:space:]' || true
  )"
  if [[ -n "$resolved_chat_id" && "$resolved_chat_id" != "null" ]]; then
    export COPILOT_FEISHU_ALLOWED_CHAT_IDS="$resolved_chat_id"
  fi
fi

if [[ -z "$COPILOT_FEISHU_ALLOWED_CHAT_IDS" ]]; then
  echo "COPILOT_FEISHU_ALLOWED_CHAT_IDS is required before starting the live sandbox." >&2
  echo "Set it directly, or make sure user auth can search: $COPILOT_FEISHU_ALLOWED_CHAT_QUERY" >&2
  exit 1
fi

if [[ -z "$COPILOT_FEISHU_REVIEWER_OPEN_IDS" ]]; then
  resolved_reviewer_open_id="$(
    lark-cli contact +get-user \
      --profile "$LARK_CLI_PROFILE" \
      --as user \
      --jq '.data.open_id // .data.user.open_id // .open_id // .user.open_id' 2>/dev/null \
      | tr -d '[:space:]' || true
  )"
  if [[ -n "$resolved_reviewer_open_id" && "$resolved_reviewer_open_id" != "null" ]]; then
    export COPILOT_FEISHU_REVIEWER_OPEN_IDS="$resolved_reviewer_open_id"
  fi
fi

if [[ -z "$COPILOT_FEISHU_REVIEWER_OPEN_IDS" ]]; then
  echo "COPILOT_FEISHU_REVIEWER_OPEN_IDS is required for /confirm and /reject." >&2
  echo "Set it to the reviewer open_id; wildcard '*' is only acceptable for throwaway debugging." >&2
  exit 1
fi

echo "Starting Feishu Memory Copilot live sandbox"
echo "  profile: $LARK_CLI_PROFILE"
echo "  db: $MEMORY_DB_PATH"
echo "  scope: $COPILOT_FEISHU_SCOPE"
echo "  roles: $COPILOT_FEISHU_DEFAULT_ROLES"
echo "  allowed chat query: $COPILOT_FEISHU_ALLOWED_CHAT_QUERY"
echo "  allowed chats: configured"
echo "  reviewers: configured"
echo "  mode: $FEISHU_BOT_MODE"
echo "  card mode: $FEISHU_CARD_MODE"
echo "  log dir: $FEISHU_LOG_DIR"
echo

python3 scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
python3 -m memory_engine init-db >/dev/null
exec python3 -m memory_engine copilot-feishu listen "$@"
