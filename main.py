import sqlite3
import os
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")  # добавить BOT_TOKEN в secrets

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ------------------ База данных ------------------
conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    category TEXT,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    role TEXT
)
""")
conn.commit()

# ------------------ Категории ------------------
CATEGORIES = [
    "Здоровье/медицина", "Авто", "Путешествие", "Подарки",
    "Ашан/Яблоко", "Привоз", "Ипотека", "Кафе", "Коммуналка", "Прочее"
]

pending_expenses = {}  # хранит временные данные при вводе суммы и категории

# ------------------ Основная клавиатура ------------------
main_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
main_keyboard.add(KeyboardButton("📊 Статистика"))

# ------------------ Команда /start ------------------
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Привет! Отправь сумму или нажми Статистика.", reply_markup=main_keyboard)

# ------------------ Обработка ввода суммы ------------------
@dp.message_handler(lambda message: message.text and not message.text.startswith("📊"))
async def add_expense(message: types.Message):
    user_id = message.from_user.id

    # Проверка роли
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("Артем", callback_data="role_husband"),
            InlineKeyboardButton("Аня", callback_data="role_wife")
        )
        await message.answer("Пожалуйста, укажите, кто вы:", reply_markup=keyboard)
        pending_expenses[user_id] = {"raw_message": message.text}
        return

    # Парсим сумму и опциональную дату
    pattern = r"(\d+\.?\d*)\s*(\d{2}\.\d{2}\.\d{4})?"
    match = re.match(pattern, message.text)
    if not match:
        await message.answer("Пример ввода: 1500 или 1500 25.02.2026", reply_markup=main_keyboard)
        return

    amount = float(match.group(1))
    date_input = match.group(2)
    date = datetime.strptime(date_input, "%d.%m.%Y").strftime("%Y-%m-%d") if date_input else datetime.now().strftime("%Y-%m-%d")

    pending_expenses[user_id] = {"amount": amount, "date": date}

    # Выбор категории
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(cat, callback_data=cat) for cat in CATEGORIES]
    keyboard.add(*buttons)
    await message.answer("Выбери категорию:", reply_markup=keyboard)

# ------------------ Выбор роли ------------------
@dp.callback_query_handler(lambda c: c.data in ["role_husband", "role_wife"])
async def process_role(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    role = "Артем" if callback_query.data == "role_husband" else "Аня"
    cursor.execute("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, ?)", (user_id, role))
    conn.commit()

    await bot.answer_callback_query(callback_query.id, text=f"Вы зарегистрированы как {role}")

    # Повторная обработка ранее введённой суммы
    raw_msg = pending_expenses[user_id]["raw_message"]
    del pending_expenses[user_id]

    # Создаем "fake" message
    fake_message = types.Message(
        message_id=callback_query.message.message_id,
        from_user=callback_query.from_user,
        chat=callback_query.message.chat,
        date=callback_query.message.date,
        text=raw_msg
    )
    await add_expense(fake_message)
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)

# ------------------ Выбор категории ------------------
@dp.callback_query_handler(lambda c: c.data in CATEGORIES)
async def process_category(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in pending_expenses:
        await bot.answer_callback_query(callback_query.id)
        return

    amount = pending_expenses[user_id]["amount"]
    date = pending_expenses[user_id]["date"]
    category = callback_query.data

    cursor.execute("INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
                   (user_id, amount, category, date))
    conn.commit()
    del pending_expenses[user_id]

    await bot.send_message(callback_query.message.chat.id,
                           f"✅ Записал: {amount} ₽\nКатегория: {category}\nДата: {date}")
    await bot.answer_callback_query(callback_query.id)

# ------------------ Кнопка Статистика ------------------
@dp.message_handler(lambda message: message.text == "📊 Статистика")
async def stats_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Сегодня", callback_data="today"),
        InlineKeyboardButton("7 дней", callback_data="week"),
        InlineKeyboardButton("Месяц", callback_data="month")
    )
    await message.answer("Выбери период:", reply_markup=keyboard)

# ------------------ Статистика ------------------
@dp.callback_query_handler(lambda c: c.data in ["today", "week", "month"])
async def process_stats(callback_query: types.CallbackQuery):
    today = datetime.now().date()
    if callback_query.data == "today":
        start_date = today
    elif callback_query.data == "week":
        start_date = today - timedelta(days=7)
    else:
        start_date = today.replace(day=1)

    start = start_date.strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    # Сумма Артем
    cursor.execute("""
        SELECT SUM(e.amount) FROM expenses e
        JOIN users u ON e.user_id = u.user_id
        WHERE u.role='Артем' AND e.date BETWEEN ? AND ?
    """, (start, end))
    husband_sum = cursor.fetchone()[0] or 0

    # Сумма Аня
    cursor.execute("""
        SELECT SUM(e.amount) FROM expenses e
        JOIN users u ON e.user_id = u.user_id
        WHERE u.role='Аня' AND e.date BETWEEN ? AND ?
    """, (start, end))
    wife_sum = cursor.fetchone()[0] or 0

    total = husband_sum + wife_sum

    # Суммы по категориям
    cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category",
                   (start, end))
    categories = cursor.fetchall()

    text = f"📊 Статистика ({start} - {end}):\n\n👨 Артем: {husband_sum} ₽\n👩 Аня: {wife_sum} ₽\n💰 Общая: {total} ₽\n\n"
    if categories:
        text += "По категориям:\n" + "\n".join(f"{cat}: {amt} ₽" for cat, amt in categories)

    await bot.send_message(callback_query.message.chat.id, text)
    await bot.answer_callback_query(callback_query.id)

# ------------------ Запуск бота ------------------
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
