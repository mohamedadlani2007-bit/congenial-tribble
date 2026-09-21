#!/bin/sh
set -eu

# The V2Ray config, port, path and fixed UUID remain unchanged.
# Telegram bot settings are optional environment variables.
if command -v python3 >/dev/null 2>&1; then
  python3 /app/bot.py &
  BOT_PID=$!
else
  echo 'python3 is unavailable; starting V2Ray only' >&2
  BOT_PID=''
fi

cleanup() {
  if [ -n "$BOT_PID" ]; then kill "$BOT_PID" 2>/dev/null || true; fi
}
trap cleanup INT TERM EXIT

exec v2ray run -config /etc/v2ray/config.json
