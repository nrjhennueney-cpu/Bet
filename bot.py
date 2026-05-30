import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
import os
from datetime import datetime, timedelta
import threading
import time

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

    # حذف جدول قدیمی و ایجاد جدول جدید با ستون‌های کامل
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT DEFAULT NULL,
            first_name TEXT DEFAULT NULL,
            balance INTEGER DEFAULT 100000,
            total_deposit INTEGER DEFAULT 0,
            total_win INTEGER DEFAULT 0,
            total_loss INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # اضافه کردن ستون‌های缺失 اگر وجود ندارند
    try:
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT")
    except:
        pass

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

def register_user(user_id, username, first_name):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, balance) 
            VALUES (%s, %s, %s, 100000) 
            ON CONFLICT (user_id) DO UPDATE 
            SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
        """, (user_id, username, first_name))
        conn.commit()
    except Exception as e:
        print(f"Error registering user: {e}")
        # اگر ستون‌ها وجود ندارند، فقط user_id را ثبت کن
        try:
            cur.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
            conn.commit()
        except:
            pass
    finally:
        cur.close()
        conn.close()

# ==================== شروع بات ====================
@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "👑 به پنل ادمین خوش آمدید!", reply_markup=admin_menu())
    else:
        bot.reply_to(message, f"🎉 به بات شرط‌بندی خوش آمدید {message.from_user.first_name}!\n\nموجودی اولیه: 100,000 تومان", reply_markup=main_menu())

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
        cur.execute("SELECT COALESCE(SUM(total_deposit),0) FROM users")
        total_deposit = cur.fetchone()[0]
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
    bot.edit_message_text(f"🏷 عنوان پیش‌بینی برای **{sport}** را وارد کنید:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, process_event_title, sport)

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
        bot.register_next_step_handler(message, process_odds_draw, sport, title, home, away, oh)

def process_odds_away(message, sport, title, home, away, oh, od):
    try:
        oa = float(message.text)
        msg = bot.reply_to(message, "⏰ ساعت شروع بازی (به وقت تهران):\nمثال: 19 یا 5")
        bot.register_next_step_handler(msg, process_start_time, sport, title, home, away, oh, od, oa)
    except:
        bot.reply_to(message, "❌ عدد وارد کنید!")
        bot.register_next_step_handler(message, process_odds_away, sport, title, home, away, oh, od)

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

        bot.reply_to(message, f"✅ پیش‌بینی **{title}** با موفقیت ثبت شد!", reply_markup=admin_menu())
        
        # یادآوری خودکار بعد از ۲ ساعت
        threading.Timer(7200, remind_admin_result, args=[message.chat.id, title, home, away]).start()

    except Exception as e:
        bot.reply_to(message, f"❌ خطا در ثبت زمان: {e}")

def remind_admin_result(chat_id, title, home, away):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"تعیین نتیجه: {title}", callback_data=f"result_{title}"))
    bot.send_message(chat_id, f"⏰ زمان تعیین نتیجه:\n{title}\n{home} vs {away}", reply_markup=kb)

# ==================== تعیین نتیجه ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("result_"))
def set_result(call):
    title = call.data.split("_", 1)[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, home_team, away_team FROM events WHERE title = %s AND status = 'active'", (title,))
    event = cur.fetchone()
    cur.close()
    conn.close()
    
    if not event:
        return bot.answer_callback_query(call.id, "رویداد یافت نشد")
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🏆 برد {event[1]}", callback_data=f"setres_{event[0]}_home"))
    kb.add(InlineKeyboardButton("⚖ تساوی", callback_data=f"setres_{event[0]}_draw"))
    kb.add(InlineKeyboardButton(f"🏆 برد {event[2]}", callback_data=f"setres_{event[0]}_away"))
    
    bot.edit_message_text(f"نتیجه {title} را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("setres_"))
def save_result(call):
    parts = call.data.split("_")
    event_id = parts[1]
    res_type = parts[2]
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT home_team, away_team, odds_home, odds_draw, odds_away FROM events WHERE id = %s", (event_id,))
    event = cur.fetchone()
    
    result_text = event[0] if res_type == "home" else "تساوی" if res_type == "draw" else event[1]

    cur.execute("UPDATE events SET status='finished', result=%s WHERE id=%s", (result_text, event_id))
    
    # پرداخت شرط‌ها
    cur.execute("SELECT id, user_id, amount, odds, bet_type FROM bets WHERE event_id=%s AND status='active'", (event_id,))
    bets = cur.fetchall()

    for bet in bets:
        bet_id, user_id, amount, user_odds, bet_type = bet
        
        if bet_type == res_type:
            win_amount = int(amount * user_odds)
            cur.execute("UPDATE users SET balance = balance + %s, total_win = total_win + %s WHERE user_id = %s", 
                       (win_amount, win_amount, user_id))
            try:
                bot.send_message(user_id, f"🎉 **تبریک!** شرط شما برنده شد!\nمبلغ برنده شده: `{win_amount:,}` تومان", parse_mode='Markdown')
            except:
                pass
        else:
            cur.execute("UPDATE users SET total_loss = total_loss + %s WHERE user_id = %s", (amount, user_id))
            try:
                bot.send_message(user_id, f"❌ متأسفانه شرط شما باخت.\nنتیجه: {result_text}\nمبلغ کسر شده: `{amount:,}` تومان", parse_mode='Markdown')
            except:
                pass

        cur.execute("UPDATE bets SET status='settled' WHERE id=%s", (bet_id,))

    conn.commit()
    cur.close()
    conn.close()
    
    bot.answer_callback_query(call.id, "نتیجه ثبت و تسویه شد ✅")
    bot.edit_message_text(f"✅ نتیجه {result_text} ثبت شد.", call.message.chat.id, call.message.message_id)

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
        if amount <= 0:
            raise ValueError
        
        text = f"""💳 **درخواست واریز**

مبلغ: `{amount}` TRX

📍 آدرس واریز:
`TQxhiwDREd8rxZuyDWx3auxcpzjSi1mAJG`

✅ بعد از واریز، رسید (عکس) را ارسال کنید."""

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ لغو", callback_data=f"cancel_dep_{message.from_user.id}"))
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=kb)
        bot.register_next_step_handler(message, process_deposit_receipt, amount)
        
    except:
        bot.reply_to(message, "❌ لطفاً عدد معتبر وارد کنید!")

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
    parts = call.data.split("_")
    user_id = int(parts[2])
    amount = float(parts[3])
    amount_toman = int(amount * 35000)

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

@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_dep_"))
def cancel_deposit(call):
    bot.edit_message_text("❌ درخواست واریز لغو شد.", call.message.chat.id, call.message.message_id)

# ==================== برداشت ====================
@bot.message_handler(func=lambda m: m.text == "➖ برداشت موجودی")
def withdraw_request(message):
    balance = get_balance(message.from_user.id)
    if balance < 1050000:
        return bot.reply_to(message, "❌ حداقل موجودی برای برداشت ۳۰ ترون (حدود ۱٫۰۵ میلیون تومان) است.")
    
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
    parts = call.data.split("_")
    user_id = int(parts[1])
    amount = parts[2]
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = 0 WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    bot.send_message(user_id, f"✅ مبلغ `{amount}` ترون به والت شما واریز شد.\nموجودی شما صفر شد.", parse_mode='Markdown')
    bot.edit_message_text("✅ برداشت ثبت شد.", call.message.chat.id, call.message.message_id)

# ==================== شرط‌بندی کاربر ====================
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
    parts = call.data.split("_")
    event_id = parts[1]
    bet_type = parts[2]
    
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
            return bot.reply_to(message, "❌ مبلغ نامعتبر (حداقل ۱۰,۰۰۰ تومان) یا موجودی کافی نیست.")

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

        bot.reply_to(message, f"✅ **پیش‌بینی شما با موفقیت ثبت شد!**\nمبلغ: {amount:,} تومان\nضریب: {odd}", parse_mode='Markdown')
        
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
        return bot.reply_to(message, "📭 شما هنوز شرطی ثبت نکرده‌اید.")

    txt = "📜 **شرط‌های اخیر شما:**\n\n"
    for bet in bets:
        bet_type_text = {"home": "برد میزبان", "draw": "تساوی", "away": "برد مهمان"}.get(bet[2], bet[2])
        status_text = "✅ فعال" if bet[5] == "active" else "🔒 تسویه شده"
        txt += f"#{bet[0]} | {bet[1]}\n   {bet_type_text} | {bet[3]:,} تومان | ضریب {bet[4]} | {status_text}\n   ⏰ {bet[6].strftime('%Y-%m-%d %H:%M')}\n\n"
    
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
        ORDER BY (total_win - total_loss) DESC
        LIMIT 10
    """)
    users = cur.fetchall()
    cur.close()
    conn.close()

    txt = "🏆 **رتبه‌بندی برترین‌ها (سود خالص):**\n\n"
    for i, u in enumerate(users, 1):
        net = u[2] - u[3]
        name = u[1] or u[0] or f"کاربر {i}"
        txt += f"{i}. {name} | سود: {net:,} تومان | موجودی: {u[4]:,}\n"
    
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
    for u in users:
        win_rate = round((u[4] / (u[4] + u[5] + 1) * 100), 1) if u[4] + u[5] > 0 else 0
        txt += f"`{u[0]}` | @{u[1] or '—'} | {u[3]:,} | برد: {u[4]:,} | ضرر: {u[5]:,} | {win_rate}%\n"

    for i in range(0, len(txt), 3000):
        bot.reply_to(message, txt[i:i+3000], parse_mode='Markdown')

# ==================== پخش پیام همگانی ====================
def broadcast_confirm(message):
    if message.text in ["لغو", "/cancel", "cancel"]:
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

# ==================== سایر دستورات ادمین ====================
@bot.message_handler(commands=['ban'], func=lambda m: m.from_user.id == ADMIN_ID)
def ban_user(message):
    try:
        user_id = int(message.text.split()[1])
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_banned = TRUE WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        bot.reply_to(message, f"✅ کاربر `{user_id}` بن شد.")
        bot.send_message(user_id, "❌ شما توسط ادمین بن شدید!")
    except:
        bot.reply_to(message, "❌ دستور اشتباه: /ban USER_ID")

@bot.message_handler(commands=['unban'], func=lambda m: m.from_user.id == ADMIN_ID)
def unban_user(message):
    try:
        user_id = int(message.text.split()[1])
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_banned = FALSE WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        bot.reply_to(message, f"✅ کاربر `{user_id}` آنبن شد.")
        bot.send_message(user_id, "✅ شما توسط ادمین آنبن شدید!")
    except:
        bot.reply_to(message, "❌ دستور اشتباه: /unban USER_ID")

@bot.message_handler(commands=['search'], func=lambda m: m.from_user.id == ADMIN_ID)
def search_user(message):
    try:
        user_id = int(message.text.split()[1])
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name, balance, total_win, total_loss, is_banned FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            return bot.reply_to(message, "❌ کاربر یافت نشد.")

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💰 تغییر موجودی", callback_data=f"editbal_{user_id}"))

        status = "🚫 بن" if user[6] else "✅ فعال"
        bot.reply_to(message, f"""👤 **اطلاعات کاربر**

🆔 آیدی: `{user[0]}`
👤 نام کاربری: @{user[1] or '—'}
📛 نام: {user[2] or '—'}
💰 موجودی: `{user[3]:,}`
🏆 کل برد: `{user[4]:,}`
📉 کل ضرر: `{user[5]:,}`
📊 وضعیت: {status}
""", parse_mode='Markdown', reply_markup=kb)
    except:
        bot.reply_to(message, "❌ /search USER_ID")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editbal_"))
def edit_balance(call):
    user_id = int(call.data.split("_")[1])
    msg = bot.send_message(call.message.chat.id, "مبلغ را وارد کنید:\n+10000 برای افزایش\n-5000 برای کاهش")
    bot.register_next_step_handler(msg, process_balance_edit, user_id)

def process_balance_edit(message, user_id):
    try:
        amount = int(message.text)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cur.close()
        conn.close()
        bot.reply_to(message, f"✅ موجودی کاربر `{user_id}` به اندازه {amount:,} تومان تغییر کرد.")
    except:
        bot.reply_to(message, "❌ عدد وارد کنید!")

# ==================== منوی اصلی ====================
@bot.message_handler(func=lambda m: m.text == "🔙 منوی اصلی")
def back_to_main(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "🔙 بازگشت به منوی اصلی", reply_markup=admin_menu())
    else:
        bot.reply_to(message, "🔙 بازگشت به منوی اصلی", reply_markup=main_menu())

# ==================== هندلر ناشناخته ====================
@bot.message_handler(func=lambda m: True)
def unknown(message):
    register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "از منوی ادمین استفاده کنید.", reply_markup=admin_menu())
    else:
        bot.reply_to(message, "لطفاً از دکمه‌های منو استفاده کنید.", reply_markup=main_menu())

# ==================== استارت بات ====================
if __name__ == "__main__":
    print("🚀 بات شرط‌بندی شروع شد...")
    print(f"👑 ادمین آیدی: {ADMIN_ID}")
    
    # پاک کردن webhook و آپدیت‌های قبلی
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    
    # شروع polling با تنظیمات مناسب
    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True
            )
        except Exception as e:
            print(f"❌ خطا: {e}")
            time.sleep(5)
