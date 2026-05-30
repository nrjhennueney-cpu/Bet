import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
import psycopg2
import os
import sys
from datetime import datetime, timedelta
import threading
import time

# ========== گرفتن متغیرها ==========
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ خطا: BOT_TOKEN تنظیم نشده است")
    sys.exit(1)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ خطا: DATABASE_URL تنظیم نشده است")
    sys.exit(1)

RAILWAY_STATIC_URL = os.getenv("RAILWAY_STATIC_URL")
WEBHOOK_URL = f"https://{RAILWAY_STATIC_URL}" if RAILWAY_STATIC_URL else os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "True").lower() == "true"

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
            total_deposit INTEGER DEFAULT 0,
            total_win INTEGER DEFAULT 0,
            total_loss INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            sport TEXT NOT NULL,
            title TEXT NOT NULL,
            home_team TEXT,
            away_team TEXT,
            odds_home FLOAT,
            odds_draw FLOAT,
            odds_away FLOAT,
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

# ==================== منوی همبرگری ====================
def set_bot_commands():
    commands = [
        BotCommand("start", "🔄 شروع مجدد"),
        BotCommand("menu", "📱 منوی اصلی"),
    ]
    bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# ==================== کیبوردها ====================
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("⚽ پیش‌بینی"), KeyboardButton("💰 کیف پول"))
    kb.add(KeyboardButton("📜 شرط‌های من"), KeyboardButton("🏆 رتبه‌بندی"))
    return kb

def wallet_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("💵 نمایش موجودی"), KeyboardButton("➕ افزایش موجودی"))
    kb.add(KeyboardButton("➖ برداشت موجودی"), KeyboardButton("🔙 منوی اصلی"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("➕ اضافه کردن پیش‌بینی"), KeyboardButton("📋 لیست پیش‌بینی‌ها"))
    kb.add(KeyboardButton("📢 پخش پیام همگانی"), KeyboardButton("📊 آمار کلی"))
    kb.add(KeyboardButton("👥 لیست کاربران"), KeyboardButton("🔙 منوی اصلی"))
    return kb

# ==================== توابع کمکی ====================
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

def is_banned(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_banned FROM users WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res and res[0]

# ==================== شروع بات ====================
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s)", 
                   (user_id, username, first_name))
        conn.commit()
        welcome_text = (
            "🤖 به بات پیش‌بینی ویکتورز کلاب خوش اومدی!\n\n"
            "💰 جایزه ثبت‌نام: 100,000 تومان\n\n"
            "⚽ می‌تونی روی بازی‌های مختلف شرط ببندی و برنده بشی!"
        )
        bot.send_message(message.chat.id, welcome_text)
    cur.close()
    conn.close()
    
    if user_id == ADMIN_ID:
        bot.send_message(message.chat.id, "👑 به پنل مدیریت خوش آمدید", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, "🧭 منوی اصلی:", reply_markup=main_menu())

# ==================== هندلر ادمین ====================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_panel(message):
    text = message.text

    if text == "➕ اضافه کردن پیش‌بینی":
        sports = ["⚽ فوتبال", "🎾 تنیس", "🏐 والیبال", "🏀 بسکتبال", "🏸 بدمینتون"]
        kb = InlineKeyboardMarkup(row_width=2)
        for sport in sports:
            kb.add(InlineKeyboardButton(sport, callback_data=f"add_event_{sport.split()[1]}"))
        bot.reply_to(message, "🏟 لطفاً ورزش مورد نظر را انتخاب کنید:", reply_markup=kb)

    elif text == "📋 لیست پیش‌بینی‌ها":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, sport, title, start_time, status FROM events ORDER BY id DESC")
        events = cur.fetchall()
        cur.close()
        conn.close()

        if not events:
            return bot.reply_to(message, "❌ پیش‌بینی فعالی وجود ندارد.")

        txt = "📋 **لیست پیش‌بینی‌ها:**\n\n"
        for e in events:
            txt += f"#{e[0]} | {e[1]} | {e[2]}\n⏰ {e[3]}\nوضعیت: {e[4]}\n\n"
        bot.reply_to(message, txt, parse_mode='Markdown')

    elif text == "📢 پخش پیام همگانی":
        msg = bot.reply_to(message, "📢 متن پیام را ارسال کنید:")
        bot.register_next_step_handler(msg, broadcast_confirm)

    elif text == "📊 آمار کلی":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM events WHERE status='active'")
        events = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(balance),0) FROM users")
        total_balance = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_win),0) FROM users")
        total_win = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_loss),0) FROM users")
        total_loss = cur.fetchone()[0]
        cur.close()
        conn.close()

        bot.reply_to(message, f"""📊 **آمار کلی ربات**

👥 کاربران: `{users}`
🎮 پیش‌بینی فعال: `{events}`
💰 مجموع موجودی: `{total_balance:,}`
📈 کل برد کاربران: `{total_win:,}`
📉 کل ضرر کاربران: `{total_loss:,}`
""", parse_mode='Markdown')

    elif text == "👥 لیست کاربران":
        send_users_list(message)

    elif text == "🔙 منوی اصلی":
        bot.send_message(message.chat.id, "🧭 منوی اصلی:", reply_markup=main_menu())

# ==================== اضافه کردن پیش‌بینی (ادامه) ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("add_event_"))
def add_event_step(call):
    sport = call.data.split("_")[2]
    msg = bot.edit_message_text(f"🏷 عنوان پیش‌بینی برای **{sport}**:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(msg, process_event_title, sport)

def process_event_title(message, sport):
    title = message.text
    msg = bot.reply_to(message, "🏠 تیم/بازیکن میزبان:")
    bot.register_next_step_handler(msg, process_home, sport, title)

def process_home(message, sport, title):
    home = message.text
    msg = bot.reply_to(message, "🏟 تیم/بازیکن مهمان:")
    bot.register_next_step_handler(msg, process_away, sport, title, home)

def process_away(message, sport, title, home):
    away = message.text
    msg = bot.reply_to(message, f"📈 ضریب برد {home}:")
    bot.register_next_step_handler(msg, process_odds_home, sport, title, home, away)

def process_odds_home(message, sport, title, home, away):
    try:
        oh = float(message.text)
        msg = bot.reply_to(message, "📈 ضریب تساوی (اگر وجود ندارد 0 بزنید):")
        bot.register_next_step_handler(msg, process_odds_draw, sport, title, home, away, oh)
    except:
        bot.reply_to(message, "❌ عدد وارد کنید!")

def process_odds_draw(message, sport, title, home, away, oh):
    try:
        od = float(message.text)
        msg = bot.reply_to(message, f"📈 ضریب برد {away}:")
        bot.register_next_step_handler(msg, process_odds_away, sport, title, home, away, oh, od)
    except:
        bot.reply_to(message, "❌ عدد وارد کنید!")

def process_odds_away(message, sport, title, home, away, oh, od):
    try:
        oa = float(message.text)
        msg = bot.reply_to(message, "⏰ ساعت شروع بازی (به وقت تهران):\nمثال: 19")
        bot.register_next_step_handler(msg, process_start_time, sport, title, home, away, oh, od if od > 0 else None, oa)
    except:
        bot.reply_to(message, "❌ عدد وارد کنید!")

def process_start_time(message, sport, title, home, away, oh, od, oa):
    try:
        hour = int(message.text)
        start_time = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
        if start_time < datetime.now():
            start_time += timedelta(days=1)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO events (sport, title, home_team, away_team, odds_home, odds_draw, odds_away, start_time, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (sport, title, home, away, oh, od, oa, start_time, ADMIN_ID))
        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(message, f"✅ پیش‌بینی **{title}** با موفقیت ثبت شد!", reply_markup=admin_menu())

    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {e}")

# ==================== کیف پول ====================
@bot.message_handler(func=lambda m: m.text == "💰 کیف پول")
def wallet(message):
    if is_banned(message.from_user.id):
        return bot.reply_to(message, "❌ شما بن شده‌اید.")
    bot.reply_to(message, "💰 بخش کیف پول", reply_markup=wallet_menu())

@bot.message_handler(func=lambda m: m.text == "💵 نمایش موجودی")
def show_balance(message):
    balance = get_balance(message.from_user.id)
    bot.reply_to(message, f"💰 موجودی فعلی شما:\n`{balance:,}` تومان", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "➕ افزایش موجودی")
def deposit_request(message):
    bot.reply_to(message, "💵 برای افزایش موجودی با ادمین تماس بگیرید:\n@AdminUsername")

@bot.message_handler(func=lambda m: m.text == "➖ برداشت موجودی")
def withdraw_request(message):
    bot.reply_to(message, "🏧 برای برداشت موجودی با ادمین تماس بگیرید:\n@AdminUsername")

@bot.message_handler(func=lambda m: m.text == "🔙 منوی اصلی")
def back_to_main(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "🧭 منوی اصلی:", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "🧭 منوی اصلی:", reply_markup=main_menu())

# ==================== پیش‌بینی ====================
@bot.message_handler(func=lambda m: m.text == "⚽ پیش‌بینی")
def betting(message):
    if is_banned(message.from_user.id):
        return bot.reply_to(message, "❌ شما بن شده‌اید.")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT sport FROM events WHERE status='active'")
    sports = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not sports:
        return bot.reply_to(message, "❌ فعلاً پیش‌بینی فعالی وجود ندارد.")

    kb = InlineKeyboardMarkup(row_width=2)
    for sport in sports:
        kb.add(InlineKeyboardButton(sport, callback_data=f"sport_{sport}"))
    bot.send_message(message.chat.id, "🏟 لطفاً ورزش را انتخاب کنید:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sport_"))
def show_events_by_sport(call):
    sport = call.data.split("_")[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, home_team, away_team, start_time 
        FROM events 
        WHERE sport = %s AND status = 'active'
    """, (sport,))
    events = cur.fetchall()
    cur.close()
    conn.close()

    if not events:
        return bot.answer_callback_query(call.id, "رویدادی در این ورزش وجود ندارد.")

    kb = InlineKeyboardMarkup(row_width=1)
    for e in events:
        kb.add(InlineKeyboardButton(f"{e[1]} | {e[2]} vs {e[3]}", callback_data=f"bet_{e[0]}"))
    
    bot.edit_message_text(f"📌 پیش‌بینی‌های {sport}:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bet_"))
def select_bet_type(call):
    event_id = int(call.data.split("_")[1])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT title, home_team, away_team, odds_home, odds_draw, odds_away, start_time FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    cur.close()
    conn.close()

    if not event:
        return bot.answer_callback_query(call.id, "رویداد یافت نشد")

    text = f"""🏟 **{event[0]}**
{event[1]} vs {event[2]}
⏰ {event[6].strftime('%Y-%m-%d %H:%M')}

ضرایب:
• برد {event[1]}: `{event[3]}`
• تساوی: `{event[4] if event[4] else '—'}`
• برد {event[2]}: `{event[5]}`
"""

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🏆 برد {event[1]}", callback_data=f"bettype_{event_id}_home"))
    if event[4]:
        kb.add(InlineKeyboardButton("⚖ تساوی", callback_data=f"bettype_{event_id}_draw"))
    kb.add(InlineKeyboardButton(f"🏆 برد {event[2]}", callback_data=f"bettype_{event_id}_away"))

    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bettype_"))
def ask_bet_amount(call):
    _, event_id, bet_type = call.data.split("_")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT odds_home, odds_draw, odds_away FROM events WHERE id = %s", (event_id,))
    odds = cur.fetchone()
    cur.close()
    conn.close()

    odd = odds[0] if bet_type == "home" else odds[1] if bet_type == "draw" else odds[2]
    
    msg = bot.send_message(call.message.chat.id, f"💰 مبلغ شرط را وارد کنید (موجودی: `{get_balance(call.from_user.id):,}`):", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_bet_amount, int(event_id), bet_type, odd)

def process_bet_amount(message, event_id, bet_type, odd):
    try:
        amount = int(message.text)
        balance = get_balance(message.from_user.id)
        
        if amount > balance or amount < 10000:
            return bot.reply_to(message, "❌ مبلغ نامعتبر یا موجودی کافی نیست.")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bets (user_id, event_id, bet_type, amount, odds)
            VALUES (%s, %s, %s, %s, %s)
        """, (message.from_user.id, event_id, bet_type, amount, odd))
        
        cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, message.from_user.id))
        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(message, "✅ **پیش‌بینی شما با موفقیت ثبت شد!**", parse_mode='Markdown')
        
    except:
        bot.reply_to(message, "❌ لطفاً عدد معتبر وارد کنید!")

# ==================== شرط‌های من ====================
@bot.message_handler(func=lambda m: m.text == "📜 شرط‌های من")
def my_bets(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, e.title, b.bet_type, b.amount, b.odds, b.status, b.created_at 
        FROM bets b 
        JOIN events e ON b.event_id = e.id 
        WHERE b.user_id = %s 
        ORDER BY b.created_at DESC 
        LIMIT 20
    """, (message.from_user.id,))
    bets = cur.fetchall()
    cur.close()
    conn.close()

    if not bets:
        return bot.reply_to(message, "📭 هنوز شرطی ثبت نکرده‌اید.")

    txt = "📜 **آخرین شرط‌های شما:**\n\n"
    for b in bets:
        status_emoji = "⏳" if b[5] == "active" else "✅" if b[5] == "settled" else "❌"
        txt += f"{status_emoji} #{b[0]} | {b[1]}\n"
        txt += f"شرط: {b[2]} | مبلغ: {b[3]:,} | ضریب: {b[4]}\n"
        txt += f"📅 {b[6].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    bot.reply_to(message, txt, parse_mode='Markdown')

# ==================== رتبه‌بندی ====================
@bot.message_handler(func=lambda m: m.text == "🏆 رتبه‌بندی")
def leaderboard(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT username, first_name, total_win, total_loss, balance 
        FROM users 
        WHERE total_win + total_loss > 0 
        ORDER BY total_win DESC 
        LIMIT 10
    """)
    users = cur.fetchall()
    cur.close()
    conn.close()

    if not users:
        return bot.reply_to(message, "📊 هنوز داده‌ای برای رتبه‌بندی وجود ندارد.")

    txt = "🏆 **رتبه‌بندی برندگان:**\n\n"
    for i, u in enumerate(users, 1):
        name = u[1] or u[0] or f"کاربر {i}"
        txt += f"{i}. {name} | برد: {u[2]:,} | ضرر: {u[3]:,} | موجودی: {u[4]:,}\n"
    
    bot.reply_to(message, txt, parse_mode='Markdown')

# ==================== لیست کاربران ====================
def send_users_list(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, first_name, balance, total_win, total_loss, joined_at 
        FROM users ORDER BY joined_at DESC
    """)
    users = cur.fetchall()
    cur.close()
    conn.close()

    if not users:
        return bot.reply_to(message, "هیچ کاربری یافت نشد.")

    txt = "👥 **لیست کاربران**\n\n"
    for u in users[:30]:
        txt += f"🆔 `{u[0]}` | @{u[1] or '—'} | {u[2] or '—'}\n💰 موجودی: {u[3]:,} | برد: {u[4]:,}\n\n"

    bot.reply_to(message, txt, parse_mode='Markdown')

# ==================== پخش پیام همگانی ====================
def broadcast_confirm(message):
    if message.text == "❌ لغو":
        return bot.reply_to(message, "❌ لغو شد.")
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ ارسال شود", callback_data="confirm_broadcast"))
    kb.add(InlineKeyboardButton("❌ لغو", callback_data="cancel_broadcast"))
    
    bot.reply_to(message, f"مطمئن هستید این پیام به همه ارسال شود؟\n\n{message.text}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "confirm_broadcast")
def do_broadcast(call):
    text = call.message.text.split("\n\n", 1)[1] if "\n\n" in call.message.text else call.message.text
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_banned = FALSE")
    users = cur.fetchall()
    cur.close()
    conn.close()

    success = 0
    for u in users:
        try:
            bot.send_message(u[0], text)
            success += 1
            time.sleep(0.05)
        except:
            pass
    bot.edit_message_text(f"✅ پیام به {success} کاربر ارسال شد.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_broadcast")
def cancel_broadcast(call):
    bot.edit_message_text("❌ پخش پیام لغو شد.", call.message.chat.id, call.message.message_id)

# ==================== هندلر ناشناخته ====================
@bot.message_handler(func=lambda m: True)
def unknown(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "👑 از منوی ادمین استفاده کنید.", reply_markup=admin_menu())
    else:
        bot.reply_to(message, "🧭 از منوی اصلی استفاده کنید.", reply_markup=main_menu())

# ==================== راه‌اندازی ====================
def setup_webhook():
    if not WEBHOOK_URL:
        print("⚠️ WEBHOOK_URL مشخص نیست، حالت Polling استفاده می‌شود")
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
        return "بات پیش‌بینی ویکتورز کلاب فعال ✅"

    if __name__ == "__main__":
        setup_webhook()
        print(f"🚀 بات روی پورت {PORT} در حال اجراست...")
        app.run(host='0.0.0.0', port=PORT)
else:
    if __name__ == "__main__":
        bot.remove_webhook()
        print("🤖 بات در حالت Polling اجرا شد...")
        bot.infinity_polling(skip_pending=True)
