#!/bin/sh
set -eu
: "${PORT:=8080}"
: "${APP_PORT:=8000}"
: "${XRAY_PORT:=10000}"
: "${WS_PATH:=/_mohalamia}"
: "${VLESS_UUID:=123e4567-e89b-12d3-a456-426614174000}"
: "${ADMIN_PASSWORD:=change-me-now}"
export VLESS_UUID ADMIN_PASSWORD
case "$VLESS_UUID" in ????????-????-????-????-????????????) ;; *) echo 'VLESS_UUID invalid' >&2; exit 1;; esac
case "$WS_PATH" in /[A-Za-z0-9._~-]*) ;; *) echo 'WS_PATH invalid' >&2; exit 1;; esac
sed -e "s|__VLESS_UUID__|$VLESS_UUID|g" -e "s|__XRAY_PORT__|$XRAY_PORT|g" -e "s|__WS_PATH__|$WS_PATH|g" /etc/xray/config.template.json > /tmp/xray.json
sed -e "s|__PORT__|$PORT|g" -e "s|__XRAY_PORT__|$XRAY_PORT|g" -e "s|__WS_PATH__|$WS_PATH|g" /etc/nginx/nginx.conf > /tmp/nginx.conf
/opt/xray/xray run -config /tmp/xray.json & XRAY_PID=$!
python3 /app/bot.py & BOT_PID=$!
nginx -c /tmp/nginx.conf -g 'daemon off;' & NGINX_PID=$!
trap 'kill "$XRAY_PID" "$BOT_PID" "$NGINX_PID" 2>/dev/null || true' INT TERM EXIT
sleep 1
kill -0 "$XRAY_PID" "$BOT_PID" "$NGINX_PID"
wait "$NGINX_PID"
