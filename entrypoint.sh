#!/bin/sh
set -eu

: "${PORT:=8080}"
: "${APP_PORT:=8000}"
: "${XRAY_PORT:=10000}"
: "${WS_PATH:=/_vless}"

# Cloud Run must be able to start the HTTP listener even when optional secrets
# were not attached during the first deployment. Production deployments should
# always provide both values through Secret Manager.
if [ -z "${VLESS_UUID:-}" ]; then
  VLESS_UUID="$(cat /proc/sys/kernel/random/uuid)"
  echo "WARNING: VLESS_UUID was not provided; generated an ephemeral UUID." >&2
fi
if [ -z "${ADMIN_PASSWORD:-}" ]; then
  ADMIN_PASSWORD="${SETUP_PASSWORD:-change-me-now}"
  echo "WARNING: ADMIN_PASSWORD was not provided; use Secret Manager in production." >&2
fi
export VLESS_UUID ADMIN_PASSWORD

case "$VLESS_UUID" in
  ????????-????-????-????-????????????) ;;
  *) echo "VLESS_UUID must be a UUID" >&2; exit 1 ;;
esac

case "$WS_PATH" in
  /[A-Za-z0-9._~-]*) ;;
  *) echo "WS_PATH must start with / and contain only URL-safe characters" >&2; exit 1 ;;
esac

sed \
  -e "s|__VLESS_UUID__|$VLESS_UUID|g" \
  -e "s|__PORT__|$XRAY_PORT|g" \
  -e "s|__WS_PATH__|$WS_PATH|g" \
  /etc/xray/config.template.json > /tmp/config.json

/opt/xray/xray run -config /tmp/config.json &
XRAY_PID=$!
python3 /app/bot.py &
BOT_PID=$!
nginx -g 'daemon off;' &
NGINX_PID=$!

trap 'kill "$XRAY_PID" "$BOT_PID" "$NGINX_PID" 2>/dev/null || true' INT TERM EXIT
wait "$NGINX_PID"
