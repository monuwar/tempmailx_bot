import os
import random
import string
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = "https://api.mail.tm"

# ---------- Utilities ----------
def random_name():
    first = ["Blake", "Ava", "Noah", "Liam", "Olivia", "Mason", "Emma", "Ethan", "Isla"]
    last = ["Allen", "Bennett", "Carter", "Davis", "Evans", "Foster", "Griffin", "Hill"]
    return f"{random.choice(first)} {random.choice(last)}"

def random_pass(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def create_account():
    name = random_name()
    password = random_pass()
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"{username}@tiffincrane.com"
    data = {"address": email, "password": password}
    s = requests.Session()
    s.post(f"{API_BASE}/accounts", json=data)
    token_resp = s.post(f"{API_BASE}/token", json=data)
    token = token_resp.json().get("token")
    return name, email, password, token

def get_inbox(token):
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API_BASE}/messages", headers=h)
    return r.json().get("hydra:member", [])

# ---------- UI Builders ----------
def make_info_text(name, email, password):
    return (
        f"📬 *Mail Ninja — Temp Inbox Ready!*\n\n"
        f"👤 *Profile*\n"
        f"🧾 Name: `{name}`\n"
        f"✉️ Email: `{email}`\n"
        f"🔐 Password: `{password}`\n\n"
        f"🟢 Status: Active\n"
        f"🔄 Auto-Refresh: Every 2 seconds"
    )

def make_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🔁 New Info", callback_data="newinfo")
        ],
        [
            InlineKeyboardButton("🧾 Copy Name", callback_data="copy_name"),
            InlineKeyboardButton("✉️ Copy Email", callback_data="copy_email"),
            InlineKeyboardButton("🔐 Copy Password", callback_data="copy_pass")
        ]
    ])

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Mail Ninja Pro v4.2 — Live Refresh Edition!\n\n"
        "Use /newmail to generate your temporary inbox.",
        parse_mode="Markdown"
    )

async def newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name, email, password, token = create_account()
    context.user_data.update({"name": name, "email": email, "password": password, "token": token})
    msg = await update.message.reply_text(make_info_text(name, email, password),
                                          parse_mode="Markdown",
                                          reply_markup=make_buttons())
    context.user_data["message_id"] = msg.message_id
    asyncio.create_task(auto_refresh(update, context))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    u = context.user_data

    if data == "newinfo":
        name, email, password, token = create_account()
        u.update({"name": name, "email": email, "password": password, "token": token})
        await q.message.edit_text(make_info_text(name, email, password),
                                  parse_mode="Markdown", reply_markup=make_buttons())

    elif data == "inbox":
        token = u.get("token")
        if not token:
            await q.message.reply_text("⚠️ No active session. Use /newmail first.")
            return
        inbox = get_inbox(token)
        if not inbox:
            text = "📭 No new messages yet."
        else:
            text = "📨 *Inbox Preview:*\n\n"
            for i, m in enumerate(inbox[:5], start=1):
                snd = m.get("from", {}).get("address", "Unknown")
                sbj = m.get("subject", "No Subject")
                prev = (m.get("intro", "") or "")[:80]
                text += f"{i}. *{sbj}*\nFrom: `{snd}`\n💬 _{prev}_\n\n"
        await q.message.edit_text(text, parse_mode="Markdown", reply_markup=make_buttons())

    elif data == "copy_name":
        await q.answer("✅ Name copied!", show_alert=True)
    elif data == "copy_email":
        await q.answer("✅ Email copied!", show_alert=True)
    elif data == "copy_pass":
        await q.answer("✅ Password copied!", show_alert=True)

async def auto_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    while True:
        await asyncio.sleep(2)
        token = context.user_data.get("token")
        if not token:
            continue
        inbox = get_inbox(token)
        if inbox:
            msg = inbox[0]
            text = f"📩 *New Mail!*\n\n*From:* {msg.get('from', {}).get('address','?')}\n" \
                   f"*Subject:* {msg.get('subject','No Subject')}\n\n" \
                   f"💬 Preview: {msg.get('intro','')}"
            try:
                await update.message.edit_text(text, parse_mode="Markdown",
                                               reply_markup=make_buttons())
            except:
                pass

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newmail", newmail))
    app.add_handler(CallbackQueryHandler(button))
    print("📬 Mail Ninja Pro v4.2 — Live Refresh Edition Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
