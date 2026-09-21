FROM alpine:3.22

ARG XRAY_VERSION=26.9.9
RUN apk add --no-cache ca-certificates curl unzip \
    && mkdir -p /opt/xray /etc/xray \
    && curl -fsSL "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip" -o /tmp/xray.zip \
    && unzip -q /tmp/xray.zip xray -d /opt/xray \
    && chmod 0755 /opt/xray/xray \
    && rm -f /tmp/xray.zip \
    && addgroup -S xray \
    && adduser -S -D -H -s /sbin/nologin -G xray xray \
    && chown -R xray:xray /opt/xray /etc/xray

COPY config.template.json /etc/xray/config.template.json
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

ENV PORT=8080
ENV WS_PATH=/_vless
EXPOSE 8080

USER xray
ENTRYPOINT ["/entrypoint.sh"]
