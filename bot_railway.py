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
def save_admins():
    with open('admins.txt', 'w') as f:
        for admin_id in ADMIN_IDS:
            f.write(str(admin_id) + '\n')

def load_admins():
    global ADMIN_IDS
    try:
        with open('admins.txt', 'r') as f:
            ADMIN_IDS = [int(line.strip()) for line in f.readlines()]
    except FileNotFoundError:
        save_admins()

def add_admin(user_id):
    if user_id not in ADMIN_IDS:
        ADMIN_IDS.append(user_id)
        save_admins()
        return True
    return False

def remove_admin(user_id):
    if user_id in ADMIN_IDS and user_id != ADMIN_IDS[0]:
        ADMIN_IDS.remove(user_id)
        save_admins()
        return True
    return False

def is_admin(user_id):
    return user_id in ADMIN_IDS

load_admins()

# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            registered_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            file_url TEXT,
            photo_id TEXT,
            created_at TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            label TEXT UNIQUE,
            created_at TEXT,
            paid_at TEXT,
            admin_notified INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS texts (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    
    # Тексты по умолчанию
    default_texts = {
        'welcome': (
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "┃   🎮 NEVERLATE   ┃\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            "Йо, бро 👋\n"
            "Хочешь конфиги, которые реально вывозят?\n"
            "Тогда ты там где надо.\n\n"
            "▸ Разные читы\n"
            "▸ Оптимизация\n"
            "▸ Никаких читов — только настройки\n"
            "▸ Обновляю под каждый патч\n\n"
            "📌 **Как забрать:**\n"
            "👉 Жми **«🛍 Каталог»**\n"
            "👉 Выбирай свой софт\n"
            "👉 Плати через ЮMoney\n"
            "👉 Нажми «✅ Я оплатил» и жди подтверждения\n\n"
            "📸 **Отзывы тут:** @reviewsneverlate"
        ),
        'payment': (
            "╭─────────────────────────────╮\n"
            "│       🎮 NEVERLATE          │\n"
            "│       ✅ ЗАКАЗ #{order_id}   │\n"
            "├─────────────────────────────┤\n"
            "│  📦 **Товар:** {product_name}\n"
            "│  💰 **Сумма:** {price} руб.\n"
            "├─────────────────────────────┤\n"
            "│  💳 **Оплата:**\n"
            "│  1. Жми «💳 Оплатить»\n"
            "│  2. Переведи деньги\n"
            "│  3. Вернись и нажми «✅ Я оплатил»\n"
            "├─────────────────────────────┤\n"
            "│  ⏳ После оплаты админ проверит\n"
            "│  и вышлет конфиг вручную\n"
            "╰─────────────────────────────╯"
        ),
        'success': (
            "╭─────────────────────────────╮\n"
            "│       ✅ ОПЛАЧЕНО!          │\n"
            "├─────────────────────────────┤\n"
            "│  🔥 Конфиг твой!\n"
            "│  Ссылка: {file_url}\n"
            "├─────────────────────────────┤\n"
            "│  📸 **Оставь отзыв:**\n"
            "│  👉 Напиши @inlezz\n"
            "╰─────────────────────────────╯"
        ),
        'cancel': (
            "╭─────────────────────────────╮\n"
            "│       ❌ ЗАКАЗ ОТМЕНЕН      │\n"
            "├─────────────────────────────┤\n"
            "│  Заказ #{order_id}\n"
            "│  Товар: {product_name}\n"
            "│  Сумма: {price} руб.\n"
            "├─────────────────────────────┤\n"
            "│  Платёж не найден.\n"
            "│  Если вы оплатили, свяжитесь с @inlezz\n"
            "╰─────────────────────────────╯"
        ),
        'about': (
            "╔════════════════════════════╗\n"
            "║      🎮 NEVERLATE         ║\n"
            "╠════════════════════════════╣\n"
            "║  Мы — Neverlate.\n"
            "║  Работаем честно и с душой 💯\n"
            "║                            \n"
            "║  📊 **Наша статистика:**\n"
            "║  ├─ ✅ Заказов выполнено: {paid_orders}/{total_orders}\n"
            "║  ├─ 👥 Довольных клиентов: {total_customers}\n"
            "║  ╰─ 💰 Продано на: {total_sales} руб.\n"
            "║                            \n"
            "║  🔥 Поможем тебе:\n"
            "║  • с настройкой конфигов\n"
            "║  • с выбором софта\n"
            "║  • с любыми вопросами\n"
            "║                            \n"
            "║  📬 Есть вопросы?\n"
            "║  👇 Жми на кнопку ниже!\n"
            "╚════════════════════════════╝"
        )
    }
    
    for key, value in default_texts.items():
        cursor.execute("INSERT OR IGNORE INTO texts (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    conn.close()
    print("✅ База данных готова")

init_db()

# === ФУНКЦИИ ДЛЯ ТЕКСТОВ ===
def get_text(key, **kwargs):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM texts WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    if result:
        try:
            return result[0].format(**kwargs)
        except:
            return result[0]
    return "Текст не найден"

def update_text(key, new_text):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE texts SET value = ? WHERE key = ?", (new_text, key))
    conn.commit()
    conn.close()

# === КЛАВИАТУРЫ ===
def get_main_keyboard(is_admin_user=False):
    keyboard = [
        [KeyboardButton(text="🛍 Каталог")],
        [KeyboardButton(text="📦 Мои заказы")],
        [KeyboardButton(text="ℹ️ О нас")]
    ]
    if is_admin_user:
        keyboard.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton(text="📁 Создать категорию")],
        [KeyboardButton(text="➕ Добавить товар")],
        [KeyboardButton(text="📝 Редактор текстов")],
        [KeyboardButton(text="👥 Управление админами")],
        [KeyboardButton(text="📋 Все заказы")],
        [KeyboardButton(text="🗑 Управление товарами")],
        [KeyboardButton(text="🗑 Удалить категорию")],
        [KeyboardButton(text="🔙 На главную")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    keyboard = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_categories_inline():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories ORDER BY created_at DESC")
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(text=f"📁 {cat[1]}", callback_data=f"cat_{cat[0]}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_products_by_category_inline(category_id):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products WHERE category_id = ? ORDER BY created_at DESC", (category_id,))
    products = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for p in products:
        keyboard.append([InlineKeyboardButton(text=f"{p[1]} - {p[2]} руб.", callback_data=f"prod_{p[0]}")])
    keyboard.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="back_cats")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_product_actions(product_id):
    keyboard = [
        [InlineKeyboardButton(text="✅ Купить", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_cats")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_categories_inline():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories ORDER BY created_at DESC")
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(text=f"❌ {cat[1]}", callback_data=f"delcat_{cat[0]}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_adm")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_products_inline():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.name, c.name 
        FROM products p
        JOIN categories c ON p.category_id = c.id
        ORDER BY p.created_at DESC
    """)
    products = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for p in products:
        keyboard.append([InlineKeyboardButton(text=f"❌ [{p[2]}] {p[1]}", callback_data=f"delprod_{p[0]}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_adm")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_texts_inline():
    keyboard = [
        [InlineKeyboardButton(text="📝 Приветствие", callback_data="edit_welcome")],
        [InlineKeyboardButton(text="💰 Сообщение об оплате", callback_data="edit_payment")],
        [InlineKeyboardButton(text="✅ Сообщение об успехе", callback_data="edit_success")],
        [InlineKeyboardButton(text="❌ Сообщение об отмене", callback_data="edit_cancel")],
        [InlineKeyboardButton(text="ℹ️ О нас", callback_data="edit_about")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_adm")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# === КОМАНДА СТАРТ ===
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    user = message.from_user
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, registered_at) VALUES (?, ?, ?, ?)",
                   (user.id, user.username, user.first_name, str(datetime.now())))
    conn.commit()
    conn.close()
    
    await message.answer(get_text('welcome'), reply_markup=get_main_keyboard(is_admin(user.id)))

# === КАТАЛОГ ===
@dp.message_handler(lambda msg: msg.text == "🛍 Каталог")
async def catalog(message: Message):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM categories")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await message.answer("📭 Категорий пока нет")
        return
    
    await message.answer("📁 Выберите категорию:", reply_markup=get_categories_inline())

# === О НАС ===
@dp.message_handler(lambda msg: msg.text == "ℹ️ О нас")
async def about(message: Message):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='paid'")
    paid_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM orders")
    total_customers = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(amount) FROM orders WHERE status='paid'")
    total_sales = cursor.fetchone()[0] or 0
    conn.close()
    
    contact_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📬 Написать @inlezz", url="https://t.me/inlezz")]
    ])
    
    await message.answer(get_text('about', paid_orders=paid_orders, total_orders=total_orders,
                                  total_customers=total_customers, total_sales=total_sales),
                         reply_markup=contact_keyboard)

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
    
    text = "╔════════════════════════════╗\n"
    text += "║      📦 МОИ ЗАКАЗЫ        ║\n"
    text += "╠════════════════════════════╣\n\n"
    
    for o in orders:
        order_id = o[0]
        product_name = o[1]
        amount = o[2]
        status = o[3]
        date = o[4][:16]
        
        if status == 'paid':
            status_text = "✅ ОПЛАЧЕН"
            status_emoji = "✅"
        else:
            status_text = "⏳ ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ"
            status_emoji = "⏳"
        
        text += f"  {status_emoji} Заказ #{order_id}\n"
        text += f"  ├─ 🎮 Товар: {product_name}\n"
        text += f"  ├─ 💰 Сумма: {amount} руб.\n"
        text += f"  ├─ 📅 Дата: {date}\n"
        text += f"  ╰─ 🔥 Статус: {status_text}\n\n"
    
    text += "╚════════════════════════════╝"
    
    await message.answer(text)

# === АДМИНКА ===
@dp.message_handler(lambda msg: msg.text == "⚙️ Админка")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа")
        return
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())

# === УПРАВЛЕНИЕ АДМИНАМИ ===
@dp.message_handler(lambda msg: msg.text == "👥 Управление админами")
async def admin_management(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    text = "👥 **Управление администраторами**\n\n"
    text += f"👑 Главный админ: `{ADMIN_IDS[0]}`\n"
    text += "📋 Список админов:\n"
    
    for admin_id in ADMIN_IDS:
        text += f"  • `{admin_id}`\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin")],
        [InlineKeyboardButton(text="❌ Удалить админа", callback_data="remove_admin")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_adm")]
    ])
    
    await message.answer(text, reply_markup=keyboard)

# Состояния для добавления админа
add_admin_data = {}

@dp.callback_query_handler(lambda c: c.data == "add_admin")
async def add_admin_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    add_admin_data[callback.from_user.id] = True
    await callback.message.delete()
    await callback.message.answer("📝 Отправь Telegram ID нового админа:", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message_handler(lambda msg: msg.from_user.id in add_admin_data)
async def add_admin_process(message: Message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отмена":
        del add_admin_data[user_id]
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())
        return
    
    try:
        new_admin_id = int(message.text.strip())
        if add_admin(new_admin_id):
            await message.answer(f"✅ Админ {new_admin_id} добавлен!", reply_markup=get_admin_keyboard())
        else:
            await message.answer("❌ Этот пользователь уже админ")
    except ValueError:
        await message.answer("❌ Введите корректный ID")
    
    del add_admin_data[user_id]

@dp.callback_query_handler(lambda c: c.data == "remove_admin")
async def remove_admin_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    if len(ADMIN_IDS) <= 1:
        await callback.answer("❌ Нельзя удалить последнего админа", show_alert=True)
        return
    
    keyboard = []
    for admin_id in ADMIN_IDS:
        if admin_id != ADMIN_IDS[0]:
            keyboard.append([InlineKeyboardButton(text=f"❌ {admin_id}", callback_data=f"deladmin_{admin_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_adm")])
    
    await callback.message.edit_text("Выберите админа для удаления:", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('deladmin_'))
async def remove_admin_process(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    admin_id = int(callback.data.split('_')[1])
    remove_admin(admin_id)
    await callback.answer("✅ Админ удален", show_alert=True)
    await admin_management(callback.message)

# === УПРАВЛЕНИЕ ТОВАРАМИ ===
@dp.message_handler(lambda msg: msg.text == "🗑 Управление товарами")
async def manage_products(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await message.answer("📭 Нет товаров для удаления")
        return
    
    await message.answer("🗑 Выберите товар для удаления:", reply_markup=get_admin_products_inline())

# === РЕДАКТОР ТЕКСТОВ ===
@dp.message_handler(lambda msg: msg.text == "📝 Редактор текстов")
async def text_editor(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("📝 Выберите текст для редактирования:", reply_markup=get_texts_inline())

# Состояния для редактирования текстов
edit_text_data = {}

@dp.callback_query_handler(lambda c: c.data.startswith('edit_'))
async def start_edit_text(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    text_key = callback.data.replace('edit_', '')
    edit_text_data[callback.from_user.id] = {'key': text_key}
    
    current_text = get_text(text_key)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📝 Редактирование текста:\n\n"
        f"Текущий текст:\n{current_text}\n\n"
        f"Отправь новый текст (или нажми ❌ Отмена):",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()

@dp.message_handler(lambda msg: msg.from_user.id in edit_text_data)
async def process_edit_text(message: Message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отмена":
        del edit_text_data[user_id]
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())
        return
    
    data = edit_text_data[user_id]
    text_key = data['key']
    new_text = message.text
    
    update_text(text_key, new_text)
    del edit_text_data[user_id]
    
    await message.answer(f"✅ Текст обновлен!", reply_markup=get_admin_keyboard())

# === КОМАНДА РУЧНОГО ПОДТВЕРЖДЕНИЯ ===
@dp.message_handler(lambda msg: msg.text and msg.text.startswith('/confirm'))
async def manual_confirm(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Использование: /confirm [номер_заказа]")
            return
        
        order_id = int(parts[1])
        
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT o.user_id, p.file_url, p.name
            FROM orders o
            JOIN products p ON o.product_id = p.id
            WHERE o.id = ?
        ''', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            await message.answer("❌ Заказ не найден")
            conn.close()
            return
        
        user_id, file_url, product_name = order
        
        cursor.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
                       (str(datetime.now()), order_id))
        conn.commit()
        conn.close()
        
        review_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📬 Написать отзыв @inlezz", url="https://t.me/inlezz")]
        ])
        
        await bot.send_message(user_id, get_text('success', file_url=file_url or "Ссылка появится позже"),
                               reply_markup=review_keyboard)
        await message.answer(f"✅ Заказ #{order_id} подтвержден")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# === СОЗДАНИЕ КАТЕГОРИИ ===
cat_data = {}

@dp.message_handler(lambda msg: msg.text == "📁 Создать категорию")
async def create_category_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    cat_data[message.from_user.id] = True
    await message.answer("Введите название категории:", reply_markup=get_cancel_keyboard())

@dp.message_handler(lambda msg: msg.from_user.id in cat_data)
async def create_category_process(message: Message):
    user_id = message.from_user.id
    
    if message.text == "❌ Отмена":
        del cat_data[user_id]
        await message.answer("❌ Отменено", reply_markup=get_admin_keyboard())
        return
    
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (name, created_at) VALUES (?, ?)",
                       (message.text, str(datetime.now())))
        conn.commit()
        conn.close()
        del cat_data[user_id]
        await message.answer(f"✅ Категория '{message.text}' создана!", reply_markup=get_admin_keyboard())
    except:
        await message.answer("❌ Ошибка. Возможно, такая категория уже есть")

# === УДАЛЕНИЕ КАТЕГОРИИ ===
@dp.message_handler(lambda msg: msg.text == "🗑 Удалить категорию")
async def delete_category_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM categories")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await message.answer("📭 Нет категорий")
        return
    
    await message.answer("Выберите категорию для удаления:", reply_markup=get_admin_categories_inline())

# === ДОБАВЛЕНИЕ ТОВАРА ===
product_data = {}

@dp.message_handler(lambda msg: msg.text == "➕ Добавить товар")
async def add_product_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM categories")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await message.answer("❌ Сначала создайте категорию!")
        return
    
    product_data[message.from_user.id] = {'step': 'category'}
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(text=cat[1], callback_data=f"selcat_{cat[0]}")])
    
    await message.answer("Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query_handler(lambda c: c.data.startswith('selcat_'))
async def select_category(callback: CallbackQuery):
    category_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    
    if user_id not in product_data:
        product_data[user_id] = {}
    
    product_data[user_id]['category_id'] = category_id
    product_data[user_id]['step'] = 'name'
    
    await callback.message.delete()
    await callback.message.answer("Введите название товара:", reply_markup=get_cancel_keyboard())
    await callback.answer()

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
            "INSERT INTO products (category_id, name, description, price, file_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (data['category_id'], data['name'], data['desc'], data['price'], data['file_url'], str(datetime.now()))
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
        SELECT o.id, u.username, p.name, o.amount, o.status, o.created_at
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        JOIN products p ON o.product_id = p.id
        ORDER BY o.created_at DESC
        LIMIT 20
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await message.answer("📭 Заказов нет")
        return
    
    text = "📊 ПОСЛЕДНИЕ ЗАКАЗЫ:\n\n"
    for o in orders:
        status = "✅" if o[4] == "paid" else "⏳"
        text += f"{status} Заказ #{o[0]}: @{o[1] or 'нет'} - {o[2]} - {o[3]} руб.\n"
    
    await message.answer(text[:4000])

# === НА ГЛАВНУЮ ===
@dp.message_handler(lambda msg: msg.text == "🔙 На главную")
async def back_main(message: Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))

# === КАТЕГОРИИ ===
@dp.callback_query_handler(lambda c: c.data.startswith('cat_'))
async def show_category(callback: CallbackQuery):
    category_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    cat = cursor.fetchone()
    conn.close()
    
    await callback.message.edit_text(f"📁 {cat[0]}\n\nВыберите товар:",
                                     reply_markup=get_products_by_category_inline(category_id))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "back_cats")
async def back_to_categories(callback: CallbackQuery):
    await callback.message.edit_text("📁 Выберите категорию:", reply_markup=get_categories_inline())
    await callback.answer()

# === ТОВАРЫ ===
@dp.callback_query_handler(lambda c: c.data.startswith('prod_'))
async def show_product(callback: CallbackQuery):
    prod_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price FROM products WHERE id = ?", (prod_id,))
    prod = cursor.fetchone()
    conn.close()
    
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
    
    label = f"order_{callback.from_user.id}_{prod_id}_{int(datetime.now().timestamp())}"
    cursor.execute(
        "INSERT INTO orders (user_id, product_id, amount, label, created_at) VALUES (?, ?, ?, ?, ?)",
        (callback.from_user.id, prod_id, prod[1], label, str(datetime.now()))
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    pay_url = f"https://yoomoney.ru/to/{YOOMONEY_WALLET}?amount={prod[1]}&comment={label}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"chk_{order_id}")]
    ])
    
    await callback.message.edit_text(get_text('payment', order_id=order_id, product_name=prod[0], price=prod[1]),
                                     reply_markup=keyboard)
    await callback.answer()

# === ПРОВЕРКА ОПЛАТЫ (С ТВОИМ ТЕКСТОМ) ===
@dp.callback_query_handler(lambda c: c.data.startswith('chk_'))
async def check_payment(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split('_')[1])
    except:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    # Получаем информацию о заказе
    cursor.execute('''
        SELECT o.user_id, o.status, o.amount
        FROM orders o
        WHERE o.id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        conn.close()
        return
    
    user_id, status, amount = order
    
    # Проверка владельца
    if user_id != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ", show_alert=True)
        conn.close()
        return
    
    # Если уже оплачен
    if status == 'paid':
        await callback.answer("✅ Заказ уже оплачен!", show_alert=True)
        conn.close()
        return
    
    # Проверяем, уведомляли ли админов
    cursor.execute("SELECT admin_notified FROM orders WHERE id = ?", (order_id,))
    admin_notified = cursor.fetchone()[0]
    
    if admin_notified == 0:
        # Отмечаем, что уведомление отправлено
        cursor.execute("UPDATE orders SET admin_notified = 1 WHERE id = ?", (order_id,))
        conn.commit()
        
        # Получаем данные для уведомления админам
        cursor.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        username = user_data[0] if user_data else None
        
        cursor.execute('SELECT name FROM products WHERE id = (SELECT product_id FROM orders WHERE id = ?)', (order_id,))
        product = cursor.fetchone()
        product_name = product[0] if product else "Товар"
        
        # Отправляем уведомление админам
        for admin_id in ADMIN_IDS:
            try:
                admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}")],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{order_id}")]
                ])
                
                await bot.send_message(
                    admin_id,
                    f"💰 **ЗАПРОС НА ПОДТВЕРЖДЕНИЕ**\n\n"
                    f"Заказ #{order_id}\n"
                    f"Пользователь: @{username or 'нет'}\n"
                    f"Товар: {product_name}\n"
                    f"Сумма: {amount} руб.",
                    reply_markup=admin_keyboard,
                    parse_mode="Markdown"
                )
            except:
                pass
        
        # ТВОЙ ТЕКСТ ПОСЛЕ НАЖАТИЯ КНОПКИ
        await callback.message.edit_text(
            "✅ Заявка отправлена администратору. Ожидайте подтверждения.\n"
            "Если прошло больше 5 минут и нет ответа — напишите @inlezz"
        )
    else:
        # Если уже отправляли
        await callback.message.edit_text(
            "⏳ Заявка уже отправлена администратору. Ожидайте подтверждения.\n"
            "Если прошло больше 5 минут и нет ответа — напишите @inlezz"
        )
    
    conn.close()

# === ПОДТВЕРЖДЕНИЕ ЗАКАЗА ===
@dp.callback_query_handler(lambda c: c.data.startswith('confirm_'))
async def confirm_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.user_id, p.file_url, p.name
        FROM orders o
        LEFT JOIN products p ON o.product_id = p.id
        WHERE o.id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        conn.close()
        return
    
    user_id, file_url, product_name = order
    
    cursor.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
                   (str(datetime.now()), order_id))
    conn.commit()
    conn.close()
    
    review_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📬 Написать отзыв @inlezz", url="https://t.me/inlezz")]
    ])
    
    try:
        await bot.send_message(
            user_id,
            get_text('success', file_url=file_url or "Ссылка появится позже"),
            reply_markup=review_keyboard
        )
    except:
        pass
    
    await callback.message.edit_text(f"✅ Заказ #{order_id} подтвержден")
    await callback.answer("✅ Готово", show_alert=True)

# === ОТМЕНА ЗАКАЗА ===
@dp.callback_query_handler(lambda c: c.data.startswith('cancel_'))
async def cancel_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.user_id, p.name, o.amount
        FROM orders o
        LEFT JOIN products p ON o.product_id = p.id
        WHERE o.id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if order:
        user_id, product_name, amount = order
        try:
            await bot.send_message(
                user_id,
                get_text('cancel', order_id=order_id, product_name=product_name or "Товар", price=amount)
            )
        except:
            pass
    
    cursor.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"❌ Заказ #{order_id} отменен")
    await callback.answer("❌ Отменено", show_alert=True)

# === УДАЛЕНИЕ КАТЕГОРИИ ===
@dp.callback_query_handler(lambda c: c.data.startswith('delcat_'))
async def delete_category(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    cat_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    
    await callback.answer("✅ Категория удалена", show_alert=True)
    await callback.message.edit_text("Выберите категорию для удаления:", reply_markup=get_admin_categories_inline())

# === УДАЛЕНИЕ ТОВАРА ===
@dp.callback_query_handler(lambda c: c.data.startswith('delprod_'))
async def delete_product(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return
    
    prod_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()
    
    await callback.answer("✅ Товар удален", show_alert=True)
    await callback.message.edit_text("🗑 Выберите товар для удаления:", reply_markup=get_admin_products_inline())

# === ВОЗВРАТ В АДМИНКУ ===
@dp.callback_query_handler(lambda c: c.data == "back_adm")
async def back_to_admin(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())
    await callback.answer()

# === ЗАПУСК ===
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    
    async def on_startup(dispatcher):
        railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'neverlate-bot-production.up.railway.app')
        webhook_url = f"https://{railway_domain}/webhook"
        await bot.set_webhook(webhook_url)
        print(f"✅ Бот запущен!")
        print(f"✅ Админы: {ADMIN_IDS}")
    
    start_webhook(
        dispatcher=dp,
        webhook_path="/webhook",
        on_startup=on_startup,
        host="0.0.0.0",
        port=PORT
    )
