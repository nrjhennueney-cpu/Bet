import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import psycopg2
import psycopg2.extras
import os
import sys

# گرفتن تنظیمات از Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ خطا: BOT_TOKEN تنظیم نشده است")
    sys.exit(1)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ خطا: DATABASE_URL تنظیم نشده است (از Neon)")
    sys.exit(1)

USE_WEBHOOK = os.getenv("USE_WEBHOOK", "False").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))

bot = telebot.TeleBot(TOKEN)

# اتصال به دیتابیس Neon (PostgreSQL)
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_start INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

init_db()

def is_first_start(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT first_start FROM users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    
    if result is None:
        # کاربر جدید
        cur.execute("INSERT INTO users (user_id, first_start) VALUES (%s, 0)", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    else:
        first = result[0]
        if first == 1:
            # بعد از نمایش، مقدار را 0 کن
            cur.execute("UPDATE users SET first_start = 0 WHERE user_id = %s", (user_id,))
            conn.commit()
        cur.close()
        conn.close()
        return first == 1

def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = KeyboardButton("⚽ پیش بینی های روز")
    btn2 = KeyboardButton("💰 موجودی")
    keyboard.add(btn1, btn2)
    return keyboard

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if is_first_start(user_id):
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

@bot.message_handler(func=lambda message: message.text == "⚽ پیش بینی های روز")
def daily_predictions(message):
    bot.reply_to(message, "📅 امروز بازی‌های زیر رو داریم:\n(اینجا لیست بازی‌ها قرار می‌گیرد)")

@bot.message_handler(func=lambda message: message.text == "💰 موجودی")
def show_balance(message):
    bot.reply_to(message, "💰 موجودی شما: 0 تومان\n(سیستم شارژ و تراکنش در حال توسعه)")

@bot.message_handler(func=lambda message: True)
def unknown(message):
    bot.reply_to(message, "❓ لطفاً از دکمه‌های منوی اصلی استفاده کنید.")

# ========== Webhook ==========
def setup_webhook():
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook: {webhook_url}")

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
        app.run(host='0.0.0.0', port=PORT)
else:
    if __name__ == "__main__":
        bot.remove_webhook()
        print("🤖 حالت Polling (محلی)")
        bot.infinity_polling(skip_pending=True)
