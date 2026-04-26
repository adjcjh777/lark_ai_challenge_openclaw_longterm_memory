#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-qwen3-embedding:0.6b-fp16}"

if ! command -v ollama >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Ollama is not installed and Homebrew is unavailable. Install Ollama from https://ollama.com/download and rerun this script." >&2
    exit 1
  fi
  HOMEBREW_NO_AUTO_UPDATE=1 brew install ollama
fi

if ! pgrep -x ollama >/dev/null 2>&1; then
  ollama serve >/tmp/feishu-memory-copilot-ollama.log 2>&1 &
  sleep 3
fi

ollama pull "$MODEL"
python3 scripts/check_embedding_provider.py --model "ollama/$MODEL" --dimensions 1024
