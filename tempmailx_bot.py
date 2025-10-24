import os
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

MAIL_API = "https://api.mail.tm"
USER_DATA = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📬 *Mail Ninja Pro is Ready!*\n\n"
        "🧩 Commands:\n"
        "📮 /generate - Create new temp mail\n"
        "📥 /inbox - Check your inbox\n"
        "🔄 /refresh - Refresh inbox\n"
        "🗑️ /delete - Delete your mail\n"
        "💡 /help - Show this message again\n\n"
        "_Powered by Mail Ninja Pro 🥷_", parse_mode="Markdown"
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # delete old account if exists
    if user_id in USER_DATA:
        del USER_DATA[user_id]

    # create new account
    r = requests.post(f"{MAIL_API}/accounts", json={
        "address": "",
        "password": "mailninjapass"
    })
    if r.status_code == 201:
        account = r.json()
        USER_DATA[user_id] = {"address": account["address"], "password": "mailninjapass"}
        await update.message.reply_text(f"🎯 *New Mail Created:*\n`{account['address']}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Failed to generate email. Try again later.")

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in USER_DATA:
        await update.message.reply_text("⚠️ Please generate a mail first using /generate.")
        return

    token_res = requests.post(f"{MAIL_API}/token", json={
        "address": USER_DATA[user_id]["address"],
        "password": USER_DATA[user_id]["password"]
    })
    token = token_res.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}

    inbox = requests.get(f"{MAIL_API}/messages", headers=headers).json()["hydra:member"]
    if not inbox:
        await update.message.reply_text("📭 No messages yet.")
        return

    for msg in inbox:
        msg_detail = requests.get(f"{MAIL_API}/messages/{msg['id']}", headers=headers).json()
        sender = msg_detail["from"]["address"]
        subject = msg_detail["subject"]
        body = msg_detail.get("text", "No text content available.")
        date = msg_detail["createdAt"].split("T")[0]

        text = (
            f"📩 *New Email!*\n\n"
            f"👤 *From:* `{sender}`\n"
            f"🧾 *Subject:* `{subject}`\n"
            f"📅 *Date:* {date}\n\n"
            f"💬 *Message:*\n{body}"
        )

        buttons = [
            [InlineKeyboardButton("📥 Refresh", callback_data="refresh"),
             InlineKeyboardButton("🗑️ Delete", callback_data="delete")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await inbox(update, context)

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in USER_DATA:
        del USER_DATA[user_id]
        await update.message.reply_text("🗑️ Mail deleted successfully!")
    else:
        await update.message.reply_text("⚠️ No mail found to delete.")

def main():
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("generate", generate))
    app.add_handler(CommandHandler("inbox", inbox))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CommandHandler("delete", delete))

    print("Mail Ninja Pro 🥷 Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
