FROM alpine:3.22

ARG XRAY_VERSION=26.9.9
RUN apk add --no-cache ca-certificates curl unzip nginx python3 \
    && mkdir -p /opt/xray /etc/xray /run/nginx \
    && curl -fsSL "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip" -o /tmp/xray.zip \
    && unzip -q /tmp/xray.zip xray -d /opt/xray \
    && chmod 0755 /opt/xray/xray \
    && rm -f /tmp/xray.zip \
    && addgroup -S app \
    && adduser -S -D -H -s /sbin/nologin -G app app \
    && chown -R app:app /opt/xray /etc/xray /run/nginx

COPY config.template.json /etc/xray/config.template.json
COPY nginx.conf /etc/nginx/nginx.conf
COPY entrypoint.sh /entrypoint.sh
COPY bot.py /app/bot.py
RUN chmod 0755 /entrypoint.sh /app/bot.py

ENV PORT=8080
ENV APP_PORT=8000
ENV XRAY_PORT=10000
ENV WS_PATH=/_vless
EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
