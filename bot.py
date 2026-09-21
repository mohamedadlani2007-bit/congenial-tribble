#!/usr/bin/env python3
import base64, html, json, os, signal, subprocess, threading, time, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("APP_PORT", "8000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "mooh2026")
DOMAIN = os.getenv("DOMAIN", "")
WS_PATH = os.getenv("WS_PATH", "/_mohalamia")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
SETUP_FILE = os.getenv("SETUP_FILE", "/tmp/vless-setup.json")
DATA_FILE = os.getenv("USERS_FILE", "/tmp/vless-users.json")
LOCK = threading.RLock()
USERS = {}
BOT_THREAD = None
XRAY_CONFIG = os.getenv("XRAY_LIVE_CONFIG", "/tmp/xray-live.json")
XRAY_PIDFILE = os.getenv("XRAY_PIDFILE", "/tmp/xray.pid")
BASE_CONFIG = os.getenv("XRAY_BASE_CONFIG", "/etc/xray/config.template.json")


def load_setup():
    global DOMAIN, BOT_TOKEN
    try:
        with open(SETUP_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        DOMAIN = saved.get("domain", DOMAIN)
        BOT_TOKEN = saved.get("token", BOT_TOKEN)
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def save_setup():
    os.makedirs(os.path.dirname(SETUP_FILE) or ".", exist_ok=True)
    tmp = SETUP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump({"domain": DOMAIN, "token": BOT_TOKEN}, f)
    os.replace(tmp, SETUP_FILE)


def setup_done():
    return bool(DOMAIN and BOT_TOKEN)


def load_users():
    global USERS
    try:
        with open(DATA_FILE, encoding="utf-8") as f: USERS = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): USERS = {}


def save_users():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(USERS, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def sync_xray():
    try:
        with open(BASE_CONFIG, encoding="utf-8") as f: cfg = json.load(f)
        clients = [{"id": u["uuid"], "level": 0} for u in USERS.values() if u.get("active", True)]
        if not clients: clients = [{"id": "123e4567-e89b-12d3-a456-426614174000", "level": 0}]
        cfg["inbounds"][0]["settings"]["clients"] = clients
        with open(XRAY_CONFIG, "w", encoding="utf-8") as f: json.dump(cfg, f)
        try:
            with open(XRAY_PIDFILE, encoding="utf-8") as f: os.kill(int(f.read().strip()), signal.SIGTERM)
        except (FileNotFoundError, ValueError, ProcessLookupError): pass
        proc = subprocess.Popen(["/opt/xray/xray", "run", "-config", XRAY_CONFIG], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        with open(XRAY_PIDFILE, "w", encoding="utf-8") as f: f.write(str(proc.pid))
    except Exception as e:
        print("xray sync:", e, flush=True)


def ensure_user(chat_id, name=""):
    key = str(chat_id)
    with LOCK:
        if key not in USERS:
            USERS[key] = {"uuid": str(uuid.uuid4()), "name": name or key, "active": True, "created": int(time.time())}
            save_users(); sync_xray()
        return USERS[key]


def dark_file(user):
    host = DOMAIN.replace("https://", "").replace("http://", "").split("/", 1)[0]
    cfg = {"type":"VLESS", "name":"VLESS-" + user["uuid"][:8], "vlessTunnelConfig":{"v2rayConfig":{"host":host,"port":443,"uuid":user["uuid"],"serverNameIndication":"youtube.com","wsPath":WS_PATH,"wsHeaderHost":host}}}
    raw = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
    return "darktunnel://" + base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def vless_link(user):
    host = DOMAIN.replace("https://", "").replace("http://", "").split("/", 1)[0]
    q = urllib.parse.urlencode({"encryption":"none","security":"tls","type":"ws","host":host,"sni":"youtube.com","path":WS_PATH})
    return f"vless://{user['uuid']}@{host}:443?{q}#VLESS-{user['uuid'][:8]}"


def api(method, payload):
    if not BOT_TOKEN: return {}
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=35) as r: return json.loads(r.read())


def send(chat, text, keyboard=None):
    p = {"chat_id":chat, "text":text, "disable_web_page_preview":True}
    if keyboard: p["reply_markup"] = {"inline_keyboard": keyboard}
    return api("sendMessage", p)


def send_document(chat, filename, content, caption):
    boundary = "----VlessBoundary7f3a"
    chunks = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n".encode()]
    chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
    chunks.append(content.encode())
    chunks.append(f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", data=b"".join(chunks), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=35) as r: return json.loads(r.read())


def menu():
    return [[{"text":"إنشاء / رابط جديد","callback_data":"create"},{"text":"ملف Dark Tunnel","callback_data":"file"}], [{"text":"تجديد","callback_data":"renew"},{"text":"توقيف","callback_data":"stop"}], [{"text":"تشغيل","callback_data":"start"},{"text":"حذف","callback_data":"delete"}], [{"text":"حالتي","callback_data":"status"}]]


def user_text(u):
    return f"المستخدم: {u['name']}\nUUID: {u['uuid']}\nالحالة: {'متصل/فعال' if u.get('active') else 'متوقف'}"


def handle_action(chat, action, name="user"):
    key = str(chat)
    if action in ("create", "renew"):
        with LOCK:
            if action == "renew" and key in USERS: USERS[key]["uuid"] = str(uuid.uuid4())
            u = ensure_user(chat, name); u["active"] = True; save_users(); sync_xray()
        send(chat, "تم إنشاء/تجديد الحساب بنجاح.\n\n" + user_text(u) + "\n\nأرسل /file للحصول على ملف Dark Tunnel.", menu())
    elif action == "file":
        u = ensure_user(chat, name)
        if not u.get("active"): return send(chat, "الحساب متوقف. اضغط تشغيل أولًا.", menu())
        dark = dark_file(u)
        caption = "تم إنشاء ملف Dark Tunnel بنجاح ✅\nالمستخدم: " + u["name"] + "\nUUID: " + u["uuid"][:8] + "\nاضغط على الملف لاستيراده في التطبيق."
        send_document(chat, "VLESS-DarkTunnel-" + u["uuid"][:8] + ".dark", dark, caption)
        send(chat, "تم إنشاء الملف بنجاح ✅\n\nنسخة للنسخ اليدوي:\n" + dark, menu())
    elif action == "stop":
        u = ensure_user(chat, name); u["active"] = False; save_users(); sync_xray(); send(chat, "تم توقيف حسابك.", menu())
    elif action == "start":
        u = ensure_user(chat, name); u["active"] = True; save_users(); sync_xray(); send(chat, "تم تشغيل حسابك.", menu())
    elif action == "delete":
        with LOCK: USERS.pop(key, None); save_users(); sync_xray()
        send(chat, "تم حذف حسابك. اضغط إنشاء للحصول على حساب جديد.", menu())
    elif action == "status":
        u = ensure_user(chat, name); send(chat, user_text(u), menu())


def bot_loop():
    offset = 0
    while True:
        try:
            result = api("getUpdates", {"timeout":25, "offset":offset, "allowed_updates":["message","callback_query"]})
            for up in result.get("result", []):
                offset = up["update_id"] + 1
                if "callback_query" in up:
                    cb = up["callback_query"]; api("answerCallbackQuery", {"callback_query_id":cb["id"]})
                    handle_action(cb["message"]["chat"]["id"], cb.get("data", ""), cb["from"].get("first_name", "user")); continue
                msg = up.get("message", {}); chat = msg.get("chat", {}).get("id"); text = (msg.get("text") or "").strip()
                if not chat: continue
                name = msg.get("from", {}).get("first_name", "user")
                if text in ("/start", "/help"): send(chat, "مرحبًا بك في VLESS Bot. استعمل الأزرار لإدارة حسابك وإنشاء ملف Dark Tunnel.", menu())
                elif text in ("/file", "/dark"): handle_action(chat, "file", name)
                elif text == "/vless": handle_action(chat, "file", name)
                elif text == "/new": handle_action(chat, "create", name)
                else: send(chat, "اختر عملية من الأزرار:", menu())
        except Exception as e:
            print("telegram:", e, flush=True); time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def out(self, code, body, typ="text/html; charset=utf-8"):
        self.send_response(code); self.send_header("Content-Type", typ); self.end_headers(); self.wfile.write(body.encode())
    def do_GET(self):
        if self.path == "/health": return self.out(200, "ok", "text/plain")
        if setup_done(): return self.out(200, "تم الاتصال بنجاح ✅", "text/plain; charset=utf-8")
        self.out(200, f"<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><style>body{{font-family:Arial;max-width:560px;margin:45px auto;padding:20px;background:#f4f4f4}}main{{background:white;padding:25px;border-radius:12px}}input{{width:100%;padding:12px;margin:7px 0 15px;box-sizing:border-box}}button{{padding:12px 22px;background:#1769aa;color:white;border:0;border-radius:6px}}</style><main><h2>إعداد VLESS Bot</h2><p>بعد التفعيل أرسل /start للبوت ثم استعمل الأزرار.</p><form method='POST'><label>كلمة سر الإدارة</label><input name='password' type='password' required><label>Telegram Bot Token</label><input name='token' type='password' required><label>الدومين</label><input name='domain' value='{html.escape(DOMAIN)}' required><button>تفعيل البوت</button></form></main></html>")
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0)); d=urllib.parse.parse_qs(self.rfile.read(n).decode())
        if d.get("password",[""])[0] != ADMIN_PASSWORD: return self.out(403,"كلمة السر غير صحيحة","text/plain")
        global DOMAIN, BOT_TOKEN
        DOMAIN=d.get("domain",[""])[0].strip(); BOT_TOKEN=d.get("token",[""])[0].strip()
        if not DOMAIN or not BOT_TOKEN: return self.out(400,"البيانات الناقصة","text/plain")
        save_setup()
        global BOT_THREAD
        if not BOT_THREAD or not BOT_THREAD.is_alive(): BOT_THREAD=threading.Thread(target=bot_loop, daemon=True); BOT_THREAD.start()
        self.out(200,"تم الاتصال بنجاح. افتح Telegram وأرسل /start.","text/plain")


if __name__ == "__main__":
    load_setup()
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True); load_users(); sync_xray()
    if BOT_TOKEN: BOT_THREAD=threading.Thread(target=bot_loop, daemon=True); BOT_THREAD.start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
