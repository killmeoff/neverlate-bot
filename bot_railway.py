import asyncio
import sqlite3
import logging
import os
from datetime import datetime
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.utils.executor import start_webhook

# === ТВОИ ДАННЫЕ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOOMONEY_WALLET = os.environ.get("YOOMONEY_WALLET")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "").split(",") if id]
SHOP_NAME = "NEVERLATE"

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO)

# === ИНИЦИАЛИЗАЦИЯ ===
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
app = Flask(__name__)

# === ФУНКЦИИ ДЛЯ РАБОТЫ С АДМИНАМИ ===
def is_admin(user_id):
    return user_id in ADMIN_IDS

# === БАЗА ДАННЫХ (УПРОЩЕННАЯ) ===
def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            file_url TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            product_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных готова")

init_db()

# === КЛАВИАТУРЫ ===
def get_main_keyboard(is_admin_user=False):
    keyboard = [
        [KeyboardButton(text="🛍 Каталог")],
        [KeyboardButton(text="📦 Мои заказы")]
    ]
    if is_admin_user:
        keyboard.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton(text="➕ Добавить товар")],
        [KeyboardButton(text="📋 Все заказы")],
        [KeyboardButton(text="🔙 На главную")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    keyboard = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_products_inline():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products")
    products = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for p in products:
        keyboard.append([InlineKeyboardButton(
            text=f"{p[1]} - {p[2]} руб.",
            callback_data=f"prod_{p[0]}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_product_actions(product_id):
    keyboard = [
        [InlineKeyboardButton(text="✅ Купить", callback_data=f"buy_{product_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# === КОМАНДА СТАРТ ===
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    await message.answer(
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃   🎮 NEVERLATE   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        "Йо, бро 👋\n"
        "Хочешь конфиги? Тогда ты по адресу.\n\n"
        "👉 Жми **🛍 Каталог** и выбирай!",
        reply_markup=get_main_keyboard(is_admin(message.from_user.id))
    )

# === КАТАЛОГ ===
@dp.message_handler(lambda msg: msg.text == "🛍 Каталог")
async def catalog(message: Message):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await message.answer("📭 Товаров пока нет")
        return
    
    await message.answer("🎮 Выберите товар:", reply_markup=get_products_inline())

# === МОИ ЗАКАЗЫ ===
@dp.message_handler(lambda msg: msg.text == "📦 Мои заказы")
async def my_orders(message: Message):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.id, p.name, o.amount, o.status, o.created_at 
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.user_id = ?
        ORDER BY o.created_at DESC
    ''', (message.from_user.id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await message.answer("📭 У вас пока нет заказов")
        return
    
    text = "📦 Ваши заказы:\n\n"
    for o in orders:
        status = "✅" if o[3] == "paid" else "⏳"
        text += f"{status} Заказ #{o[0]}: {o[1]} - {o[2]} руб.\n"
    
    await message.answer(text)

# === АДМИНКА ===
@dp.message_handler(lambda msg: msg.text == "⚙️ Админка")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа")
        return
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())

# === ДОБАВЛЕНИЕ ТОВАРА ===
product_data = {}

@dp.message_handler(lambda msg: msg.text == "➕ Добавить товар")
async def add_product_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    product_data[message.from_user.id] = {'step': 'name'}
    await message.answer("Введите название товара:", reply_markup=get_cancel_keyboard())

@dp.message_handler(lambda msg: msg.from_user.id in product_data)
async def add_product_process(message: Message):
    user_id = message.from_user.id
    if message.text == "❌ Отмена":
        del product_data[user_id]
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())
        return
    
    data = product_data[user_id]
    
    if data['step'] == 'name':
        data['name'] = message.text
        data['step'] = 'desc'
        await message.answer("Введите описание:")
    
    elif data['step'] == 'desc':
        data['desc'] = message.text
        data['step'] = 'price'
        await message.answer("Введите цену (только цифры):")
    
    elif data['step'] == 'price':
        try:
            price = int(message.text)
            if price <= 0:
                await message.answer("Цена должна быть больше 0!")
                return
            data['price'] = price
            data['step'] = 'file'
            await message.answer("Введите ссылку на файл:")
        except:
            await message.answer("Введите число!")
    
    elif data['step'] == 'file':
        data['file_url'] = message.text
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO products (name, description, price, file_url) VALUES (?, ?, ?, ?)",
            (data['name'], data['desc'], data['price'], data['file_url'])
        )
        conn.commit()
        conn.close()
        
        del product_data[user_id]
        await message.answer("✅ Товар добавлен!", reply_markup=get_admin_keyboard())

# === ВСЕ ЗАКАЗЫ (ДЛЯ АДМИНА) ===
@dp.message_handler(lambda msg: msg.text == "📋 Все заказы")
async def all_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.id, u.username, p.name, o.amount, o.status
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        JOIN products p ON o.product_id = p.id
        ORDER BY o.id DESC
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await message.answer("📭 Заказов нет")
        return
    
    text = "📊 Заказы:\n\n"
    for o in orders:
        status = "✅" if o[4] == "paid" else "⏳"
        text += f"{status} Заказ #{o[0]}: @{o[1] or 'anon'} - {o[2]} - {o[3]} руб.\n"
    
    await message.answer(text)

# === НА ГЛАВНУЮ ===
@dp.message_handler(lambda msg: msg.text == "🔙 На главную")
async def back_main(message: Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))

# === ТОВАР ===
@dp.callback_query_handler(lambda c: c.data.startswith('prod_'))
async def show_product(callback: CallbackQuery):
    prod_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price FROM products WHERE id = ?", (prod_id,))
    prod = cursor.fetchone()
    conn.close()
    
    if not prod:
        await callback.answer("Товар не найден")
        return
    
    text = f"🎮 {prod[0]}\n\n📝 {prod[1]}\n\n💰 {prod[2]} руб."
    
    await callback.message.edit_text(text, reply_markup=get_product_actions(prod_id))
    await callback.answer()

# === ПОКУПКА ===
@dp.callback_query_handler(lambda c: c.data.startswith('buy_'))
async def buy_product(callback: CallbackQuery):
    prod_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, price FROM products WHERE id = ?", (prod_id,))
    prod = cursor.fetchone()
    
    if not prod:
        await callback.answer("Товар не найден")
        conn.close()
        return
    
    # Создаем заказ
    cursor.execute(
        "INSERT INTO orders (user_id, username, product_id, amount, created_at) VALUES (?, ?, ?, ?, ?)",
        (callback.from_user.id, callback.from_user.username, prod_id, prod[1], str(datetime.now()))
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    pay_url = f"https://yoomoney.ru/to/{YOOMONEY_WALLET}?amount={prod[1]}"
    
    text = (
        f"✅ Заказ #{order_id} создан!\n\n"
        f"Товар: {prod[0]}\n"
        f"Сумма: {prod[1]} руб.\n\n"
        f"💳 Для оплаты нажмите кнопку ниже.\n"
        f"После оплаты администратор подтвердит заказ."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{order_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# === ПОДТВЕРЖДЕНИЕ ОПЛАТЫ (ПРОСТОЕ) ===
@dp.callback_query_handler(lambda c: c.data.startswith('paid_'))
async def payment_notify(callback: CallbackQuery):
    order_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    # Получаем информацию о заказе
    cursor.execute('''
        SELECT o.user_id, o.username, p.name, o.amount
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        conn.close()
        return
    
    user_id, username, product_name, amount = order
    
    # Уведомляем всех админов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 **НОВЫЙ ПЛАТЕЖ**\n\n"
                f"Заказ #{order_id}\n"
                f"Пользователь: @{username or 'нет'}\n"
                f"Товар: {product_name}\n"
                f"Сумма: {amount} руб.\n\n"
                f"Проверьте поступление денег и подтвердите заказ.",
                parse_mode="Markdown"
            )
        except:
            pass
    
    await callback.answer("✅ Уведомление отправлено администратору", show_alert=True)
    await callback.message.edit_text(
        "✅ Запрос отправлен администратору. Ожидайте подтверждения."
    )
    conn.close()

# === ЗАПУСК ===
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    
    async def on_startup(dispatcher):
        railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'neverlate-bot-production.up.railway.app')
        webhook_url = f"https://{railway_domain}/webhook"
        await bot.set_webhook(webhook_url)
        print(f"✅ Бот запущен!")
    
    start_webhook(
        dispatcher=dp,
        webhook_path="/webhook",
        on_startup=on_startup,
        host="0.0.0.0",
        port=PORT
    )
