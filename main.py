import telebot
from telebot import types
import sqlite3
import time
import threading
import re
import os
import random
from datetime import datetime
from flask import Flask

# === BOT CONFIGURATION ===
BOT_TOKEN = "YAHAN_APNA_NAYA_TOKEN_PASTE_KAREIN"
CHANNEL_USERNAME = "@ai2kmm"
ADMIN_USERNAME = "@egofiremax"
ADMIN_GROUP = "-1004322519230"  # Aapki Admin Group ID
UPI_ID = "kumar.14534@superyes"

bot = telebot.TeleBot(BOT_TOKEN)
BOT_USERNAME = bot.get_me().username
url_pattern = re.compile(r'(https?://\S+|www\.\S+|\b\w+\.\w{2,}\b)')

# === DATABASE SETUP ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "stranger_bot.db")

db_lock = threading.Lock() 
q_lock = threading.Lock() 

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    with db_lock:
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, verified INTEGER DEFAULT 0,
            name TEXT, age INTEGER, gender TEXT, state TEXT, 
            is_vip INTEGER DEFAULT 0, vip_expiry REAL,
            warnings INTEGER DEFAULT 0, banned_until REAL DEFAULT 0,
            referred_by INTEGER DEFAULT 0, last_active REAL,
            vip_warned INTEGER DEFAULT 0, username TEXT
        )''')
        try: cursor.execute("ALTER TABLE users ADD COLUMN last_active REAL")
        except: pass
        try: cursor.execute("ALTER TABLE users ADD COLUMN vip_warned INTEGER DEFAULT 0")
        except: pass
        try: cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        except: pass
        conn.commit()

init_db()

# === GLOBAL VARIABLES ===
user_states = {} 
waiting_queue = [] 
active_chats = {} 
ai_chats = {} 
pending_photos = {} 

# === KEYBOARDS ===
def get_main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add("🔍 /search", "👤 /profile", "✏️ /editprofile")
    m.add("💎 /vip", "🔗 /invite")
    return m

def get_chat_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    m.add("⏭️ /next", "🛑 /stop", "💌 /share")
    return m

# === HELPER FUNCTIONS ===
def update_activity(user_id, username):
    now = time.time()
    uname = username.lower() if username else ""
    with db_lock:
        cursor.execute("UPDATE users SET last_active=?, username=? WHERE user_id=?", (now, uname, user_id))
        conn.commit()

def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['creator', 'administrator', 'member']
    except: 
        return False

def get_user(user_id):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cursor.fetchone()

def is_vip(user_id):
    u = get_user(user_id)
    return True if u and u[6] == 1 and u[7] and time.time() < u[7] else False

def check_ban(user_id):
    u = get_user(user_id)
    if u and u[9] > time.time():
        return True, int((u[9] - time.time()) / 3600)
    return False, 0

def auto_delete_msg(chat1, msg1, chat2, msg2, delay):
    time.sleep(delay)
    try:
        bot.delete_message(chat1, msg1)
        if msg2: bot.delete_message(chat2, msg2)
    except: pass

def disconnect_chat(user_id, send_msg=True):
    if user_id in active_chats:
        p_id = active_chats.pop(user_id)
        if p_id in active_chats: del active_chats[p_id]
        if send_msg:
            try: bot.send_message(user_id, "🚫 Chat disconnected.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
            except: pass
            try: bot.send_message(p_id, "🚫 Your partner has stopped the chat.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
            except: pass
            
    if user_id in ai_chats:
        del ai_chats[user_id]
        if send_msg:
            try: bot.send_message(user_id, "🚫 Chat disconnected.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
            except: pass

def find_match(user_id, pref_gender="Any"):
    u = get_user(user_id)
    if not u: return False
    u_gender = u[4]
    
    global waiting_queue
    with q_lock:
        for i, w_user in enumerate(waiting_queue):
            w_id = w_user['id']
            w_pref, w_gender = w_user['pref'], w_user['gender']
            if w_id == user_id: continue
            
            if (pref_gender == "Any" or pref_gender == w_gender) and (w_pref == "Any" or w_pref == u_gender):
                waiting_queue.pop(i)
                active_chats[user_id] = w_id
                active_chats[w_id] = user_id
                
                if user_id in ai_chats: del ai_chats[user_id]
                if w_id in ai_chats: del ai_chats[w_id]
                
                try: bot.send_message(user_id, "✅ Real Stranger found! Say Hi! 👋\n\n👑 Owner: @egofiremax", reply_markup=get_chat_menu())
                except: pass
                try: bot.send_message(w_id, "✅ Real Stranger found! Say Hi! 👋\n\n👑 Owner: @egofiremax", reply_markup=get_chat_menu())
                except: pass
                return True
                
        if not any(w['id'] == user_id for w in waiting_queue):
            waiting_queue.append({'id': user_id, 'gender': u_gender, 'pref': pref_gender})
            
    try: bot.send_message(user_id, "⏳ Looking for a real stranger... Please wait.\nType /stop to cancel.\n\n👑 Owner: @egofiremax")
    except: pass
    
    threading.Thread(target=safe_ai_fallback_timer, args=(user_id,)).start()
    return False

def safe_ai_fallback_timer(user_id):
    time.sleep(6)
    global waiting_queue
    in_queue = False
    
    with q_lock:
        for w in waiting_queue:
            if w['id'] == user_id:
                in_queue = True
                break
        if in_queue:
            waiting_queue = [w for w in waiting_queue if w['id'] != user_id]
            
    if in_queue and user_id not in active_chats and user_id not in ai_chats:
        ai_chats[user_id] = {"step": 0}
        try:
            bot.send_message(user_id, "✅ Real Stranger found! Say Hi! 👋\n\n👑 Owner: @egofiremax", reply_markup=get_chat_menu())
            age = random.choice([17, 18, 19, 20])
            openings = [
                f"F{age} here from India and you? 😉",
                f"Hey! F{age} this side, bore ho rahi thi toh aagyi. Tum batao?",
                f"Hi there! F{age} from Mumbai, koi cute sa banda hai kya yahan? ✨",
                f"Hello! F{age} here, single hu aur bore ho rahi hu 🙈 tum kahan se ho?",
                f"Hieee! F{age} this side, kya chal raha hai?"
            ]
            time.sleep(1)
            bot.send_message(user_id, random.choice(openings))
        except: pass

# === COMMAND HANDLERS ===
@bot.message_handler(commands=['start'])
def start_bot(msg):
    u_id = msg.from_user.id
    username = msg.from_user.username
    user = get_user(u_id)
    
    if user and check_ban(u_id)[0]:
        bot.send_message(u_id, "🚫 You are BANNED for spamming.\n\n👑 Owner: @egofiremax")
        return

    if not user:
        with db_lock:
            cursor.execute("INSERT INTO users (user_id, username, last_active) VALUES (?, ?, ?)", (u_id, username, time.time()))
            conn.commit()
        user = get_user(u_id)
    else:
        update_activity(u_id, username)

    parts = msg.text.split()
    if not user[2] and len(parts) > 1 and parts[1].isdigit() and int(parts[1]) != u_id:
        ref_id = int(parts[1])
        with db_lock:
            cursor.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref_id, u_id))
            conn.commit()

    if not is_subscribed(u_id):
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔄 Verify", callback_data="verify_sub"))
        bot.send_message(u_id, f"⚠️ Please join our official channel first, then verify.\n👉 {CHANNEL_USERNAME}\n\n👑 Owner: @egofiremax", reply_markup=m)
        return

    with db_lock:
        cursor.execute("UPDATE users SET verified=1 WHERE user_id=?", (u_id,))
        conn.commit()

    if not user[2]:
        user_states[u_id] = 'W_NAME'
        bot.send_message(u_id, "👋 Welcome! Please enter your First Name:")
    elif not user[3]:
        user_states[u_id] = 'W_AGE'
        bot.send_message(u_id, f"Hello {user[2]}! Please enter your Age (in numbers):")
    elif not user[4]:
        user_states[u_id] = 'W_GENDER'
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add("👦 Male", "👧 Female")
        bot.send_message(u_id, "What is your Gender?", reply_markup=m)
    elif not user[5]:
        user_states[u_id] = 'W_STATE'
        bot.send_message(u_id, "Great! Which State/City are you from? (e.g., Mumbai, Delhi):", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.send_message(u_id, "🌟 Welcome back to Stranger Chat!\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())

@bot.callback_query_handler(func=lambda c: c.data == 'verify_sub')
def verify_subscription(c):
    if is_subscribed(c.from_user.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.send_message(c.from_user.id, "✅ Channel verified! You can now use the bot. Type /start to continue.")
    else:
        bot.answer_callback_query(c.id, "❌ Aapne abhi tak channel join nahi kiya hai!", show_alert=True)

@bot.message_handler(commands=['profile'])
def show_profile(msg):
    update_activity(msg.from_user.id, msg.from_user.username)
    u_id = msg.from_user.id
    u = get_user(u_id)
    if not u or not u[5]:
        bot.send_message(u_id, "❌ Your profile is incomplete. Type /start.")
        return
    v_stat = f"✅ Active" if is_vip(u_id) else "❌ Inactive"
    txt = f"👤 **YOUR PROFILE**\n📜 Name: {u[2]}\n🎂 Age: {u[3]}\n🚻 Gender: {u[4]}\n📍 Area: {u[5]}\n💎 VIP: {v_stat}\n\n👑 Owner: {ADMIN_USERNAME}"
    bot.send_message(u_id, txt, parse_mode="Markdown")

@bot.message_handler(commands=['editprofile'])
def edit_profile(msg):
    update_activity(msg.from_user.id, msg.from_user.username)
    u_id = msg.from_user.id
    u = get_user(u_id)
    if not u or not u[5]:
        bot.send_message(u_id, "❌ Please complete your profile first using /start")
        return
    user_states[u_id] = 'EDIT_NAME'
    bot.send_message(u_id, f"✏️ Enter your new First Name (current: {u[2]}):")

@bot.message_handler(commands=['vip'])
def vip_plan(msg):
    update_activity(msg.from_user.id, msg.from_user.username)
    pay_msg = f"💎 **NEW VIP PLANS** 💎\n\n🌟 1 Week - ₹49\n🌟 2 Weeks - ₹99\n🌟 1 Month - ₹150\n\nUPI ID: `{UPI_ID}`\nSend Screenshot to 👉 {ADMIN_USERNAME}\n\n👑 Owner: {ADMIN_USERNAME}"
    bot.send_message(msg.chat.id, pay_msg, parse_mode="Markdown")

@bot.message_handler(commands=['invite'])
def invite_link(msg):
    update_activity(msg.from_user.id, msg.from_user.username)
    link = f"https://t.me/{BOT_USERNAME}?start={msg.from_user.id}"
    bot.send_message(msg.chat.id, f"🎁 **Referral Program**\n🔗 {link}\nGet 2 Hours Free VIP per invite!\n\n👑 Owner: {ADMIN_USERNAME}")

@bot.message_handler(commands=['addvip'])
def add_vip_start(msg):
    if msg.from_user.username == None or msg.from_user.username.lower() != ADMIN_USERNAME.replace('@', '').lower():
        bot.send_message(msg.chat.id, f"You want be a vip user so contact owner - {ADMIN_USERNAME}")
        return
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("By Username (@)", callback_data="vipby_uname"),
          types.InlineKeyboardButton("By TG ID", callback_data="vipby_id"))
    bot.send_message(msg.chat.id, "VIP kis detail ke zariye add karna hai?", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith('vipby_'))
def ask_vip_detail(c):
    bot.delete_message(c.message.chat.id, c.message.message_id)
    if c.data == "vipby_uname":
        m = bot.send_message(c.message.chat.id, "User ka Telegram Username bhejiye (bina @ ke):")
        bot.register_next_step_handler(m, process_vip_target, "username")
    else:
        m = bot.send_message(c.message.chat.id, "User ki Telegram ID bhejiye:")
        bot.register_next_step_handler(m, process_vip_target, "id")

def process_vip_target(msg, method):
    target = msg.text.replace('@', '').strip().lower()
    target_id = None
    
    with db_lock:
        if method == "username":
            cursor.execute("SELECT user_id FROM users WHERE username=?", (target,))
            row = cursor.fetchone()
            if row: target_id = row[0]
        else:
            if target.isdigit(): target_id = int(target)
            cursor.execute("SELECT user_id FROM users WHERE user_id=?", (target_id,))
            if not cursor.fetchone(): target_id = None
            
    if not target_id:
        return bot.send_message(msg.chat.id, "❌ User database mein nahi mila! Dhyan rahe user ne ek baar bot start kiya ho.")
        
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("1 Week", callback_data=f"setvip_7_{target_id}"))
    m.add(types.InlineKeyboardButton("2 Weeks", callback_data=f"setvip_14_{target_id}"))
    m.add(types.InlineKeyboardButton("1 Month", callback_data=f"setvip_30_{target_id}"))
    bot.send_message(msg.chat.id, f"✅ User mil gaya (ID: {target_id}). Kitne time ka VIP dena hai?", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith('setvip_'))
def finalize_vip(c):
    parts = c.data.split('_')
    days = int(parts[1])
    target_id = int(parts[2])
    
    expiry = time.time() + (days * 86400)
    with db_lock:
        cursor.execute("UPDATE users SET is_vip=1, vip_expiry=?, vip_warned=0 WHERE user_id=?", (expiry, target_id))
        conn.commit()
    
    bot.delete_message(c.message.chat.id, c.message.message_id)
    bot.send_message(c.message.chat.id, f"🎉 Success! User {target_id} ko {days} days ka VIP mil gaya.")
    try: bot.send_message(target_id, f"🎉 Congratulations! Aapke account mein {days} Days ka VIP plan activate kar diya gaya hai.\n\n👑 Owner: @egofiremax")
    except: pass

@bot.message_handler(commands=['share'])
def share_uname(msg):
    u_id = msg.from_user.id
    uname = msg.from_user.username
    if u_id in active_chats:
        if uname:
            bot.send_message(active_chats[u_id], f"💌 Partner shared ID: @{uname}")
            bot.send_message(u_id, "✅ Username sent!")
        else: bot.send_message(u_id, "❌ Set Telegram Username in app settings.")
    else: bot.send_message(u_id, "Not in a chat.")

@bot.message_handler(commands=['search', 'next', 'skip'])
def search_stranger(msg):
    u_id = msg.from_user.id
    update_activity(u_id, msg.from_user.username)
    
    if check_ban(u_id)[0]: return
    
    if not is_subscribed(u_id):
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔄 Verify", callback_data="verify_sub"))
        bot.send_message(u_id, f"⚠️ Aapne hamara channel leave kar diya hai!\nBot ko aage use karne ke liye pehle channel join karein: {CHANNEL_USERNAME}", reply_markup=m)
        return

    u = get_user(u_id)
    if not u or not u[5]:
        bot.send_message(u_id, "❌ Profile incomplete. Type /start.")
        return
    disconnect_chat(u_id, False)
    global waiting_queue
    with q_lock:
        waiting_queue = [w for w in waiting_queue if w['id'] != u_id]
    if is_vip(u_id):
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("👦 Male", callback_data="f_M"), types.InlineKeyboardButton("👧 Female", callback_data="f_F"), types.InlineKeyboardButton("🎲 Any", callback_data="f_Any"))
        bot.send_message(u_id, "💎 VIP: Choose Gender:\n\n👑 Owner: @egofiremax", reply_markup=m)
    else: find_match(u_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('f_'))
def process_find(c):
    bot.delete_message(c.message.chat.id, c.message.message_id)
    find_match(c.from_user.id, c.data.split('_')[1])

@bot.message_handler(commands=['stop'])
def stop_chat(msg):
    u_id = msg.from_user.id
    update_activity(u_id, msg.from_user.username)
    global waiting_queue
    was_w = False
    with q_lock:
        was_w = any(w['id'] == u_id for w in waiting_queue)
        waiting_queue = [w for w in waiting_queue if w['id'] != u_id]
    if u_id in active_chats or u_id in ai_chats: disconnect_chat(u_id, True)
    elif was_w: bot.send_message(u_id, "🚫 Stopped searching.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
    else: bot.send_message(u_id, "Not in a chat.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())

@bot.message_handler(content_types=['photo'])
def h_photo(msg):
    u_id = msg.from_user.id
    update_activity(u_id, msg.from_user.username)
    if check_ban(u_id)[0]: return
    if u_id in active_chats:
        pending_photos[u_id] = msg.photo[-1].file_id
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("Normal", callback_data="timer_0"))
        m.add(types.InlineKeyboardButton("3s ⏱️", callback_data="timer_3"), types.InlineKeyboardButton("10s ⏱️", callback_data="timer_10"))
        bot.send_message(u_id, "📸 Select Photo Mode:", reply_markup=m)
    else: bot.send_message(u_id, "❌ Not connected.")

@bot.callback_query_handler(func=lambda c: c.data.startswith('timer_'))
def p_photo_t(c):
    u_id = c.from_user.id
    bot.delete_message(c.message.chat.id, c.message.message_id)
    if u_id not in active_chats or u_id not in pending_photos: return
    t = int(c.data.split('_')[1])
    p_id = active_chats[u_id]
    ph_id = pending_photos.pop(u_id)
    if t == 0:
        bot.send_photo(p_id, ph_id)
        bot.send_message(u_id, "✅ Sent normally.")
    else:
        m_p = bot.send_photo(p_id, ph_id, caption=f"⏱️ Secret Photo ({t}s)", protect_content=True)
        m_u = bot.send_message(u_id, f"✅ Secret sent ({t}s).")
        threading.Thread(target=auto_delete_msg, args=(p_id, m_p.message_id, u_id, m_u.message_id, t)).start()

@bot.message_handler(func=lambda msg: True)
def handle_all(msg):
    u_id = msg.from_user.id
    text = msg.text
    update_activity(u_id, msg.from_user.username)
    
    if check_ban(u_id)[0]: return
    
    if text in ["⏭️ /next", "/next", "🔍 /search"]: return search_stranger(msg)
    elif text in ["🛑 /stop", "/stop"]: return stop_chat(msg)
    elif text in ["💌 /share", "/share"]: return share_uname(msg)
    elif text in ["👤 /profile", "/profile"]: return show_profile(msg)
    elif text in ["✏️ /editprofile", "/editprofile"]: return edit_profile(msg)
    elif text in ["💎 /vip", "/vip"]: return vip_plan(msg)
    elif text in ["🔗 /invite", "/invite"]: return invite_link(msg)

    u = get_user(u_id)
    st = user_states.get(u_id)
    
    if st == 'EDIT_NAME':
        with db_lock:
            cursor.execute("UPDATE users SET name=? WHERE user_id=?", (text, u_id))
            conn.commit()
        user_states[u_id] = 'EDIT_AGE'
        bot.send_message(u_id, "Enter new Age:")
        return
    elif st == 'EDIT_AGE':
        if not text.isdigit(): return bot.send_message(u_id, "Numbers only:")
        with db_lock:
            cursor.execute("UPDATE users SET age=? WHERE user_id=?", (int(text), u_id))
            conn.commit()
        user_states[u_id] = 'EDIT_GENDER'
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add("👦 Male", "👧 Female")
        bot.send_message(u_id, "Select Gender:", reply_markup=m)
        return
    elif st == 'EDIT_GENDER':
        g = "M" if "Male" in text else "F"
        with db_lock:
            cursor.execute("UPDATE users SET gender=? WHERE user_id=?", (g, u_id))
            conn.commit()
        user_states[u_id] = 'EDIT_STATE'
        bot.send_message(u_id, "Enter City:", reply_markup=types.ReplyKeyboardRemove())
        return
    elif st == 'EDIT_STATE':
        with db_lock:
            cursor.execute("UPDATE users SET state=? WHERE user_id=?", (text, u_id))
            conn.commit()
        if u_id in user_states: del user_states[u_id]
                bot.send_message(u_id, "✅ Updated!\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
        return

    if u and not st:
        if not u[2]: st = 'W_NAME'
        elif not u[3]: st = 'W_AGE'
        elif not u[4]: st = 'W_GENDER'
        elif not u[5]: st = 'W_STATE'

    if st == 'W_NAME':
        with db_lock:
            cursor.execute("UPDATE users SET name=? WHERE user_id=?", (text, u_id))
            conn.commit()
        user_states[u_id] = 'W_AGE'
        bot.send_message(u_id, "Enter Age:")
        return
    elif st == 'W_AGE':
        if not text.isdigit(): return bot.send_message(u_id, "Numbers only:")
        with db_lock:
            cursor.execute("UPDATE users SET age=? WHERE user_id=?", (int(text), u_id))
            conn.commit()
        user_states[u_id] = 'W_GENDER'
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add("👦 Male", "👧 Female")
        bot.send_message(u_id, "Gender?", reply_markup=m)
        return
    elif st == 'W_GENDER':
        g = "M" if "Male" in text else "F"
        with db_lock:
            cursor.execute("UPDATE users SET gender=? WHERE user_id=?", (g, u_id))
            conn.commit()
        user_states[u_id] = 'W_STATE'
        bot.send_message(u_id, "City?:", reply_markup=types.ReplyKeyboardRemove())
        return
    elif st == 'W_STATE':
        with db_lock:
            cursor.execute("UPDATE users SET state=? WHERE user_id=?", (text, u_id))
            conn.commit()
            
        fresh_u = get_user(u_id)
        if fresh_u:
            try:
                uname = f"@{msg.from_user.username}" if msg.from_user.username else "Not Set"
                admin_msg = f"🆕 New User Registered!\n\n👤 Name: {fresh_u[2]}\n🎂 Age: {fresh_u[3]}\n🚻 Gender: {fresh_u[4]}\n📍 City: {fresh_u[5]}\n🔑 User ID: {u_id}\n🌐 Username: {uname}"
                bot.send_message(ADMIN_GROUP, admin_msg)
            except Exception as e:
                print(f"Group Notification Error: {e}")

        ref_id = u[9]
        if ref_id and ref_id != u_id:
            ref_u = get_user(ref_id)
            if ref_u:
                exp = ref_u[7] if ref_u[7] and ref_u[7] > time.time() else time.time()
                with db_lock:
                    cursor.execute("UPDATE users SET is_vip=1, vip_expiry=? WHERE user_id=?", (exp + 7200, ref_id))
                    conn.commit()
                try: bot.send_message(ref_id, "🎉 Referral Success! +2 Hours VIP added.\n\n👑 Owner: @egofiremax")
                except: pass
        if u_id in user_states: del user_states[u_id]
        bot.send_message(u_id, "✅ Profile Created!\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
        return

    if url_pattern.search(text):
        bot.delete_message(u_id, msg.message_id)
        return bot.send_message(u_id, "❌ Links not allowed!")

    if u_id in ai_chats:
        ai_data = ai_chats[u_id]
        if ai_data.get("step", 0) == 0:
            ai_data["step"] = 1
            def auto_skip_ai():
                time.sleep(random.randint(5, 12))
                if u_id in ai_chats:
                    del ai_chats[u_id]
                    try: bot.send_message(u_id, "🚫 Partner has left.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())
                    except: pass
            threading.Thread(target=auto_skip_ai).start()
            r_list = ["Acha ji? Sahi hai 😉", "Baad me milti hu bye! ✨", "Mummy bula rhi hai bye 🙈"]
            time.sleep(1.5)
            try: bot.send_message(u_id, random.choice(r_list))
            except: pass
        return

    if u_id in active_chats:
        try: bot.send_message(active_chats[u_id], text)
        except: disconnect_chat(u_id)
    else:
        bot.send_message(u_id, "Not in a chat. Press /search.\n\n👑 Owner: @egofiremax", reply_markup=get_main_menu())

# === BACKGROUND TASKS (INACTIVE & VIP EXPIRY) ===
def background_checker():
    while True:
        time.sleep(3600) 
        now = time.time()
        with db_lock:
            cursor.execute("SELECT user_id, last_active, is_vip, vip_expiry, vip_warned FROM users")
            all_users = cursor.fetchall()
        
        for u in all_users:
            uid, last_active, is_vip_stat, vip_expiry, vip_warned = u
            
            if last_active and (now - last_active) > 86400:
                try:
                    bot.send_message(uid, "🔔 Aap kafi der se inactive hain! Naye strangers se judne ke liye abhi /search dabayein 🚀")
                    with db_lock:
                        cursor.execute("UPDATE users SET last_active=? WHERE user_id=?", (now, uid))
                        conn.commit()
                except: pass
            
            if is_vip_stat == 1 and vip_expiry:
                time_left = vip_expiry - now
                if time_left <= 0:
                    with db_lock:
                        cursor.execute("UPDATE users SET is_vip=0, vip_expiry=0, vip_warned=0 WHERE user_id=?", (uid,))
                        conn.commit()
                    try: bot.send_message(uid, "❌ Aapka VIP plan ab expire ho chuka hai. Free features par wapas switch kar diya gaya hai.")
                    except: pass
                elif time_left <= 86400 and vip_warned == 0:
                    with db_lock:
                        cursor.execute("UPDATE users SET vip_warned=1 WHERE user_id=?", (uid,))
                        conn.commit()
                    try: bot.send_message(uid, "⚠️ Aapka VIP plan kal khatam hone wala hai. Continuous benefits ke liye renew karein!")
                    except: pass

# === FLASK & BOT START ===
app = Flask('')

@app.route('/')
def home():
    return "Bot is active 24/7!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

def keep_alive():
    t = threading.Thread(target=run)
    t.start()
    t2 = threading.Thread(target=background_checker, daemon=True)
    t2.start()

if __name__ == "__main__":
    keep_alive()
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        try:
            bot.send_message(ADMIN_GROUP, f"⚠️ **BOT ERROR ALERT!**\nBot has stopped working. Please check logs.\nError: `{str(e)}`")
        except:
            pass
            
        
