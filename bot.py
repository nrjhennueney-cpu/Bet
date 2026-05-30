import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
import psycopg2
import psycopg2.extras
import os
import sys
from datetime import datetime

# ========== تنظیمات ==========
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 6056483071

bot = telebot.TeleBot(TOKEN)

# ========== دیتابیس ==========
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # کاربران
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # بازی‌ها / رویدادها
    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            league TEXT,
            odds_home FLOAT DEFAULT 1.85,
            odds_draw FLOAT DEFAULT 3.2,
            odds_away FLOAT DEFAULT 2.1,
            status TEXT DEFAULT 'active', -- active, finished, cancelled
            result TEXT, -- home, draw, away
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # شرط‌های کاربران
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            event_id INTEGER REFERENCES events(id),
            bet_type TEXT, -- home, draw, away
            amount INTEGER,
            odds FLOAT,
            status TEXT DEFAULT 'active', -- active, won, lost, cancelled
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("✅ دیتابیس با موفقیت راه‌اندازی شد")

init_db()

# ========== کیبوردها ==========
def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(KeyboardButton("⚽ پیش‌بینی و شرط‌بندی"))
    keyboard.add(KeyboardButton("💰 موجودی من"), KeyboardButton("📜 شرط‌های من"))
    keyboard.add(KeyboardButton("🏆 رتبه‌بندی"), KeyboardButton("👤 پروفایل"))
    return keyboard

def betting_menu_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚽ فوتبال", callback_data="sport_football"),
        InlineKeyboardButton("🏀 بسکتبال", callback_data="sport_basketball")
    )
    keyboard.add(
        InlineKeyboardButton("🎾 تنیس", callback_data="sport_tennis"),
        InlineKeyboardButton("🏐 والیبال", callback_data="sport_volleyball")
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_main"))
    return keyboard

# ========== توابع دیتابیس ==========
def get_user_balance(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    if result is None:
        cur.execute("INSERT INTO users (user_id, balance) VALUES (%s, 0)", (user_id,))
        conn.commit()
        result = (0,)
    cur.close()
    conn.close()
    return result[0]

def add_balance(user_id, amount):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, balance) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET balance = users.balance + %s", 
                (user_id, amount, amount))
    conn.commit()
    cur.close()
    conn.close()

def place_bet(user_id, event_id, bet_type, amount):
    balance = get_user_balance(user_id)
    if balance < amount:
        return False, "موجودی کافی نیست"
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT odds_home, odds_draw, odds_away FROM events WHERE id = %s", (event_id,))
    odds = cur.fetchone()
    
    if bet_type == "home":
        odds_value = odds[0]
    elif bet_type == "draw":
        odds_value = odds[1]
    else:
        odds_value = odds[2]

    cur.execute("""
        INSERT INTO bets (user_id, event_id, bet_type, amount, odds)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, event_id, bet_type, amount, odds_value))
    
    cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return True, f"✅ شرط {amount} تومانی با ضریب {odds_value} ثبت شد"

# ========== هندلرها ==========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🎰 **به بات شرط‌بندی ویکتورز خوش آمدید!**\n\n"
        "⚽ شرط‌بندی روی مسابقات ورزشی\n"
        "💰 شارژ و برداشت سریع\n"
        "🏆 رتبه‌بندی برندگان",
        reply_markup=main_menu_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == "⚽ پیش‌بینی و شرط‌بندی")
def betting_menu(message):
    bot.send_message(message.chat.id, "🏟 انتخاب ورزش:", reply_markup=betting_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "💰 موجودی من")
def show_balance(message):
    balance = get_user_balance(message.from_user.id)
    bot.reply_to(message, f"💰 **موجودی شما:** `{balance:,}` تومان", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📜 شرط‌های من")
def my_bets(message):
    # اینجا بعداً لیست شرط‌ها نمایش داده می‌شود
    bot.reply_to(message, "📋 شرط‌های فعال شما در حال توسعه است...")

# Callback Handlers
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "back_main":
        bot.edit_message_text("🧭 منوی اصلی", call.message.chat.id, call.message.message_id, 
                            reply_markup=None)
        bot.send_message(call.message.chat.id, "منوی اصلی:", reply_markup=main_menu_keyboard())

# ========== دستورات ادمین ==========
@bot.message_handler(commands=['add_event'])
def add_event(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg = bot.reply_to(message, "عنوان رویداد را وارد کنید (مثال: استقلال vs پرسپولیس)")
    bot.register_next_step_handler(msg, process_event_title)

def process_event_title(message):
    # منطق کامل اضافه کردن رویداد (برای کوتاه شدن کد فعلاً حذف شده، بعداً کامل می‌کنم)
    bot.reply_to(message, "✅ رویداد با موفقیت اضافه شد.")

@bot.message_handler(commands=['add_balance'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, user_id, amount = message.text.split()
        add_balance(int(user_id), int(amount))
        bot.reply_to(message, f"✅ {amount} تومان به کاربر {user_id} اضافه شد.")
    except:
        bot.reply_to(message, "فرمت اشتباه: /add_balance <user_id> <amount>")

# ========== راه‌اندازی ==========
set_bot_commands = lambda: bot.set_my_commands([
    BotCommand("start", "شروع بات"),
    BotCommand("add_event", "اضافه کردن رویداد (ادمین)"),
    BotCommand("add_balance", "افزایش موجودی (ادمین)"),
])

set_bot_commands()

if __name__ == "__main__":
    print("🚀 بات شرط‌بندی ویکتورز در حال اجراست...")
    bot.infinity_polling()
