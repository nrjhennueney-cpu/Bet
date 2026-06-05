import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
import os
from datetime import datetime, timedelta
import threading
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 6056483071

bot = telebot.TeleBot(TOKEN)

# ==================== بهبود اتصال ====================
def setup_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    bot.session = session

setup_session()

# ==================== دیتابیس ====================
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        return conn
    except Exception as e:
        print(f"❌ خطای اتصال دیتابیس: {e}")
        time.sleep(3)
        return psycopg2.connect(DATABASE_URL, connect_timeout=10)

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
    print("✅ دیتابیس اولیه آماده شد")

def migrate_db():
    conn = get_db_connection()
    cur = conn.cursor()
    migrations = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS sport TEXT;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS home_team TEXT;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS away_team TEXT;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS odds_home FLOAT;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS odds_draw FLOAT;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS odds_away FLOAT;",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS result TEXT;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_deposit INTEGER DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_win INTEGER DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_loss INTEGER DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
    ]
    for sql in migrations:
        try:
            cur.execute(sql)
        except:
            pass
    conn.commit()
    cur.close()
    conn.close()
    print("✅ مهاجرت دیتابیس انجام شد")

init_db()
migrate_db()

# ==================== پیام آپدیت بعد از دپلوی ====================
def send_startup_message():
    try:
        bot.send_message(ADMIN_ID, "🚀 **بات با موفقیت آپدیت و راه‌اندازی شد**\n✅ آماده دریافت دستورات", parse_mode='Markdown')
        print("✅ پیام آپدیت به ادمین ارسال شد")
    except:
        print("⚠️ پیام آپدیت ارسال نشد")

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
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ لغو", callback_data="cancel_broadcast"))
        bot.reply_to(message, "📢 متن پیام را ارسال کنید:", reply_markup=kb)
        bot.register_next_step_handler(message, broadcast_confirm)

    elif text == "📊 آمار کلی":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users"); users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM events WHERE status='active'"); events = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(balance),0) FROM users"); total_balance = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_win),0) FROM users"); total_win = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_loss),0) FROM users"); total_loss = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_deposit),0) FROM users"); total_deposit = cur.fetchone()[0]
        cur.close()
        conn.close()
        bot.reply_to(message, f"""📊 **آمار کلی ربات**

👥 کاربران: `{users}`
🎮 پیش‌بینی فعال: `{events}`
💰 مجموع موجودی: `{total_balance:,}`
📈 کل برد کاربران: `{total_win:,}`
📉 کل ضرر کاربران: `{total_loss:,}`
💵 مجموع واریز: `{total_deposit:,}`
""", parse_mode='Markdown')

    elif text == "👥 لیست کاربران":
        send_users_list(message)

    elif text == "🔙 منوی اصلی":
        bot.send_message(message.chat.id, "👑 پنل مدیریت", reply_markup=admin_menu())

# ==================== اضافه کردن پیش‌بینی ====================
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
        bot.register_next_step_handler(message, process_odds_home, sport, title, home, away)

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
        msg = bot.reply_to(message, "⏰ ساعت شروع بازی (به وقت تهران):\nمثال: 19 یا 5")
        bot.register_next_step_handler(msg, process_start_time, sport, title, home, away, oh, od, oa)
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
        """, (sport, title, home, away, oh, od if od > 0 else None, oa, start_time, ADMIN_ID))
        conn.commit()
        cur.close()
        conn.close()
        bot.reply_to(message, f"✅ پیش‌بینی **{title}** ثبت شد!", reply_markup=admin_menu())
    except:
        bot.reply_to(message, "❌ خطا در ثبت!")

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
    msg = bot.reply_to(message, "💵 مقدار واریز ترون (مثال: 5):")
    bot.register_next_step_handler(msg, process_deposit_amount)

def process_deposit_amount(message):
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
        text = f"""💳 **درخواست واریز**

مبلغ: `{amount}` TRX

📍 آدرس واریز:
`TQxhiwDREd8rxZuyDWx3auxcpzjSi1mAJG`

✅ بعد از واریز، رسید را ارسال کنید."""
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ لغو", callback_data=f"cancel_dep_{message.from_user.id}"))
        bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=kb)
        bot.register_next_step_handler(message, process_deposit_receipt, amount)
    except:
        bot.reply_to(message, "❌ عدد معتبر وارد کنید!")

# ==================== ادامه توابع واریز ====================
def process_deposit_receipt(message, amount):
    if not message.photo:
        return bot.reply_to(message, "❌ باید عکس رسید ارسال کنید!")
    
    user_id = message.from_user.id
    caption = f"""🔔 **درخواست واریز جدید**

👤 کاربر: `{user_id}`
💰 مبلغ: `{amount}` TRX

📸 رسید:"""

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("✅ تایید", callback_data=f"confirm_dep_{user_id}_{amount}"))
    kb.add(InlineKeyboardButton("❌ رد", callback_data=f"reject_dep_{user_id}"))
    
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=kb)
    bot.reply_to(message, "✅ رسید شما برای ادمین ارسال شد. لطفاً منتظر باشید.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_dep_"))
def confirm_deposit(call):
    _, user_id, amount = call.data.split("_")
    user_id = int(user_id)
    amount_toman = int(float(amount) * 35000)   # نرخ تقریبی ترون به تومان

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + %s, total_deposit = total_deposit + %s WHERE user_id = %s", 
                (amount_toman, amount_toman, user_id))
    conn.commit()
    cur.close()
    conn.close()

    bot.edit_message_caption("✅ واریز تایید و موجودی شارژ شد.", call.message.chat.id, call.message.message_id)
    bot.send_message(user_id, f"✅ واریز شما به مبلغ `{amount_toman:,}` تومان تایید شد!", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_dep_"))
def reject_deposit(call):
    user_id = int(call.data.split("_")[2])
    bot.edit_message_caption("❌ واریز رد شد.", call.message.chat.id, call.message.message_id)
    bot.send_message(user_id, "❌ درخواست واریز شما رد شد.")

# ==================== برداشت ====================
@bot.message_handler(func=lambda m: m.text == "➖ برداشت موجودی")
def withdraw_request(message):
    balance = get_balance(message.from_user.id)
    if balance < 1050000:
        return bot.reply_to(message, "❌ حداقل موجودی برای برداشت ۱٫۰۵ میلیون تومان است.")
    
    msg = bot.reply_to(message, "🏧 آدرس والت ترون خود را ارسال کنید:")
    bot.register_next_step_handler(msg, process_withdraw_address, balance)

def process_withdraw_address(message, balance):
    address = message.text.strip()
    amount_trx = balance // 35000

    text = f"""🟡 **درخواست برداشت**

👤 کاربر: `{message.from_user.id}`
💰 موجودی: `{balance:,}` تومان
📤 مقدار تقریبی: `{amount_trx}` TRX
📍 آدرس: `{address}`"""

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ واریز شد", callback_data=f"paid_{message.from_user.id}_{amount_trx}"))
    
    bot.send_message(ADMIN_ID, text, parse_mode='Markdown', reply_markup=kb)
    bot.reply_to(message, "✅ درخواست برداشت به ادمین ارسال شد.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("paid_"))
def paid_withdraw(call):
    _, user_id, amount = call.data.split("_")
    user_id = int(user_id)
    bot.send_message(user_id, f"✅ مبلغ `{amount}` ترون به والت شما واریز شد.\nموجودی صفر شد.", parse_mode='Markdown')
    bot.edit_message_text("✅ برداشت ثبت شد.", call.message.chat.id, call.message.message_id)

# ==================== شرط‌بندی ====================
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
    cur.execute("SELECT id, title, home_team, away_team, start_time FROM events WHERE sport = %s AND status = 'active'", (sport,))
    events = cur.fetchall()
    cur.close()
    conn.close()

    if not events:
        return bot.answer_callback_query(call.id, "رویدادی یافت نشد.")

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
        cur.execute("INSERT INTO bets (user_id, event_id, bet_type, amount, odds) VALUES (%s, %s, %s, %s, %s)",
                    (message.from_user.id, event_id, bet_type, amount, odd))
        cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, message.from_user.id))
        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(message, "✅ **پیش‌بینی شما ثبت شد!**", parse_mode='Markdown')
    except:
        bot.reply_to(message, "❌ عدد معتبر وارد کنید!")

# ==================== شروع بات ====================
def startup_cleanup():
    try:
        bot.remove_webhook()
        bot.get_updates(offset=-1, limit=1)
        print("✅ پاکسازی اولیه انجام شد")
    except:
        pass

if __name__ == "__main__":
    startup_cleanup()
    send_startup_message()
    print("🚀 بات شرط‌بندی شروع شد...")
    
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                none_stop=True,
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=['message', 'callback_query']
            )
        except Exception as e:
            print(f"⚠️ خطای polling: {e}")
            time.sleep(5)
