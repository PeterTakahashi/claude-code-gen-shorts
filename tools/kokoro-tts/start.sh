#!/usr/bin/env bash
# Start Kokoro-82M HTTP server (port 10103, warm-loaded).
# Use --foreground to run in this terminal; default backgrounds via nohup.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LOG="$ROOT/.kokoro-tts-server.log"

if [[ "$1" == "--foreground" ]]; then
  exec "$HERE/.venv/bin/python" "$HERE/server.py" --warm
fi

if curl -s --max-time 1 http://127.0.0.1:10103/health 2>/dev/null | grep -q '"status":"ok"'; then
  echo "Kokoro TTS server already running on :10103"
  exit 0
fi

nohup "$HERE/.venv/bin/python" "$HERE/server.py" --warm > "$LOG" 2>&1 &
echo "started Kokoro TTS server (pid=$!), log: $LOG"
echo "Warm-load takes ~30s. Tail the log to watch."
