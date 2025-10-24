import os, asyncio, random, string, re, requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import nest_asyncio, time

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = "https://api.mail.tm"
REFRESH_INTERVAL = 2  # seconds


def random_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def random_name():
    first = ["Olivia", "Mason", "Ava", "Liam", "Ella", "Noah", "Isla", "Blake", "Sophia"]
    last = ["Davis", "Brooks", "Allen", "Foster", "Green", "Hill", "Carter"]
    return f"{random.choice(first)} {random.choice(last)}"


async def create_mail_account():
    domain_resp = requests.get(f"{API_BASE}/domains")
    domain = domain_resp.json()["hydra:member"][0]["domain"]
    local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"{local}@{domain}"
    password = random_password()
    requests.post(f"{API_BASE}/accounts", json={"address": email, "password": password})
    time.sleep(2)  # let mail.tm register
    token_resp = requests.post(f"{API_BASE}/token", json={"address": email, "password": password})
    token = token_resp.json().get("token")
    return email, password, token


async def get_inbox(token):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{API_BASE}/messages", headers=headers)
        if r.status_code == 200:
            return r.json().get("hydra:member", [])
    except Exception as e:
        print("Inbox fetch error:", e)
    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *Mail Ninja Pro v4.8 — Smart Popup Build!*\n\n"
        "Use /newmail to generate your temporary inbox.",
        parse_mode="Markdown"
    )


async def newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = random_name()
    email, password, token = await create_mail_account()

    context.user_data.update({
        "name": name,
        "email": email,
        "password": password,
        "token": token,
        "html": None,
        "last_id": None
    })

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
        [InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
         InlineKeyboardButton("🆕 New Info", callback_data="newinfo")]
    ]

    msg = await update.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["main_msg_id"] = msg.message_id
    context.job_queue.run_repeating(auto_refresh, REFRESH_INTERVAL, context=(update.message.chat_id, token))


async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    token = context.user_data.get("token")
    mails = await get_inbox(token)

    # ✅ popup instead of “Inbox is empty” message
    if not mails:
        await query.answer("📭 No new mail found!", show_alert=True)
        return

    mail = mails[0]
    sender = mail.get("from", {}).get("address", "Unknown")
    subject = mail.get("subject", "No subject")
    preview = mail.get("intro", "No preview")
    html = mail.get("html", [""])[0] if mail.get("html") else "No HTML content."
    context.user_data["html"] = html

    links = re.findall(r'https?://[^\s]+', html)
    link_text = f"\n\n🔗 [Link]({links[0]})" if links else ""

    text = (
        "📬 *Mail Ninja — Temp Inbox Ready!*\n\n"
        "👤 *Profile*\n"
        f"🧾 *Name:* {context.user_data['name']}\n"
        f"✉️ *Email:* {context.user_data['email']}\n"
        f"🔐 *Password:* {context.user_data['password']}\n\n"
        "🟢 *Status:* Active\n"
        f"⏱️ *Auto-Refresh:* Every {REFRESH_INTERVAL} seconds\n\n"
        "📨 *New Mail!*\n"
        f"📬 From: {sender}\n"
        f"📨 Subject: {subject}\n"
        f"💬 Preview: {preview}{link_text}"
    )

    keyboard = [
        [InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
         InlineKeyboardButton("🆕 New Info", callback_data="newinfo")],
        [InlineKeyboardButton("📄 View HTML", callback_data="viewhtml")]
    ]

    await query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def newinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    name = random_name()
    email, password, token = await create_mail_account()

    context.user_data.update({
        "name": name,
        "email": email,
        "password": password,
        "token": token,
        "html": None,
        "last_id": None
    })

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
        [InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
         InlineKeyboardButton("🆕 New Info", callback_data="newinfo")]
    ]

    # ✅ এখন নতুন ইনফো নতুন বক্সে পাঠাবে, আগেরটা রিপ্লেস করবে না
    await query.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # নতুন বক্সের ইনবক্স অটো-রিফ্রেশও শুরু করবে
    context.job_queue.run_repeating(auto_refresh, REFRESH_INTERVAL, context=(query.message.chat_id, token))async def newinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    name = random_name()
    email, password, token = await create_mail_account()

    context.user_data.update({
        "name": name,
        "email": email,
        "password": password,
        "token": token,
        "html": None,
        "last_id": None
    })

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
        [InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
         InlineKeyboardButton("🆕 New Info", callback_data="newinfo")]
    ]

    # ✅ এখন নতুন ইনফো নতুন বক্সে পাঠাবে, আগেরটা রিপ্লেস করবে না
    await query.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # নতুন বক্সের ইনবক্স অটো-রিফ্রেশও শুরু করবে
    context.job_queue.run_repeating(auto_refresh, REFRESH_INTERVAL, context=(query.message.chat_id, token))


async def viewhtml(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    html = context.user_data.get("html", "No HTML content found.")
    await query.message.reply_text(html[:4000], disable_web_page_preview=False)


async def auto_refresh(context: ContextTypes.DEFAULT_TYPE):
    chat_id, token = context.job.context
    mails = await get_inbox(token)
    if mails:
        mail = mails[0]
        mail_id = mail["id"]
        if context.chat_data.get("last_id") == mail_id:
            return
        context.chat_data["last_id"] = mail_id
        sender = mail.get("from", {}).get("address", "Unknown")
        subject = mail.get("subject", "No subject")
        preview = mail.get("intro", "No preview")
        html = mail.get("html", [""])[0] if mail.get("html") else ""
        links = re.findall(r'https?://[^\s]+', html)
        link_text = f"\n\n🔗 [Link]({links[0]})" if links else ""
        await context.bot.send_message(
            chat_id,
            f"📨 *New Mail Auto-Received!*\n\n"
            f"📬 From: {sender}\n"
            f"📨 Subject: {subject}\n"
            f"💬 Preview: {preview}{link_text}",
            parse_mode="Markdown"
        )


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newmail", newmail))
    app.add_handler(CallbackQueryHandler(inbox, pattern="inbox"))
    app.add_handler(CallbackQueryHandler(newinfo, pattern="newinfo"))
    app.add_handler(CallbackQueryHandler(viewhtml, pattern="viewhtml"))
    print("📬 Mail Ninja Pro v4.8 — Smart Popup Build Running...")
    await app.run_polling()


if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
