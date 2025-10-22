import asyncio
import aiohttp
import nest_asyncio
import uuid
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import os

nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://api.mail.tm"
user_data = {}

# --------------- Helper Functions ---------------
async def create_new_mail():
    username = f"{uuid.uuid4().hex[:10]}@tiffincrane.com"
    password = uuid.uuid4().hex
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BASE_URL}/accounts", json={"address": username, "password": password})
        resp = await session.post(f"{BASE_URL}/token", json={"address": username, "password": password})
        data = await resp.json()
        return username, data.get("token")

async def get_messages(token):
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(f"{BASE_URL}/messages", headers=headers) as resp:
            return await resp.json()

async def get_message_body(token, msg_id):
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(f"{BASE_URL}/messages/{msg_id}", headers=headers) as resp:
            return await resp.json()

# --------------- Auto-refresh System ---------------
async def auto_check_task(app):
    while True:
        await asyncio.sleep(5)  # 1s interval
        for user_id, data in user_data.items():
            token = data.get("token")
            if not token:
                continue
            messages = await get_messages(token)
            msg_list = messages.get("hydra:member", [])
            if msg_list:
                last_id = msg_list[0]["id"]
                if data.get("last_id") != last_id:
                    data["last_id"] = last_id
                    msg = msg_list[0]
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=f"📩 *New Email Received!*\n\n"
                             f"📧 *From:* {msg['from']['address']}\n"
                             f"📝 *Subject:* {msg['subject']}\n"
                             f"💬 *Preview:* {msg.get('intro', 'No content')}",
                        parse_mode="Markdown"
                    )

# --------------- Bot Commands ---------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data:
        email, token = await create_new_mail()
        user_data[user_id] = {"email": email, "token": token, "last_id": None}

    buttons = [
        [InlineKeyboardButton("📥 View Inbox", callback_data="refresh")],
        [InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        f"👋 *Welcome to Mail Ninja*\n\n"
        f"📧 Your temporary email:\n`{user_data[user_id]['email']}`\n\n"
        f"Use the buttons below to manage your mailbox.\n"
        f"🕒 Auto-refresh enabled (every 5s)\n\n"
        f"Type /help to see all commands.",
        parse_mode="Markdown",
        reply_markup=markup,
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id in user_data:
        old = user_data[user_id]["email"]
        user_data.pop(user_id, None)
        await query.edit_message_text(f"🗑️ Old email deleted:\n`{old}`", parse_mode="Markdown")

    email, token = await create_new_mail()
    user_data[user_id] = {"email": email, "token": token, "last_id": None}

    buttons = [
        [InlineKeyboardButton("📥 View Inbox", callback_data="refresh")],
        [InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    await query.message.reply_text(
        f"✅ New temporary email created:\n`{email}`\n\nYou can manage your mailbox below 👇",
        parse_mode="Markdown",
        reply_markup=markup,
    )

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_data:
        await query.edit_message_text("⚠️ Please use /start to create your temp mail first.")
        return

    token = user_data[user_id]["token"]
    email = user_data[user_id]["email"]
    messages = await get_messages(token)
    msg_list = messages.get("hydra:member", [])

    if not msg_list:
        text = f"📫 *Current email:*\n`{email}`\n\n_No new emails yet._"
    else:
        text = f"📬 *Current email:*\n`{email}`\n\n✉️ *Inbox messages:*\n"
        for i, msg in enumerate(msg_list, 1):
            text += f"\n{i}) *From:* {msg['from']['address']}\n*Subject:* {msg['subject']}"

    buttons = [
        [InlineKeyboardButton("📥 Refresh", callback_data="refresh")],
        [InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Mail Ninja — Help Menu*\n\n"
        "Available commands:\n"
        "• /start — Start or restart the bot\n"
        "• /newmail — Generate new temporary email\n"
        "• /inbox — View your mailbox\n"
        "• /autocheck — Toggle auto-refresh\n"
        "• /setinterval — Set refresh time\n"
        "• /help — Show this message\n\n"
        "Developed with ❤️ by [@Luizzsec](https://t.me/Luizzsec)",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

# --------------- Main ---------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(generate, pattern="generate"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))

    asyncio.create_task(auto_check_task(app))
    print("🚀 Mail Ninja v3.5 — Auto Refresh Edition running…")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
