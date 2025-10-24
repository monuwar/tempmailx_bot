import os
import random
import string
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

API_BASE = "https://api.mail.tm"
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ---------- Utility ----------
def generate_random_name():
    first = ["John", "Jane", "Alex", "Sam", "Chris", "Taylor", "Jordan", "Casey"]
    last = ["Doe", "Smith", "Brown", "Davis", "Miller", "Wilson", "Anderson"]
    return f"{random.choice(first)} {random.choice(last)}"

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ---------- Mail.tm ----------
def create_account():
    name = generate_random_name()
    password = generate_password()
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"{username}@tiffincrane.com"

    data = {"address": email, "password": password}
    session = requests.Session()
    session.post(f"{API_BASE}/accounts", json=data)
    token_resp = session.post(f"{API_BASE}/token", json=data)
    token = token_resp.json().get("token")

    return name, email, password, token

def fetch_inbox(token):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{API_BASE}/messages", headers=headers)
    return resp.json().get("hydra:member", [])

# ---------- Telegram ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Mail Ninja!\n\n"
        "📨 Use /newmail to generate a fresh temporary email.\n"
        "💾 Messages will appear here automatically."
    )

async def newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name, email, password, token = create_account()
    context.user_data["token"] = token

    msg = (
        "```congrats\n"
        "👤 USER INFO\n"
        f"Name     — {name}\n"
        f"Email    — {email}\n"
        f"Password — {password}\n"
        "```"
    )

    keyboard = [
        [InlineKeyboardButton("📥 View Inbox", callback_data="inbox"),
         InlineKeyboardButton("🆕 Generate / Delete", callback_data="newmail")]
    ]

    await update.message.reply_text(
        msg, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "newmail":
        await newmail(update, context)
        return

    if query.data == "inbox":
        token = context.user_data.get("token")
        if not token:
            await query.message.reply_text("⚠️ Please create a new email first using /newmail")
            return

        inbox = fetch_inbox(token)
        if not inbox:
            await query.message.reply_text("📭 Inbox is empty. Try again later.")
            return

        text = "📩 **Inbox Messages:**\n\n"
        for i, mail in enumerate(inbox[:5], start=1):
            subject = mail.get("subject", "No Subject")
            sender = mail.get("from", {}).get("address", "Unknown")
            text += f"{i}. ✉️ *{subject}*\n   From: `{sender}`\n\n"

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="inbox"),
             InlineKeyboardButton("📤 Back", callback_data="newmail")]
        ]

        await query.message.reply_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newmail", newmail))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("📬 Mail Ninja v3.9 — Stable Railway Build Running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
