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

# Apply async patch for Railway
nest_asyncio.apply()

TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://api.mail.tm"
user_data = {}

# -------- Helper functions --------
async def create_new_mail():
    username = f"{uuid.uuid4().hex[:10]}@tiffincrane.com"
    password = uuid.uuid4().hex
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BASE_URL}/accounts",
                           json={"address": username, "password": password})
        resp = await session.post(f"{BASE_URL}/token",
                                  json={"address": username, "password": password})
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

# -------- Command handlers --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data:
        email, token = await create_new_mail()
        user_data[user_id] = {"email": email, "token": token}

    buttons = [
        [
            InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        f"👋 Welcome to *Mail Ninja* — secure temp mail inside Telegram.\n\n"
        f"📧 Current email:\n`{user_data[user_id]['email']}`\n\n"
        f"Use the buttons below 👇",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Delete old mail
    if user_id in user_data:
        old_email = user_data[user_id]["email"]
        await query.edit_message_text(f"🗑️ Old email deleted:\n`{old_email}`",
                                      parse_mode="Markdown")

    # Create new
    email, token = await create_new_mail()
    user_data[user_id] = {"email": email, "token": token}

    buttons = [
        [
            InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
        ]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.message.reply_text(f"✅ New email generated:\n`{email}`",
                                   parse_mode="Markdown",
                                   reply_markup=markup)

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in user_data:
        await query.edit_message_text("⚠️ Please /start to generate a mail first.")
        return

    token = user_data[user_id]["token"]
    messages = await get_messages(token)
    msg_list = messages.get("hydra:member", [])

    if not msg_list:
        await query.edit_message_text(
            f"📬 Current email:\n`{user_data[user_id]['email']}`\n\nNo new messages yet.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                ]]
            ),
        )
        return

    out = [f"📬 Current email:\n`{user_data[user_id]['email']}`\n\n✉️ Emails:"]
    for i, msg in enumerate(msg_list, 1):
        out.append(f"{i}) From: {msg['from']['address']}\nSubject: {msg['subject']}")
    text = "\n\n".join(out)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate"),
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
            ]]
        ),
    )

# -------- Main --------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(generate, pattern="generate"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))

    print("📨 Mail Ninja v2.2 PRO Final running…")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
