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
    print("✅ دیتابیس آماده شد")

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

def get_active_events():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, home_team, away_team, odds_home, odds_draw, odds_away 
        FROM events WHERE status = 'active' ORDER BY id DESC
    """)
    return cur.fetchall()

# ==================== شروع بات ====================
def startup_cleanup():
    try:
        bot.remove_webhook()           # مهمه! اگر قبلاً webhook تنظیم شده باشه
        print("✅ Webhook حذف شد")
    except:
        pass

startup_cleanup()

# ==================== هندلرها ====================
@bot.message_handler(commands=['start'])
def start(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "👑 **پنل مدیریت فعال شد**", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, "🎰 **به بات شرط‌بندی خوش آمدید!**", reply_markup=main_menu())

# ==================== ادمین ====================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_panel(message):
    text = message.text

    if text == "➕ اضافه کردن رویداد":
        bot.reply_to(message, "📝 عنوان رویداد را وارد کنید:")
        bot.register_next_step_handler(message, process_title)

    elif text == "📋 لیست رویدادها":
        events = get_active_events()
        if not events:
            return bot.reply_to(message, "❌ رویداد فعالی وجود ندارد.")
        txt = "📋 **رویدادهای فعال:**\n\n"
        for e in events:
            txt += f"• {e[1]} | {e[2]} vs {e[3]}\n   ضرایب: {e[4]} | {e[5]} | {e[6]}\n\n"
        bot.reply_to(message, txt)

    elif text == "📊 آمار کلی":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users"); users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM events WHERE status='active'"); events = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(balance),0) FROM users"); total = cur.fetchone()[0]
        cur.close()
        conn.close()
        bot.reply_to(message, f"👥 کاربران: {users}\n🎮 رویداد فعال: {events}\n💰 مجموع موجودی: {total:,}", parse_mode='Markdown')

    elif text == "👥 لیست کاربران":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name, balance FROM users ORDER BY joined_at DESC LIMIT 40")
        users = cur.fetchall()
        cur.close()
        conn.close()
        txt = "👥 **کاربران:**\n\n"
        for u in users:
            txt += f"`{u[0]}` | @{u[1] or '—'} | {u[3]:,} تومان\n"
        bot.reply_to(message, txt, parse_mode='Markdown')

    elif text == "📢 پخش پیام همگانی":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ لغو", callback_data="cancel_broadcast"))
        bot.reply_to(message, "📢 متن پیام را ارسال کنید:", reply_markup=kb)
        bot.register_next_step_handler(message, broadcast_message)

    elif text == "🔙 منوی اصلی":
        bot.send_message(message.chat.id, "👑 پنل مدیریت", reply_markup=admin_menu())

def process_title(message):
    title = message.text
    msg = bot.reply_to(message, "🏠 تیم میزبان:")
    bot.register_next_step_handler(msg, process_home, title)

def process_home(message, title):
    home = message.text
    msg = bot.reply_to(message, "🏟 تیم مهمان:")
    bot.register_next_step_handler(msg, process_away, title, home)

def process_away(message, title, home):
    away = message.text
    msg = bot.reply_to(message, "📈 ضریب برد میزبان:")
    bot.register_next_step_handler(msg, process_odds_home, title, home, away)

def process_odds_home(message, title, home, away):
    try:
        oh = float(message.text)
        msg = bot.reply_to(message, "📈 ضریب تساوی:")
        bot.register_next_step_handler(msg, process_odds_draw, title, home, away, oh)
    except:
        bot.reply_to(message, "❌ عدد وارد کنید!")

# ... (بقیه process_odds_draw و process_odds_away مثل کد قبلی)

def broadcast_message(message):
    if message.text in ["/cancel", "لغو", "cancel"]:
        return bot.reply_to(message, "❌ لغو شد.", reply_markup=admin_menu())

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    success = 0
    for u in users:
        try:
            bot.send_message(u[0], message.text)
            success += 1
        except:
            pass
    bot.reply_to(message, f"✅ به {success} کاربر ارسال شد.", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "cancel_broadcast")
def cancel(call):
    bot.edit_message_text("❌ پخش پیام لغو شد.", call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "👑 پنل مدیریت", reply_markup=admin_menu())

# ==================== کاربر ====================
@bot.message_handler(func=lambda m: m.text == "⚽ شرط‌بندی")
def betting(message):
    events = get_active_events()
    if not events:
        return bot.reply_to(message, "❌ رویدادی وجود ندارد.")
    kb = InlineKeyboardMarkup(row_width=1)
    for e in events:
        kb.add(InlineKeyboardButton(f"{e[1]} | {e[2]} vs {e[3]}", callback_data=f"event_{e[0]}"))
    bot.send_message(message.chat.id, "🏟 رویدادهای فعال:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "💰 موجودی من")
def show_balance(message):
    bot.reply_to(message, f"💰 موجودی: `{get_balance(message.from_user.id):,}` تومان", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def unknown(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "از دکمه‌های منوی ادمین استفاده کنید.", reply_markup=admin_menu())
    else:
        bot.reply_to(message, "از دکمه‌های منو استفاده کنید.", reply_markup=main_menu())

print("🚀 بات شرط‌بندی شروع شد...")
bot.infinity_polling(skip_pending=True, none_stop=True)
