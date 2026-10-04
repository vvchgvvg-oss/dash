# ============================================================
#  Hup Server — Final v18 (Production Ready)
# ============================================================
from flask import Flask, request, redirect, session, render_template_string, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import requests, sqlite3, os, re, secrets, string, base64, traceback, smtplib, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime, timezone, timedelta
from functools import wraps

# ================== CONFIG ==================
SITE_NAME            = "Hup Server"
SITE_DOMAIN          = "hupserver.com"
SECRET_KEY           = "hup-server-secret-key-2025-change-me"
PANEL_URL            = "https://panel-vex-production.up.railway.app"
PANEL_ADMIN_USERNAME = "VEXpak2008X"
PANEL_ADMIN_PASSWORD = "VEX 2008X"
PANEL_SYNC           = True
TELEGRAM_USER        = "V2X_2"
TELEGRAM_CHANNEL     = "https://t.me/V_P1_V1"
ADMIN_USERNAME       = "vex.com@gmail.com"
ADMIN_PASSWORD       = "Vex@2025#Admin"
STORE_DB             = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storefront.sqlite3")

SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "zmhmdalhmaqy@gmail.com"
SMTP_PASSWORD = "xlpwtovyziehuppu"
SMTP_FROM     = formataddr((f"{SITE_NAME} Team", SMTP_USER))

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=5*1024*1024)

PLANS = {
    'free':      {'name':'Free',       'credits':0,   'ram':'308 Mo', 'disk':'716 Mo',   'cpu':'25%',  'days':4,  'servers':1,  'price':0,     'paid':False},
    'starter':   {'name':'Starter',    'credits':150, 'ram':'1512 Mo','disk':'4098 Mo',  'cpu':'150%', 'days':30, 'servers':3,  'price':2.99,  'paid':True},
    'pro':       {'name':'Pro',        'credits':200, 'ram':'2048 Mo','disk':'8190 Mo',  'cpu':'200%', 'days':30, 'servers':6,  'price':4.99,  'paid':True},
    'advanced':  {'name':'Advanced',   'credits':400, 'ram':'4096 Mo','disk':'16380 Mo', 'cpu':'300%', 'days':30, 'servers':10, 'price':7.99,  'paid':True},
    'expert':    {'name':'Expert',     'credits':600, 'ram':'8190 Mo','disk':'32770 Mo', 'cpu':'500%', 'days':30, 'servers':15, 'price':11.99, 'paid':True},
}

def now(): return datetime.now(timezone.utc).isoformat()

def db():
    con = sqlite3.connect(STORE_DB, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=30000')
    con.execute('PRAGMA synchronous=NORMAL')
    return con

def init_db():
    con = db()
    try:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            balance REAL NOT NULL DEFAULT 0, display_name TEXT,
            avatar TEXT, email TEXT, email_verified INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0, is_banned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS servers(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'Nodejs', description TEXT DEFAULT '',
            plan TEXT NOT NULL, identifier TEXT, panel_username TEXT,
            panel_password TEXT, panel_link TEXT,
            panel_status TEXT NOT NULL DEFAULT 'Active',
            renew_at TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS domains(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, domain TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activity(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, event TEXT NOT NULL,
            detail TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, subject TEXT NOT NULL,
            message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open',
            reply TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS announcements(
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS verifications(
            id INTEGER PRIMARY KEY, email TEXT NOT NULL, code TEXT NOT NULL,
            username TEXT, password_hash TEXT, purpose TEXT NOT NULL DEFAULT 'register',
            used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        ''')
        cols={r['name'] for r in con.execute('PRAGMA table_info(users)').fetchall()}
        for col,typ in [('avatar','TEXT'),('email','TEXT'),
                        ('email_verified','INTEGER NOT NULL DEFAULT 0'),
                        ('is_admin','INTEGER NOT NULL DEFAULT 0'),
                        ('is_banned','INTEGER NOT NULL DEFAULT 0')]:
            if col not in cols: con.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
        scols={r['name'] for r in con.execute('PRAGMA table_info(servers)').fetchall()}
        for col,typ in [('type',"TEXT DEFAULT 'Nodejs'"),('identifier','TEXT'),
                        ('description',"TEXT DEFAULT ''"),('renew_at','TEXT')]:
            if col not in scols: con.execute(f'ALTER TABLE servers ADD COLUMN {col} {typ}')
        admin = con.execute('SELECT id FROM users WHERE username=?',(ADMIN_USERNAME,)).fetchone()
        if not admin:
            con.execute('INSERT INTO users(username,password_hash,plan,display_name,is_admin,created_at) VALUES(?,?,?,?,1,?)',
                        (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 'expert', 'Administrator', now()))
    finally:
        con.close()

init_db()

def current_user():
    if not session.get('user_id'): return None
    con = db()
    try:
        return con.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    finally:
        con.close()

def log(uid,event,detail=''):
    con = db()
    try:
        con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',(uid,event,detail,now()))
    finally:
        con.close()

def notify(uid,message):
    con = db()
    try:
        con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(uid,message,now()))
    finally:
        con.close()

def admin_required(f):
    @wraps(f)
    def wrapper(*a,**kw):
        u=current_user()
        if not u or not u['is_admin']: return redirect('/login')
        return f(*a,**kw)
    return wrapper

def login_required(f):
    @wraps(f)
    def wrapper(*a,**kw):
        if not current_user(): return redirect('/login')
        return f(*a,**kw)
    return wrapper

def count_user_servers(uid):
    con = db()
    try:
        r = con.execute('SELECT COUNT(*) FROM servers WHERE user_id=?',(uid,)).fetchone()
        return r[0] if r else 0
    finally:
        con.close()

# ================== PROFESSIONAL EMAIL ==================
def send_verification_email(to_email, code):
    text = f"""{SITE_NAME}

Verify your email address

Your verification code is: {code}

This code will expire in 15 minutes.

If you didn't create an account, you can ignore this email.

—
{SITE_NAME} · Enterprise hosting infrastructure
https://{SITE_DOMAIN}
Support: https://t.me/V_P1_V1

© 2025 {SITE_NAME}. All rights reserved.
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Verify your email · {SITE_NAME}</title>
</head>
<body style="margin:0;padding:0;background:#07070b;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">
<div style="display:none;font-size:1px;color:#07070b;line-height:1px;max-height:0;overflow:hidden;">Your {SITE_NAME} verification code is {code} — expires in 15 minutes.</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#07070b;padding:56px 24px;">
<tr><td align="center">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;">

<tr><td align="left" style="padding-bottom:40px;">
<table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
<td style="vertical-align:middle;">
<div style="width:42px;height:42px;background:linear-gradient(135deg,#8b5cf6 0%,#a78bfa 100%);border-radius:11px;color:#fff;font-size:20px;font-weight:800;line-height:42px;text-align:center;font-family:Arial,sans-serif;">H</div>
</td>
<td style="vertical-align:middle;padding-left:14px;">
<div style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.4px;line-height:1.2;">{SITE_NAME}</div>
<div style="color:#5a5a72;font-size:11px;font-weight:500;letter-spacing:0.4px;line-height:1.4;text-transform:uppercase;">Cloud Infrastructure</div>
</td>
</tr></table>
</td></tr>

<tr><td style="background:#0f0f18;border:1px solid #1f1f2a;border-radius:20px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,0.5);">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td style="height:1px;background:linear-gradient(90deg,transparent,rgba(139,92,246,0.6),transparent);"></td></tr></table>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="padding:52px 44px 44px;">

<tr><td align="center" style="padding-bottom:24px;">
<div style="width:64px;height:64px;background:linear-gradient(135deg,rgba(139,92,246,0.2),rgba(139,92,246,0.05));border:1px solid rgba(139,92,246,0.35);border-radius:16px;color:#a78bfa;font-size:28px;line-height:64px;text-align:center;">✉</div>
</td></tr>

<tr><td align="center" style="padding-bottom:12px;">
<div style="color:#ffffff;font-size:28px;font-weight:700;letter-spacing:-0.7px;line-height:1.2;">Verify your email</div>
</td></tr>

<tr><td align="center" style="padding-bottom:36px;">
<div style="color:#8b8ba0;font-size:15px;line-height:1.7;">Welcome to {SITE_NAME}! Use the verification code below to confirm your email address and activate your account.</div>
</td></tr>

<tr><td align="center" style="padding-bottom:32px;">
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(135deg,rgba(139,92,246,0.15) 0%,rgba(139,92,246,0.05) 100%);border:1px solid rgba(139,92,246,0.4);border-radius:16px;padding:32px 48px;">
<tr><td align="center">
<div style="color:#6e6e85;font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;padding-bottom:12px;">Verification code</div>
<div style="font-family:'SF Mono','Courier New',monospace;font-size:46px;font-weight:800;color:#a78bfa;letter-spacing:14px;line-height:1;padding-left:14px;">{code}</div>
</td></tr>
</table>
</td></tr>

<tr><td align="center" style="padding-bottom:32px;">
<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);border-radius:10px;padding:14px 20px;color:#fcd34d;font-size:13px;line-height:1.6;display:inline-block;">
⏱ This code will expire in <b style="color:#fbbf24;">15 minutes</b>
</div>
</td></tr>

<tr><td style="border-top:1px solid #1f1f2a;padding-top:28px;">
<div style="color:#5a5a72;font-size:13px;line-height:1.7;text-align:center;">
If you didn't request this code, you can safely ignore this email.
</div>
</td></tr>

</table>
</td></tr>

<tr><td align="center" style="padding-top:32px;">
<div style="margin-bottom:16px;">
<a href="https://t.me/V_P1_V1" style="color:#8b8ba0;font-size:12px;text-decoration:none;padding:0 10px;">Telegram</a>
<span style="color:#3d3d52;">·</span>
<a href="mailto:{SMTP_USER}" style="color:#8b8ba0;font-size:12px;text-decoration:none;padding:0 10px;">Support</a>
</div>
<div style="color:#3d3d52;font-size:11px;line-height:1.6;">
© 2025 {SITE_NAME} · All rights reserved<br>
This is an automated message, please do not reply.
</div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Verify your email · {SITE_NAME}"
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    msg['Reply-To'] = SMTP_USER
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

def gen_code(): return ''.join(random.choices(string.digits, k=6))

def save_verification(email, code, username, password_hash, purpose='register'):
    con = db()
    try:
        con.execute('DELETE FROM verifications WHERE email=? AND purpose=?',(email,purpose))
        con.execute('INSERT INTO verifications(email,code,username,password_hash,purpose,created_at) VALUES(?,?,?,?,?,?)',
                    (email,code,username,password_hash,purpose,now()))
    finally:
        con.close()

def check_verification(email, code, purpose='register'):
    con = db()
    try:
        row = con.execute('SELECT * FROM verifications WHERE email=? AND code=? AND purpose=? AND used=0',
                          (email,code,purpose)).fetchone()
        if not row: return None
        created = datetime.fromisoformat(row['created_at'].replace('Z','+00:00'))
        if datetime.now(timezone.utc) - created > timedelta(minutes=15):
            return None
        return row
    finally:
        con.close()

# ================== PANEL SYNC ==================
def create_site_account_for_server(username, password):
    if not username or not password: return {'created':False, 'user_id':None}
    con = db()
    try:
        existing = con.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
        if existing: return {'created':False, 'user_id':existing['id']}
        try:
            con.execute('INSERT INTO users(username,password_hash,plan,display_name,created_at) VALUES(?,?,?,?,?)',
                        (username, generate_password_hash(password), 'free', username, now()))
            uid = con.execute('SELECT last_insert_rowid()').fetchone()[0]
            return {'created':True, 'user_id':uid}
        except sqlite3.IntegrityError:
            return {'created':False, 'user_id':None}
    finally:
        con.close()

def make_panel_username():
    letters = string.ascii_lowercase
    digits  = string.digits
    letters_part = ''.join(secrets.choice(letters) for _ in range(8))
    digits_part  = ''.join(secrets.choice(digits) for _ in range(4))
    return 'hup' + letters_part + digits_part

def sanitize_panel_username(raw):
    if not raw: return ''
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', raw)
    if not cleaned: return ''
    if not cleaned[0].isalpha(): cleaned = 'hx' + cleaned
    if not any(c.isalpha() for c in cleaned): cleaned = 'hup' + cleaned
    return cleaned[:32]

def create_panel_account(username, password, max_servers):
    if not PANEL_SYNC:
        return {'success':True,'status':'Active','link':PANEL_URL,'method':'sync-disabled'}
    errors = []
    try:
        client = requests.Session()
        login = client.post(PANEL_URL+'/login',
                            data={'username':PANEL_ADMIN_USERNAME,'password':PANEL_ADMIN_PASSWORD},
                            timeout=20, allow_redirects=False)
        if login.status_code not in (302,303,200):
            return {'success':False,'error':f'Panel admin login failed (HTTP {login.status_code}).'}
        payloads = [
            (PANEL_URL+'/api/users/add',  {'username':username,'password':password,'max_sessions':2,'max_servers':max_servers,'main_file':'main.py'}),
            (PANEL_URL+'/api/users',      {'username':username,'password':password,'max_servers':max_servers}),
            (PANEL_URL+'/users/add',      {'username':username,'password':password,'max_servers':max_servers}),
            (PANEL_URL+'/admin/users/add',{'username':username,'password':password,'max_servers':max_servers}),
            (PANEL_URL+'/register',       {'username':username,'password':password}),
        ]
        for url, data in payloads:
            try:
                r = client.post(url, json=data, timeout=15)
                if r.status_code in (200,201) and ('success' in r.text.lower() or 'created' in r.text.lower()):
                    return {'success':True,'status':'Active','link':PANEL_URL,'method':url}
                if r.status_code in (400,409):
                    try:
                        j = r.json()
                        if j.get('success') is False:
                            if 'exist' in str(j).lower() or 'taken' in str(j).lower():
                                return {'success':True,'status':'Active','link':PANEL_URL,'method':url+'(exists)'}
                            errors.append(f'{url}: {j.get("error","bad request")}')
                    except Exception:
                        errors.append(f'{url}: HTTP {r.status_code}')
            except requests.RequestException as e:
                errors.append(f'{url}: {str(e)[:60]}')
        return {'success':False,'error':'Panel rejected: '+ ' | '.join(errors[:2])}
    except requests.RequestException as e:
        return {'success':False,'error':f'Cannot reach Panel: {str(e)[:80]}'}

def user_data(uid):
    con = db()
    try:
        return (con.execute('SELECT * FROM servers WHERE user_id=? ORDER BY id DESC',(uid,)).fetchall(),
                con.execute('SELECT * FROM domains WHERE user_id=? ORDER BY id DESC',(uid,)).fetchall(),
                con.execute('SELECT * FROM activity WHERE user_id=? ORDER BY id DESC LIMIT 10',(uid,)).fetchall())
    finally:
        con.close()

# ================== ERROR HANDLER ==================
@app.errorhandler(500)
def internal_error(e):
    tb = traceback.format_exc()
    return f"""<html><head><title>Error</title><style>body{{background:#0e0e14;color:#fff;font-family:monospace;padding:20px}}pre{{background:#131319;padding:20px;border-radius:10px;overflow:auto;color:#fca5a5;font-size:12px;line-height:1.6}}</style></head>
<body><h1 style="color:#fca5a5">⚠ Internal Server Error</h1><pre>{tb}</pre><a href="/" style="color:#a78bfa">← Back</a></body></html>""", 500

# ================== CSS ==================
BASE_CSS = r'''
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{overflow-x:hidden;max-width:100vw}
:root{
    --bg:#08080c;--bg-2:#0e0e14;--panel:#131319;--panel-2:#1a1a22;
    --line:#1f1f2a;--line-2:#2a2a38;
    --text:#ffffff;--text-2:#b8b8c4;--muted:#6e6e85;--dim:#3d3d52;
    --purple:#8b5cf6;--purple-2:#a78bfa;--purple-dark:#6d3fdb;
    --green:#22c55e;--red:#ef4444;--gold:#f59e0b;
    --grad:linear-gradient(135deg,#8b5cf6 0%,#a78bfa 100%);
}
html.light{
    --bg:#f7f7fa;--bg-2:#ffffff;--panel:#ffffff;--panel-2:#fafafd;
    --line:#e5e5ec;--line-2:#d4d4de;
    --text:#0a0a0f;--text-2:#4a4a5a;--muted:#78788c;--dim:#a8a8b8;
}
html,body{height:100%}
body{font-family:Inter,system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;font-size:14px;line-height:1.5;letter-spacing:-0.01em;transition:background .2s,color .2s}
a{color:inherit;text-decoration:none}
button,input,select,textarea{font:inherit;color:inherit;background:none;border:0;outline:none}
code{font-family:'SF Mono',Monaco,monospace}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:0;cursor:pointer;border-radius:8px;padding:10px 16px;font-size:13px;font-weight:500;transition:all .15s;white-space:nowrap}
.btn-primary{background:var(--purple);color:#fff}
.btn-primary:hover{background:var(--purple-dark)}
.btn-ghost{background:transparent;color:var(--text-2);border:1px solid var(--line-2)}
.btn-ghost:hover{background:rgba(139,92,246,.06);border-color:var(--purple);color:var(--text)}
.btn-danger{background:transparent;color:var(--red);border:1px solid rgba(239,68,68,.3)}
.btn-danger:hover{background:rgba(239,68,68,.08)}
.btn-success{background:transparent;color:var(--green);border:1px solid rgba(34,197,94,.3)}
.btn-success:hover{background:rgba(34,197,94,.08)}
.btn-tg{background:#229ED9;color:#fff;border:1px solid #229ED9}
.btn-tg:hover{background:#1a89bd}
.btn-sm{padding:6px 12px;font-size:12px;border-radius:6px}
.btn-lg{padding:12px 22px;font-size:14px;border-radius:10px}
.btn-block{width:100%}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px}
.card-lg{padding:28px;border-radius:14px}
.card-title{font-size:15px;font-weight:600;margin-bottom:18px;color:var(--text)}
.field{margin-bottom:16px}
.field label{display:block;font-size:13px;color:var(--text-2);margin-bottom:8px}
.field input,.field select,.field textarea{width:100%;padding:11px 14px;background:var(--bg-2);border:1px solid var(--line);border-radius:8px;color:var(--text);font-size:13px;transition:border-color .15s}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--purple)}
.field input::placeholder{color:var(--dim)}
.field input:disabled,.field input[readonly]{color:var(--text-2);background:var(--panel-2);cursor:not-allowed}
.alert{padding:12px 14px;border-radius:8px;font-size:13px;margin-bottom:16px;border:1px solid}
.alert-error{background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.25);color:#fca5a5}
.alert-success{background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.25);color:#86efac}
.alert-info{background:rgba(139,92,246,.08);border-color:rgba(139,92,246,.25);color:#c4b5fd}
.alert-warning{background:rgba(245,158,11,.08);border-color:rgba(245,158,11,.25);color:#fcd34d}
.badge{display:inline-flex;align-items:center;padding:3px 8px;border-radius:5px;font-size:11px;font-weight:500}
.badge-active{background:rgba(34,197,94,.12);color:#86efac}
.badge-pending{background:rgba(245,158,11,.12);color:#fcd34d}
.badge-off{background:rgba(239,68,68,.12);color:#fca5a5}
.badge-purple{background:rgba(139,92,246,.15);color:#c4b5fd}
.tbl{width:100%;border-collapse:collapse}
.tbl th{text-align:left;padding:12px 14px;font-size:12px;font-weight:500;color:var(--muted);border-bottom:1px solid var(--line)}
.tbl td{padding:14px;font-size:13px;border-bottom:1px solid var(--line);color:var(--text-2)}
.tbl tr:last-child td{border-bottom:0}
.tbl tr:hover td{background:rgba(139,92,246,.02)}
.empty{text-align:center;padding:56px 20px;color:var(--muted)}
.empty svg{opacity:.25;margin-bottom:18px}
.empty p{font-size:13px;margin-bottom:16px}
.bc{font-size:13px;color:var(--muted);margin-bottom:6px}
.bc a{color:var(--muted)}
.bc a:hover{color:var(--purple-2)}
.bc span{color:var(--text-2)}
'''

FAVICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#a78bfa"/></linearGradient></defs><rect width="32" height="32" rx="8" fill="url(#g)"/><path d="M9 9h4v6h6V9h4v14h-4v-6h-6v6H9z" fill="#fff"/></svg>'''
FAVICON_B64 = base64.b64encode(FAVICON_SVG.encode()).decode()

# ================== SHELL ==================
SHELL = r'''<!doctype html><html lang="en" class="{{ 'light' if theme=='light' else '' }}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · Hup Server</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,''' + FAVICON_B64 + r'''">
<style>'''+BASE_CSS+r'''
.app{min-height:100vh;display:flex}
.sidebar{width:240px;position:fixed;top:0;left:0;bottom:0;z-index:60;background:var(--bg-2);border-right:1px solid var(--line);display:flex;flex-direction:column;overflow-y:auto;transition:transform .2s ease}
.sb-head{padding:20px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700}
.brand-logo{width:30px;height:30px;border-radius:7px;display:grid;place-items:center;overflow:hidden;flex-shrink:0}
.brand-logo svg{width:100%;height:100%}
.sb-nav{padding:14px 10px;flex:1}
.nav-group{margin-bottom:22px}
.nav-group-title{font-size:10px;font-weight:600;color:var(--dim);padding:0 12px 8px;text-transform:uppercase;letter-spacing:1.2px}
.nav-item{display:flex;align-items:center;gap:11px;padding:9px 12px;border-radius:7px;color:var(--muted);font-size:13px;font-weight:500;transition:all .15s;margin-bottom:1px;position:relative}
.nav-item:hover{background:rgba(139,92,246,.06);color:var(--text-2)}
.nav-item.active{background:rgba(139,92,246,.1);color:var(--text)}
.nav-item svg{width:17px;height:17px;flex-shrink:0;color:inherit}
.nav-item .nav-badge{background:var(--red);color:#fff;font-size:10px;padding:2px 6px;border-radius:10px;margin-left:auto;font-weight:700}
.sb-foot{padding:14px 10px;border-top:1px solid var(--line)}
.sb-user{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:7px;margin-bottom:4px}
.sb-user:hover{background:rgba(139,92,246,.06)}
.avatar{width:30px;height:30px;border-radius:50%;background:var(--grad);display:grid;place-items:center;font-weight:600;color:#fff;font-size:12px;flex-shrink:0;overflow:hidden}
.avatar img{width:100%;height:100%;object-fit:cover}
.sb-user-info{min-width:0;flex:1}
.sb-user-info b{font-size:12px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-weight:500}
.sb-user-info small{font-size:11px;color:var(--muted);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.main{flex:1;margin-left:240px;min-width:0;background:var(--bg)}
.topbar{height:60px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:50}
.topbar-left{display:flex;align-items:center;gap:14px;min-width:0}
.menu-btn{display:none;width:36px;height:36px;border-radius:7px;background:transparent;border:1px solid var(--line-2);color:var(--text);align-items:center;justify-content:center;cursor:pointer}
.menu-btn:hover{background:rgba(139,92,246,.06)}
.topbar-title{font-size:14px;font-weight:500;color:var(--text)}
.topbar-right{display:flex;align-items:center;gap:8px}
.icon-btn{width:36px;height:36px;border-radius:7px;display:grid;place-items:center;color:var(--muted);cursor:pointer;transition:all .15s;position:relative}
.icon-btn:hover{background:rgba(139,92,246,.06);color:var(--text)}
.icon-btn .dot{position:absolute;top:8px;right:8px;width:8px;height:8px;background:var(--red);border-radius:50%;border:2px solid var(--bg)}
.content{padding:24px;max-width:1400px}
.page-head{margin-bottom:20px}
.page-head h1{font-size:22px;font-weight:600;letter-spacing:-.4px;margin-bottom:4px}
.page-head p{font-size:13px;color:var(--muted)}
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:55}
.overlay.show{display:block}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:20px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px}
.stat-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.stat-label{font-size:12px;color:var(--muted)}
.stat-icon{width:32px;height:32px;border-radius:8px;display:grid;place-items:center;background:rgba(139,92,246,.1);color:var(--purple-2)}
.stat-icon svg{width:16px;height:16px}
.stat-value{font-size:24px;font-weight:600;letter-spacing:-.5px;color:var(--text);margin-bottom:3px}
.stat-sub{font-size:11px;color:var(--muted)}
.res-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:14px}
.res-item{background:var(--bg-2);border:1px solid var(--line);border-radius:8px;padding:12px}
.res-item small{font-size:10px;color:var(--muted);display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:.6px}
.res-item b{font-size:13px;font-weight:500;color:var(--text)}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--line);margin-bottom:22px;overflow-x:auto}
.tab{padding:11px 16px;font-size:13px;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap;background:none}
.tab:hover{color:var(--text-2)}
.tab.active{color:var(--text);border-bottom-color:var(--purple);font-weight:500}
.plan-list{display:flex;flex-direction:column;gap:8px}
.plan-item{display:flex;align-items:center;gap:14px;padding:14px 16px;border:1px solid var(--line);border-radius:9px;cursor:pointer;transition:all .15s;background:var(--bg-2)}
.plan-item:hover{border-color:var(--line-2)}
.plan-item.selected{border-color:var(--purple);background:rgba(139,92,246,.05)}
.plan-item-radio{width:16px;height:16px;border-radius:50%;border:2px solid var(--line-2);display:grid;place-items:center;flex-shrink:0}
.plan-item.selected .plan-item-radio{border-color:var(--purple)}
.plan-item.selected .plan-item-radio::after{content:'';width:7px;height:7px;border-radius:50%;background:var(--purple)}
.plan-item-info{flex:1;min-width:0}
.plan-item-info b{display:block;font-size:13px;font-weight:500;color:var(--text);margin-bottom:2px}
.plan-item-info small{font-size:11px;color:var(--muted);display:block;line-height:1.5}
.plan-item .paid-badge{background:rgba(139,92,246,.15);color:#c4b5fd;font-size:10px;padding:2px 7px;border-radius:5px;margin-left:6px;font-weight:600}
.check{display:flex;align-items:flex-start;gap:10px;font-size:13px;color:var(--text-2);cursor:pointer;margin:16px 0}
.check input[type=checkbox]{appearance:none;width:16px;height:16px;border:1px solid var(--line-2);border-radius:4px;flex-shrink:0;cursor:pointer;position:relative;margin-top:1px;background:var(--bg-2)}
.check input[type=checkbox]:checked{background:var(--purple);border-color:var(--purple)}
.check input[type=checkbox]:checked::after{content:'';position:absolute;left:5px;top:2px;width:4px;height:8px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.check a{color:var(--purple-2)}
.avatar-upload{display:flex;align-items:center;gap:18px;margin-bottom:20px}
.avatar-preview{width:80px;height:80px;border-radius:50%;background:var(--grad);display:grid;place-items:center;color:#fff;font-weight:700;font-size:28px;overflow:hidden;flex-shrink:0}
.avatar-preview img{width:100%;height:100%;object-fit:cover}
.avatar-upload-actions{display:flex;flex-direction:column;gap:8px}
.avatar-upload-actions small{color:var(--muted);font-size:11px}
.ticket-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px;border-bottom:1px solid var(--line)}
.ticket-row:last-child{border-bottom:0}
.announce{background:linear-gradient(135deg,rgba(139,92,246,.1),rgba(139,92,246,.02));border:1px solid rgba(139,92,246,.25);border-radius:10px;padding:16px;margin-bottom:12px}
.announce h3{font-size:14px;font-weight:600;color:var(--text);margin-bottom:6px}
.announce p{font-size:13px;color:var(--text-2);line-height:1.6}
.announce small{font-size:11px;color:var(--muted);display:block;margin-top:8px}
.notif{background:linear-gradient(135deg,rgba(34,158,217,.1),rgba(34,158,217,.02));border:1px solid rgba(34,158,217,.3);border-radius:10px;padding:14px;margin-bottom:10px;display:flex;gap:12px;align-items:flex-start}
.notif svg{color:#229ED9;flex-shrink:0;margin-top:2px}
.notif p{font-size:13px;color:var(--text-2);line-height:1.5}
.notif small{font-size:11px;color:var(--muted);display:block;margin-top:4px}
.cred-box{background:linear-gradient(135deg,rgba(34,197,94,.1),rgba(34,197,94,.02));border:1px solid rgba(34,197,94,.35);border-radius:12px;padding:20px;margin-bottom:18px}
.cred-box h3{color:#86efac;font-size:15px;font-weight:600;margin-bottom:10px}
.cred-box p{font-size:12px;color:var(--muted);margin-bottom:14px}
.cred-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.cred-grid .item{background:rgba(0,0,0,.2);padding:12px;border-radius:8px}
.cred-grid .item small{font-size:10px;color:var(--muted);display:block;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.cred-grid .item b{font-size:13px;color:var(--text);word-break:break-all}
.cred-grid .item a{color:var(--purple-2);font-size:13px}
.admin-actions{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.admin-actions form{display:inline-flex;gap:4px;align-items:center}
.admin-actions input[type=number]{width:64px;padding:6px 8px;background:var(--bg-2);border:1px solid var(--line);border-radius:6px;color:var(--text);font-size:12px}
@media (max-width: 900px){
    .sidebar{transform:translateX(-100%)}.sidebar.open{transform:translateX(0)}
    .main{margin-left:0}.menu-btn{display:flex}.content{padding:18px 14px}
    .topbar{padding:0 14px;height:56px}.page-head h1{font-size:19px}
    .card{padding:16px;border-radius:10px}.card-lg{padding:20px}
    .stats{grid-template-columns:1fr 1fr}.stat{padding:14px}.stat-value{font-size:20px}
    .tbl th,.tbl td{padding:10px 8px;font-size:12px}
    .res-grid{grid-template-columns:1fr 1fr}.tab{padding:10px 12px;font-size:12px}
    .avatar-upload{flex-direction:column;align-items:flex-start}
    .cred-grid{grid-template-columns:1fr}.admin-actions{flex-direction:column;align-items:stretch}
}
</style></head><body>
<div class="app">
    <aside class="sidebar" id="sidebar">
        <div class="sb-head"><div class="brand"><div class="brand-logo">''' + FAVICON_SVG + r'''</div><div>Hup Server</div></div></div>
        <nav class="sb-nav">
            <div class="nav-group"><div class="nav-group-title">Main</div>
                <a class="nav-item {{ 'active' if active=='dashboard' else '' }}" href="/dashboard"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>Dashboard</a>
                <a class="nav-item {{ 'active' if active=='create' else '' }}" href="/servers/create"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Order</a>
                <a class="nav-item {{ 'active' if active=='servers' else '' }}" href="/servers"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="3" width="20" height="6" rx="1.5"/><rect x="2" y="15" width="20" height="6" rx="1.5"/></svg>My servers</a>
                <a class="nav-item {{ 'active' if active=='domains' else '' }}" href="/domains"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>My domains</a>
            </div>
            <div class="nav-group"><div class="nav-group-title">Shop</div>
                <a class="nav-item {{ 'active' if active=='wallet' else '' }}" href="/wallet"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>Buy credits</a>
                <a class="nav-item {{ 'active' if active=='plans' else '' }}" href="/plans"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>Plans</a>
            </div>
            <div class="nav-group"><div class="nav-group-title">Support</div>
                <a class="nav-item {{ 'active' if active=='notifications' else '' }}" href="/notifications"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>Notifications{% if unread_count %}<span class="nav-badge">{{ unread_count }}</span>{% endif %}</a>
                <a class="nav-item {{ 'active' if active=='tickets' else '' }}" href="/tickets"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>My tickets</a>
                <a class="nav-item" href="''' + TELEGRAM_CHANNEL + r'''" target="_blank"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg>Telegram</a>
            </div>
            <div class="nav-group"><div class="nav-group-title">Account</div>
                <a class="nav-item {{ 'active' if active=='settings' else '' }}" href="/settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>Settings</a>
                {% if user['is_admin'] %}<a class="nav-item {{ 'active' if active=='admin' else '' }}" href="/admin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2l3 6 6 1-4.5 4.5L18 20l-6-3-6 3 1.5-6.5L3 9l6-1 3-6z"/></svg>Admin panel</a>{% endif %}
            </div>
        </nav>
        <div class="sb-foot">
            <a class="sb-user" href="/settings"><div class="avatar">{% if user['avatar'] %}<img src="{{ user['avatar'] }}">{% else %}{{ (user['display_name'] or user['username'])[0].upper() }}{% endif %}</div><div class="sb-user-info"><b>{{ user['display_name'] or user['username'] }}</b><small>{{ PLANS[user['plan']].name }}</small></div></a>
            <a class="nav-item" href="/logout"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>Sign out</a>
        </div>
    </aside>
    <div class="overlay" id="overlay" onclick="toggleSide()"></div>
    <main class="main">
        <div class="topbar">
            <div class="topbar-left"><button class="menu-btn" onclick="toggleSide()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg></button><div class="topbar-title">{{ title }}</div></div>
            <div class="topbar-right">
                <a class="icon-btn" href="/notifications" title="Notifications"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>{% if unread_count %}<span class="dot"></span>{% endif %}</a>
                <a class="icon-btn" href="#" onclick="toggleTheme(event)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg></a>
            </div>
        </div>
        <div class="content">{{ body|safe }}</div>
    </main>
</div>
<script>
function toggleSide(){document.getElementById('sidebar').classList.toggle('open');document.getElementById('overlay').classList.toggle('show');}
function toggleTheme(e){e.preventDefault();const h=document.documentElement;h.classList.toggle('light');document.cookie='theme='+(h.classList.contains('light')?'light':'dark')+';path=/;max-age=31536000';}
</script>
</body></html>'''

# ================== WELCOME ==================
WELCOME = r'''<!doctype html><html lang="en" class="{{ 'light' if theme=='light' else '' }}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hup Server — Professional Hosting</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,''' + FAVICON_B64 + r'''">
<style>'''+BASE_CSS+r'''
.nav{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(8,8,12,.85);backdrop-filter:blur(20px);z-index:100}
.nav-logo{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700}
.nav-links{display:flex;align-items:center;gap:24px;font-size:13px}
.nav-links a{color:var(--text-2)}
.nav-links a:hover{color:var(--text)}
.hero{max-width:1100px;margin:0 auto;padding:70px 24px;text-align:center}
.badge-top{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.3);border-radius:30px;font-size:12px;font-weight:500;color:#c4b5fd;margin-bottom:22px}
.badge-top .dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 12px var(--green)}
.hero h1{font-size:clamp(30px,5vw,56px);font-weight:800;line-height:1.15;letter-spacing:-1.5px;margin-bottom:16px}
.hero h1 span{background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:15px;line-height:1.8;color:var(--muted);max-width:580px;margin:0 auto 12px}
.hero-actions{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:28px}
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;max-width:900px;margin:60px auto 0;padding:0 24px}
.stats-row .s{text-align:center}
.stats-row .s b{display:block;font-size:32px;font-weight:800;background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-1px}
.stats-row .s small{color:var(--muted);font-size:12px}
.features{max-width:1100px;margin:0 auto;padding:60px 24px}
.features h2{text-align:center;font-size:28px;font-weight:800;letter-spacing:-1px;margin-bottom:8px;color:var(--text)}
.features .sub{text-align:center;color:var(--text-2);font-size:14px;margin-bottom:44px}
.feat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.feat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;transition:all .15s}
.feat:hover{border-color:var(--purple);transform:translateY(-2px)}
.feat-icon{width:42px;height:42px;border-radius:10px;background:rgba(139,92,246,.12);display:grid;place-items:center;color:var(--purple-2);margin-bottom:16px;font-size:20px}
.feat h3{font-size:15px;font-weight:700;margin-bottom:8px;color:var(--text)}
.feat p{font-size:13px;color:var(--muted);line-height:1.7}
.tg-banner{max-width:1100px;margin:40px auto 0;padding:0 24px}
.tg-card{background:linear-gradient(135deg,rgba(34,158,217,.15),rgba(139,92,246,.1));border:1px solid rgba(34,158,217,.35);border-radius:16px;padding:28px;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.tg-card .info{flex:1;min-width:240px}
.tg-card h3{font-size:18px;font-weight:700;margin-bottom:6px;color:#fff}
.tg-card p{font-size:13px;color:var(--text-2);line-height:1.7}
.tg-card .btn{background:#229ED9;color:#fff;padding:12px 22px;font-size:14px;font-weight:600}
.tg-card .btn:hover{background:#1a89bd}
.faq{max-width:800px;margin:0 auto;padding:60px 24px}
.faq h2{text-align:center;font-size:28px;font-weight:800;letter-spacing:-1px;margin-bottom:44px}
.faq-item{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px 22px;margin-bottom:10px}
.faq-item summary{cursor:pointer;font-size:14px;font-weight:500;color:var(--text);list-style:none;display:flex;justify-content:space-between;align-items:center}
.faq-item summary::-webkit-details-marker{display:none}
.faq-item summary::after{content:'+';font-size:18px;color:var(--purple-2);transition:transform .2s}
.faq-item[open] summary::after{transform:rotate(45deg)}
.faq-item p{margin-top:12px;color:var(--muted);font-size:13px;line-height:1.8}
.foot{border-top:1px solid var(--line);padding:26px;text-align:center;color:var(--dim);font-size:12px}
.foot a{color:var(--purple-2)}
@media(max-width:900px){.hero{padding:50px 20px}.feat-grid{grid-template-columns:1fr}.stats-row{grid-template-columns:1fr 1fr}.nav{padding:0 16px;height:56px}.nav-links a:not(.btn){display:none}.features,.faq,.tg-banner{padding:40px 20px}.tg-card{flex-direction:column;align-items:flex-start}}
</style></head><body>
<nav class="nav">
    <div class="nav-logo"><div class="brand-logo">''' + FAVICON_SVG + r'''</div><div>Hup Server</div></div>
    <div class="nav-links"><a href="#features">Features</a><a href="#faq">FAQ</a><a href="/login">Sign in</a><a class="btn btn-primary" href="/register">Get started</a></div>
</nav>
<section class="hero">
    <div class="badge-top"><span class="dot"></span> The most advanced hosting platform</div>
    <h1>Everything in one place. <span>Unlimited possibilities.</span></h1>
    <p>Smart management for your servers, domains, and resources from a single dashboard.</p>
    <p>Start free and launch your first server in seconds — no credit card required.</p>
    <div class="hero-actions">
        <a class="btn btn-primary btn-lg" href="/register">Create free account</a>
        <a class="btn btn-tg btn-lg" href="''' + TELEGRAM_CHANNEL + r'''" target="_blank">Telegram Channel</a>
    </div>
    <div class="stats-row">
        <div class="s"><b>99.9%</b><small>Uptime</small></div>
        <div class="s"><b>24/7</b><small>Support</small></div>
        <div class="s"><b>&lt;1s</b><small>Deploy time</small></div>
        <div class="s"><b>10K+</b><small>Active servers</small></div>
    </div>
</section>
<div class="tg-banner">
    <div class="tg-card">
        <div class="info"><h3>Join our Telegram Channel</h3><p>Follow the latest offers, updates, and direct support from the Hup Server team.</p></div>
        <a class="btn" href="''' + TELEGRAM_CHANNEL + r'''" target="_blank">Join Now →</a>
    </div>
</div>
<section class="features" id="features">
    <h2>Built to make hosting simpler</h2>
    <p class="sub">Clear interface, powerful tools, faster decisions.</p>
    <div class="feat-grid">
        <div class="feat"><div class="feat-icon">⚡</div><h3>Server Management</h3><p>Create your server, choose a plan and monitor status from a single interface.</p></div>
        <div class="feat"><div class="feat-icon">🌐</div><h3>Domains</h3><p>Order your domain and track its activation status from your account.</p></div>
        <div class="feat"><div class="feat-icon">💎</div><h3>Flexible Plans</h3><p>Start with a free plan and upgrade to Starter, Pro, or Expert anytime.</p></div>
        <div class="feat"><div class="feat-icon">🔒</div><h3>Secure by Default</h3><p>Encrypted credentials and secure infrastructure for peace of mind.</p></div>
        <div class="feat"><div class="feat-icon">💬</div><h3>Ticket Support</h3><p>Our support team is available 24/7 to help you whenever you need.</p></div>
        <div class="feat"><div class="feat-icon">📧</div><h3>Email Verification</h3><p>Secure sign-up with email verification codes for maximum account safety.</p></div>
    </div>
</section>
<section class="faq" id="faq">
    <h2>Frequently Asked Questions</h2>
    <details class="faq-item"><summary>How do I create a server?</summary><p>Sign up for free, verify your email, then go to "Order" and choose your plan. Your server will be ready in seconds.</p></details>
    <details class="faq-item"><summary>What payment methods do you accept?</summary><p>You can pay using credits in your account, or contact us via Telegram to add credits.</p></details>
    <details class="faq-item"><summary>Can I upgrade my plan later?</summary><p>Absolutely. You can upgrade or downgrade at any time from the Plans page.</p></details>
    <details class="faq-item"><summary>Is there a free tier?</summary><p>Yes — the Free plan is free forever with no credit card required.</p></details>
</section>
<footer class="foot">Hup Server © 2025 · All rights reserved · <a href="''' + TELEGRAM_CHANNEL + r'''" target="_blank">Telegram</a></footer>
</body></html>'''

# ================== AUTH ==================
AUTH = r'''<!doctype html><html lang="en" class="{{ 'light' if theme=='light' else '' }}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · Hup Server</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,''' + FAVICON_B64 + r'''">
<style>'''+BASE_CSS+r'''
.wrap{min-height:100vh;display:grid;place-items:center;padding:32px 20px;background:var(--bg);overflow-x:hidden}
.card{width:min(420px,100%);max-width:100%}
.brand{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:700;margin-bottom:28px;justify-content:center}
.brand-logo{width:34px;height:34px}
h1{font-size:22px;font-weight:600;letter-spacing:-.3px;margin-bottom:6px;text-align:center}
.sub{color:var(--muted);font-size:13px;text-align:center;margin-bottom:28px}
.links{text-align:center;margin-top:18px;color:var(--muted);font-size:13px}
.links a{color:var(--purple-2);font-weight:500}
.tg-mini{margin-top:20px;padding-top:20px;border-top:1px solid var(--line);text-align:center;font-size:12px;color:var(--muted)}
.tg-mini a{color:#229ED9;font-weight:600}
</style></head><body>
<div class="wrap">
    <div class="card card-lg">
        <div class="brand"><div class="brand-logo">''' + FAVICON_SVG + r'''</div><div>Hup Server</div></div>
        <h1>{{ 'Create your account' if register else 'Welcome back' }}</h1>
        <p class="sub">{{ 'Start your journey — verify your email to continue' if register else 'Sign in to continue' }}</p>
        {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
        <form method="post">
            <div class="field"><label>Username</label><input name="username" required autofocus autocomplete="username" placeholder="your_username" value="{{ request.form.get('username','') }}"></div>
            <div class="field"><label>Email</label><input type="email" name="email" required autocomplete="email" placeholder="you@example.com" value="{{ request.form.get('email','') }}"></div>
            <div class="field"><label>Password</label><input type="password" name="password" required autocomplete="{{ 'new-password' if register else 'current-password' }}" placeholder="••••••••"></div>
            {% if register %}<div class="field"><label>Confirm password</label><input type="password" name="confirm" required autocomplete="new-password" placeholder="••••••••"></div>{% endif %}
            <button class="btn btn-primary btn-lg btn-block">{{ 'Send verification code' if register else 'Sign in' }}</button>
        </form>
        <div class="links">{% if register %}Already have an account? <a href="/login">Sign in</a>{% else %}Don't have an account? <a href="/register">Create one</a>{% endif %}</div>
        <div class="tg-mini"><a href="''' + TELEGRAM_CHANNEL + r'''" target="_blank">Join our Telegram Channel</a></div>
    </div>
</div>
</body></html>'''

# ================== VERIFY ==================
VERIFY = r'''<!doctype html><html lang="en" class="{{ 'light' if theme=='light' else '' }}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verify Email · Hup Server</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,''' + FAVICON_B64 + r'''">
<style>'''+BASE_CSS+r'''
.wrap{min-height:100vh;display:grid;place-items:center;padding:24px 16px;background:var(--bg);overflow-x:hidden;width:100%}
.card{width:min(440px,100%);max-width:100%}
.brand{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:700;margin-bottom:28px;justify-content:center}
.brand-logo{width:34px;height:34px}
h1{font-size:22px;font-weight:600;letter-spacing:-.3px;margin-bottom:6px;text-align:center}
.sub{color:var(--muted);font-size:13px;text-align:center;margin-bottom:24px;line-height:1.6}
.sub b{color:#a78bfa;display:block;margin-top:4px;word-break:break-all}
.code-inputs{display:flex;gap:8px;justify-content:center;margin:20px 0;width:100%}
.code-inputs input{width:44px;height:52px;text-align:center;font-size:22px;font-weight:700;background:var(--bg-2);border:1px solid var(--line-2);border-radius:10px;color:#fff;transition:all .15s;padding:0;flex-shrink:0}
.code-inputs input:focus{border-color:var(--purple);background:rgba(139,92,246,.08);box-shadow:0 0 0 3px rgba(139,92,246,.15);outline:none}
.links{text-align:center;margin-top:18px;color:var(--muted);font-size:13px}
.links a{color:var(--purple-2);font-weight:500}
@media (max-width:400px){
    .code-inputs{gap:6px}
    .code-inputs input{width:38px;height:46px;font-size:19px}
}
</style></head><body>
<div class="wrap">
    <div class="card card-lg">
        <div class="brand"><div class="brand-logo">''' + FAVICON_SVG + r'''</div><div>Hup Server</div></div>
        <h1>Verify your email</h1>
        <p class="sub">We sent a 6-digit code to<b>{{ email }}</b></p>
        {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
        <form method="post" id="verify-form" autocomplete="off">
            <div class="code-inputs">
                <input type="text" inputmode="numeric" maxlength="1" pattern="[0-9]" required data-idx="0">
                <input type="text" inputmode="numeric" maxlength="1" pattern="[0-9]" required data-idx="1">
                <input type="text" inputmode="numeric" maxlength="1" pattern="[0-9]" required data-idx="2">
                <input type="text" inputmode="numeric" maxlength="1" pattern="[0-9]" required data-idx="3">
                <input type="text" inputmode="numeric" maxlength="1" pattern="[0-9]" required data-idx="4">
                <input type="text" inputmode="numeric" maxlength="1" pattern="[0-9]" required data-idx="5">
            </div>
            <input type="hidden" name="code" id="full-code">
            <button class="btn btn-primary btn-lg btn-block" type="submit" onclick="document.getElementById('full-code').value=[...document.querySelectorAll('.code-inputs input')].map(i=>i.value).join('')">Verify account</button>
        </form>
        <div class="links">Didn't receive it? <a href="/register">Try again</a></div>
    </div>
</div>
<script>
document.addEventListener('DOMContentLoaded',function(){
    var inputs=document.querySelectorAll('.code-inputs input');
    inputs.forEach(function(el,i){
        el.addEventListener('input',function(){
            el.value=el.value.replace(/[^0-9]/g,'');
            if(el.value && i<5){inputs[i+1].focus();}
        });
        el.addEventListener('keydown',function(e){
            if(e.key==='Backspace' && !el.value && i>0){inputs[i-1].focus();}
        });
        el.addEventListener('paste',function(e){
            e.preventDefault();
            var text=(e.clipboardData||window.clipboardData).getData('text').replace(/[^0-9]/g,'').slice(0,6);
            [...text].forEach(function(ch,j){if(inputs[j])inputs[j].value=ch;});
            if(text.length){inputs[Math.min(text.length,5)].focus();}
        });
    });
    if(inputs[0]) inputs[0].focus();
});
</script>
</body></html>'''

def get_unread_count(uid):
    if not uid: return 0
    con = db()
    try:
        r = con.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0',(uid,)).fetchone()
        return r[0] if r else 0
    except Exception:
        return 0
    finally:
        con.close()

def shell(title, body, active='dashboard'):
    u=current_user()
    if not u: return redirect('/login')
    theme=request.cookies.get('theme','dark')
    unread = get_unread_count(u['id'])
    return render_template_string(SHELL,title=title,body=body,user=u,active=active,PLANS=PLANS,theme=theme,unread_count=unread)

def auth_page(register=False):
    error=None
    if request.method=='POST':
        uname=request.form.get('username','').strip()
        email=request.form.get('email','').strip().lower()
        pw=request.form.get('password','')
        if register:
            confirm=request.form.get('confirm','')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}',uname):
                error='Username must be 3-32 characters.'
            elif not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
                error='Please enter a valid email address.'
            elif len(pw)<6:
                error='Password must be at least 6 characters.'
            elif pw != confirm:
                error='Passwords do not match.'
            else:
                con = db()
                try:
                    exists = con.execute('SELECT id FROM users WHERE username=?',(uname,)).fetchone()
                    email_exists = con.execute('SELECT id FROM users WHERE email=? AND email_verified=1',(email,)).fetchone()
                finally:
                    con.close()
                if exists: error='Username is already taken.'
                elif email_exists: error='Email is already registered.'
                else:
                    code = gen_code()
                    pw_hash = generate_password_hash(pw)
                    save_verification(email, code, uname, pw_hash, 'register')
                    ok, err = send_verification_email(email, code)
                    if ok:
                        session['verify_email'] = email
                        session['verify_username'] = uname
                        return redirect('/verify')
                    else:
                        error = f'Failed to send email: {err}'
        else:
            con = db()
            try:
                row=con.execute('SELECT * FROM users WHERE username=? OR email=?',(uname,uname)).fetchone()
            finally:
                con.close()
            if row and row['is_banned']:
                error='This account has been banned.'
            elif row and check_password_hash(row['password_hash'],pw):
                session['user_id']=row['id']; log(row['id'],'Signed in','')
                return redirect('/admin') if row['is_admin'] else redirect('/dashboard')
            else:
                error='Invalid credentials.'
    theme=request.cookies.get('theme','dark')
    return render_template_string(AUTH,title='Create account' if register else 'Sign in',register=register,error=error,theme=theme)

# ================== ROUTES ==================
@app.route('/')
def home(): return redirect('/dashboard' if current_user() else '/welcome')

@app.route('/welcome')
def welcome():
    theme=request.cookies.get('theme','dark')
    return render_template_string(WELCOME,theme=theme)

@app.route('/login',methods=['GET','POST'])
def login(): return auth_page(False)

@app.route('/register',methods=['GET','POST'])
def register(): return auth_page(True)

@app.route('/verify',methods=['GET','POST'])
def verify():
    email = session.get('verify_email')
    uname = session.get('verify_username')
    if not email or not uname:
        return redirect('/register')
    error=None
    if request.method=='POST':
        code = request.form.get('code','').strip()
        if len(code)!=6 or not code.isdigit():
            error='Please enter the 6-digit code.'
        else:
            row = check_verification(email, code, 'register')
            if not row:
                error='Invalid or expired code. Please try again.'
            else:
                con = db()
                try:
                    con.execute('UPDATE verifications SET used=1 WHERE id=?',(row['id'],))
                    con.execute('INSERT INTO users(username,password_hash,plan,display_name,email,email_verified,created_at) VALUES(?,?,?,?,?,1,?)',
                                (uname, row['password_hash'], 'free', uname, email, now()))
                    uid=con.execute('SELECT last_insert_rowid()').fetchone()[0]
                finally:
                    con.close()
                panel_user = sanitize_panel_username(uname)
                panel_result = create_panel_account(panel_user, 'temp123456', 1)
                if panel_result.get('success'):
                    log(uid,'Panel synced',f'Panel user: {panel_user}')
                else:
                    log(uid,'Panel sync failed',panel_result.get('error',''))
                session.pop('verify_email', None)
                session.pop('verify_username', None)
                session['user_id'] = uid
                log(uid,'Account created','Welcome to Hup Server')
                return redirect('/dashboard')
    theme=request.cookies.get('theme','dark')
    return render_template_string(VERIFY, email=email, error=error, theme=theme)

@app.route('/logout')
def logout(): session.clear(); return redirect('/welcome')

# ============ Notifications ============
@app.route('/notifications')
@login_required
def notifications_page():
    u=current_user()
    con = db()
    try:
        notifs = con.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
        con.execute('UPDATE notifications SET is_read=1 WHERE user_id=?',(u['id'],))
    finally:
        con.close()
    body=render_template_string(r'''
    <div class="bc">Home / <span>Notifications</span></div>
    <div class="page-head"><h1>Notifications</h1><p>Messages from the admin team.</p></div>
    <div class="card">
        {% if notifs %}{% for n in notifs %}<div class="notif"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><div style="flex:1"><p>{{ n['message'] }}</p><small>{{ n['created_at'][:19].replace('T',' ') }}</small></div></div>{% endfor %}
        {% else %}<div class="empty"><p>No notifications yet.</p></div>{% endif %}
    </div>
    ''',notifs=notifs)
    return shell('Notifications',body,'notifications')

# ============ Dashboard ============
@app.route('/dashboard')
@login_required
def dashboard():
    u=current_user()
    servers,domains,events=user_data(u['id'])
    con = db()
    try:
        announce=con.execute('SELECT * FROM announcements ORDER BY id DESC LIMIT 1').fetchone()
        open_tickets=con.execute('SELECT COUNT(*) FROM tickets WHERE user_id=? AND status="Open"',(u['id'],)).fetchone()[0]
        recent_notifs=con.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 3',(u['id'],)).fetchall()
    finally:
        con.close()
    server_count = len(servers)
    max_servers = PLANS[u['plan']]['servers'] if u['plan'] in PLANS else 1
    body=render_template_string(r'''
    <div class="bc">Home / <span>Dashboard</span></div>
    <div class="page-head"><h1>Dashboard</h1><p>Welcome back, {{ user['display_name'] or user['username'] }}</p></div>
    {% if recent_notifs %}{% for n in recent_notifs %}<div class="notif"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><div style="flex:1"><p>{{ n['message'] }}</p><small>{{ n['created_at'][:19].replace('T',' ') }}</small></div></div>{% endfor %}{% endif %}
    {% if announce %}<div class="announce"><h3>{{ announce['title'] }}</h3><p>{{ announce['body'] }}</p><small>{{ announce['created_at'][:19].replace('T',' ') }}</small></div>{% endif %}
    <div class="stats">
        <div class="stat"><div class="stat-head"><div class="stat-label">Credits</div><div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg></div></div><div class="stat-value">${{ '%.2f'|format(user['balance']) }}</div><div class="stat-sub">Available balance</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Servers</div><div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="3" width="20" height="6" rx="1.5"/><rect x="2" y="15" width="20" height="6" rx="1.5"/></svg></div></div><div class="stat-value">{{ server_count }}</div><div class="stat-sub">of {{ max_servers }} allowed</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Current plan</div><div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div></div><div class="stat-value" style="font-size:20px">{{ PLANS[user['plan']].name if user['plan'] in PLANS else 'Free' }}</div><div class="stat-sub">Active subscription</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Open tickets</div><div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></div></div><div class="stat-value">{{ open_tickets }}</div><div class="stat-sub">Support</div></div>
    </div>
    <div class="card" style="margin-bottom:18px">
        <div class="card-title">Your servers</div>
        {% if servers %}<div style="overflow-x:auto"><table class="tbl"><thead><tr><th>#</th><th>Name</th><th>Type</th><th>Status</th><th></th></tr></thead><tbody>{% for s in servers[:5] %}<tr><td style="color:var(--muted)">{{ s['id'] }}</td><td style="color:var(--text);font-weight:500">{{ s['name'] }}</td><td>{{ s['type'] }}</td><td><span class="badge badge-active">{{ s['panel_status'] }}</span></td><td style="text-align:right"><a class="btn btn-ghost btn-sm" href="/servers/{{ s['id'] }}">Manage</a></td></tr>{% endfor %}</tbody></table></div>
        {% else %}<div class="empty"><p>You don't have any servers yet.</p><a class="btn btn-primary" href="/servers/create">Create your first server</a></div>{% endif %}
    </div>
    <div class="card">
        <div class="card-title">Recent activity</div>
        {% if events %}<table class="tbl">{% for e in events[:5] %}<tr><td style="color:var(--text);font-weight:500">{{ e['event'] }}</td><td>{{ e['detail'] }}</td><td style="text-align:right;color:var(--muted);font-size:12px">{{ e['created_at'][:19].replace('T',' ') }}</td></tr>{% endfor %}</table>
        {% else %}<div class="empty"><p>No activity yet.</p></div>{% endif %}
    </div>
    ''',user=u,servers=servers,domains=domains,events=events,PLANS=PLANS,announce=announce,open_tickets=open_tickets,recent_notifs=recent_notifs,server_count=server_count,max_servers=max_servers)
    return shell('Dashboard',body,'dashboard')

# ============ Create Server ============
@app.route('/servers/create',methods=['GET','POST'])
@login_required
def server_create():
    u=current_user()
    error=None
    created_creds=None

    user_plan_key = u['plan'] if u['plan'] in PLANS else 'free'
    user_plan = PLANS[user_plan_key]
    max_servers = user_plan['servers']

    if request.method=='POST':
        name=request.form.get('name','').strip()
        stype=request.form.get('type','Nodejs')
        plan=request.form.get('plan','free')
        terms=request.form.get('terms')

        current_count = count_user_servers(u['id'])

        if not name: error='Please enter a server name.'
        elif stype not in ('Nodejs','Python'): error='Invalid server type.'
        elif plan not in PLANS: error='Invalid plan.'
        elif not terms: error='You must accept the terms of use.'
        elif current_count >= max_servers:
            error=f'You have reached the maximum servers ({max_servers}) allowed in your plan. Upgrade to add more.'
        else:
            plan_data = PLANS[plan]
            if plan_data['paid']:
                price = plan_data['price']
                if u['balance'] >= price:
                    con = db()
                    try:
                        con.execute('UPDATE users SET balance=balance-? WHERE id=?',(price,u['id']))
                        con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',
                                    (u['id'],f'Charged ${price:.2f} for {plan_data["name"]} plan.',now()))
                        con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',
                                    (u['id'],'Payment',f'-${price:.2f} for {plan_data["name"]}',now()))
                    finally:
                        con.close()
                else:
                    return redirect(f'https://t.me/{TELEGRAM_USER}')

            raw_user=request.form.get('panel_username','').strip()
            panel_user=sanitize_panel_username(raw_user) if raw_user else make_panel_username()
            panel_password=request.form.get('panel_password','').strip() or secrets.token_urlsafe(10)
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{2,31}', panel_user):
                error='Panel username must start with a letter.'
            elif len(panel_password)<6:
                error='Password must be at least 6 characters.'
            else:
                result=create_panel_account(panel_user,panel_password,PLANS[plan]['servers'])
                if not result['success']: error=result['error']
                else:
                    identifier=secrets.token_hex(6)
                    renew=datetime.now(timezone.utc)+timedelta(days=PLANS[plan]['days'])
                    con = db()
                    try:
                        con.execute('INSERT INTO servers(user_id,name,type,plan,identifier,panel_username,panel_password,panel_link,panel_status,renew_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                    (u['id'],name,stype,plan,identifier,panel_user,panel_password,result['link'],result['status'],renew.isoformat(),now()))
                        sid=con.execute('SELECT last_insert_rowid()').fetchone()[0]
                    finally:
                        con.close()
                    acc = create_site_account_for_server(panel_user, panel_password)
                    if acc['created']:
                        log(acc['user_id'],'Account created','Auto-created from server')
                        log(u['id'],'Site account created',f'Login: {panel_user}')
                    else:
                        log(u['id'],'Site account exists',panel_user)
                    log(u['id'],'Server created',name)
                    session['new_server_creds'] = {
                        'name': name, 'panel_user': panel_user,
                        'panel_password': panel_password,
                        'panel_link': result['link'], 'identifier': identifier,
                    }
                    return redirect(f'/servers/{sid}')

    created_creds = session.pop('new_server_creds', None)
    current_count = count_user_servers(u['id'])

    body=render_template_string(r'''
    <div class="bc"><a href="/servers">My servers</a> / <span>Create server</span></div>
    <div class="page-head"><h1>Create server</h1><p>Paid plans are charged from your balance. If insufficient, you'll be redirected to Telegram.</p></div>

    <div class="stats" style="max-width:620px">
        <div class="stat"><div class="stat-head"><div class="stat-label">Your balance</div></div><div class="stat-value">${{ '%.2f'|format(user['balance']) }}</div><div class="stat-sub">Available credits</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Your plan</div></div><div class="stat-value" style="font-size:20px">{{ user_plan.name }}</div><div class="stat-sub">{{ max_servers }} servers allowed</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Used servers</div></div><div class="stat-value">{{ current_count }} / {{ max_servers }}</div><div class="stat-sub">Create or upgrade</div></div>
    </div>

    {% if creds %}
    <div class="cred-box">
        <h3>✓ Server created successfully!</h3>
        <p>Save these credentials — you can use them to sign in to the site as well.</p>
        <div class="cred-grid">
            <div class="item"><small>Username</small><b>{{ creds.panel_user }}</b></div>
            <div class="item"><small>Password</small><b>{{ creds.panel_password }}</b></div>
            <div class="item"><small>Identifier</small><b>{{ creds.identifier }}</b></div>
            <div class="item"><small>Server Name</small><b>{{ creds.name }}</b></div>
            <div class="item"><small>Panel Link</small><a href="{{ creds.panel_link }}" target="_blank">Open Panel →</a></div>
            <div class="item"><small>Site Login</small><a href="/logout">Try signing in</a></div>
        </div>
    </div>
    {% endif %}

    <div class="card card-lg" style="max-width:620px">
        {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
        <form method="post" id="srv-form">
            <div class="field"><label>Server name</label><input name="name" required value="{{ request.form.get('name','') }}" placeholder="My awesome project"></div>
            <div class="field"><label>Type</label>
                <div class="plan-list">
                    <label class="plan-item {{ 'selected' if request.form.get('type','Nodejs')=='Nodejs' else '' }}">
                        <input type="radio" name="type" value="Nodejs" {{ 'checked' if request.form.get('type','Nodejs')=='Nodejs' else '' }} style="display:none">
                        <div class="plan-item-radio"></div><div class="plan-item-info"><b>Nodejs</b><small>JavaScript runtime — great for web apps and APIs</small></div>
                    </label>
                    <label class="plan-item {{ 'selected' if request.form.get('type')=='Python' else '' }}">
                        <input type="radio" name="type" value="Python" {{ 'checked' if request.form.get('type')=='Python' else '' }} style="display:none">
                        <div class="plan-item-radio"></div><div class="plan-item-info"><b>Python</b><small>Perfect for bots, scripts and data projects</small></div>
                    </label>
                </div>
            </div>
            <div class="field"><label>Resources</label>
                <div class="plan-list" id="plan-list">
                    {% for k,p in PLANS.items() %}
                    <label class="plan-item {{ 'selected' if request.form.get('plan','free')==k else '' }}" data-paid="{{ 'true' if p.paid else 'false' }}" data-price="{{ p.price }}" data-name="{{ p.name }}">
                        <input type="radio" name="plan" value="{{ k }}" {{ 'checked' if request.form.get('plan','free')==k else '' }} style="display:none">
                        <div class="plan-item-radio"></div>
                        <div class="plan-item-info">
                            <b>{{ p.credits }} credits → {{ p.name }}{% if p.paid %}<span class="paid-badge">${{ p.price }}</span>{% endif %}</b>
                            <small>{{ p.ram }} RAM → {{ p.disk }} NVMe → {{ p.cpu }} CPU → Up to {{ p.servers }} servers</small>
                        </div>
                    </label>
                    {% endfor %}
                </div>
            </div>
            <div class="field"><label>Panel username <span style="color:var(--dim)">(optional — must start with a letter)</span></label><input name="panel_username" placeholder="Leave blank to auto-generate" pattern="[A-Za-z][A-Za-z0-9]{2,31}"></div>
            <div class="field"><label>Panel password <span style="color:var(--dim)">(optional)</span></label><input type="password" name="panel_password" placeholder="Leave blank to auto-generate"></div>
            <label class="check"><input type="checkbox" name="terms" required><span>I have read and accept the <a href="#">terms of use</a>.</span></label>
            <button class="btn btn-primary btn-lg btn-block" id="submit-btn">Create server</button>
        </form>
    </div>
    <script>
    var balance = {{ user['balance'] }};
    document.querySelectorAll('.plan-list').forEach(function(list){
        list.querySelectorAll('.plan-item').forEach(function(item){
            item.addEventListener('click',function(e){
                if(e.target.tagName==='INPUT')return;
                var r=item.querySelector('input[type=radio]');
                if(r){
                    r.checked=true;
                    list.querySelectorAll('.plan-item').forEach(function(x){x.classList.remove('selected');});
                    item.classList.add('selected');
                    if(list.id==='plan-list'){
                        var paid=item.dataset.paid==='true';
                        var price=parseFloat(item.dataset.price)||0;
                        var btn=document.getElementById('submit-btn');
                        if(paid){
                            if(balance>=price){
                                btn.textContent='Pay $'+price.toFixed(2)+' & Create';
                                btn.style.background='#22c55e';
                            }else{
                                btn.textContent='Insufficient balance → Telegram';
                                btn.style.background='#229ED9';
                            }
                        }else{
                            btn.textContent='Create server';
                            btn.style.background='';
                        }
                    }
                }
            });
        });
    });
    </script>
    ''',error=error,PLANS=PLANS,creds=created_creds,user=u,user_plan=user_plan,max_servers=max_servers,current_count=current_count)
    return shell('Create server',body,'create')

# ============ Server Detail ============
@app.route('/servers/<int:sid>',methods=['GET','POST'])
@login_required
def server_detail(sid):
    u=current_user()
    con = db()
    try:
        s=con.execute('SELECT * FROM servers WHERE id=? AND user_id=?',(sid,u['id'])).fetchone()
    finally:
        con.close()
    if not s: return redirect('/servers')
    msg=None; tab=request.args.get('tab','general')
    if request.method=='POST':
        action=request.form.get('action')
        con = db()
        try:
            if action=='rename':
                new_name=request.form.get('name','').strip(); desc=request.form.get('description','').strip()
                if new_name:
                    con.execute('UPDATE servers SET name=?,description=? WHERE id=?',(new_name,desc,sid))
                    log(u['id'],'Server updated',new_name); msg='Server updated.'
            elif action=='change_password':
                new_pw=request.form.get('new_password','')
                if len(new_pw)<6: msg='Password must be at least 6 characters.'
                else:
                    con.execute('UPDATE servers SET panel_password=? WHERE id=?',(new_pw,sid))
                    log(u['id'],'Server password changed',s['name']); msg='Password changed.'
            elif action=='change_type':
                new_type=request.form.get('new_type')
                if new_type in ('Nodejs','Python'):
                    con.execute('UPDATE servers SET type=? WHERE id=?',(new_type,sid))
                    log(u['id'],'Server type changed',f"{s['name']} → {new_type}"); msg=f'Type changed to {new_type}.'
            elif action=='renew':
                renew=datetime.now(timezone.utc)+timedelta(days=PLANS[s['plan']]['days'])
                con.execute('UPDATE servers SET renew_at=? WHERE id=?',(renew.isoformat(),sid))
                log(u['id'],'Server renewed',s['name']); msg='Server renewed.'
            elif action=='delete':
                con.execute('DELETE FROM servers WHERE id=?',(sid,))
                log(u['id'],'Server deleted',s['name'])
                con.close()
                return redirect('/servers')
            s=con.execute('SELECT * FROM servers WHERE id=?',(sid,)).fetchone()
        finally:
            con.close()
    body=render_template_string(r'''
    <div class="bc"><a href="/servers">My servers</a> / <span>Your server</span></div>
    <div class="page-head"><h1>Your server</h1></div>
    {% if msg %}<div class="alert alert-success">{{ msg }}</div>{% endif %}
    <div class="tabs">
        <a class="tab {{ 'active' if tab=='general' else '' }}" href="?tab=general">General</a>
        <a class="tab {{ 'active' if tab=='modify' else '' }}" href="?tab=modify">Modify server</a>
        <a class="tab {{ 'active' if tab=='password' else '' }}" href="?tab=password">Change password</a>
        <a class="tab {{ 'active' if tab=='type' else '' }}" href="?tab=type">Change type</a>
    </div>
    {% if tab=='general' %}
    <div class="card" style="margin-bottom:18px">
        <div style="font-size:14px;color:var(--text-2);font-weight:500;margin-bottom:14px">🚀 Access server</div>
        <div class="field"><label>Link</label><input value="{{ s['panel_link'] }}" readonly></div>
        <div class="field"><label>Username</label><input value="{{ s['panel_username'] }}" readonly></div>
        <div class="field"><label>Identifier</label><input value="{{ s['identifier'] }}" readonly></div>
        <div class="field"><label>Current password</label><input value="{{ s['panel_password'] }}" readonly></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
            <a class="btn btn-primary" href="{{ s['panel_link'] }}" target="_blank">Go to server</a>
            <form method="post" style="display:inline"><input type="hidden" name="action" value="renew"><button class="btn btn-ghost">Renew now</button></form>
        </div>
    </div>
    <div class="card">
        <div style="font-size:14px;color:var(--text-2);font-weight:500;margin-bottom:14px">Server details</div>
        <div style="display:grid;grid-template-columns:1fr;gap:14px;font-size:13px">
            <div style="display:flex;justify-content:space-between"><span style="color:var(--muted)">Name</span><span style="color:var(--text)">{{ s['name'] }}</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--muted)">Type</span><span style="color:var(--text)">{{ s['type'] }}</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--muted)">Plan</span><span style="color:var(--text)">{{ PLANS[s['plan']].name }}</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--muted)">Renewal</span><span style="color:var(--text)">{{ s['renew_at'][:10] if s['renew_at'] else '—' }}</span></div>
            <div style="display:flex;justify-content:space-between"><span style="color:var(--muted)">Status</span><span class="badge badge-active">{{ s['panel_status'] }}</span></div>
        </div>
    </div>
    {% elif tab=='modify' %}
    <div class="card" style="max-width:620px"><div style="font-size:14px;color:var(--text-2);font-weight:500;margin-bottom:14px">Modify server</div>
        <form method="post"><input type="hidden" name="action" value="rename">
            <div class="field"><label>Name</label><input name="name" value="{{ s['name'] }}" required></div>
            <div class="field"><label>Description</label><textarea name="description" rows="4">{{ s['description'] or '' }}</textarea></div>
            <button class="btn btn-primary">Save changes</button>
        </form>
    </div>
    {% elif tab=='password' %}
    <div class="card" style="max-width:620px"><div style="font-size:14px;color:var(--text-2);font-weight:500;margin-bottom:14px">Change password</div>
        <form method="post"><input type="hidden" name="action" value="change_password">
            <div class="field"><label>Current password</label><input value="{{ s['panel_password'] }}" readonly></div>
            <div class="field"><label>New password</label><input type="password" name="new_password" minlength="6" required></div>
            <button class="btn btn-primary">Change password</button>
        </form>
    </div>
    {% elif tab=='type' %}
    <div class="alert alert-warning">⚠ Changing the type will reset the startup command. Files are not affected.</div>
    <div class="card" style="max-width:620px"><div style="font-size:14px;color:var(--text-2);font-weight:500;margin-bottom:14px">Change type</div>
        <form method="post"><input type="hidden" name="action" value="change_type">
            <div class="field"><label>Current type</label><input value="{{ s['type'] }}" readonly></div>
            <div class="field"><label>New type</label><select name="new_type"><option value="Nodejs" {{ 'selected' if s['type']=='Nodejs' else '' }}>Nodejs</option><option value="Python" {{ 'selected' if s['type']=='Python' else '' }}>Python</option></select></div>
            <button class="btn btn-primary">Change type</button>
        </form>
    </div>
    {% endif %}
    <div class="card" style="max-width:620px;margin-top:18px;border-color:rgba(239,68,68,.3)">
        <div style="font-size:14px;color:#fca5a5;font-weight:500;margin-bottom:8px">Danger zone</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:14px">Delete this server permanently.</p>
        <form method="post" onsubmit="return confirm('Delete this server?')"><input type="hidden" name="action" value="delete"><button class="btn btn-danger">Delete server</button></form>
    </div>
    ''',s=s,msg=msg,tab=tab,PLANS=PLANS)
    return shell(s['name'],body,'servers')

# ============ My Servers ============
@app.route('/servers')
@login_required
def servers_list():
    u=current_user(); servers,_,_=user_data(u['id'])
    body=render_template_string(r'''
    <div class="bc"><span>My servers</span></div>
    <div class="page-head" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px"><div><h1>My servers</h1></div><a class="btn btn-primary" href="/servers/create">Create server</a></div>
    <div class="card">
        {% if servers %}<div style="overflow-x:auto"><table class="tbl"><thead><tr><th>#</th><th>Name</th><th>Username</th><th>Type</th><th>Plan</th><th>Status</th><th></th></tr></thead><tbody>{% for s in servers %}<tr><td style="color:var(--muted)">{{ s['id'] }}</td><td style="color:var(--text);font-weight:500">{{ s['name'] }}</td><td>{{ s['panel_username'] or '—' }}</td><td>{{ s['type'] }}</td><td>{{ PLANS[s['plan']].name }}</td><td><span class="badge badge-active">{{ s['panel_status'] }}</span></td><td style="text-align:right"><a class="btn btn-ghost btn-sm" href="/servers/{{ s['id'] }}">Manage</a></td></tr>{% endfor %}</tbody></table></div>
        {% else %}<div class="empty"><p>You don't have any servers yet.</p><a class="btn btn-primary" href="/servers/create">Create your first server</a></div>{% endif %}
    </div>
    ''',servers=servers,PLANS=PLANS)
    return shell('My servers',body,'servers')

# ============ Domains ============
@app.route('/domains',methods=['GET','POST'])
@login_required
def domains_page():
    u=current_user(); error=None
    if request.method=='POST':
        domain=request.form.get('domain','').strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,62}\.[a-z]{2,}',domain): error='Please enter a valid domain like example.com.'
        else:
            con = db()
            try:
                con.execute('INSERT INTO domains(user_id,domain,status,created_at) VALUES(?,?,?,?)',(u['id'],domain,'Pending',now()))
            finally:
                con.close()
            log(u['id'],'Domain ordered',domain); return redirect('/domains')
    _,domains,_=user_data(u['id'])
    body=render_template_string(r'''
    <div class="bc">Home / <span>My domains</span></div>
    <div class="page-head"><h1>My domains</h1></div>
    {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
    <div class="card" style="margin-bottom:16px">
        <div style="display:flex;align-items:center;gap:10px;font-size:15px;font-weight:500;margin-bottom:16px">Domains</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px"><button class="btn btn-primary" onclick="document.getElementById('order-form').style.display='block'">+ Order a domain</button></div>
        <div id="order-form" style="display:none;border-top:1px solid var(--line);padding-top:16px"><form method="post"><div class="field"><label>Domain name</label><input name="domain" placeholder="yourbrand.com" required></div><button class="btn btn-primary">Order</button></form></div>
        {% if not domains %}<div class="empty" style="padding:40px 20px"><p>You don't have any domain yet.</p><button class="btn btn-primary" onclick="document.getElementById('order-form').style.display='block'">Order my first domain</button></div>{% endif %}
    </div>
    {% if domains %}<div class="card"><div style="overflow-x:auto"><table class="tbl"><thead><tr><th>Domain</th><th>Ordered</th><th>Status</th></tr></thead><tbody>{% for d in domains %}<tr><td style="color:var(--text);font-weight:500">{{ d['domain'] }}</td><td>{{ d['created_at'][:10] }}</td><td><span class="badge badge-pending">{{ d['status'] }}</span></td></tr>{% endfor %}</tbody></table></div></div>{% endif %}
    ''',error=error,domains=domains)
    return shell('My domains',body,'domains')

# ============ Plans ============
@app.route('/plans')
@login_required
def plans_page():
    body=render_template_string(r'''
    <div class="bc"><span>Plans</span></div>
    <div class="page-head"><h1>Plans & Pricing</h1><p>Choose the plan that fits your needs.</p></div>
    <div class="stats">
        {% for k,p in PLANS.items() %}
        <div class="stat" style="{{ 'border-color:var(--purple)' if k==user_plan else '' }}">
            <div class="stat-head"><div class="stat-label">{{ p.name }}</div>{% if k==user_plan %}<span class="badge badge-purple">Current</span>{% endif %}</div>
            <div class="stat-value">${{ p.price }}</div>
            <div class="stat-sub" style="margin-bottom:12px">per month · {{ p.credits }} credits</div>
            <div style="border-top:1px solid var(--line);padding-top:12px;font-size:12px;color:var(--muted);line-height:2">{{ p.ram }} RAM<br>{{ p.disk }} NVMe<br>{{ p.cpu }} CPU<br><b style="color:var(--text)">{{ p.servers }} servers</b></div>
            <div style="margin-top:14px">
            {% if k==user_plan %}<button class="btn btn-ghost btn-block" disabled>Your current plan</button>
            {% elif k=='free' %}<form method="post" action="/choose-plan"><input type="hidden" name="plan" value="free"><button class="btn btn-ghost btn-block">Choose Free</button></form>
            {% else %}<a class="btn btn-tg btn-block" href="https://t.me/{{ tg }}" target="_blank" rel="noopener">Buy credits via Telegram</a>{% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
    ''',PLANS=PLANS,tg=TELEGRAM_USER,user_plan=current_user()['plan'])
    return shell('Plans',body,'plans')

@app.post('/choose-plan')
@login_required
def choose_plan():
    u=current_user(); plan=request.form.get('plan')
    if plan in PLANS and plan=='free':
        con = db()
        try:
            con.execute('UPDATE users SET plan=? WHERE id=?',(plan,u['id']))
        finally:
            con.close()
        log(u['id'],'Plan changed','Free')
    return redirect('/plans')

# ============ Wallet ============
@app.route('/wallet')
@login_required
def wallet():
    u=current_user()
    body=render_template_string(r'''
    <div class="bc"><span>Buy credits</span></div>
    <div class="page-head"><h1>Buy credits</h1></div>
    <div class="card card-lg" style="max-width:540px">
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px">Available balance</div>
        <div style="font-size:36px;font-weight:600;letter-spacing:-1.2px;margin-bottom:20px">${{ '%.2f'|format(user['balance']) }}</div>
        <a class="btn btn-tg btn-lg btn-block" href="https://t.me/{{ tg }}" target="_blank" rel="noopener">Contact developer on Telegram</a>
        <p style="font-size:12px;color:var(--muted);margin-top:14px;text-align:center">You will be redirected to <b style="color:#229ED9">@{{ tg }}</b></p>
    </div>
    ''',user=u,tg=TELEGRAM_USER)
    return shell('Buy credits',body,'wallet')

# ============ Tickets ============
@app.route('/tickets',methods=['GET','POST'])
@login_required
def tickets_page():
    u=current_user(); error=None
    if request.method=='POST':
        subject=request.form.get('subject','').strip(); message=request.form.get('message','').strip()
        if not subject or not message: error='Subject and message are required.'
        else:
            con = db()
            try:
                con.execute('INSERT INTO tickets(user_id,subject,message,created_at) VALUES(?,?,?,?)',(u['id'],subject,message,now()))
            finally:
                con.close()
            log(u['id'],'Ticket opened',subject); return redirect('/tickets')
    con = db()
    try:
        tickets=con.execute('SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
    finally:
        con.close()
    body=render_template_string(r'''
    <div class="bc"><span>Support tickets</span></div>
    <div class="page-head"><h1>Support tickets</h1></div>
    {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
    <div class="card" style="margin-bottom:16px"><div class="card-title">Open new ticket</div>
        <form method="post"><div class="field"><label>Subject</label><input name="subject" required></div><div class="field"><label>Message</label><textarea name="message" rows="5" required></textarea></div><button class="btn btn-primary">Submit</button></form>
    </div>
    <div class="card"><div class="card-title">Your tickets</div>
        {% if tickets %}{% for t in tickets %}<div class="ticket-row"><div><b style="color:var(--text);font-size:14px">{{ t['subject'] }}</b><p style="font-size:12px;color:var(--muted);margin-top:4px">{{ t['message'][:100] }}</p>{% if t['reply'] %}<div style="margin-top:8px;padding:10px;background:rgba(139,92,246,.06);border-left:3px solid var(--purple);border-radius:6px;font-size:12px"><b style="color:var(--purple-2)">Admin:</b> {{ t['reply'] }}</div>{% endif %}</div><span class="badge {{ 'badge-active' if t['status']=='Closed' else 'badge-pending' }}">{{ t['status'] }}</span></div>{% endfor %}
        {% else %}<div class="empty"><p>No tickets yet.</p></div>{% endif %}
    </div>
    ''',error=error,tickets=tickets)
    return shell('Support',body,'tickets')

# ============ Settings ============
@app.route('/settings',methods=['GET','POST'])
@login_required
def settings():
    u=current_user(); msg=None; err=None
    if request.method=='POST':
        action=request.form.get('action')
        if action=='profile':
            name=request.form.get('display_name','').strip()[:40]
            email=request.form.get('email','').strip().lower()
            if name:
                con = db()
                try:
                    if email and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
                        con.execute('UPDATE users SET display_name=?,email=? WHERE id=?',(name,email,u['id']))
                    else:
                        con.execute('UPDATE users SET display_name=? WHERE id=?',(name,u['id']))
                finally:
                    con.close()
                log(u['id'],'Profile updated',''); msg='Profile updated.'; u=current_user()
        elif action=='password':
            current=request.form.get('current',''); new=request.form.get('new',''); confirm=request.form.get('confirm','')
            if not check_password_hash(u['password_hash'],current): err='Current password is incorrect.'
            elif len(new)<6: err='New password must be at least 6 characters.'
            elif new!=confirm: err='Passwords do not match.'
            else:
                con = db()
                try:
                    con.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),u['id']))
                finally:
                    con.close()
                log(u['id'],'Password changed',''); msg='Password changed.'
        elif action=='avatar':
            data=request.form.get('avatar_data','')
            if data and data.startswith('data:image/'):
                m=re.match(r'data:image/(\w+);base64,(.+)', data)
                if m:
                    ext=m.group(1)
                    if ext=='jpeg': ext='jpg'
                    if ext in ('png','jpg','gif','webp'):
                        raw=base64.b64decode(m.group(2))
                        if len(raw)<=2*1024*1024:
                            con = db()
                            try:
                                con.execute('UPDATE users SET avatar=? WHERE id=?',(data,u['id']))
                            finally:
                                con.close()
                            log(u['id'],'Avatar updated',''); msg='Avatar updated.'; u=current_user()
                        else: err='Image too large (max 2MB).'
                    else: err='Only PNG, JPG, GIF, WEBP allowed.'
    body=render_template_string(r'''
    <div class="bc"><span>Settings</span></div>
    <div class="page-head"><h1>Settings</h1></div>
    {% if msg %}<div class="alert alert-success">{{ msg }}</div>{% endif %}
    {% if err %}<div class="alert alert-error">{{ err }}</div>{% endif %}
    <div class="card card-lg" style="max-width:620px;margin-bottom:18px">
        <div class="card-title">Profile picture</div>
        <div class="avatar-upload">
            <div class="avatar-preview" id="avatar-preview">{% if user['avatar'] %}<img src="{{ user['avatar'] }}">{% else %}{{ (user['display_name'] or user['username'])[0].upper() }}{% endif %}</div>
            <div class="avatar-upload-actions"><form method="post" id="avatar-form"><input type="hidden" name="action" value="avatar"><input type="hidden" name="avatar_data" id="avatar_data"><input type="file" name="avatar" accept="image/*" id="avatar-input" style="display:none"><button type="button" class="btn btn-primary" onclick="document.getElementById('avatar-input').click()">Upload image</button><small>PNG, JPG, GIF or WEBP. Max 2MB.</small></form></div>
        </div>
    </div>
    <div class="card card-lg" style="max-width:620px;margin-bottom:18px">
        <div class="card-title">Profile</div>
        <form method="post"><input type="hidden" name="action" value="profile">
            <div class="field"><label>Username</label><input value="{{ user['username'] }}" disabled></div>
            <div class="field"><label>Display name</label><input name="display_name" value="{{ user['display_name'] or user['username'] }}" required></div>
            <div class="field"><label>Email</label><input type="email" name="email" value="{{ user['email'] or '' }}"></div>
            <button class="btn btn-primary">Save</button>
        </form>
    </div>
    <div class="card card-lg" style="max-width:620px">
        <div class="card-title">Change password</div>
        <form method="post"><input type="hidden" name="action" value="password">
            <div class="field"><label>Current password</label><input type="password" name="current" required></div>
            <div class="field"><label>New password</label><input type="password" name="new" minlength="6" required></div>
            <div class="field"><label>Confirm new password</label><input type="password" name="confirm" minlength="6" required></div>
            <button class="btn btn-primary">Update</button>
        </form>
    </div>
    <script>document.getElementById('avatar-input').addEventListener('change',function(e){var f=e.target.files[0];if(!f)return;if(f.size>2*1024*1024){alert('Max 2MB');return;}var r=new FileReader();r.onload=function(ev){document.getElementById('avatar_data').value=ev.target.result;document.getElementById('avatar-preview').innerHTML='<img src="'+ev.target.result+'">';document.getElementById('avatar-form').submit();};r.readAsDataURL(f);});</script>
    ''',user=u,msg=msg,err=err)
    return shell('Settings',body,'settings')

# ============ Admin ============
@app.route('/admin')
@admin_required
def admin_panel():
    con = db()
    try:
        users=con.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
        total_users=len(users)
        total_servers=con.execute('SELECT COUNT(*) FROM servers').fetchone()[0]
        total_domains=con.execute('SELECT COUNT(*) FROM domains').fetchone()[0]
        total_balance=con.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0]
        banned=con.execute('SELECT COUNT(*) FROM users WHERE is_banned=1').fetchone()[0]
        tickets=con.execute('SELECT t.*,u.username FROM tickets t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC').fetchall()
        announcements=con.execute('SELECT * FROM announcements ORDER BY id DESC').fetchall()
    finally:
        con.close()
    msg=session.pop('admin_msg',None)
    users_list=[dict(x) for x in users]
    tickets_list=[dict(t) for t in tickets]
    announcements_list=[dict(a) for a in announcements]
    body=render_template_string(r'''
    <div class="bc"><span>Admin panel</span></div>
    <div class="page-head"><h1>Admin panel</h1></div>
    {% if msg %}<div class="alert alert-success">{{ msg }}</div>{% endif %}
    <div class="stats">
        <div class="stat"><div class="stat-head"><div class="stat-label">Users</div></div><div class="stat-value">{{ total_users }}</div><div class="stat-sub">{{ banned }} banned</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Servers</div></div><div class="stat-value">{{ total_servers }}</div><div class="stat-sub">Total</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Domains</div></div><div class="stat-value">{{ total_domains }}</div><div class="stat-sub">Total</div></div>
        <div class="stat"><div class="stat-head"><div class="stat-label">Balance</div></div><div class="stat-value">${{ '%.2f'|format(total_balance) }}</div><div class="stat-sub">All accounts</div></div>
    </div>
    <div class="card" style="margin-bottom:18px">
        <div class="card-title">Post announcement</div>
        <form method="post" action="/admin/announce"><div class="field"><label>Title</label><input name="title" required></div><div class="field"><label>Body</label><textarea name="body" rows="3" required></textarea></div><button class="btn btn-primary">Publish</button></form>
        {% if announcements_list %}<div style="margin-top:14px;font-size:12px;color:var(--muted)">Last: <b style="color:var(--text)">{{ announcements_list[0].title }}</b></div>{% endif %}
    </div>
    <div class="card" style="margin-bottom:18px">
        <div class="card-title">Users</div>
        <div style="overflow-x:auto"><table class="tbl">
            <thead><tr><th>#</th><th>User</th><th>Email</th><th>Plan</th><th>Balance</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{% for x in users_list %}
            <tr>
                <td style="color:var(--muted)">{{ x.id }}</td>
                <td><span style="color:var(--text);font-weight:500">{{ x.username }}</span>{% if x.is_admin %} <span class="badge badge-purple">ADMIN</span>{% endif %}</td>
                <td style="font-size:12px">{{ x.email or '—' }}</td>
                <td>
                    <form method="post" action="/admin/set-plan" style="display:inline-flex;gap:4px;align-items:center">
                        <input type="hidden" name="user_id" value="{{ x.id }}">
                        <select name="plan" style="padding:5px 8px;background:var(--bg-2);border:1px solid var(--line);border-radius:6px;color:var(--text);font-size:12px">{% for pk,pv in PLANS.items() %}<option value="{{ pk }}" {{ 'selected' if x.plan==pk else '' }}>{{ pv.name }} ({{ pv.servers }})</option>{% endfor %}</select>
                        <button class="btn btn-primary btn-sm">Set</button>
                    </form>
                </td>
                <td>${{ '%.2f'|format(x.balance) }}</td>
                <td>{% if x.is_banned %}<span class="badge badge-off">Banned</span>{% else %}<span class="badge badge-active">Active</span>{% endif %}</td>
                <td>
                    <div class="admin-actions">
                        <form method="post" action="/admin/balance">
                            <input type="hidden" name="user_id" value="{{ x.id }}">
                            <input type="number" step="0.01" name="amount" placeholder="Amt" required>
                            <button name="op" value="add" class="btn btn-success btn-sm" title="Add">+</button>
                            <button name="op" value="sub" class="btn btn-danger btn-sm" title="Subtract">−</button>
                        </form>
                        <form method="post" action="/admin/ban" style="display:inline">
                            <input type="hidden" name="user_id" value="{{ x.id }}">
                            <input type="hidden" name="ban" value="{{ 0 if x.is_banned else 1 }}">
                            <button class="btn {{ 'btn-success' if x.is_banned else 'btn-danger' }} btn-sm">{{ 'Unban' if x.is_banned else 'Ban' }}</button>
                        </form>
                        <button class="btn btn-ghost btn-sm" onclick="document.getElementById('msg-{{ x.id }}').style.display='block'">Message</button>
                    </div>
                    <form method="post" action="/admin/message" id="msg-{{ x.id }}" style="display:none;margin-top:8px">
                        <input type="hidden" name="user_id" value="{{ x.id }}">
                        <input name="message" placeholder="Write a message..." required style="width:100%;padding:8px 12px;background:var(--bg-2);border:1px solid var(--line);border-radius:6px;color:var(--text);font-size:12px;margin-bottom:6px">
                        <button class="btn btn-primary btn-sm">Send</button>
                    </form>
                </td>
            </tr>{% endfor %}</tbody>
        </table></div>
    </div>
    <div class="card">
        <div class="card-title">Support tickets</div>
        {% if tickets_list %}{% for t in tickets_list %}<div class="ticket-row" style="flex-direction:column;align-items:flex-start"><div style="width:100%"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px"><b style="color:var(--text)">{{ t.subject }}</b><span class="badge {{ 'badge-active' if t.status=='Closed' else 'badge-pending' }}">{{ t.status }}</span></div><p style="font-size:12px;color:var(--muted);margin-top:6px">From <b>{{ t.username }}</b> · {{ t.created_at[:10] }}</p><p style="font-size:13px;color:var(--text-2);margin-top:8px">{{ t.message }}</p>{% if t.reply %}<div style="margin-top:10px;padding:10px;background:rgba(139,92,246,.06);border-left:3px solid var(--purple);border-radius:6px;font-size:12px"><b style="color:var(--purple-2)">Reply:</b> {{ t.reply }}</div>{% else %}<form method="post" action="/admin/ticket-reply" style="margin-top:10px;display:flex;gap:6px"><input type="hidden" name="tid" value="{{ t.id }}"><input name="reply" placeholder="Type reply..." required style="flex:1;padding:8px 12px;background:var(--bg-2);border:1px solid var(--line);border-radius:6px;color:var(--text);font-size:12px"><button class="btn btn-primary btn-sm">Reply & close</button></form>{% endif %}</div></div>{% endfor %}{% else %}<div class="empty"><p>No tickets.</p></div>{% endif %}
    </div>
    ''',users_list=users_list, tickets_list=tickets_list, announcements_list=announcements_list,
    total_users=total_users, total_servers=total_servers, total_domains=total_domains,
    total_balance=total_balance, banned=banned, PLANS=PLANS, msg=msg)
    return shell('Admin',body,'admin')

@app.post('/admin/balance')
@admin_required
def admin_balance():
    uid=request.form.get('user_id',type=int); amount=request.form.get('amount',type=float); op=request.form.get('op')
    if uid and amount and op in ('add','sub'):
        con = db()
        try:
            ur=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if ur:
                if op=='add':
                    con.execute('UPDATE users SET balance=balance+? WHERE id=?',(amount,uid))
                    con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(uid,f'Admin added ${amount:.2f} to your balance.',now()))
                    con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',(uid,'Balance added',f'+${amount:.2f}',now()))
                    session['admin_msg']=f'Added ${amount:.2f} to {ur["username"]}.'
                else:
                    new_bal=max(0, ur['balance']-amount)
                    con.execute('UPDATE users SET balance=? WHERE id=?',(new_bal,uid))
                    con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(uid,f'Admin deducted ${amount:.2f} from your balance.',now()))
                    con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',(uid,'Balance deducted',f'-${amount:.2f}',now()))
                    session['admin_msg']=f'Deducted ${amount:.2f} from {ur["username"]}.'
        finally:
            con.close()
    return redirect('/admin')

@app.post('/admin/ban')
@admin_required
def admin_ban():
    uid=request.form.get('user_id',type=int); ban=request.form.get('ban','0')=='1'
    if uid:
        con = db()
        try:
            ur=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if ur and not ur['is_admin']:
                con.execute('UPDATE users SET is_banned=? WHERE id=?',(1 if ban else 0,uid))
                msg_txt = 'Your account has been banned by the admin.' if ban else 'Your account has been unbanned.'
                con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(uid,msg_txt,now()))
                con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',(uid,'Banned' if ban else 'Unbanned','by admin',now()))
                session['admin_msg']=f'{"Banned" if ban else "Unbanned"} {ur["username"]}.'
        finally:
            con.close()
    return redirect('/admin')

@app.post('/admin/set-plan')
@admin_required
def admin_set_plan():
    uid=request.form.get('user_id',type=int); plan=request.form.get('plan')
    if uid and plan in PLANS:
        con = db()
        try:
            ur=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if ur:
                con.execute('UPDATE users SET plan=? WHERE id=?',(plan,uid))
                con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(uid,f'Your plan has been changed to {PLANS[plan]["name"]} ({PLANS[plan]["servers"]} servers) by admin.',now()))
                con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',(uid,'Plan changed',f'→ {PLANS[plan]["name"]}',now()))
                session['admin_msg']=f'Plan of {ur["username"]} changed to {PLANS[plan]["name"]}.'
        finally:
            con.close()
    return redirect('/admin')

@app.post('/admin/message')
@admin_required
def admin_message():
    uid=request.form.get('user_id',type=int); message=request.form.get('message','').strip()
    if uid and message:
        con = db()
        try:
            ur=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if ur:
                con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(uid,message,now()))
                con.execute('INSERT INTO activity(user_id,event,detail,created_at) VALUES(?,?,?,?)',(uid,'Message from admin',message[:50],now()))
                session['admin_msg']=f'Message sent to {ur["username"]}.'
        finally:
            con.close()
    return redirect('/admin')

@app.post('/admin/announce')
@admin_required
def admin_announce():
    title=request.form.get('title','').strip(); body_txt=request.form.get('body','').strip()
    if title and body_txt:
        con = db()
        try:
            con.execute('INSERT INTO announcements(title,body,created_at) VALUES(?,?,?)',(title,body_txt,now()))
        finally:
            con.close()
        session['admin_msg']='Announcement published.'
    return redirect('/admin')

@app.post('/admin/ticket-reply')
@admin_required
def admin_ticket_reply():
    tid=request.form.get('tid',type=int); reply=request.form.get('reply','').strip()
    if tid and reply:
        con = db()
        try:
            con.execute('UPDATE tickets SET reply=?,status="Closed" WHERE id=?',(reply,tid))
            t=con.execute('SELECT * FROM tickets WHERE id=?',(tid,)).fetchone()
            if t:
                con.execute('INSERT INTO notifications(user_id,message,created_at) VALUES(?,?,?)',(t['user_id'],f'Admin replied to your ticket: {reply}',now()))
        finally:
            con.close()
        session['admin_msg']='Ticket replied and closed.'
    return redirect('/admin')

@app.get('/health')
def health(): return jsonify(ok=True,service='hup-server',version='18.0')


# ================== MAIN ==================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 11154))
    print(f"""
    ╔══════════════════════════════════════════════════════╗
    ║  Hup Server v18.0                                    ║
    ║  http://localhost:{port}                                ║
    ║  Admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}       ║
    ╚══════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=False)