#!/usr/bin/env python3
import html
import json
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("APP_PORT", "8000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DOMAIN = os.getenv("DOMAIN", "")
WS_PATH = os.getenv("WS_PATH", "/_vless")
ADMIN_CHAT_ID = str(os.getenv("ADMIN_CHAT_ID", "")).strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DATA_DIR = os.getenv("DATA_DIR", "/tmp/vless-data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
LOCK = threading.RLock()
BOT_THREAD = None
STOP = threading.Event()


def load_users():
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            value = json.load(f)
            return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


USERS = load_users()


def save_users():
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(USERS, f, ensure_ascii=False, indent=2)
    os.replace(tmp, USERS_FILE)


def get_user_uuid(chat_id):
    key = str(chat_id)
    with LOCK:
        if key not in USERS:
            USERS[key] = {"uuid": str(uuid.uuid4()), "created_at": int(time.time())}
            save_users()
        return USERS[key]["uuid"]


def vless_uri(user_uuid):
    host = DOMAIN.strip().replace("https://", "").replace("http://", "").split("/", 1)[0]
    query = urllib.parse.urlencode({
        "encryption": "none", "security": "tls", "type": "ws",
        "host": host, "path": WS_PATH, "sni": host,
    })
    return f"vless://{user_uuid}@{host}:443?{query}#VLESS-{user_uuid[:8]}"


def telegram(method, payload=None):
    if not BOT_TOKEN:
        return {}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read().decode())


def send(chat_id, text):
    telegram("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})


def bot_loop():
    offset = 0
    while not STOP.is_set():
        try:
            result = telegram("getUpdates", {"timeout": 25, "offset": offset})
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = (message.get("text") or "").strip()
                if not chat_id:
                    continue
                if text in ("/start", "/help", "مساعدة"):
                    send(chat_id, "أهلًا. استعمل /vless للحصول على رابطك الخاص، أو /status للحالة.")
                elif text in ("/vless", "الرابط"):
                    if not DOMAIN:
                        send(chat_id, "الدومين غير مضبوط بعد.")
                    else:
                        user_uuid = get_user_uuid(chat_id)
                        send(chat_id, "رابط VLESS الخاص بك (UUID مستقل):\n\n" + vless_uri(user_uuid))
                elif text in ("/new", "/renew"):
                    with LOCK:
                        USERS[str(chat_id)] = {"uuid": str(uuid.uuid4()), "created_at": int(time.time())}
                        save_users()
                    send(chat_id, "تم إنشاء UUID جديد لك. أرسل /vless للحصول على الرابط الجديد.")
                elif text in ("/status", "الحالة"):
                    send(chat_id, f"الخدمة: VLESS WebSocket\nالدومين: {DOMAIN or 'غير مضبوط'}\nالمسار: {WS_PATH}\nالمستخدمون: {len(USERS)}")
                elif ADMIN_CHAT_ID and str(chat_id) == ADMIN_CHAT_ID and text == "/users":
                    send(chat_id, f"عدد المستخدمين المسجلين: {len(USERS)}")
                else:
                    send(chat_id, "الأوامر: /vless للحصول على رابطك، /new لتجديد UUID، /status للحالة.")
        except Exception as exc:
            print(f"telegram loop error: {exc}", flush=True)
            time.sleep(5)


def start_bot(token):
    global BOT_TOKEN, BOT_THREAD
    with LOCK:
        BOT_TOKEN = token.strip()
        if BOT_THREAD and BOT_THREAD.is_alive():
            return
        STOP.clear()
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
        body = f"""<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>VLESS Bot</title>
<style>body{{font-family:Arial;max-width:560px;margin:50px auto;padding:20px;background:#f5f5f5}}main{{background:#fff;padding:24px;border-radius:12px}}input{{width:100%;padding:11px;margin:7px 0 15px;box-sizing:border-box}}button{{padding:11px 22px;background:#1769aa;color:#fff;border:0;border-radius:6px}}</style>
<main><h2>إعداد بوت VLESS</h2><p>كل مستخدم يحصل على UUID مستقل. أدخل كلمة سر الإدارة وتوكن Telegram.</p>
<form method='POST'><label>كلمة سر الإدارة</label><input name='password' type='password' required><label>Telegram Bot Token</label><input name='token' type='password' required><label>الدومين</label><input name='domain' value='{html.escape(DOMAIN)}' placeholder='vless.example.com' required><label>Admin Chat ID اختياري</label><input name='chat_id' value='{html.escape(ADMIN_CHAT_ID)}'><button>تفعيل البوت</button></form></main></html>"""
        self.response(200, body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if not ADMIN_PASSWORD or data.get("password", [""])[0] != ADMIN_PASSWORD:
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
        self.response(200, "تم تفعيل البوت. أرسل /vless للبوت للحصول على UUID خاص بك.", "text/plain; charset=utf-8")


if __name__ == "__main__":
    if BOT_TOKEN:
        start_bot(BOT_TOKEN)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
