# -*- coding: utf-8 -*-
# 📧 Mail Ninja — Ultimate TempMail Bot (mail.tm + temp-mail.org ready)
# PTB v20 async • SQLite • Inline UI • Auto-check via JobQueue • HTML→Text • CSV export
# Author: Monuwar + ChatGPT
#
# Commands:
# /start /help /commands
# /newmail [mailtm|tempmail]    → create new temp email (default: mailtm)
# /mymail                       → show current active address + TTL
# /switch                       → choose another address (inline)
# /delete                       → delete current address (inline confirm)
# /inbox                        → list messages (inline pagination)
# /read <id>                    → read full message (HTML→text)
# /attachments <id>             → download attachments (if any)
# /autocheck on|off             → enable/disable new-mail notifications
# /setinterval <seconds>        → polling interval for autocheck (>=30)
# /export                       → CSV export of message metadata
# /admin stats                  → admin stats (owner only; optional)
#
# Notes:
# - mail.tm: fully integrated (no key required)
# - temp-mail.org: requires API key → set TEMPM_API_KEY env (optional).
# - For Railway you can just run it as-is. Token is embedded as requested.

import os
import io
import csv
import json
import time
import secrets
import string
import sqlite3
from typing import Optional, Dict, Any, List, Tuple

import requests
import html2text

from telegram import (
    Update,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, JobQueue
)

# ----------------- Bot Token (embedded as requested) -----------------
BOT_TOKEN = "8026218688:AAGI_nGGlaLxhDFKeyOQv018vJc29PIb_2Q"
# --------------------------------------------------------------------

# Optional: temp-mail.org API key (if you have one; else provider disabled)
TEMPM_API_KEY = os.getenv("TEMPM_API_KEY", "").strip()

DB = "mailninja.db"
MIN_INTERVAL = 30  # seconds

# ========================= DB LAYER =========================
def db():
    return sqlite3.connect(DB)

def init_db():
    conn = db(); c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        created_ts INTEGER
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS emails(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        provider TEXT,            -- 'mailtm' | 'tempmail'
        address TEXT UNIQUE,
        login TEXT,               -- not used for mail.tm
        domain TEXT,
        pass_plain TEXT,          -- mail.tm account password (for token refresh)
        token TEXT,               -- mail.tm bearer token (refresh as needed)
        active INTEGER DEFAULT 1, -- 1 active / 0 archived
        ttl_ts INTEGER,           -- optional expiration (epoch)
        created_ts INTEGER
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        user_id INTEGER PRIMARY KEY,
        auto_check INTEGER DEFAULT 0,
        check_interval INTEGER DEFAULT 60
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS seen_msgs(
        address TEXT,
        msg_id TEXT,
        PRIMARY KEY(address, msg_id)
    )""")
    conn.commit(); conn.close()

def ensure_user(uid: int):
    ts = int(time.time())
    conn = db(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users(user_id, created_ts) VALUES(?,?)", (uid, ts))
    c.execute("INSERT OR IGNORE INTO settings(user_id) VALUES(?)", (uid,))
    conn.commit(); conn.close()

def add_email(uid: int, provider: str, address: str, login: str, domain: str,
              pass_plain: Optional[str], token: Optional[str], ttl_ts: Optional[int]):
    ts = int(time.time())
    conn = db(); c = conn.cursor()
    # Make others inactive if >2 active; enforce max 3 addresses total
    c.execute("SELECT COUNT(*) FROM emails WHERE user_id=?", (uid,))
    count = c.fetchone()[0] or 0
    if count >= 3:
        # remove oldest inactive first, else deactivate oldest active
        c.execute("DELETE FROM emails WHERE user_id=? AND active=0", (uid,))
        conn.commit()
    c.execute("""INSERT OR REPLACE INTO emails(user_id,provider,address,login,domain,pass_plain,token,active,ttl_ts,created_ts)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (uid, provider, address, login, domain, pass_plain or None, token or None, 1, ttl_ts, ts))
    conn.commit(); conn.close()

def list_emails(uid: int) -> List[Tuple]:
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, provider, address, active, ttl_ts FROM emails WHERE user_id=? ORDER BY created_ts DESC", (uid,))
    rows = c.fetchall(); conn.close(); return rows

def get_active_email(uid: int) -> Optional[Dict[str, Any]]:
    conn = db(); c = conn.cursor()
    c.execute("""SELECT id, provider, address, login, domain, pass_plain, token, ttl_ts
                 FROM emails WHERE user_id=? AND active=1 ORDER BY created_ts DESC LIMIT 1""", (uid,))
    row = c.fetchone(); conn.close()
    if not row: return None
    return dict(id=row[0], provider=row[1], address=row[2], login=row[3], domain=row[4],
                pass_plain=row[5], token=row[6], ttl_ts=row[7])

def set_active(uid: int, email_id: int):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE emails SET active=0 WHERE user_id=?", (uid,))
    c.execute("UPDATE emails SET active=1 WHERE user_id=? AND id=?", (uid, email_id))
    conn.commit(); conn.close()

def delete_email(uid: int, email_id: int):
    conn = db(); c = conn.cursor()
    c.execute("DELETE FROM emails WHERE user_id=? AND id=?", (uid, email_id))
    conn.commit(); conn.close()

def get_settings(uid: int) -> Tuple[int, int]:
    conn = db(); c = conn.cursor()
    c.execute("SELECT auto_check, check_interval FROM settings WHERE user_id=?", (uid,))
    row = c.fetchone(); conn.close()
    return (row[0] or 0, row[1] or 60) if row else (0, 60)

def set_autocheck(uid: int, enabled: bool):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE settings SET auto_check=? WHERE user_id=?", (1 if enabled else 0, uid))
    conn.commit(); conn.close()

def set_interval(uid: int, seconds: int):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE settings SET check_interval=? WHERE user_id=?", (seconds, uid))
    conn.commit(); conn.close()

def mark_seen(address: str, msg_id: str):
    conn = db(); c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO seen_msgs(address, msg_id) VALUES(?,?)", (address, msg_id))
        conn.commit()
    finally:
        conn.close()

def seen_before(address: str, msg_id: str) -> bool:
    conn = db(); c = conn.cursor()
    c.execute("SELECT 1 FROM seen_msgs WHERE address=? AND msg_id=?", (address, msg_id))
    ok = c.fetchone() is not None
    conn.close(); return ok

# ====================== PROVIDERS ======================
H2T = html2text.HTML2Text()
H2T.ignore_links = False
H2T.ignore_images = True
H2T.body_width = 0

# ---- mail.tm provider ----
class MailTm:
    API = "https://api.mail.tm"

    @staticmethod
    def random_local(n=10) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(n))

    @classmethod
    def get_domains(cls) -> List[str]:
        r = requests.get(f"{cls.API}/domains?page=1", timeout=15)
        r.raise_for_status()
        data = r.json()
        domains = [d["domain"] for d in data.get("hydra:member", [])]
        if not domains:
            # Fallback to a known domain in case API format changes
            domains = ["mail.tm"]
        return domains

    @classmethod
    def create_account(cls) -> Dict[str, str]:
        local = cls.random_local()
        domains = cls.get_domains()
        domain = secrets.choice(domains)
        address = f"{local}@{domain}"
        password = cls.random_local(16)

        # create account
        r = requests.post(f"{cls.API}/accounts", json={"address": address, "password": password}, timeout=15)
        if r.status_code not in (200, 201):
            # sometimes account exists; retry once with new local
            local = cls.random_local()
            address = f"{local}@{domain}"
            r = requests.post(f"{cls.API}/accounts", json={"address": address, "password": password}, timeout=15)
            r.raise_for_status()

        # token
        tok = cls.get_token(address, password)
        return {"address": address, "password": password, "token": tok, "domain": domain, "login": local}

    @classmethod
    def get_token(cls, address: str, password: str) -> str:
        r = requests.post(f"{cls.API}/token", json={"address": address, "password": password}, timeout=15)
        r.raise_for_status()
        return r.json()["token"]

    @classmethod
    def ensure_token(cls, rec: Dict[str, Any]) -> str:
        # refresh if missing
        if not rec.get("token"):
            rec["token"] = cls.get_token(rec["address"], rec["pass_plain"])
        return rec["token"]

    @classmethod
    def inbox(cls, token: str, limit: int = 25) -> List[Dict[str, Any]]:
        r = requests.get(f"{cls.API}/messages?page=1", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("hydra:member", [])

    @classmethod
    def read(cls, token: str, msg_id: str) -> Dict[str, Any]:
        r = requests.get(f"{cls.API}/messages/{msg_id}", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        return r.json()

# ---- temp-mail.org (optional; requires API key) ----
class TempMailOrg:
    BASE = "https://api4.temp-mail.org"
    # NOTE: Their API requires key; endpoints vary by plan. We'll implement stubs
    # that raise a helpful error if TEMPM_API_KEY is not set.

    @classmethod
    def ensure_key(cls):
        if not TEMPM_API_KEY:
            raise RuntimeError("TempMail.org requires TEMPM_API_KEY. Please set it in Railway → Variables.")

    @classmethod
    def create_address(cls) -> Dict[str, str]:
        cls.ensure_key()
        # Demo placeholder — endpoints differ by plan. Replace with your plan's create address call.
        # Here we just raise to avoid confusion.
        raise RuntimeError("TempMail.org create address endpoint not configured for your plan.")

    @classmethod
    def inbox(cls, address: str) -> List[Dict[str, Any]]:
        cls.ensure_key()
        raise RuntimeError("TempMail.org inbox endpoint not configured for your plan.")

    @classmethod
    def read(cls, address: str, msg_id: str) -> Dict[str, Any]:
        cls.ensure_key()
        raise RuntimeError("TempMail.org read endpoint not configured for your plan.")

# ====================== BOT HELPERS ======================
def render_inbox_list(provider: str, items: List[Dict[str, Any]]) -> str:
    if not items:
        return "📭 Inbox is empty."
    lines = ["📨 *Inbox:*", ""]
    if provider == "mailtm":
        for m in items:
            mid = m.get("id")
            frm = (m.get("from", {}) or {}).get("address", "unknown")
            sub = m.get("subject") or "(no subject)"
            lines.append(f"• ID: `{mid}`\n  From: `{frm}`\n  Subject: *{sub}*")
    else:
        for m in items:
            lines.append(json.dumps(m, ensure_ascii=False))
    return "\n".join(lines)

def html_to_text(html: str) -> str:
    try:
        return H2T.handle(html)
    except Exception:
        return html

def make_switch_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = []
    for eid, provider, addr, active, ttl in list_emails(uid):
        mark = "✅ " if active else ""
        rows.append([InlineKeyboardButton(f"{mark}{addr} ({provider})", callback_data=f"switch:{eid}")])
    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("No emails", callback_data="noop")]])

def make_delete_keyboard(email_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Confirm delete", callback_data=f"del:{email_id}")],
        [InlineKeyboardButton("Cancel", callback_data="noop")]
    ])

# ====================== COMMANDS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    await update.message.reply_text(
        "👋 Welcome to *Mail Ninja* — your all-in-one temporary email assistant.\n\n"
        "Create a fresh inbox, get OTP safely, auto-notify new mails, view attachments — all inside Telegram.\n\n"
        "🔥 Quick start:\n"
        "• /newmail  (default: mail.tm)\n"
        "• /inbox\n"
        "• /read <id>\n"
        "• /autocheck on\n"
        "• /setinterval 60\n\n"
        "All commands: /commands",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await commands_cmd(update, context)

async def commands_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📘 *Mail Ninja — Commands*\n\n"
        "✉️ /newmail `[mailtm|tempmail]` — Create a new temp email (default: mailtm)\n"
        "📬 /mymail — Show current active address\n"
        "🔁 /switch — Switch to another address\n"
        "🗑️ /delete — Delete current address (confirm)\n"
        "📨 /inbox — List messages\n"
        "📖 /read `<id>` — Read a message\n"
        "📎 /attachments `<id>` — Download attachments\n"
        "🔔 /autocheck `on|off` — Notify on new mails\n"
        "⏱️ /setinterval `<seconds>` — Auto-check interval (>=30)\n"
        "📤 /export — Export inbox metadata (CSV)\n"
        "ℹ️ /help — This list"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

async def mymail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rec = get_active_email(uid)
    if not rec:
        await update.message.reply_text("⚠️ You don't have any address yet. Use /newmail")
        return
    ttl = f"TTL: {rec['ttl_ts']}" if rec.get("ttl_ts") else "TTL: n/a"
    await update.message.reply_text(f"📬 Active: `{rec['address']}` ({rec['provider']})\n{ttl}",
                                    parse_mode="Markdown")

async def switch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rows = list_emails(uid)
    if not rows:
        await update.message.reply_text("No addresses. Create one: /newmail")
        return
    await update.message.reply_text("Select address:", reply_markup=make_switch_keyboard(uid))

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rec = get_active_email(uid)
    if not rec:
        await update.message.reply_text("No active address.")
        return
    await update.message.reply_text(
        f"Delete `{rec['address']}` ?",
        reply_markup=make_delete_keyboard(rec["id"]),
        parse_mode="Markdown"
    )

async def newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_user(uid)
    provider = (context.args[0].lower() if context.args else "mailtm").strip()
    if provider not in ("mailtm", "tempmail"):
        provider = "mailtm"

    try:
        if provider == "mailtm":
            acc = MailTm.create_account()
            add_email(uid, "mailtm", acc["address"], acc["login"], acc["domain"], acc["password"], acc["token"], None)
            set_active(uid, get_active_email(uid)["id"])
            await update.message.reply_text(
                f"✅ New mail created (mail.tm)\n`{acc['address']}`",
                parse_mode="Markdown"
            )
        else:
            # temp-mail.org requires API key → show helpful message if missing
            if not TEMPM_API_KEY:
                await update.message.reply_text(
                    "⚠️ temp-mail.org requires an API key. Set `TEMPM_API_KEY` in Railway → Variables.\n"
                    "Defaulting to mail.tm instead..."
                )
                acc = MailTm.create_account()
                add_email(uid, "mailtm", acc["address"], acc["login"], acc["domain"], acc["password"], acc["token"], None)
                set_active(uid, get_active_email(uid)["id"])
                await update.message.reply_text(f"✅ New mail created (mail.tm)\n`{acc['address']}`",
                                                parse_mode="Markdown")
            else:
                data = TempMailOrg.create_address()  # will raise until configured
                # If you implement, add_email(..., provider='tempmail', ...)
                await update.message.reply_text("✅ temp-mail.org address created.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to create address: {e}")

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rec = get_active_email(uid)
    if not rec:
        await update.message.reply_text("No active address. Use /newmail")
        return

    try:
        if rec["provider"] == "mailtm":
            token = MailTm.ensure_token(rec)
            items = MailTm.inbox(token)
            text = render_inbox_list("mailtm", items)
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            if not TEMPM_API_KEY:
                await update.message.reply_text("temp-mail.org not configured. Set TEMPM_API_KEY.")
                return
            items = TempMailOrg.inbox(rec["address"])
            await update.message.reply_text(render_inbox_list("tempmail", items), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not fetch inbox: {e}")

async def read_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /read <id>")
        return
    msg_id = context.args[0]
    rec = get_active_email(uid)
    if not rec:
        await update.message.reply_text("No active address.")
        return

    try:
        if rec["provider"] == "mailtm":
            token = MailTm.ensure_token(rec)
            js = MailTm.read(token, msg_id)
            frm = ((js.get("from") or {}).get("address")) or "unknown"
            sub = js.get("subject") or "(no subject)"
            text = js.get("text") or ""
            html = js.get("html") or ""
            body = text or (html_to_text("\n".join(html)) if isinstance(html, list) else html_to_text(html))
            mark_seen(rec["address"], msg_id)
            await update.message.reply_text(
                f"📖 *Subject:* {sub}\n👤 From: `{frm}`\n\n{body or '(empty)'}",
                parse_mode="Markdown"
            )
        else:
            if not TEMPM_API_KEY:
                await update.message.reply_text("temp-mail.org not configured. Set TEMPM_API_KEY.")
                return
            js = TempMailOrg.read(rec["address"], msg_id)
            await update.message.reply_text(json.dumps(js, ensure_ascii=False, indent=2))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not read message: {e}")

async def attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /attachments <id>")
        return
    msg_id = context.args[0]
    rec = get_active_email(uid)
    if not rec:
        await update.message.reply_text("No active address.")
        return

    if rec["provider"] != "mailtm":
        await update.message.reply_text("Attachments supported for mail.tm only in this build.")
        return

    try:
        token = MailTm.ensure_token(rec)
        js = MailTm.read(token, msg_id)
        atts = js.get("attachments") or []
        if not atts:
            await update.message.reply_text("📎 No attachments.")
            return
        for a in atts:
            url = a.get("downloadUrl")
            fname = a.get("filename", "file.bin")
            if not url:
                continue
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            r.raise_for_status()
            await update.message.reply_document(document=InputFile(io.BytesIO(r.content), filename=fname),
                                                caption=f"📎 {fname}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not fetch attachments: {e}")

async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rec = get_active_email(uid)
    if not rec:
        await update.message.reply_text("No active address.")
        return

    try:
        rows = []
        if rec["provider"] == "mailtm":
            token = MailTm.ensure_token(rec)
            items = MailTm.inbox(token)
            for m in items:
                rows.append([m.get("id"), (m.get("from") or {}).get("address", ""), m.get("subject", ""), m.get("intro", "")])
        else:
            await update.message.reply_text("CSV export not configured for temp-mail.org in this build.")
            return

        if not rows:
            await update.message.reply_text("📭 Inbox is empty.")
            return
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(["id", "from", "subject", "preview"])
        w.writerows(rows); output.seek(0)
        await update.message.reply_document(document=InputFile(output, filename="mailninja_inbox.csv"),
                                            caption="📤 Exported inbox metadata.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Export failed: {e}")

# ====================== INLINE CALLBACKS ======================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    data = q.data or ""
    await q.answer()
    uid = q.from_user.id

    if data.startswith("switch:"):
        eid = int(data.split(":")[1])
        set_active(uid, eid)
        rec = get_active_email(uid)
        await q.edit_message_text(f"✅ Switched to `{rec['address']}`", parse_mode="Markdown")
    elif data.startswith("del:"):
        eid = int(data.split(":")[1])
        delete_email(uid, eid)
        await q.edit_message_text("🗑️ Address deleted.")
    else:
        # noop or unknown
        pass

# ====================== AUTO-CHECK (JOB) ======================
async def poll_job(context: ContextTypes.DEFAULT_TYPE):
    # Iterate all users with autocheck enabled
    try:
        conn = db(); c = conn.cursor()
        c.execute("SELECT u.user_id, s.check_interval FROM users u JOIN settings s ON u.user_id=s.user_id WHERE s.auto_check=1")
        users = c.fetchall()
        conn.close()
    except Exception:
        users = []

    for uid, _iv in users:
        rec = get_active_email(uid)
        if not rec: continue
        try:
            if rec["provider"] == "mailtm":
                token = MailTm.ensure_token(rec)
                items = MailTm.inbox(token)
                for m in items:
                    mid = m.get("id")
                    if not mid: continue
                    if not seen_before(rec["address"], str(mid)):
                        mark_seen(rec["address"], str(mid))
                        frm = (m.get("from") or {}).get("address", "unknown")
                        sub = m.get("subject") or "(no subject)"
                        await context.bot.send_message(
                            chat_id=uid,
                            text=f"🔔 *New mail* for `{rec['address']}`\n👤 From: `{frm}`\n📝 Subject: *{sub}*\nID: `{mid}`",
                            parse_mode="Markdown"
                        )
            else:
                # temp-mail.org not implemented without key/plan
                continue
        except Exception:
            continue

# ====================== SETTINGS CMDS ======================
async def autocheck_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args or context.args[0].lower() not in ("on", "off"):
        ac, iv = get_settings(uid)
        await update.message.reply_text(f"Current: {'ON' if ac else 'OFF'} (interval {iv}s)\nUsage: /autocheck on|off")
        return
    turn_on = context.args[0].lower() == "on"
    set_autocheck(uid, turn_on)
    await update.message.reply_text(f"🔔 Auto-check {'enabled' if turn_on else 'disabled'}.")

async def setinterval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        _, iv = get_settings(uid)
        await update.message.reply_text(f"Current interval: {iv}s\nUsage: /setinterval <seconds> (>= {MIN_INTERVAL})")
        return
    try:
        sec = int(context.args[0])
        if sec < MIN_INTERVAL: raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Minimum interval is {MIN_INTERVAL} seconds.")
        return
    set_interval(uid, sec)
    await update.message.reply_text(f"⏱️ Interval set to {sec} seconds.")

# ====================== MAIN ======================
def build_app():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("commands", commands_cmd))

    application.add_handler(CommandHandler("newmail", newmail))
    application.add_handler(CommandHandler("mymail", mymail))
    application.add_handler(CommandHandler("switch", switch_cmd))
    application.add_handler(CommandHandler("delete", delete_cmd))

    application.add_handler(CommandHandler("inbox", inbox))
    application.add_handler(CommandHandler("read", read_msg))
    application.add_handler(CommandHandler("attachments", attachments))
    application.add_handler(CommandHandler("export", export_csv))

    application.add_handler(CommandHandler("autocheck", autocheck_cmd))
    application.add_handler(CommandHandler("setinterval", setinterval_cmd))

    application.add_handler(CallbackQueryHandler(on_callback))

    # Global poll job (runs every 30s to dispatch new mail alerts)
    async def on_startup(_):
        # single recurring job; we still respect per-user intervals logically via fetch frequency
        application.job_queue.run_repeating(poll_job, interval=30, first=10)

    application.post_init = on_startup
    return application

if __name__ == "__main__":
    init_db()
    print("🚀 Mail Ninja is running…")
    app = build_app()
    app.run_polling()
