import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
import psycopg2
import os
import threading
import time as time_module
from datetime import datetime, timezone, timedelta
import re

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 6056483071
TRON_ADDRESS = "TQxhiwDREd8rxZuyDWx3auxcpzjSi1mAJG"
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)

bot = telebot.TeleBot(TOKEN)
bot_active = True

MENU_BUTTONS = {
    "➕ اضافه کردن پیش‌بینی", "📋 لیست پیش‌بینی‌ها",
    "📢 پخش پیام همگانی", "📊 آمار کلی",
    "👥 لیست کاربران", "🔍 سرچ کاربر",
    "🚫 بن کاربر", "✅ آن‌بن کاربر",
    "🔴 خاموش کردن بات", "🟢 روشن کردن بات",
    "🔙 منوی اصلی", "⚽ پیش‌بینی", "👜 کیف پول",
    "📜 شرط‌های من", "🏆 رتبه‌بندی",
    "🗑 مدیریت پیش‌بینی‌ها",
}

# ==================== دیتابیس ====================
def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 10000,
            total_deposit INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            total_lost INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # match_minute ستون جدید برای دقیقه بازی
    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            sport TEXT DEFAULT 'فوتبال',
            team1 TEXT NOT NULL,
            team2 TEXT NOT NULL,
            odds1 FLOAT NOT NULL,
            odds2 FLOAT NOT NULL,
            odds_draw FLOAT,
            match_hour INTEGER NOT NULL,
            match_minute INTEGER NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'active',
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE
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
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            trx_address TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # اضافه کردن ستون‌های جدید اگه وجود نداشتن (migration)
    cur.execute("""
        ALTER TABLE events ADD COLUMN IF NOT EXISTS match_minute INTEGER NOT NULL DEFAULT 0
    """)
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_deposit INTEGER DEFAULT 0
    """)
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_won INTEGER DEFAULT 0
    """)
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_lost INTEGER DEFAULT 0
    """)
    cur.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ==================== ابزارها ====================
def now_tehran():
    return datetime.now(timezone.utc) + TEHRAN_OFFSET

def ensure_user(user):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s", (user.id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (%s,%s,%s)",
            (user.id, user.username, user.first_name)
        )
        conn.commit()
    cur.close()
    conn.close()

def get_balance(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r[0] if r else 0

def is_banned(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_banned FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r[0] if r else False

def is_valid_tron(address):
    # آدرس ترون با T شروع میشه و 34 کاراکتر base58
    return bool(re.match(r'^T[a-zA-Z0-9]{33}$', address))

def parse_time(text):
    """پارس ساعت از فرمت‌های مختلف: 19، 19:30، 19.30"""
    text = text.strip()
    m = re.match(r'^(\d{1,2})[:\.](\d{2})$', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
    elif re.match(r'^\d{1,2}$', text):
        h, mn = int(text), 0
    else:
        return None, None
    if 0 <= h <= 23 and 0 <= mn <= 59:
        return h, mn
    return None, None

def cancel_next_step(chat_id):
    try:
        bot.clear_step_handler_by_chat_id(chat_id)
    except:
        pass

def is_menu_button(text):
    return text in MENU_BUTTONS

# ==================== کیبوردها ====================
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("⚽ پیش‌بینی"), KeyboardButton("👜 کیف پول"))
    kb.add(KeyboardButton("📜 شرط‌های من"), KeyboardButton("🏆 رتبه‌بندی"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("➕ اضافه کردن پیش‌بینی"), KeyboardButton("📋 لیست پیش‌بینی‌ها"))
    kb.add(KeyboardButton("🗑 مدیریت پیش‌بینی‌ها"), KeyboardButton("📢 پخش پیام همگانی"))
    kb.add(KeyboardButton("📊 آمار کلی"), KeyboardButton("👥 لیست کاربران"))
    kb.add(KeyboardButton("🔍 سرچ کاربر"), KeyboardButton("🚫 بن کاربر"))
    kb.add(KeyboardButton("✅ آن‌بن کاربر"), KeyboardButton("🔴 خاموش کردن بات"))
    kb.add(KeyboardButton("🟢 روشن کردن بات"), KeyboardButton("🔙 منوی اصلی"))
    return kb

def wallet_menu():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💰 نمایش موجودی", callback_data="wallet_balance"),
        InlineKeyboardButton("➕ افزایش موجودی", callback_data="wallet_deposit"),
        InlineKeyboardButton("💸 برداشت موجودی", callback_data="wallet_withdraw"),
    )
    return kb

SPORTS = ["⚽ فوتبال", "🎾 تنیس", "🏐 والیبال"]

# ==================== /start ====================
@bot.message_handler(commands=['start'])
def start(msg):
    cancel_next_step(msg.chat.id)
    ensure_user(msg.from_user)
    if msg.from_user.id == ADMIN_ID:
        bot.send_message(msg.chat.id, "👑 *پنل مدیریت فعال شد*", parse_mode='Markdown', reply_markup=admin_menu())
    else:
        bot.send_message(msg.chat.id, "🎰 *به ربات پیش‌بینی خوش آمدید!*", parse_mode='Markdown', reply_markup=main_menu())

# ==================== /fixdb ====================
@bot.message_handler(commands=['fixdb'])
def fixdb(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    bot.send_message(msg.chat.id, "⏳ در حال بازسازی جداول دیتابیس...")
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS bets CASCADE")
        cur.execute("DROP TABLE IF EXISTS events CASCADE")
        cur.execute("DROP TABLE IF EXISTS users CASCADE")
        cur.execute("DROP TABLE IF EXISTS withdrawals CASCADE")
        conn.commit()
        cur.close()
        conn.close()
        init_db()
        bot.send_message(msg.chat.id, "✅ دیتابیس با موفقیت بازسازی شد!")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ خطا:\n`{e}`", parse_mode='Markdown')

# ==================== میان‌گیر دکمه‌های منو ====================
@bot.message_handler(func=lambda m: is_menu_button(m.text), content_types=['text'])
def menu_interceptor(msg):
    cancel_next_step(msg.chat.id)
    dispatch_menu(msg)

def dispatch_menu(msg):
    text = msg.text
    uid = msg.from_user.id

    if text == "👜 کیف پول":
        return wallet(msg)
    if text == "⚽ پیش‌بینی":
        return user_betting(msg)
    if text == "📜 شرط‌های من":
        return my_bets(msg)
    if text == "🏆 رتبه‌بندی":
        return leaderboard(msg)

    if uid != ADMIN_ID:
        return

    if text == "➕ اضافه کردن پیش‌بینی":
        return add_prediction(msg)
    if text == "📋 لیست پیش‌بینی‌ها":
        return list_events_admin(msg)
    if text == "🗑 مدیریت پیش‌بینی‌ها":
        return manage_predictions(msg)
    if text == "📢 پخش پیام همگانی":
        return broadcast_prompt(msg)
    if text == "📊 آمار کلی":
        return stats(msg)
    if text == "👥 لیست کاربران":
        return list_users(msg)
    if text == "🔍 سرچ کاربر":
        return search_user_prompt(msg)
    if text == "🚫 بن کاربر":
        return ban_prompt(msg)
    if text == "✅ آن‌بن کاربر":
        return unban_prompt(msg)
    if text == "🔴 خاموش کردن بات":
        return bot_off(msg)
    if text == "🟢 روشن کردن بات":
        return bot_on(msg)
    if text == "🔙 منوی اصلی":
        return back_to_admin(msg)

# ==================== کیف پول ====================
def wallet(msg):
    ensure_user(msg.from_user)
    bot.send_message(msg.chat.id, "👜 *کیف پول*\nیک گزینه انتخاب کنید:", parse_mode='Markdown', reply_markup=wallet_menu())

@bot.callback_query_handler(func=lambda c: c.data == "wallet_balance")
def wallet_balance(call):
    bal = get_balance(call.from_user.id)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"💰 موجودی شما: `{bal/100:.2f}` TRX", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: c.data == "wallet_deposit")
def wallet_deposit(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "💳 مقدار واریز ترون خود را وارد کنید:\nمثال: `5`", parse_mode='Markdown')
    bot.register_next_step_handler(m, deposit_amount_step, call.from_user.id)

def deposit_amount_step(msg, uid):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        amount = float(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        return bot.send_message(msg.chat.id, "❌ مقدار نامعتبر است.")
    bot.send_message(
        msg.chat.id,
        f"📥 *آدرس واریز ترون:*\n\n`{TRON_ADDRESS}`\n\n💡 مبلغ: `{amount}` TRX\n\n✅ پس از واریز، رسید (عکس) را ارسال کنید.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler_by_chat_id(msg.chat.id, deposit_receipt_step, uid, amount)

def deposit_receipt_step(msg, uid, amount):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    if not msg.photo:
        m = bot.send_message(msg.chat.id, "❌ لطفاً عکس رسید را ارسال کنید.")
        bot.register_next_step_handler(m, deposit_receipt_step, uid, amount)
        return
    file_id = msg.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ تایید", callback_data=f"dep_approve_{uid}_{int(amount*100)}"),
        InlineKeyboardButton("❌ رد", callback_data=f"dep_reject_{uid}")
    )
    bot.send_photo(ADMIN_ID, file_id,
        caption=f"📥 *درخواست واریز*\n👤 کاربر: `{uid}`\n💰 مبلغ: `{amount}` TRX",
        parse_mode='Markdown', reply_markup=kb)
    bot.send_message(msg.chat.id, "✅ رسید دریافت شد. منتظر تایید ادمین باشید.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep_approve_"))
def dep_approve(call):
    parts = call.data.split("_")
    uid = int(parts[2])
    amount_trx = int(parts[3]) / 100
    amount_units = int(parts[3])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance=balance+%s, total_deposit=total_deposit+%s WHERE user_id=%s",
                (amount_units, amount_units, uid))
    conn.commit(); cur.close(); conn.close()
    try:
        bot.edit_message_caption(
            f"✅ تایید | {amount_trx} TRX به موجودی افزوده شد",
            call.message.chat.id, call.message.message_id, reply_markup=None
        )
    except: pass
    bot.answer_callback_query(call.id, "✅ تایید شد")
    bot.send_message(uid, f"✅ *واریز تایید شد!*\n💰 `{amount_trx}` TRX به موجودی شما افزوده شد.", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep_reject_"))
def dep_reject(call):
    uid = int(call.data.split("_")[2])
    try:
        bot.edit_message_caption("❌ رد شد.", call.message.chat.id, call.message.message_id, reply_markup=None)
    except: pass
    bot.answer_callback_query(call.id, "❌ رد شد")
    bot.send_message(uid, "❌ واریز شما تایید نشد.")

# ==================== برداشت ====================
@bot.callback_query_handler(func=lambda c: c.data == "wallet_withdraw")
def wallet_withdraw(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    bal = get_balance(uid)
    min_units = 30 * 100  # 30 TRX
    if bal < min_units:
        return bot.send_message(call.message.chat.id,
            f"❌ حداقل برداشت 30 TRX است.\nموجودی شما: `{bal/100:.2f}` TRX", parse_mode='Markdown')
    m = bot.send_message(call.message.chat.id,
        f"💸 چه مقدار TRX برداشت می‌کنید؟\n*(موجودی: `{bal/100:.2f}` TRX، حداقل 30 TRX)*",
        parse_mode='Markdown')
    bot.register_next_step_handler(m, withdraw_amount_step, uid, bal)

def withdraw_amount_step(msg, uid, bal):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        amount_trx = float(msg.text.strip())
        amount_units = int(amount_trx * 100)
        if amount_trx < 30:
            raise ValueError("min")
        if amount_units > bal:
            raise ValueError("balance")
    except ValueError as e:
        if "min" in str(e):
            return bot.send_message(msg.chat.id, "❌ حداقل مقدار برداشت 30 TRX است.")
        elif "balance" in str(e):
            return bot.send_message(msg.chat.id, f"❌ موجودی کافی ندارید. موجودی: `{bal/100:.2f}` TRX", parse_mode='Markdown')
        return bot.send_message(msg.chat.id, "❌ مقدار نامعتبر.")
    m = bot.send_message(msg.chat.id, "📤 آدرس ترون خود را وارد کنید:")
    bot.register_next_step_handler(m, withdraw_address_step, uid, amount_units)

def withdraw_address_step(msg, uid, amount_units):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    address = (msg.text or "").strip()
    if not is_valid_tron(address):
        m = bot.send_message(msg.chat.id, "❌ آدرس ترون نامعتبر است.\nآدرس باید با T شروع شود و 34 کاراکتر باشد.")
        bot.register_next_step_handler(m, withdraw_address_step, uid, amount_units)
        return
    amount_trx = amount_units / 100
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO withdrawals (user_id, amount, trx_address) VALUES (%s,%s,%s) RETURNING id",
                (uid, amount_units, address))
    wid = cur.fetchone()[0]
    cur.execute("UPDATE users SET balance=balance-%s WHERE user_id=%s", (amount_units, uid))
    conn.commit(); cur.close(); conn.close()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ واریز انجام شد", callback_data=f"withdraw_done_{uid}_{wid}_{int(amount_trx*100)}"))
    bot.send_message(ADMIN_ID,
        f"💸 *درخواست برداشت*\n👤 کاربر: `{uid}`\n💰 مبلغ: `{amount_trx:.2f}` TRX\n📮 آدرس:\n`{address}`",
        parse_mode='Markdown', reply_markup=kb)
    bot.send_message(msg.chat.id, "✅ درخواست برداشت ثبت شد. منتظر پردازش باشید.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("withdraw_done_"))
def withdraw_done(call):
    parts = call.data.split("_")
    uid = int(parts[2])
    wid = int(parts[3])
    amount_trx = int(parts[4]) / 100
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status='done' WHERE id=%s", (wid,))
    conn.commit(); cur.close(); conn.close()
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except: pass
    bot.send_message(uid, f"✅ *برداشت انجام شد!*\n💰 `{amount_trx:.2f}` TRX به حساب شما واریز شد.", parse_mode='Markdown')
    bot.answer_callback_query(call.id, "✅ ارسال شد")

# ==================== اضافه کردن پیش‌بینی ====================
def add_prediction(msg):
    kb = InlineKeyboardMarkup(row_width=1)
    for s in SPORTS:
        kb.add(InlineKeyboardButton(s, callback_data=f"sport_{s}"))
    bot.send_message(msg.chat.id, "🏅 نوع ورزش را انتخاب کنید:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sport_"))
def sport_selected(call):
    sport = call.data[6:]
    cancel_next_step(call.message.chat.id)
    bot.edit_message_text(f"✅ ورزش: {sport}", call.message.chat.id, call.message.message_id)
    m = bot.send_message(call.message.chat.id,
        "📝 کانداکتور بازی را وارد کنید:\nمثال: `PSG vs Arsenal`", parse_mode='Markdown')
    bot.register_next_step_handler(m, add_teams_step, sport)

def add_teams_step(msg, sport):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    text = (msg.text or "").strip()
    if " vs " not in text.lower():
        m = bot.send_message(msg.chat.id, "❌ فرمت اشتباه. مثال: PSG vs Arsenal")
        bot.register_next_step_handler(m, add_teams_step, sport)
        return
    parts = text.split(" vs ")
    team1, team2 = parts[0].strip(), parts[1].strip()
    m = bot.send_message(msg.chat.id, f"📈 ضریب {team1}?")
    bot.register_next_step_handler(m, add_odds1_step, sport, team1, team2)

def add_odds1_step(msg, sport, team1, team2):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        o1 = float((msg.text or "").strip())
    except:
        m = bot.send_message(msg.chat.id, "❌ عدد وارد کنید!")
        bot.register_next_step_handler(m, add_odds1_step, sport, team1, team2)
        return
    m = bot.send_message(msg.chat.id, f"📈 ضریب {team2}?")
    bot.register_next_step_handler(m, add_odds2_step, sport, team1, team2, o1)

def add_odds2_step(msg, sport, team1, team2, o1):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        o2 = float((msg.text or "").strip())
    except:
        m = bot.send_message(msg.chat.id, "❌ عدد وارد کنید!")
        bot.register_next_step_handler(m, add_odds2_step, sport, team1, team2, o1)
        return
    if sport == "⚽ فوتبال":
        m = bot.send_message(msg.chat.id, "📈 ضریب مساوی؟")
        bot.register_next_step_handler(m, add_draw_step, sport, team1, team2, o1, o2)
    else:
        m = bot.send_message(msg.chat.id,
            "🕐 ساعت بازی (به وقت تهران)?\nمثال: `19` یا `19:30` یا `19.30`", parse_mode='Markdown')
        bot.register_next_step_handler(m, add_hour_step, sport, team1, team2, o1, o2, None)

def add_draw_step(msg, sport, team1, team2, o1, o2):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        od = float((msg.text or "").strip())
    except:
        m = bot.send_message(msg.chat.id, "❌ عدد وارد کنید!")
        bot.register_next_step_handler(m, add_draw_step, sport, team1, team2, o1, o2)
        return
    m = bot.send_message(msg.chat.id,
        "🕐 ساعت بازی (به وقت تهران)?\nمثال: `19` یا `19:30` یا `19.30`", parse_mode='Markdown')
    bot.register_next_step_handler(m, add_hour_step, sport, team1, team2, o1, o2, od)

def add_hour_step(msg, sport, team1, team2, o1, o2, od):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    hour, minute = parse_time(msg.text or "")
    if hour is None:
        m = bot.send_message(msg.chat.id,
            "❌ فرمت اشتباه. مثال: `19` یا `19:30` یا `19.30`", parse_mode='Markdown')
        bot.register_next_step_handler(m, add_hour_step, sport, team1, team2, o1, o2, od)
        return

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (sport, team1, team2, odds1, odds2, odds_draw, match_hour, match_minute) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (sport, team1, team2, o1, o2, od, hour, minute)
    )
    eid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()

    time_str = f"{hour:02d}:{minute:02d}"
    draw_txt = f"\n🤝 مساوی: `{od}`" if od else ""
    bot.send_message(msg.chat.id,
        f"✅ *پیش‌بینی ثبت شد!*\n\n🏅 {sport}\n🆚 {team1} vs {team2}\n"
        f"📈 {team1}: `{o1}` | {team2}: `{o2}`{draw_txt}\n⏰ ساعت: {time_str} تهران\n🔢 ID: `{eid}`",
        parse_mode='Markdown', reply_markup=admin_menu())

# ==================== لیست پیش‌بینی‌ها ====================
def list_events_admin(msg):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, sport, team1, team2, odds1, odds2, odds_draw, match_hour, match_minute FROM events WHERE status='active' ORDER BY id DESC")
    events = cur.fetchall()
    cur.close(); conn.close()
    if not events:
        return bot.send_message(msg.chat.id, "❌ پیش‌بینی فعالی وجود ندارد.")
    txt = "📋 *پیش‌بینی‌های فعال:*\n\n"
    for e in events:
        draw = f" | مساوی: {e[6]}" if e[6] else ""
        txt += f"#{e[0]} {e[1]}\n🆚 {e[2]} vs {e[3]}\n⚖️ {e[4]} | {e[5]}{draw} | ⏰{e[7]:02d}:{e[8]:02d}\n\n"
    bot.send_message(msg.chat.id, txt, parse_mode='Markdown')

# ==================== مدیریت پیش‌بینی‌ها (حذف) ====================
def manage_predictions(msg):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, sport, team1, team2, match_hour, match_minute FROM events WHERE status='active' ORDER BY id DESC")
    events = cur.fetchall()
    cur.close(); conn.close()
    if not events:
        return bot.send_message(msg.chat.id, "❌ پیش‌بینی فعالی وجود ندارد.")
    kb = InlineKeyboardMarkup(row_width=1)
    for e in events:
        kb.add(InlineKeyboardButton(
            f"🗑 #{e[0]} | {e[2]} vs {e[3]} | ⏰{e[4]:02d}:{e[5]:02d}",
            callback_data=f"del_event_{e[0]}"
        ))
    bot.send_message(msg.chat.id, "🗑 *کدام پیش‌بینی را حذف می‌کنید؟*", parse_mode='Markdown', reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del_event_"))
def delete_event(call):
    eid = int(call.data.split("_")[2])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT team1, team2 FROM events WHERE id=%s", (eid,))
    e = cur.fetchone()
    if not e:
        cur.close(); conn.close()
        return bot.answer_callback_query(call.id, "❌ یافت نشد.")
    # برگرداندن پول شرط‌بندها
    cur.execute("SELECT user_id, amount FROM bets WHERE event_id=%s AND status='pending'", (eid,))
    bets = cur.fetchall()
    for uid, amount in bets:
        cur.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (amount, uid))
        try:
            bot.send_message(uid,
                f"🔔 پیش‌بینی *{e[0]}* vs *{e[1]}* توسط ادمین حذف شد.\n💰 مبلغ `{amount/100:.2f}` TRX به موجودی شما بازگشت.",
                parse_mode='Markdown')
        except: pass
    cur.execute("UPDATE bets SET status='cancelled' WHERE event_id=%s AND status='pending'", (eid,))
    cur.execute("UPDATE events SET status='cancelled' WHERE id=%s", (eid,))
    conn.commit(); cur.close(); conn.close()
    bot.edit_message_text(f"✅ پیش‌بینی #{eid} ({e[0]} vs {e[1]}) حذف شد.",
                          call.message.chat.id, call.message.message_id)

# ==================== تعیین نتیجه ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("setresult_"))
def set_result_menu(call):
    eid = int(call.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT team1, team2, odds_draw FROM events WHERE id=%s", (eid,))
    e = cur.fetchone()
    cur.close(); conn.close()
    if not e:
        return bot.answer_callback_query(call.id, "رویداد یافت نشد.")
    t1, t2, od = e
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"🏆 برد {t1}", callback_data=f"result_{eid}_1"),
        InlineKeyboardButton(f"🏆 برد {t2}", callback_data=f"result_{eid}_2"),
    )
    if od:
        kb.add(InlineKeyboardButton("🤝 مساوی", callback_data=f"result_{eid}_draw"))
    bot.send_message(call.message.chat.id, f"نتیجه *{t1}* vs *{t2}*:", parse_mode='Markdown', reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("result_"))
def process_result(call):
    parts = call.data.split("_")
    eid = int(parts[1])
    outcome = parts[2]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT team1, team2, odds1, odds2, odds_draw FROM events WHERE id=%s AND status='active'", (eid,))
    e = cur.fetchone()
    if not e:
        cur.close(); conn.close()
        return bot.answer_callback_query(call.id, "❌ رویداد یافت نشد یا قبلاً ثبت شده.")
    t1, t2, o1, o2, od = e
    result_label = {"1": f"برد {t1}", "2": f"برد {t2}", "draw": "مساوی"}[outcome]
    cur.execute("UPDATE events SET status='finished', result=%s WHERE id=%s", (outcome, eid))
    cur.execute("SELECT id, user_id, bet_type, amount, odds FROM bets WHERE event_id=%s AND status='pending'", (eid,))
    bets = cur.fetchall()
    for bid, uid, btype, amount, odds in bets:
        if btype == outcome:
            prize = int(amount * odds)
            cur.execute("UPDATE users SET balance=balance+%s, total_won=total_won+%s WHERE user_id=%s",
                        (prize, prize - amount, uid))
            cur.execute("UPDATE bets SET status='won' WHERE id=%s", (bid,))
            try:
                bot.send_message(uid,
                    f"🎉 *شرط شما برنده شد!*\n🆚 {t1} vs {t2}\n✅ {result_label}\n"
                    f"💰 سود: `{(prize-amount)/100:.2f}` TRX\n🏆 دریافتی: `{prize/100:.2f}` TRX",
                    parse_mode='Markdown')
            except: pass
        else:
            cur.execute("UPDATE users SET total_lost=total_lost+%s WHERE user_id=%s", (amount, uid))
            cur.execute("UPDATE bets SET status='lost' WHERE id=%s", (bid,))
            try:
                bot.send_message(uid,
                    f"😔 *پیش‌بینی شما اشتباه بود!*\n🆚 {t1} vs {t2}\n❌ {result_label}\n"
                    f"💸 از دست رفته: `{amount/100:.2f}` TRX",
                    parse_mode='Markdown')
            except: pass
    conn.commit(); cur.close(); conn.close()
    bot.edit_message_text(f"✅ نتیجه ثبت شد: *{result_label}*",
                          call.message.chat.id, call.message.message_id, parse_mode='Markdown')

# ==================== background thread ====================
def background_thread():
    """
    هر دقیقه چک میکنه:
    1. بازی‌هایی که ساعتشون رسیده → بسته بشن و به ادمین اطلاع بده
    2. ۲ ساعت بعد از بازی → یادآوری نتیجه به ادمین
    """
    while True:
        time_module.sleep(30)
        try:
            now = now_tehran()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, team1, team2, match_hour, match_minute, notified
                FROM events WHERE status='active'
            """)
            events = cur.fetchall()

            for eid, t1, t2, hour, minute, notified in events:
                match_total_minutes = hour * 60 + minute
                now_total_minutes = now.hour * 60 + now.minute

                # بستن پیش‌بینی وقتی ساعت بازی رسید
                if now_total_minutes >= match_total_minutes:
                    cur.execute("UPDATE events SET status='locked' WHERE id=%s AND status='active'", (eid,))
                    conn.commit()
                    # اطلاع به کاربرها
                    cur.execute("SELECT DISTINCT user_id FROM bets WHERE event_id=%s AND status='pending'", (eid,))
                    bettors = cur.fetchall()
                    for (uid,) in bettors:
                        try:
                            bot.send_message(uid,
                                f"⏰ بازی *{t1}* vs *{t2}* شروع شد!\nشرط‌بندی بسته شد، منتظر نتیجه باشید.",
                                parse_mode='Markdown')
                        except: pass

                # یادآوری نتیجه به ادمین (۲ ساعت بعد از شروع بازی)
                if not notified:
                    remind_total = match_total_minutes + 120
                    remind_hour = (remind_total // 60) % 24
                    remind_minute = remind_total % 60
                    if now.hour == remind_hour and now.minute == remind_minute:
                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton("🏁 تعیین نتیجه", callback_data=f"setresult_{eid}"))
                        bot.send_message(ADMIN_ID,
                            f"⏰ بازی *{t1}* vs *{t2}* احتمالاً تمام شده!\nلطفاً نتیجه را ثبت کنید:",
                            parse_mode='Markdown', reply_markup=kb)
                        cur.execute("UPDATE events SET notified=TRUE WHERE id=%s", (eid,))
                        conn.commit()

            cur.close(); conn.close()
        except Exception as ex:
            print("Background error:", ex)

threading.Thread(target=background_thread, daemon=True).start()

# ==================== پیش‌بینی کاربر ====================
def user_betting(msg):
    ensure_user(msg.from_user)
    if not bot_active and msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "🔴 ربات در حال حاضر غیرفعال است.")
    if is_banned(msg.from_user.id):
        return bot.send_message(msg.chat.id, "🚫 حساب شما مسدود شده است.")
    kb = InlineKeyboardMarkup(row_width=1)
    for s in SPORTS:
        kb.add(InlineKeyboardButton(s, callback_data=f"usersport_{s}"))
    bot.send_message(msg.chat.id, "🏅 ورزش مورد نظر را انتخاب کنید:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("usersport_"))
def user_sport_selected(call):
    sport = call.data[10:]
    conn = get_db()
    cur = conn.cursor()
    # فقط پیش‌بینی‌های active نشون بده (locked یعنی شروع شده)
    cur.execute("""
        SELECT id, team1, team2, match_hour, match_minute
        FROM events WHERE status='active' AND sport=%s ORDER BY id DESC
    """, (sport,))
    events = cur.fetchall()
    cur.close(); conn.close()
    if not events:
        return bot.answer_callback_query(call.id, "❌ بازی فعالی یافت نشد.", show_alert=True)
    kb = InlineKeyboardMarkup(row_width=1)
    for e in events:
        kb.add(InlineKeyboardButton(
            f"{e[1]} vs {e[2]} | ⏰{e[3]:02d}:{e[4]:02d}",
            callback_data=f"userevent_{e[0]}"
        ))
    bot.edit_message_text(f"🏟 بازی‌های فعال {sport}:",
                          call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("userevent_"))
def user_event_selected(call):
    eid = int(call.data.split("_")[1])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT sport, team1, team2, odds1, odds2, odds_draw, match_hour, match_minute, status FROM events WHERE id=%s", (eid,))
    e = cur.fetchone()
    cur.close(); conn.close()
    if not e:
        return bot.answer_callback_query(call.id, "❌ رویداد یافت نشد.")
    sport, t1, t2, o1, o2, od, hour, minute, status = e
    if status != 'active':
        return bot.answer_callback_query(call.id, "❌ این بازی دیگر قابل شرط‌بندی نیست.", show_alert=True)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"🏆 برد {t1} | ضریب {o1}", callback_data=f"bettype_{eid}_1_{o1}"),
        InlineKeyboardButton(f"🏆 برد {t2} | ضریب {o2}", callback_data=f"bettype_{eid}_2_{o2}"),
    )
    if od:
        kb.add(InlineKeyboardButton(f"🤝 مساوی | ضریب {od}", callback_data=f"bettype_{eid}_draw_{od}"))
    bal = get_balance(call.from_user.id)
    bot.edit_message_text(
        f"🏟 *{t1}* vs *{t2}*\n🏅 {sport} | ⏰ {hour:02d}:{minute:02d} تهران\n\n"
        f"📈 {t1}: `{o1}` | {t2}: `{o2}`" + (f" | مساوی: `{od}`" if od else "") +
        f"\n\n💰 موجودی: `{bal/100:.2f}` TRX\n\nروی کدام شرط می‌بندید؟",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bettype_"))
def bet_type_selected(call):
    parts = call.data.split("_")
    eid = int(parts[1])
    btype = parts[2]
    odds = float(parts[3])
    # چک کن هنوز active باشه
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM events WHERE id=%s", (eid,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r or r[0] != 'active':
        return bot.answer_callback_query(call.id, "❌ این بازی بسته شده است.", show_alert=True)
    bal = get_balance(call.from_user.id)
    bot.answer_callback_query(call.id)
    cancel_next_step(call.message.chat.id)
    m = bot.send_message(call.message.chat.id,
        f"💰 مقدار شرط (TRX) را وارد کنید:\n*(موجودی: `{bal/100:.2f}` TRX)*", parse_mode='Markdown')
    bot.register_next_step_handler(m, place_bet_step, call.from_user.id, eid, btype, odds)

def place_bet_step(msg, uid, eid, btype, odds):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        amount_trx = float((msg.text or "").strip())
        if amount_trx <= 0:
            raise ValueError
        amount = int(amount_trx * 100)
    except:
        return bot.send_message(msg.chat.id, "❌ مقدار نامعتبر است.")
    # دوباره چک کن status
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM events WHERE id=%s", (eid,))
    r = cur.fetchone()
    if not r or r[0] != 'active':
        cur.close(); conn.close()
        return bot.send_message(msg.chat.id, "❌ این بازی بسته شده است.")
    bal = get_balance(uid)
    if amount > bal:
        cur.close(); conn.close()
        return bot.send_message(msg.chat.id, f"❌ موجودی کافی ندارید. موجودی: `{bal/100:.2f}` TRX", parse_mode='Markdown')
    cur.execute("UPDATE users SET balance=balance-%s WHERE user_id=%s", (amount, uid))
    cur.execute("INSERT INTO bets (user_id, event_id, bet_type, amount, odds) VALUES (%s,%s,%s,%s,%s)",
                (uid, eid, btype, amount, odds))
    conn.commit(); cur.close(); conn.close()
    prize = int(amount * odds)
    bot.send_message(msg.chat.id,
        f"✅ *پیش‌بینی شما با موفقیت ثبت شد!*\n\n"
        f"💰 مبلغ: `{amount_trx}` TRX | ⚖️ ضریب: `{odds}`\n"
        f"🏆 سود احتمالی: `{(prize-amount)/100:.2f}` TRX",
        parse_mode='Markdown')

# ==================== شرط‌های من ====================
def my_bets(msg):
    ensure_user(msg.from_user)
    uid = msg.from_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, e.team1, e.team2, b.bet_type, b.amount, b.odds, b.status
        FROM bets b JOIN events e ON b.event_id=e.id
        WHERE b.user_id=%s ORDER BY b.created_at DESC LIMIT 20
    """, (uid,))
    bets = cur.fetchall()
    cur.close(); conn.close()
    if not bets:
        return bot.send_message(msg.chat.id, "❌ شرطی ثبت نکرده‌اید.")
    sm = {"pending": "⏳", "won": "✅", "lost": "❌", "cancelled": "🚫"}
    txt = "📜 *شرط‌های شما:*\n\n"
    for b in bets:
        txt += f"{sm.get(b[6],'❓')} #{b[0]} | {b[1]} vs {b[2]}\n   {b[3]} | {b[4]/100:.2f} TRX | ضریب {b[5]}\n\n"
    bot.send_message(msg.chat.id, txt, parse_mode='Markdown')

# ==================== رتبه‌بندی ====================
def leaderboard(msg):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT first_name, username, balance FROM users ORDER BY balance DESC LIMIT 10")
    users = cur.fetchall()
    cur.close(); conn.close()
    txt = "🏆 *برترین کاربران:*\n\n"
    medals = ["🥇","🥈","🥉"]
    for i, u in enumerate(users):
        m = medals[i] if i < 3 else f"{i+1}."
        name = u[0] or u[1] or "ناشناس"
        txt += f"{m} {name} | `{u[2]/100:.2f}` TRX\n"
    bot.send_message(msg.chat.id, txt, parse_mode='Markdown')

# ==================== آمار کلی ====================
def stats(msg):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(total_deposit),0), COALESCE(SUM(total_won),0), COALESCE(SUM(total_lost),0) FROM users")
    count, deposits, won, lost = cur.fetchone()
    cur.close(); conn.close()
    net = lost - won
    bot.send_message(msg.chat.id,
        f"📊 *آمار کلی:*\n\n👥 کاربران: `{count}`\n📥 مجموع واریز: `{deposits/100:.2f}` TRX\n"
        f"🏆 برد کاربران: `{won/100:.2f}` TRX\n💸 ضرر کاربران: `{lost/100:.2f}` TRX\n"
        f"📈 برآیند ربات: `{net/100:.2f}` TRX", parse_mode='Markdown')

# ==================== لیست کاربران ====================
def list_users(msg):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, balance, total_won, total_lost, joined_at FROM users ORDER BY joined_at DESC")
    users = cur.fetchall()
    cur.close(); conn.close()
    if not users:
        return bot.send_message(msg.chat.id, "❌ کاربری وجود ندارد.")
    CHUNK = 15
    for i in range(0, len(users), CHUNK):
        chunk = users[i:i+CHUNK]
        txt = f"👥 *کاربران ({i+1}-{i+len(chunk)}):*\n\n"
        for u in chunk:
            uid2, uname, fname, bal, won, lost, joined = u
            net = won - lost
            ns = "+" if net >= 0 else ""
            wt = won + lost
            wp = f"{(won/wt*100):.0f}%" if wt > 0 else "0%"
            txt += (f"👤 `{uid2}` | @{uname or '—'} | {fname or '—'}\n"
                    f"   💰 {bal/100:.2f} TRX | 🏆 {wp} | {ns}{net/100:.2f} TRX\n"
                    f"   📅 {joined.strftime('%Y-%m-%d') if joined else '—'}\n\n")
        bot.send_message(msg.chat.id, txt, parse_mode='Markdown')

# ==================== سرچ کاربر ====================
def search_user_prompt(msg):
    m = bot.send_message(msg.chat.id, "🔍 آیدی عددی کاربر:")
    bot.register_next_step_handler(m, search_user_step)

def search_user_step(msg):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        uid = int((msg.text or "").strip())
    except:
        return bot.send_message(msg.chat.id, "❌ آیدی نامعتبر.")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, balance, total_deposit, total_won, total_lost, is_banned, joined_at FROM users WHERE user_id=%s", (uid,))
    u = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM bets WHERE user_id=%s AND status='won'", (uid,))
    wins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bets WHERE user_id=%s", (uid,))
    total_bets = cur.fetchone()[0]
    cur.close(); conn.close()
    if not u:
        return bot.send_message(msg.chat.id, "❌ کاربر یافت نشد.")
    uid2, uname, fname, bal, deposit, won, lost, banned, joined = u
    net = won - lost
    ns = "+" if net >= 0 else ""
    wp = f"{(wins/total_bets*100):.0f}%" if total_bets > 0 else "0%"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💰 افزایش/کاهش موجودی", callback_data=f"editbal_{uid2}"))
    bot.send_message(msg.chat.id,
        f"🔍 *اطلاعات کاربر:*\n\n🆔 `{uid2}`\n👤 {fname or '—'} | @{uname or '—'}\n"
        f"💰 موجودی: `{bal/100:.2f}` TRX\n📥 واریز کل: `{deposit/100:.2f}` TRX\n"
        f"🏆 برد: `{won/100:.2f}` TRX | ضرر: `{lost/100:.2f}` TRX\n"
        f"📈 برآیند: `{ns}{abs(net)/100:.2f}` TRX\n🎯 درصد برد: {wp} ({wins}/{total_bets})\n"
        f"🚫 بن: {'بله' if banned else 'خیر'}\n📅 {joined.strftime('%Y-%m-%d') if joined else '—'}",
        parse_mode='Markdown', reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("editbal_"))
def editbal_prompt(call):
    uid = int(call.data.split("_")[1])
    cancel_next_step(call.message.chat.id)
    m = bot.send_message(call.message.chat.id,
        f"💰 تغییر موجودی `{uid}` (مقدار به TRX):\n`+5` برای افزایش | `5` برای کاهش", parse_mode='Markdown')
    bot.register_next_step_handler(m, editbal_step, uid)

def editbal_step(msg, uid):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    text = (msg.text or "").strip()
    try:
        if text.startswith("+"):
            amount = int(float(text[1:]) * 100)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (amount, uid))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, f"✅ `{amount/100:.2f}` TRX افزوده شد.", parse_mode='Markdown')
        else:
            amount = int(float(text) * 100)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET balance=GREATEST(0,balance-%s) WHERE user_id=%s", (amount, uid))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, f"✅ `{amount/100:.2f}` TRX کسر شد.", parse_mode='Markdown')
    except:
        bot.send_message(msg.chat.id, "❌ مقدار نامعتبر.")

# ==================== بن/آن‌بن ====================
def ban_prompt(msg):
    m = bot.send_message(msg.chat.id, "🚫 آیدی عددی کاربر:")
    bot.register_next_step_handler(m, ban_step, True)

def unban_prompt(msg):
    m = bot.send_message(msg.chat.id, "✅ آیدی عددی کاربر:")
    bot.register_next_step_handler(m, ban_step, False)

def ban_step(msg, do_ban):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    try:
        uid = int((msg.text or "").strip())
    except:
        return bot.send_message(msg.chat.id, "❌ آیدی نامعتبر.")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_banned=%s WHERE user_id=%s", (do_ban, uid))
    conn.commit(); cur.close(); conn.close()
    action = "بن" if do_ban else "آن‌بن"
    bot.send_message(msg.chat.id, f"✅ کاربر `{uid}` {action} شد.", parse_mode='Markdown')
    if do_ban:
        try:
            bot.send_message(uid, "🚫 حساب شما مسدود شده است.")
        except: pass

# ==================== خاموش/روشن ====================
def bot_off(msg):
    global bot_active
    bot_active = False
    bot.send_message(msg.chat.id, "🔴 ربات برای کاربران خاموش شد.", reply_markup=admin_menu())

def bot_on(msg):
    global bot_active
    bot_active = True
    bot.send_message(msg.chat.id, "🟢 ربات برای کاربران روشن شد.", reply_markup=admin_menu())

# ==================== پخش پیام ====================
def broadcast_prompt(msg):
    m = bot.send_message(msg.chat.id, "📢 متن پیام را ارسال کنید:")
    bot.register_next_step_handler(m, broadcast_confirm_step)

def broadcast_confirm_step(msg):
    if is_menu_button(msg.text or ""):
        return dispatch_menu(msg)
    text = msg.text
    bot._broadcast_pending = text
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ ارسال", callback_data="broadcast_yes"),
        InlineKeyboardButton("❌ لغو", callback_data="broadcast_no")
    )
    bot.send_message(msg.chat.id,
        f"📢 *پیش‌نمایش:*\n\n{text}\n\n✅ مطمئن هستید؟",
        parse_mode='Markdown', reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "broadcast_yes")
def broadcast_send(call):
    text = getattr(bot, '_broadcast_pending', None)
    if not text:
        return bot.answer_callback_query(call.id, "❌ متنی یافت نشد.")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close(); conn.close()
    success = 0
    for u in users:
        try:
            bot.send_message(u[0], text)
            success += 1
        except: pass
    bot.edit_message_text(f"✅ پیام به {success} کاربر ارسال شد.",
                          call.message.chat.id, call.message.message_id)
    bot._broadcast_pending = None

@bot.callback_query_handler(func=lambda c: c.data == "broadcast_no")
def broadcast_cancel(call):
    bot.edit_message_text("❌ ارسال لغو شد.", call.message.chat.id, call.message.message_id)
    bot._broadcast_pending = None

# ==================== منوی اصلی ادمین ====================
def back_to_admin(msg):
    bot.send_message(msg.chat.id, "👑 پنل مدیریت", reply_markup=admin_menu())

# ==================== فالبک ====================
@bot.message_handler(func=lambda m: True)
def fallback(msg):
    ensure_user(msg.from_user)
    if not bot_active and msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "🔴 ربات در حال حاضر غیرفعال است.")
    if is_banned(msg.from_user.id):
        return bot.send_message(msg.chat.id, "🚫 حساب شما مسدود شده است.")
    if msg.from_user.id == ADMIN_ID:
        bot.send_message(msg.chat.id, "از دکمه‌های منو استفاده کنید.", reply_markup=admin_menu())
    else:
        bot.send_message(msg.chat.id, "از دکمه‌های منو استفاده کنید.", reply_markup=main_menu())

# ==================== اجرا ====================
print("🚀 ربات پیش‌بینی شروع شد...")
try:
    bot.remove_webhook()
    time_module.sleep(2)
except: pass

try:
    bot.send_message(ADMIN_ID, "🔄 *ربات آپدیت و راه‌اندازی شد!*", parse_mode='Markdown')
except: pass

bot.infinity_polling(skip_pending=True, none_stop=True)
