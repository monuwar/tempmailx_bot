import asyncio
import html
import re
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import json
import os
import time

# =================== CONFIG ===================
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://api.mail.tm"
USER_DATA_FILE = "user_data.json"

# =================== DATA STORAGE ===================
def load_users():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

USERS = load_users()
AUTO_JOBS = {}

# =================== MAIL.TM API ===================
class MailTm:
    @staticmethod
    def create_account():
        import uuid
        email = f"{uuid.uuid4().hex[:10]}@tiffincrane.com"  # 👈 Custom domain (no mail.tm)
        password = uuid.uuid4().hex
        r = requests.post(f"{BASE_URL}/accounts", json={"address": email, "password": password})
        return {"address": email, "password": password}

    @staticmethod
    def get_token(email, password):
        r = requests.post(f"{BASE_URL}/token", json={"address": email, "password": password})
        if r.status_code == 200:
            return r.json()["token"]
        return None

    @staticmethod
    def get_messages(token):
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/messages", headers=headers)
        if r.status_code == 200:
            return r.json()["hydra:member"]
        return []

    @staticmethod
    def get_message_detail(token, msg_id):
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/messages/{msg_id}", headers=headers)
        if r.status_code == 200:
            return r.json()
        return {}

# =================== USER FUNCTIONS ===================
def get_user(uid):
    return USERS.get(str(uid))

def set_user(uid, data):
    USERS[str(uid)] = data
    save_users(USERS)

def html_to_text(html_data):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", html_data)

# =================== COMMANDS ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user:
        user = MailTm.create_account()
        user["interval"] = 5  # default 5 sec
        user["auto"] = False
        set_user(uid, user)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Generate / Switch", callback_data="switch_mail"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_inbox"),
        ]
    ])
    await update.message.reply_text(
        f"📧 *Current email:* `{user['address']}`\n\nUse the buttons below 👇",
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No active email. Use /start to generate one.")
        return

    token = MailTm.get_token(user["address"], user["password"])
    if not token:
        await update.message.reply_text("❌ Token error. Please /start again.")
        return

    mails = MailTm.get_messages(token)
    if not mails:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🆕 Generate / Switch", callback_data="switch_mail"),
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_inbox"),
            ]
        ])
        await update.message.reply_text(
            f"📬 *Current email:* `{user['address']}`\n\n_No new messages yet._",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return

    msg_list = [f"📧 *Current email:* `{user['address']}`\n\n📩 *Inbox:*"]
    for i, mail in enumerate(mails[:5], start=1):
        sender = mail["from"]["address"]
        subject = mail.get("subject", "(no subject)")
        detail = MailTm.get_message_detail(token, mail["id"])
        body = detail.get("text", "") or html_to_text(detail.get("html", ""))
        preview = body[:1500] + ("..." if len(body) > 1500 else "")
        msg_list.append(f"📨 *{i})* From: `{sender}`\n*Subject:* {subject}\n\n{preview}\n")

    text = "\n".join(msg_list)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Generate / Switch", callback_data="switch_mail"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_inbox"),
        ]
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

# =================== AUTO REFRESH ===================
async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    uid = job.data["uid"]
    chat_id = job.data["chat_id"]
    user = get_user(uid)
    if not user:
        return
    token = MailTm.get_token(user["address"], user["password"])
    mails = MailTm.get_messages(token)
    if not mails:
        return
    latest = mails[0]
    last_seen = user.get("last_seen")
    if latest["id"] != last_seen:
        user["last_seen"] = latest["id"]
        set_user(uid, user)
        detail = MailTm.get_message_detail(token, latest["id"])
        body = detail.get("text", "") or html_to_text(detail.get("html", ""))
        msg = f"📩 *New mail received!*\n\n*From:* `{latest['from']['address']}`\n*Subject:* {latest['subject']}`\n\n{body[:1500]}"
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def autocheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    user = get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /start first.")
        return

    if len(context.args) == 0:
        await update.message.reply_text(f"Usage: /autocheck on|off (interval {user.get('interval', 5)}s)")
        return

    action = context.args[0].lower()
    if action == "on":
        job_queue = context.job_queue
        AUTO_JOBS[uid] = job_queue.run_repeating(auto_check, interval=user.get("interval", 5), first=1, data={"uid": uid, "chat_id": chat_id})
        user["auto"] = True
        set_user(uid, user)
        await update.message.reply_text("✅ Auto-check enabled.")
    elif action == "off":
        if uid in AUTO_JOBS:
            AUTO_JOBS[uid].schedule_removal()
            del AUTO_JOBS[uid]
        user["auto"] = False
        set_user(uid, user)
        await update.message.reply_text("🛑 Auto-check disabled.")
    else:
        await update.message.reply_text("Use /autocheck on or /autocheck off")

async def setinterval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /start first.")
        return
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /setinterval <seconds>")
        return
    sec = int(context.args[0])
    if sec < 1:
        sec = 1
    user["interval"] = sec
    set_user(uid, user)
    await update.message.reply_text(f"⏱️ Interval set to {sec}s")

# =================== CALLBACK ===================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "refresh_inbox":
        fake_update = Update(update.update_id, message=None)
        fake_update.effective_user = q.from_user
        fake_update.message = type("obj", (), {"chat_id": q.message.chat_id, "reply_text": q.message.reply_text})
        await inbox(fake_update, context)

    elif data == "switch_mail":
        new = MailTm.create_account()
        set_user(uid, new)
        await q.edit_message_text(f"✅ New email generated:\n`{new['address']}`", parse_mode="Markdown")

# =================== MAIN ===================
async def main():
    print("📬 Mail Ninja v2.0 is running...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("inbox", inbox))
    app.add_handler(CommandHandler("autocheck", autocheck))
    app.add_handler(CommandHandler("setinterval", setinterval))
    app.add_handler(CallbackQueryHandler(on_callback))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
