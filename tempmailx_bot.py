import os, asyncio, random, string, re, requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ==============================
# 🔧 CONFIGURATION
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Token already set in Railway
API_BASE = "https://api.mail.tm"
REFRESH_INTERVAL = 2  # seconds

# ==============================
# ⚙️ UTILITIES
# ==============================
def random_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def random_name():
    first_names = ["Blake", "Isla", "Mason", "Liam", "Ava", "Ella", "Noah"]
    last_names = ["Foster", "Allen", "Carter", "Brooks", "Green", "Hill"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

async def fetch_mailbox():
    """Fetch inbox emails from mail.tm"""
    try:
        response = requests.get(f"{API_BASE}/messages")
        if response.status_code == 200:
            data = response.json()
            return data.get("hydra:member", [])
    except Exception as e:
        print("Mail fetch error:", e)
    return []

# ==============================
# 🚀 BOT HANDLERS
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *Mail Ninja Pro v4.3 — Live Refresh Edition!*\n\n"
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

    keyboard = [
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🆕 New Info", callback_data="newinfo")
        ],
        [InlineKeyboardButton("📄 View HTML", callback_data="viewhtml")]
    ]

    await update.message.reply_text(
        text=(
            f"🎉 *Your Temporary Email is Ready!*\n\n"
            f"👤 *USER INFO*\n"
            f"Name — {name}\n"
            f"Email — {email}\n"
            f"Password — {password}\n\n"
            f"🟢 *Status:* Active\n"
            f"⏱️ *Auto-Refresh:* Every {REFRESH_INTERVAL} seconds"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Start background auto-refresh
    context.job_queue.run_repeating(auto_check, interval=REFRESH_INTERVAL, context=update.message.chat_id)

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    inbox_data = await fetch_mailbox()
    if not inbox_data:
        await query.message.reply_text("📭 Inbox is empty.")
        return

    message = inbox_data[0]
    sender = message.get("from", {}).get("address", "Unknown")
    subject = message.get("subject", "No subject")
    preview = message.get("intro", "No preview")
    html = message.get("html", [""])[0] if message.get("html") else "No HTML found."
    context.user_data["html"] = html

    links = re.findall(r'https?://[^\s]+', html)
    link_text = f"\n\n🔗 [Link]({links[0]})" if links else ""

    await query.message.reply_text(
        f"📩 *New Email Received!*\n\n"
        f"📬 From: {sender}\n"
        f"📨 Subject: {subject}\n"
        f"💬 Preview: {preview}{link_text}",
        parse_mode="Markdown"
    )

async def viewhtml(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    html_content = context.user_data.get("html", "No HTML content found.")
    await query.message.reply_text(html_content[:4000])

async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.context
    mails = await fetch_mailbox()
    if mails:
        await context.bot.send_message(chat_id=chat_id, text="📨 *New Mail Arrived Automatically!*", parse_mode="Markdown")

# ==============================
# 🧠 MAIN
# ==============================
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newmail", newmail))
    app.add_handler(CallbackQueryHandler(inbox, pattern="inbox"))
    app.add_handler(CallbackQueryHandler(viewhtml, pattern="viewhtml"))

    print("📬 Mail Ninja Pro v4.3 — Auto HTML + Link Edition Running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
