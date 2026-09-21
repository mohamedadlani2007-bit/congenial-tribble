#!/usr/bin/env python3
import html
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("APP_PORT", "8000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DOMAIN = os.getenv("DOMAIN", "")
WS_PATH = os.getenv("WS_PATH", "/_vless")
VLESS_UUID = os.getenv("VLESS_UUID", "")
ADMIN_CHAT_ID = str(os.getenv("ADMIN_CHAT_ID", "")).strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BOT_LOCK = threading.Lock()
BOT_THREAD = None
STOP_EVENT = threading.Event()


def vless_uri(domain: str) -> str:
    host = domain.strip().replace("https://", "").replace("http://", "").split("/", 1)[0]
    query = urllib.parse.urlencode({
        "encryption": "none",
        "security": "tls",
        "type": "ws",
        "host": host,
        "path": WS_PATH,
        "sni": host,
    })
    return f"vless://{VLESS_UUID}@{host}:443?{query}#VLESS-Cloud-Run"


def telegram(method, payload=None):
    if not BOT_TOKEN:
        return {}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read().decode())


def allowed(chat_id):
    return not ADMIN_CHAT_ID or str(chat_id) == ADMIN_CHAT_ID


def send_message(chat_id, text):
    telegram("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})


def bot_loop():
    offset = 0
    while not STOP_EVENT.is_set():
        try:
            result = telegram("getUpdates", {"timeout": 25, "offset": offset})
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = (message.get("text") or "").strip()
                if not chat_id or not allowed(chat_id):
                    continue
                if text in ("/start", "/help", "مساعدة"):
                    send_message(chat_id, "بوت VLESS جاهز. استعمل /vless لإظهار رابط الاتصال أو /status لعرض الحالة.")
                elif text in ("/vless", "VLESS", "الرابط"):
                    if not DOMAIN or not VLESS_UUID:
                        send_message(chat_id, "الإعداد غير مكتمل: أضف DOMAIN وVLESS_UUID.")
                    else:
                        send_message(chat_id, "رابط VLESS الخاص بك:\n\n" + vless_uri(DOMAIN))
                elif text in ("/status", "الحالة"):
                    send_message(chat_id, f"الخدمة: VLESS WebSocket\nالدومين: {DOMAIN or 'غير مضبوط'}\nالمسار: {WS_PATH}\nالحالة: تعمل")
                else:
                    send_message(chat_id, "الأوامر المتاحة: /vless و /status و /help")
        except Exception:
            time.sleep(5)


def start_bot(token):
    global BOT_TOKEN, BOT_THREAD
    with BOT_LOCK:
        BOT_TOKEN = token.strip()
        if BOT_THREAD and BOT_THREAD.is_alive():
            return
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(target=bot_loop, daemon=True)
        BOT_THREAD.start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def response(self, status, body, content_type="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path == "/health":
            self.response(200, "ok", "text/plain; charset=utf-8")
            return
        configured = bool(BOT_TOKEN and DOMAIN and VLESS_UUID)
        state = "مُفعّل" if configured else "يحتاج إعدادًا"
        body = f"""<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>VLESS Bot</title>
        <style>body{{font-family:Arial;max-width:560px;margin:50px auto;padding:20px;background:#f5f5f5}}main{{background:#fff;padding:24px;border-radius:12px}}input{{width:100%;padding:11px;margin:7px 0 15px;box-sizing:border-box}}button{{padding:11px 22px;background:#1769aa;color:white;border:0;border-radius:6px}}</style>
        <main><h2>إعداد بوت VLESS</h2><p>الحالة: <b>{state}</b></p><p>أدخل كلمة سر الإدارة وتوكن Telegram. لا يتم عرض التوكن بعد حفظه.</p>
        <form method='POST'><label>كلمة سر الإدارة</label><input name='password' type='password' required><label>Telegram Bot Token</label><input name='token' type='password' required><label>الدومين</label><input name='domain' value='{html.escape(DOMAIN)}' placeholder='vless.example.com' required><label>Admin Chat ID اختياري</label><input name='chat_id' value='{html.escape(ADMIN_CHAT_ID)}'><button>تفعيل البوت</button></form></main></html>"""
        self.response(200, body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if data.get("password", [""])[0] != ADMIN_PASSWORD or not ADMIN_PASSWORD:
            self.response(403, "كلمة السر غير صحيحة", "text/plain; charset=utf-8")
            return
        global DOMAIN, ADMIN_CHAT_ID
        DOMAIN = data.get("domain", [""])[0].strip()
        ADMIN_CHAT_ID = data.get("chat_id", [""])[0].strip()
        token = data.get("token", [""])[0].strip()
        if not token or not DOMAIN:
            self.response(400, "البيانات ناقصة", "text/plain; charset=utf-8")
            return
        start_bot(token)
        self.response(200, "تم تفعيل البوت. افتح Telegram وأرسل /vless للبوت.", "text/plain; charset=utf-8")


if __name__ == "__main__":
    if not ADMIN_PASSWORD:
        raise SystemExit("ADMIN_PASSWORD is required")
    if BOT_TOKEN:
        start_bot(BOT_TOKEN)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
