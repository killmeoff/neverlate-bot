import asyncio
import sqlite3
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.utils.executor import start_webhook

# === ТВОИ ДАННЫЕ (Railway подставит их сам) ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOOMONEY_WALLET = os.environ.get("YOOMONEY_WALLET")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "").split(",") if id]
SHOP_NAME = "NEVERLATE"

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO)

# === ИНИЦИАЛИЗАЦИЯ ===
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден! Добавь его в Variables на Railway")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

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
            paid_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS texts (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    
    default_texts = {
        'welcome': (
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "┃   🎮 NEVERLATE   ┃\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            "Йо, бро 👋\n"
            "Хочешь конфиги, которые реально вывозят?\n"
            "Тогда ты там где надо.\n\n"
            "📌 **Как забрать:**\n"
            "👉 Жми **«🛍 Каталог»**\n"
            "👉 Выбирай свой софт\n"
            "👉 Плати через ЮMoney\n"
            "👉 Пользуйся 💪\n\n"
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
            "│  ⚡️ Жми «Оплатить»\n"
            "│  ✅ Вернись и нажми «Я оплатил»\n"
            "╰─────────────────────────────╯"
        ),
        'success': (
            "╭─────────────────────────────╮\n"
            "│       ✅ ОПЛАЧЕНО!          │\n"
            "├─────────────────────────────┤\n"
            "│  🔥 Конфиг твой!\n"
            "│  Ссылка: {file_url}\n"
            "├─────────────────────────────┤\n"
            "│  📸 **Отзыв:** @inlezz\n"
            "╰─────────────────────────────╯"
        ),
        'about': (
            "╔════════════════════════════╗\n"
            "║      🎮 NEVERLATE         ║\n"
            "╠════════════════════════════╣\n"
            "║  Работаем честно 💯\n"
            "║  📊 Заказов: {paid_orders}/{total_orders}\n"
            "║  👥 Клиентов: {total_customers}\n"
            "║  💰 Продано: {total_sales} руб.\n"
            "║  🔥 Поможем с настройкой\n"
            "║  📬 Вопросы: @inlezz\n"
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

# === ПРОВЕРКА АДМИНА ===
def is_admin(user_id):
    return user_id in ADMIN_IDS

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
        [KeyboardButton(text="📋 Все заказы")],
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
    cursor.execute("SELECT id, name FROM products ORDER BY created_at DESC")
    products = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for p in products:
        keyboard.append([InlineKeyboardButton(text=f"❌ {p[1]}", callback_data=f"delprod_{p[0]}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_adm")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# === КОМАНДЫ ===
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
        text += f"{status} Заказ #{o[0]}\n"
        text += f"  Товар: {o[1]}\n"
        text += f"  Сумма: {o[2]} руб.\n"
        text += f"  Дата: {o[4][:16]}\n\n"
    
    await message.answer(text)

@dp.message_handler(lambda msg: msg.text == "⚙️ Админка")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа")
        return
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())

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

# === УДАЛЕНИЕ ТОВАРА ===
@dp.message_handler(lambda msg: msg.text == "🗑 Удалить товар")
async def delete_product_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await message.answer("📭 Нет товаров")
        return
    
    await message.answer("Выберите товар для удаления:", reply_markup=get_admin_products_inline())

# === ВСЕ ЗАКАЗЫ ===
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
    
    text = "📊 Заказы:\n\n"
    for o in orders:
        status = "✅" if o[4] == "paid" else "⏳"
        text += f"{status} #{o[0]} @{o[1]}: {o[2]} - {o[3]} руб.\n"
    
    await message.answer(text)

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

# === ПРОВЕРКА ОПЛАТЫ ===
@dp.callback_query_handler(lambda c: c.data.startswith('chk_'))
async def check_payment(callback: CallbackQuery):
    order_id = int(callback.data.split('_')[1])
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.status, o.user_id, p.file_url 
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.id = ?
    ''', (order_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    status, user_id, file_url = result
    
    if status == 'paid':
        review_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📬 Написать отзыв @inlezz", url="https://t.me/inlezz")]
        ])
        await callback.message.edit_text(get_text('success', file_url=file_url or "Ссылка появится позже"),
                                         reply_markup=review_keyboard)
        conn.close()
        return
    
    await callback.answer("❌ Платёж не найден", show_alert=True)
    conn.close()

# === УДАЛЕНИЕ ===
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
    await callback.message.edit_text("Выберите товар для удаления:", reply_markup=get_admin_products_inline())

@dp.callback_query_handler(lambda c: c.data == "back_adm")
async def back_to_admin(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())
    await callback.answer()

# === ЗАПУСК ДЛЯ RAILWAY (ИСПРАВЛЕНО) ===
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    
    # Функция, которая выполнится при старте
    async def on_startup(dispatcher):
        await bot.set_webhook(f"https://{os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'neverlate-bot.up.railway.app')}/webhook")
        print("✅ Вебхук установлен")
        print("✅ Бот запущен на Railway!")
    
    start_webhook(
        dispatcher=dp,
        webhook_path="/webhook",
        on_startup=on_startup,
        host="0.0.0.0",
        port=PORT
    )
