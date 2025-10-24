import os, asyncio, random, string, re, requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import nest_asyncio

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = "https://api.mail.tm"
REFRESH_INTERVAL = 2  # seconds


# ========== UTILITIES ==========
def random_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def random_name():
    first_names = ["Olivia", "Mason", "Ava", "Liam", "Ella", "Noah", "Isla", "Blake", "Sophia"]
    last_names = ["Davis", "Brooks", "Allen", "Foster", "Green", "Hill", "Carter"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

async def fetch_mailbox():
    try:
        r = requests.get(f"{API_BASE}/messages")
        if r.status_code == 200:
            data = r.json()
            return data.get("hydra:member", [])
    except Exception as e:
        print("Mail fetch error:", e)
    return []


# ========== HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *Mail Ninja Pro v4.5 — Live Refresh + Smart UI Edition!*\n\n"
        "Use /newmail to generate your temporary inbox.",
        parse_mode="Markdown"
    )

async def newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = random_name()
    email = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@tiffincrane.com"
    password = random_password()

    context.user_data["name"] = name
    context.user_data["email"] = email
    context.user_data["password"] = password
    context.user_data["html"] = None
    context.user_data["last_msg_id"] = None

    text = (
        "📬 *Mail Ninja — Temp Inbox Ready!*\n\n"
        "👤 *Profile*\n"
        f"🧾 *Name:* {name}\n"
        f"✉️ *Email:* {email}\n"
        f"🔐 *Password:* {password}\n\n"
        "🟢 *Status:* Active\n"
        f"⏱️ *Auto-Refresh:* Every {REFRESH_INTERVAL} seconds"
    )

    keyboard = [
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🆕 New Info", callback_data="newinfo")
        ]
    ]

    msg = await update.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    context.user_data["main_msg"] = msg
    context.job_queue.run_repeating(auto_refresh, REFRESH_INTERVAL, context=update.message.chat_id)


async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mails = await fetch_mailbox()
    if not mails:
        await query.edit_message_text(
            text=query.message.text_markdown + "\n\n📭 *Inbox is empty.*",
            parse_mode="Markdown"
        )
        return

    mail = mails[0]
    sender = mail.get("from", {}).get("address", "Unknown")
    subject = mail.get("subject", "No subject")
    preview = mail.get("intro", "No preview")
    html = mail.get("html", [""])[0] if mail.get("html") else "No HTML content."
    context.user_data["html"] = html

    links = re.findall(r'https?://[^\s]+', html)
    link_text = f"\n\n🔗 [Link]({links[0]})" if links else ""

    updated_text = (
        query.message.text_markdown +
        f"\n\n📨 *New Mail!*\n\n"
        f"📬 From: {sender}\n"
        f"📨 Subject: {subject}\n"
        f"💬 Preview: {preview}{link_text}"
    )

    keyboard = [
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🆕 New Info", callback_data="newinfo"),
        ],
        [InlineKeyboardButton("📄 View HTML", callback_data="viewhtml")]
    ]

    await query.edit_message_text(
        text=updated_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def newinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    name = random_name()
    email = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@tiffincrane.com"
    password = random_password()

    context.user_data["name"] = name
    context.user_data["email"] = email
    context.user_data["password"] = password

    text = (
        "📬 *Mail Ninja — Temp Inbox Ready!*\n\n"
        "👤 *Profile*\n"
        f"🧾 *Name:* {name}\n"
        f"✉️ *Email:* {email}\n"
        f"🔐 *Password:* {password}\n\n"
        "🟢 *Status:* Active\n"
        f"⏱️ *Auto-Refresh:* Every {REFRESH_INTERVAL} seconds"
    )

    keyboard = [
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🆕 New Info", callback_data="newinfo")
        ]
    ]

    await query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def viewhtml(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    html_content = context.user_data.get("html", "No HTML content found.")
    await query.message.reply_text(html_content[:4000])


async def auto_refresh(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.context
    mails = await fetch_mailbox()
    if mails:
        mail = mails[0]
        sender = mail.get("from", {}).get("address", "Unknown")
        subject = mail.get("subject", "No subject")
        preview = mail.get("intro", "No preview")

        links = re.findall(r'https?://[^\s]+', mail.get("html", [""])[0])
        link_text = f"\n\n🔗 [Link]({links[0]})" if links else ""

        await context.bot.send_message(
            chat_id,
            f"📨 *New Mail Automatically Received!*\n\n"
            f"📬 From: {sender}\n"
            f"📨 Subject: {subject}\n"
            f"💬 Preview: {preview}{link_text}",
            parse_mode="Markdown"
        )


# ========== MAIN ==========
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newmail", newmail))
    app.add_handler(CallbackQueryHandler(inbox, pattern="inbox"))
    app.add_handler(CallbackQueryHandler(newinfo, pattern="newinfo"))
    app.add_handler(CallbackQueryHandler(viewhtml, pattern="viewhtml"))

    print("📬 Mail Ninja Pro v4.5 — Live Refresh + Smart UI Edition Running...")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
