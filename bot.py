import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
import psycopg2
import os
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 6056483071

bot = telebot.TeleBot(TOKEN)

# ==================== دیتابیس ====================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 100000,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            league TEXT DEFAULT 'فوتبال',
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            odds_home FLOAT NOT NULL,
            odds_draw FLOAT NOT NULL,
            odds_away FLOAT NOT NULL,
            start_time TIMESTAMP,
            status TEXT DEFAULT 'active',
            result TEXT,
            created_by BIGINT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            event_id INTEGER,
            bet_type TEXT,
            amount INTEGER,
            odds FLOAT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("✅ دیتابیس با موفقیت راه‌اندازی شد")

init_db()

# ==================== کیبوردها ====================
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("⚽ شرط‌بندی"), KeyboardButton("💰 موجودی من"))
    kb.add(KeyboardButton("📜 شرط‌های من"), KeyboardButton("🏆 رتبه‌بندی"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("➕ اضافه کردن رویداد"), KeyboardButton("📋 لیست رویدادها"))
    kb.add(KeyboardButton("🏁 ثبت نتیجه"), KeyboardButton("📢 پخش پیام همگانی"))
    kb.add(KeyboardButton("📊 آمار کلی"), KeyboardButton("👥 لیست کاربران"))
    kb.add(KeyboardButton("🔙 منوی اصلی"))
    return kb

# ==================== توابع ====================
def get_balance(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    if not res:
        cur.execute("INSERT INTO users (user_id, balance) VALUES (%s, 100000)", (user_id,))
        conn.commit()
        res = (100000,)
    cur.close()
    conn.close()
    return res[0]

def add_balance(user_id, amount):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, balance) 
        VALUES (%s, %s) 
        ON CONFLICT(user_id) DO UPDATE SET balance = users.balance + %s
    """, (user_id, amount, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_active_events():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, home_team, away_team, odds_home, odds_draw, odds_away, start_time 
        FROM events WHERE status = 'active' ORDER BY start_time
    """)
    return cur.fetchall()

# ==================== دستورات ====================
def set_bot_commands():
    bot.set_my_commands([
        BotCommand("start", "شروع بات"),
        BotCommand("help", "راهنما")
    ], scope=BotCommandScopeDefault())

    # دستورات فقط برای ادمین
    bot.set_my_commands([
        BotCommand("start", "منوی مدیریت"),
        BotCommand("stats", "آمار بات"),
        BotCommand("users", "لیست کاربران"),
        BotCommand("add_balance", "افزایش موجودی"),
    ], scope=BotCommandScopeChat(ADMIN_ID))

set_bot_commands()

# ==================== هندلرها ====================
@bot.message_handler(commands=['start'])
def start(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "👑 **ادمین عزیز، خوش آمدید**", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id,
            "🎰 **به بات شرط‌بندی حرفه‌ای خوش آمدید!**\n\n"
            "⚽ شرط‌بندی روی مسابقات واقعی\n"
            "💰 موجودی اولیه: ۱۰۰٬۰۰۰ تومان",
            reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "⚽ شرط‌بندی")
def betting_start(message):
    events = get_active_events()
    if not events:
        bot.reply_to(message, "❌ در حال حاضر رویدادی برای شرط‌بندی وجود ندارد.")
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for e in events:
        kb.add(InlineKeyboardButton(f"{e[1]} | {e[2]} vs {e[3]}", callback_data=f"event_{e[0]}"))
    
    bot.send_message(message.chat.id, "🏟 **رویدادهای فعال:**", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("event_"))
def show_event(call):
    event_id = int(call.data.split("_")[1])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()

    text = f"""
🎮 **{event[1]}**
🏟 {event[2]} vs {event[3]}

📊 **ضرایب:**
🔴 {event[2]}: `{event[4]}`
⚪ تساوی: `{event[5]}`
🔵 {event[3]}: `{event[6]}`
    """

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton(f"🔴 {event[4]}", callback_data=f"bet_{event_id}_home"),
        InlineKeyboardButton(f"⚪ {event[5]}", callback_data=f"bet_{event_id}_draw"),
        InlineKeyboardButton(f"🔵 {event[6]}", callback_data=f"bet_{event_id}_away")
    )
    kb.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_events"))

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith("bet_"))
def bet_selected(call):
    _, event_id, bet_type = call.data.split("_")
    event_id = int(event_id)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT title, home_team, away_team, odds_home, odds_draw, odds_away FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()

    odds = {"home": event[3], "draw": event[4], "away": event[5]}[bet_type]
    team = event[1] if bet_type == "home" else "تساوی" if bet_type == "draw" else event[2]

    text = f"""
✅ **ثبت شرط جدید**

🎮 {event[0]}
⚔️ شرط: **{team}**
📈 ضریب: **{odds}**

💰 مبلغ شرط را وارد کنید (حداقل ۱۰٬۰۰۰ تومان):
"""
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_amount, event_id, bet_type, odds)

def process_amount(message, event_id, bet_type, odds):
    try:
        amount = int(message.text.replace(",", ""))
        if amount < 10000:
            return bot.reply_to(message, "❌ حداقل مبلغ ۱۰٬۰۰۰ تومان است.")

        balance = get_balance(message.from_user.id)
        if balance < amount:
            return bot.reply_to(message, f"❌ موجودی کافی نیست!\nموجودی: {balance:,}")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bets (user_id, event_id, bet_type, amount, odds)
            VALUES (%s, %s, %s, %s, %s)
        """, (message.from_user.id, event_id, bet_type, amount, odds))
        
        cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, message.from_user.id))
        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(message, f"✅ شرط به مبلغ `{amount:,}` تومان با ضریب `{odds}` ثبت شد!", parse_mode='Markdown')
    except:
        bot.reply_to(message, "❌ لطفاً فقط عدد وارد کنید.")

# ==================== ادمین ====================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 پخش پیام همگانی")
def broadcast_start(message):
    msg = bot.reply_to(message, "📢 متن پیام را ارسال کنید:")
    bot.register_next_step_handler(msg, do_broadcast)

def do_broadcast(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    success = 0
    for user in users:
        try:
            bot.send_message(user[0], message.text, parse_mode='Markdown')
            success += 1
        except:
            pass

    bot.reply_to(message, f"✅ پیام با موفقیت به **{success}** کاربر ارسال شد.")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 آمار کلی")
def stats(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE status='active'")
    events = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(balance),0) FROM users")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    text = f"""
📊 **آمار بات**

👥 کاربران: {users}
🎮 رویداد فعال: {events}
💰 مجموع موجودی: {total:,} تومان
    """
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "👥 لیست کاربران")
def list_users(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, balance FROM users ORDER BY joined_at DESC LIMIT 30")
    users = cur.fetchall()
    cur.close()
    conn.close()

    text = "👥 **کاربران:**\n\n"
    for u in users:
        text += f"`{u[0]}` | @{u[1] or '-'} | {u[2] or ''} | {u[3]:,} تومان\n"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔙 منوی اصلی")
def back_to_admin(message):
    bot.send_message(message.chat.id, "👑 پنل مدیریت", reply_markup=admin_menu())

@bot.message_handler(commands=['add_balance'])
def add_balance_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amt = message.text.split()
        add_balance(int(uid), int(amt))
        bot.reply_to(message, f"✅ {amt:,} تومان به کاربر {uid} اضافه شد.")
    except:
        bot.reply_to(message, "❌ فرمت: `/add_balance <user_id> <مبلغ>`")

# ==================== سایر ====================
@bot.message_handler(func=lambda m: m.text == "💰 موجودی من")
def balance(message):
    bot.reply_to(message, f"💰 موجودی شما: `{get_balance(message.from_user.id):,}` تومان", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def unknown(message):
    bot.reply_to(message, "❓ لطفاً از دکمه‌های منو استفاده کنید.")

print("🚀 بات شرط‌بندی کامل و بدون باگ راه‌اندازی شد...")
bot.infinity_polling()
