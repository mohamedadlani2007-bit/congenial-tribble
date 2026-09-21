FROM teddysun/v2ray:latest

# config.json يبقى VLESS المباشر كما أرسله المستخدم.
RUN apk add --no-cache python3

EXPOSE 8080

COPY config.json /etc/v2ray/config.json
COPY bot.py /app/bot.py
COPY start.sh /start.sh
RUN chmod 0755 /start.sh

CMD ["/start.sh"]
