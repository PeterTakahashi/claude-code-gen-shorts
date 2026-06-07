#!/usr/bin/env bash
# Start Qwen3-TTS HTTP server (port 10102, warm-loaded).
# Use --foreground to run in this terminal; default backgrounds via nohup.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LOG="$ROOT/.qwen-tts-server.log"

if [[ "$1" == "--foreground" ]]; then
  exec "$HERE/.venv/bin/python" "$HERE/server.py" --warm
fi

if curl -s --max-time 1 http://127.0.0.1:10102/health 2>/dev/null | grep -q '"status":"ok"'; then
  echo "Qwen TTS server already running on :10102"
  exit 0
fi

nohup "$HERE/.venv/bin/python" "$HERE/server.py" --warm > "$LOG" 2>&1 &
echo "started Qwen TTS server (pid=$!), log: $LOG"
echo "Warm-load takes ~90s. Tail the log to watch."
