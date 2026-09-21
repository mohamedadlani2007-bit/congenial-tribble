#!/usr/bin/env python3
import html, json, os, threading, time, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("APP_PORT", "8000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "mooh2026")
VLESS_UUID = os.getenv("VLESS_UUID", "123e4567-e89b-12d3-a456-426614174000")
DOMAIN = os.getenv("DOMAIN", "")
WS_PATH = os.getenv("WS_PATH", "/_mohalamia")
ADMIN_CHAT_ID = str(os.getenv("ADMIN_CHAT_ID", "")).strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DATA_DIR = os.getenv("DATA_DIR", "/tmp/vless-data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
LOCK = threading.RLock()
USERS = {}
BOT_THREAD = None


def load_users():
    global USERS
    try:
        with open(USERS_FILE, encoding="utf-8") as f: USERS = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): USERS = {}


def save_users():
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(USERS, f)
    os.replace(tmp, USERS_FILE)


def user_uuid(chat_id):
    # Xray accepts the UUID configured in its single inbound client.
    # Keep the bot link and Xray authorization identical.
    return VLESS_UUID


def link(uid):
    host = DOMAIN.replace("https://", "").replace("http://", "").split("/", 1)[0]
    q = urllib.parse.urlencode({"encryption":"none", "security":"tls", "type":"ws", "host":host, "sni":host, "path":WS_PATH})
    return f"vless://{uid}@{host}:443?{q}#VLESS-{uid[:8]}"


def api(method, payload):
    if not BOT_TOKEN: return {}
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=35) as r: return json.loads(r.read())


def send(chat, text): api("sendMessage", {"chat_id":chat, "text":text, "disable_web_page_preview":True})


def bot_loop():
    offset = 0
    while True:
        try:
            for upd in api("getUpdates", {"timeout":25, "offset":offset}).get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {}); chat = msg.get("chat", {}).get("id"); text = (msg.get("text") or "").strip()
                if not chat: continue
                if text in ("/start", "/help"):
                    send(chat, "أهلًا. أرسل /vless للحصول على رابطك الخاص أو /new لتجديده.")
                elif text in ("/vless", "الرابط"):
                    send(chat, "رابط VLESS الخاص بك:\n\n" + link(user_uuid(chat)) if DOMAIN else "الدومين غير مضبوط.")
                elif text in ("/new", "/renew"):
                    send(chat, "تم تحديث رابط VLESS. بما أن إعداد Xray يستخدم UUID واحدًا، أرسل /vless لاستعمال الرابط الفعّال.")
                elif text == "/status": send(chat, f"VLESS WebSocket\nالدومين: {DOMAIN}\nالمسار: {WS_PATH}\nالمستخدمون: {len(USERS)}")
                else: send(chat, "الأوامر: /vless و /new و /status")
        except Exception as e:
            print(f"telegram: {e}", flush=True); time.sleep(5)


def start_bot(token):
    global BOT_TOKEN, BOT_THREAD
    BOT_TOKEN = token.strip()
    if not BOT_THREAD or not BOT_THREAD.is_alive(): BOT_THREAD = threading.Thread(target=bot_loop, daemon=True); BOT_THREAD.start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def out(self, code, body, typ="text/html; charset=utf-8"):
        self.send_response(code); self.send_header("Content-Type", typ); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body.encode())
    def do_GET(self):
        if self.path == "/health": return self.out(200, "ok", "text/plain")
        self.out(200, f"""<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><style>body{{font-family:Arial;max-width:560px;margin:45px auto;padding:20px;background:#f4f4f4}}main{{background:white;padding:25px;border-radius:12px}}input{{width:100%;padding:12px;margin:7px 0 15px;box-sizing:border-box}}button{{padding:12px 22px;background:#1769aa;color:white;border:0;border-radius:6px}}</style><main><h2>إعداد VLESS Bot</h2><p>نفس تدفق المشروع الأصلي، لكن الرابط الناتج VLESS.</p><form method='POST'><label>كلمة سر الإدارة</label><input name='password' type='password' required><label>Telegram Bot Token</label><input name='token' type='password' required><label>الدومين</label><input name='domain' value='{html.escape(DOMAIN)}' required><label>Admin Chat ID اختياري</label><input name='chat_id' value='{html.escape(ADMIN_CHAT_ID)}'><button>تفعيل البوت</button></form></main></html>""")
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0)); d=urllib.parse.parse_qs(self.rfile.read(n).decode())
        if not ADMIN_PASSWORD or d.get("password",[""])[0] != ADMIN_PASSWORD: return self.out(403,"كلمة السر غير صحيحة","text/plain")
        global DOMAIN, ADMIN_CHAT_ID
        DOMAIN=d.get("domain",[""])[0].strip(); ADMIN_CHAT_ID=d.get("chat_id",[""])[0].strip(); token=d.get("token",[""])[0].strip()
        if not DOMAIN or not token: return self.out(400,"البيانات ناقصة","text/plain")
        start_bot(token); self.out(200,"تم تفعيل البوت بنجاح. أرسل /vless للحصول على رابط VLESS.","text/plain")


if __name__ == "__main__":
    load_users()
    if BOT_TOKEN: start_bot(BOT_TOKEN)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
