import random
import string
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

MAIL_API = "https://api.mail.tm"

USER_DATA = {}

# Generate random password (letters + digits only)
def generate_password(length=9):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# Generate random realistic name
def generate_name():
    first_names = [
        "John", "Alex", "Emma", "Sophia", "James", "Olivia",
        "Liam", "Ava", "Ethan", "Mia", "Noah", "Grace",
        "Lucas", "Ella", "Mason", "Lily", "Henry", "Zoe"
    ]
    last_names = [
        "Doe", "Smith", "Brown", "Taylor", "Wilson",
        "Anderson", "Thomas", "Clark", "Harris", "Lewis",
        "Walker", "Young", "King", "Scott", "Hall"
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

# /newmail command
async def newmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Generate new random name and password
    name = generate_name()
    password = generate_password()

    # Create a new mail.tm account
    account_res = requests.post(f"{MAIL_API}/accounts", json={
        "address": "",
        "password": password
    })

    account = account_res.json()

    if "address" not in account:
        await update.message.reply_text("⚠️ Failed to generate a new email. Please try again.")
        return

    email_address = account["address"]

    # Save user data
    USER_DATA[user_id] = {
        "name": name,
        "email": email_address,
        "password": password
    }

    # Stylish info block (monospace with copy option)
    info_block = (
        "```\n"
        "────────────────────────\n"
        f"Name: {name}\n"
        f"Email: {email_address}\n"
        f"Password: {password}\n"
        "────────────────────────\n"
        "```"
    )

    buttons = [
        [InlineKeyboardButton("📥 View Inbox", callback_data="inbox")],
        [InlineKeyboardButton("🆕 Generate / Delete", callback_data="generate")]
    ]

    await update.message.reply_text(
        f"✅ *Your new temporary email has been generated!*\n\n{info_block}",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
