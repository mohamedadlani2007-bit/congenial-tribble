#!/bin/sh
set -eu

: "${PORT:=8080}"
: "${WS_PATH:=/_vless}"

if [ -z "${VLESS_UUID:-}" ]; then
  echo "VLESS_UUID is required" >&2
  exit 1
fi

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
  -e "s|__PORT__|$PORT|g" \
  -e "s|__WS_PATH__|$WS_PATH|g" \
  /etc/xray/config.template.json > /tmp/config.json

exec /opt/xray/xray run -config /tmp/config.json
