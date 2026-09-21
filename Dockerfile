FROM alpine:3.22
ARG XRAY_VERSION=26.9.9
RUN apk add --no-cache ca-certificates curl unzip nginx python3 \
    && mkdir -p /opt/xray /etc/xray /run/nginx /tmp/vless-data \
    && curl -fsSL "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip" -o /tmp/xray.zip \
    && unzip -q /tmp/xray.zip xray -d /opt/xray \
    && chmod 0755 /opt/xray/xray \
    && rm -f /tmp/xray.zip
COPY config.template.json /etc/xray/config.template.json
COPY nginx.conf /etc/nginx/nginx.conf
COPY bot.py /app/bot.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh /app/bot.py
ENV PORT=8080 APP_PORT=8000 XRAY_PORT=10000 WS_PATH=/_mohalamia
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
