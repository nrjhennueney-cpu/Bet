import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
import psycopg2
import psycopg2.extras
import os
import sys
from datetime import datetime

# ========== گرفتن متغیرها ==========
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ خطا: BOT_TOKEN تنظیم نشده است")
    sys.exit(1)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ خطا: DATABASE_URL تنظیم نشده است (از Neon)")
    sys.exit(1)

RAILWAY_STATIC_URL = os.getenv("RAILWAY_STATIC_URL")
WEBHOOK_URL = f"https://{RAILWAY_STATIC_URL}" if RAILWAY_STATIC_URL else os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "False").lower() == "true"

# شناسه ادمین (ثابت)
ADMIN_ID = 6056483071

bot = telebot.TeleBot(TOKEN)

# ========== دیتابیس ==========
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # جدول کاربران
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_start INTEGER DEFAULT 1,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # جدول بازی‌ها
    cur.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            prediction TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by BIGINT
        )
    ''')
    # جدول تنظیمات بات
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # درج تنظیمات پیش‌فرض
    cur.execute("INSERT INTO bot_settings (key, value) VALUES ('bot_enabled', 'true') ON CONFLICT (key) DO NOTHING")
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ دیتابیس آماده است")

init_db()

def is_first_start(user_id, username, first_name, last_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT first_start FROM users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    
    if result is None:
        cur.execute("""
            INSERT INTO users (user_id, first_start, username, first_name, last_name) 
            VALUES (%s, 0, %s, %s, %s)
        """, (user_id, username, first_name, last_name))
        conn.commit()
        cur.close()
        conn.close()
        return True
    else:
        first = result[0]
        if first == 1:
            cur.execute("UPDATE users SET first_start = 0 WHERE user_id = %s", (user_id,))
            conn.commit()
        cur.close()
        conn.close()
        return first == 1

def is_bot_enabled():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM bot_settings WHERE key = 'bot_enabled'")
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] == 'true'

def set_bot_enabled(enabled):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bot_settings SET value = %s WHERE key = 'bot_enabled'", ('true' if enabled else 'false',))
    conn.commit()
    cur.close()
    conn.close()

def add_game(title, prediction, created_by):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO games (title, prediction, created_by) 
        VALUES (%s, %s, %s) RETURNING id
    """, (title, prediction, created_by))
    game_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return game_id

def get_active_games():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, prediction FROM games WHERE status = 'active' ORDER BY created_at DESC")
    games = cur.fetchall()
    cur.close()
    conn.close()
    return games

def get_all_users():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, last_name, joined_at FROM users ORDER BY joined_at DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users

def get_user_count():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

# ========== کیبوردها ==========
def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = KeyboardButton("⚽ پیش بینی های روز")
    btn2 = KeyboardButton("💰 موجودی")
    keyboard.add(btn1, btn2)
    return keyboard

def games_inline_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    games = get_active_games()
    for game in games:
        btn = InlineKeyboardButton(f"🎮 {game[1]}", callback_data=f"game_{game[0]}")
        keyboard.add(btn)
    return keyboard

# ========== منوی همبرگری (دستورات بات) ==========
def set_bot_commands():
    commands = [
        BotCommand("start", "🔄 شروع مجدد بات"),
        BotCommand("stats", "📊 آمار کاربران (فقط ادمین)"),
        BotCommand("users", "👥 لیست کاربران (فقط ادمین)"),
        BotCommand("disable_bot", "🔴 خاموش کردن بات (فقط ادمین)"),
        BotCommand("enable_bot", "🟢 روشن کردن بات (فقط ادمین)"),
        BotCommand("add_game", "➕ اضافه کردن بازی جدید (فقط ادمین)"),
    ]
    bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# ========== هندلرها ==========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    if not is_bot_enabled() and user_id != ADMIN_ID:
        bot.reply_to(message, "🔴 بات در حال حاضر غیرفعال است. لطفاً بعداً مراجعه کنید.")
        return
    
    if is_first_start(user_id, username, first_name, last_name):
        welcome_text = (
            "🤖 به بات ویکتورز کلاب خوش اومدی!\n\n"
            "ما اینجا پیش‌بینی بازی‌های مهم ورزشی از جمله فوتبال رو انجام میدیم.\n"
            "⚡️ با ما همراه باش تا بهترین تحلیل‌ها رو دریافت کنی."
        )
        bot.send_message(message.chat.id, welcome_text)
    
    bot.send_message(
        message.chat.id,
        "🧭 منوی اصلی:",
        reply_markup=main_menu_keyboard()
    )

@bot.message_handler(commands=['stats'])
def stats_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ شما دسترسی به این بخش ندارید.")
        return
    
    user_count = get_user_count()
    games = get_active_games()
    status_text = "🟢 فعال" if is_bot_enabled() else "🔴 غیرفعال"
    
    stats_text = f"""
📊 **آمار بات ویکتورز کلاب**

👥 تعداد کاربران: {user_count}
🎮 بازی‌های فعال: {len(games)}
⚙️ وضعیت بات: {status_text}

📅 آخرین به‌روزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    bot.reply_to(message, stats_text, parse_mode='Markdown')

@bot.message_handler(commands=['users'])
def users_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ شما دسترسی به این بخش ندارید.")
        return
    
    users = get_all_users()
    if not users:
        bot.reply_to(message, "📭 هنوز کاربری ثبت نشده است.")
        return
    
    text = "👥 **لیست کاربران:**\n\n"
    for user in users[:20]:  # حداکثر 20 تا
        user_id, username, first_name, last_name, joined_at = user
        name = first_name or "بدون نام"
        username_str = f"@{username}" if username else "بدون یوزرنیم"
        text += f"• {name} ({username_str}) - ID: {user_id}\n"
        text += f"  📅 عضویت: {joined_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    
    if len(users) > 20:
        text += f"\n... و {len(users) - 20} کاربر دیگر"
    
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['disable_bot'])
def disable_bot_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ شما دسترسی به این بخش ندارید.")
        return
    
    set_bot_enabled(False)
    bot.reply_to(message, "🔴 **بات با موفقیت غیرفعال شد**\n\nکاربران جدید نمی‌توانند از بات استفاده کنند.", parse_mode='Markdown')

@bot.message_handler(commands=['enable_bot'])
def enable_bot_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ شما دسترسی به این بخش ندارید.")
        return
    
    set_bot_enabled(True)
    bot.reply_to(message, "🟢 **بات با موفقیت فعال شد**\n\nکاربران می‌توانند از بات استفاده کنند.", parse_mode='Markdown')

@bot.message_handler(commands=['add_game'])
def add_game_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ شما دسترسی به این بخش ندارید.")
        return
    
    msg = bot.reply_to(message, "🎮 **عنوان بازی رو وارد کن:**\nمثال: ایران vs آمریکا", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_game_title)

def process_game_title(message):
    title = message.text
    msg = bot.reply_to(message, f"📝 **پیش‌بینی برای «{title}» رو وارد کن:**\nمثال: برد ایران 2-1", parse_mode='Markdown')
    bot.register_next_step_handler(msg, lambda m: process_game_prediction(m, title))

def process_game_prediction(message, title):
    prediction = message.text
    game_id = add_game(title, prediction, message.from_user.id)
    
    bot.reply_to(
        message, 
        f"✅ **بازی با موفقیت اضافه شد!**\n\n🎮 {title}\n📝 {prediction}\n\nاین بازی در بخش «پیش‌بینی‌های روز» نمایش داده می‌شود.",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "⚽ پیش بینی های روز")
def daily_predictions(message):
    if not is_bot_enabled() and message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🔴 بات در حال حاضر غیرفعال است.")
        return
    
    games = get_active_games()
    if not games:
        bot.reply_to(message, "📭 امروز هیچ بازی فعالی وجود ندارد.")
        return
    
    bot.reply_to(
        message, 
        "🎮 **بازی‌های امروز:**\nبرای مشاهده جزئیات هر بازی روی دکمه زیر کلیک کن:",
        reply_markup=games_inline_keyboard(),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('game_'))
def handle_game_callback(call):
    game_id = int(call.data.split('_')[1])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT title, prediction FROM games WHERE id = %s", (game_id,))
    game = cur.fetchone()
    cur.close()
    conn.close()
    
    if game:
        text = f"""
🎮 **{game[0]}**

📝 **پیش‌بینی ویکتورز کلاب:** 
{game[1]}

⭐️ نتیجه رو بعد از بازی با شما به اشتراک می‌ذاریم.
        """
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        bot.answer_callback_query(call.id, "✅ جزئیات بازی نمایش داده شد")
    else:
        bot.answer_callback_query(call.id, "❌ بازی یافت نشد")

@bot.message_handler(func=lambda message: message.text == "💰 موجودی")
def show_balance(message):
    bot.reply_to(message, "💰 **موجودی شما:** 0 تومان\n\n💳 سیستم شارژ در حال توسعه است.", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def unknown(message):
    bot.reply_to(message, "❓ لطفاً از دکمه‌های منوی اصلی یا دستورات استفاده کنید.\n\n/start - منوی اصلی")

# ========== راه‌اندازی ==========
def setup_webhook():
    if not WEBHOOK_URL:
        print("❌ خطا: WEBHOOK_URL مشخص نیست")
        return False
    webhook_full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_full_url)
    print(f"✅ Webhook تنظیم شد: {webhook_full_url}")
    return True

# ست کردن منوی همبرگری
set_bot_commands()

if USE_WEBHOOK:
    from flask import Flask, request, abort
    app = Flask(__name__)

    @app.route(WEBHOOK_PATH, methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        abort(403)

    @app.route('/')
    def index():
        return "بات ویکتورز کلاب فعال ✅"

    if __name__ == "__main__":
        setup_webhook()
        print(f"🚀 بات روی پورت {PORT} در حال اجراست...")
        app.run(host='0.0.0.0', port=PORT)
else:
    if __name__ == "__main__":
        bot.remove_webhook()
        print("🤖 حالت Polling (برای تست لوکال)")
        bot.infinity_polling(skip_pending=True)
