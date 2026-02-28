import sqlite3
import os
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- БАЗА ---
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
conn.commit()

# --- КАТЕГОРИИ ---
CATEGORIES = [
    "Здоровье/медицина",
    "Авто",
    "Путешествие",
    "Подарки",
    "Ашан/Яблоко",
    "Привоз",
    "Ипотека",
    "Кафе",
    "Коммуналка",
    "Прочее"
]

# временное хранение данных до выбора категории
pending_expenses = {}

# --- СТАРТ ---
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Отправь сумму и (опционально) дату.\nПример:\n1500\n2000 25.02.2026")

# --- ВВОД СУММЫ ---
@dp.message_handler()
async def add_expense(message: types.Message):

    pattern = r"(\d+)\s*(\d{2}\.\d{2}\.\d{4})?"
    match = re.match(pattern, message.text)

    if not match:
        await message.answer("Пример: 1500 или 1500 25.02.2026")
        return

    amount = float(match.group(1))
    date_input = match.group(2)

    if date_input:
        try:
            date = datetime.strptime(date_input, "%d.%m.%Y").strftime("%Y-%m-%d")
        except:
            await message.answer("❌ Неверный формат даты. Используй 25.02.2026")
            return
    else:
        date = datetime.now().strftime("%Y-%m-%d")

    # сохраняем временно
    pending_expenses[message.from_user.id] = {
        "amount": amount,
        "date": date
    }

    # создаем кнопки
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(cat, callback_data=cat) for cat in CATEGORIES]
    keyboard.add(*buttons)

    await message.answer("Выбери категорию:", reply_markup=keyboard)

# --- ВЫБОР КАТЕГОРИИ ---
@dp.callback_query_handler(lambda c: c.data in CATEGORIES)
async def process_category(callback_query: types.CallbackQuery):

    user_id = callback_query.from_user.id

    if user_id not in pending_expenses:
        await bot.answer_callback_query(callback_query.id, "Ошибка")
        return

    amount = pending_expenses[user_id]["amount"]
    date = pending_expenses[user_id]["date"]
    category = callback_query.data

    cursor.execute("""
    INSERT INTO expenses (user_id, amount, category, date)
    VALUES (?, ?, ?, ?)
    """, (user_id, amount, category, date))

    conn.commit()

    del pending_expenses[user_id]

    await bot.edit_message_text(
        f"✅ Записал: {amount} ₽\nКатегория: {category}\nДата: {date}",
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id
    )

    await bot.answer_callback_query(callback_query.id)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
