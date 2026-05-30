import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
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
            league TEXT,
            home_team TEXT,
            away_team TEXT,
            odds_home FLOAT,
            odds_draw FLOAT,
            odds_away FLOAT,
            start_time TIMESTAMP,
            status TEXT DEFAULT 'active',  -- active, finished, cancelled
            result TEXT,  -- home, draw, away
            created_by BIGINT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            event_id INTEGER,
            bet_type TEXT,  -- home, draw, away
            amount INTEGER,
            odds FLOAT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("✅ دیتابیس کامل راه‌اندازی شد")

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
    kb.add(KeyboardButton("👤 مدیریت کاربران"), KeyboardButton("🔙 منوی اصلی"))
    return kb

# ==================== توابع دیتابیس ====================
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
    cur.execute("INSERT INTO users (user_id, balance) VALUES (%s, %s) ON CONFLICT(user_id) DO UPDATE SET balance = users.balance + %s", 
                (user_id, amount, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_active_events():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""SELECT id, title, home_team, away_team, odds_home, odds_draw, odds_away, start_time 
                   FROM events WHERE status = 'active' ORDER BY start_time""")
    events = cur.fetchall()
    cur.close()
    conn.close()
    return events

# ==================== هندلرها ====================
@bot.message_handler(commands=['start'])
def start(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "👑 **ادمین عزیز خوش آمدید**", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, 
            "🎰 **به بات شرط‌بندی حرفه‌ای خوش آمدید**\n\n"
            "⚽ شرط‌بندی زنده و پیش‌بینی\n"
            "💰 موجودی اولیه: ۱۰۰٬۰۰۰ تومان",
            reply_markup=main_menu())

# ==================== منوی کاربر ====================
@bot.message_handler(func=lambda m: m.text == "⚽ شرط‌بندی")
def betting_start(message):
    events = get_active_events()
    if not events:
        bot.reply_to(message, "❌ در حال حاضر رویدادی برای شرط‌بندی وجود ندارد.")
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for e in events:
        text = f"{e[1]} | {e[2]} vs {e[3]}"
        kb.add(InlineKeyboardButton(text, callback_data=f"event_{e[0]}"))
    
    bot.send_message(message.chat.id, "🏟 **رویدادهای فعال:**\nانتخاب کنید:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("event_"))
def show_event_details(call):
    event_id = int(call.data.split("_")[1])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()

    if not event:
        bot.answer_callback_query(call.id, "رویداد یافت نشد")
        return

    text = f"""
🎮 **{event[1]}**
🏟 {event[2]} vs {event[3]}

📊 **ضرایب:**
🔴 برد {event[2]}: **{event[4]}**
⚪ تساوی: **{event[5]}**
🔵 برد {event[3]}: **{event[6]}**

⏰ شروع: {event[7].strftime('%Y-%m-%d %H:%M') if event[7] else 'نامشخص'}
    """

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton(f"🔴 {event[4]}", callback_data=f"bet_{event_id}_home"),
        InlineKeyboardButton(f"⚪ {event[5]}", callback_data=f"bet_{event_id}_draw"),
        InlineKeyboardButton(f"🔵 {event[6]}", callback_data=f"bet_{event_id}_away")
    )
    kb.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_events"))

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith("bet_"))
def start_betting(call):
    _, event_id, bet_type = call.data.split("_")
    event_id = int(event_id)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT title, home_team, away_team, odds_home, odds_draw, odds_away FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()

    odds = event[3] if bet_type == "home" else event[4] if bet_type == "draw" else event[5]
    team = event[1] if bet_type == "home" else "تساوی" if bet_type == "draw" else event[2]

    text = f"""
✅ **ثبت شرط جدید**

🎮 {event[0]}
⚔️ شرط: **{team}**
📈 ضریب: **{odds}**

💰 مبلغ مورد نظر خود را وارد کنید:
    """
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_bet_amount, event_id, bet_type, odds)

def process_bet_amount(message, event_id, bet_type, odds):
    try:
        amount = int(message.text)
        if amount < 10000:
            bot.reply_to(message, "❌ حداقل مبلغ شرط ۱۰٬۰۰۰ تومان است.")
            return

        balance = get_balance(message.from_user.id)
        if balance < amount:
            bot.reply_to(message, "❌ موجودی کافی نیست.")
            return

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

        bot.reply_to(message, f"✅ شرط به مبلغ **{amount:,}** تومان با ضریب **{odds}** با موفقیت ثبت شد!", parse_mode='Markdown')

    except:
        bot.reply_to(message, "❌ لطفاً فقط عدد وارد کنید.")

@bot.message_handler(func=lambda m: m.text == "💰 موجودی من")
def show_balance(message):
    bal = get_balance(message.from_user.id)
    bot.reply_to(message, f"💰 **موجودی فعلی شما:**\n`{bal:,}` تومان", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📜 شرط‌های من")
def my_bets(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""SELECT e.title, b.bet_type, b.amount, b.odds, b.status 
                   FROM bets b JOIN events e ON b.event_id = e.id 
                   WHERE b.user_id = %s ORDER BY b.created_at DESC LIMIT 10""", (message.from_user.id,))
    bets = cur.fetchall()
    cur.close()
    conn.close()

    if not bets:
        bot.reply_to(message, "شما هنوز شرطی ثبت نکرده‌اید.")
        return

    text = "📜 **شرط‌های اخیر شما:**\n\n"
    for b in bets:
        status = "🟢 برنده" if b[4] == "won" else "🔴 باخته" if b[4] == "lost" else "⏳ فعال"
        text += f"• {b[0]}\n  شرط: {b[1]} | مبلغ: {b[2]:,} | ضریب: {b[3]} | وضعیت: {status}\n\n"

    bot.reply_to(message, text)

# ==================== بخش ادمین ====================
@bot.message_handler(func=lambda m: m.text == "➕ اضافه کردن رویداد" and m.from_user.id == ADMIN_ID)
def add_event_start(message):
    bot.send_message(message.chat.id, "📝 **عنوان رویداد:**\nمثال: استقلال vs پرسپولیس")
    bot.register_next_step_handler(message, process_event_title)

def process_event_title(message):
    title = message.text
    msg = bot.send_message(message.chat.id, "🏟 تیم میزبان:")
    bot.register_next_step_handler(msg, process_home_team, title)

def process_home_team(message, title):
    home = message.text
    msg = bot.send_message(message.chat.id, "🏟 تیم مهمان:")
    bot.register_next_step_handler(msg, process_away_team, title, home)

def process_away_team(message, title, home):
    away = message.text
    msg = bot.send_message(message.chat.id, "📈 ضریب برد میزبان:")
    bot.register_next_step_handler(msg, process_odds_home, title, home, away)

def process_odds_home(message, title, home, away):
    try:
        oh = float(message.text)
        msg = bot.send_message(message.chat.id, "📈 ضریب تساوی:")
        bot.register_next_step_handler(msg, process_odds_draw, title, home, away, oh)
    except:
        bot.reply_to(message, "عدد وارد کنید!")

def process_odds_draw(message, title, home, away, oh):
    try:
        od = float(message.text)
        msg = bot.send_message(message.chat.id, "📈 ضریب برد مهمان:")
        bot.register_next_step_handler(msg, process_odds_away, title, home, away, oh, od)
    except:
        bot.reply_to(message, "عدد وارد کنید!")

def process_odds_away(message, title, home, away, oh, od):
    try:
        oa = float(message.text)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO events (title, home_team, away_team, odds_home, odds_draw, odds_away, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (title, home, away, oh, od, oa, message.from_user.id))
        conn.commit()
        cur.close()
        conn.close()
        bot.reply_to(message, "✅ رویداد با موفقیت اضافه شد!")
    except:
        bot.reply_to(message, "خطا در ثبت!")

@bot.message_handler(func=lambda m: m.text == "📋 لیست رویدادها" and m.from_user.id == ADMIN_ID)
def list_events_admin(message):
    events = get_active_events()
    text = "📋 **رویدادهای فعال:**\n\n"
    for e in events:
        text += f"ID: {e[0]} | {e[1]} | {e[2]} vs {e[3]}\n"
    bot.reply_to(message, text or "رویدادی وجود ندارد")

@bot.message_handler(commands=['add_balance'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amt = message.text.split()
        add_balance(int(uid), int(amt))
        bot.reply_to(message, f"✅ {amt:,} تومان به کاربر {uid} اضافه شد.")
    except:
        bot.reply_to(message, "استفاده: /add_balance <user_id> <amount>")

@bot.message_handler(func=lambda m: m.text == "📢 پخش پیام همگانی" and m.from_user.id == ADMIN_ID)
def broadcast(message):
    msg = bot.reply_to(message, "📢 پیام خود را برای پخش به همه کاربران بنویسید:")
    bot.register_next_step_handler(msg, do_broadcast)

def do_broadcast(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    sent = 0
    for user in users:
        try:
            bot.send_message(user[0], message.text)
            sent += 1
        except:
            pass
    bot.reply_to(message, f"✅ پیام به {sent} کاربر ارسال شد.")

# ==================== راه‌اندازی ====================
bot.set_my_commands([
    BotCommand("start", "شروع / منو"),
    BotCommand("add_balance", "افزایش موجودی کاربر (ادمین)"),
])

print("🚀 بات شرط‌بندی کامل راه‌اندازی شد...")
bot.infinity_polling()
