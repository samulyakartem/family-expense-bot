import sqlite3
import os
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

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

pending_expenses = {}

# КНОПКА СТАТИСТИКИ
main_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
main_keyboard.add(KeyboardButton("📊 Статистика"))

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Отправь сумму или нажми Статистика", reply_markup=main_keyboard)

# ----------- СТАТИСТИКА ------------

@dp.message_handler(lambda message: message.text == "📊 Статистика")
async def stats_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Сегодня", callback_data="today"),
        InlineKeyboardButton("7 дней", callback_data="week"),
        InlineKeyboardButton("Месяц", callback_data="month")
    )
    await message.answer("Выбери период:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data in ["today", "week", "month"])
async def process_stats(callback_query: types.CallbackQuery):

    today = datetime.now().date()

    if callback_query.data == "today":
        start_date = today
    elif callback_query.data == "week":
        start_date = today - timedelta(days=7)
    else:
        start_date = today.replace(day=1)

    cursor.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    WHERE date BETWEEN ? AND ?
    GROUP BY category
    """, (start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")))

    rows = cursor.fetchall()

    if not rows:
        text = "Нет записей за этот период."
    else:
        total = 0
        text = "📊 Статистика:\n\n"
        for category, amount in rows:
            text += f"{category}: {amount} ₽\n"
            total += amount
        text += f"\nИТОГО: {total} ₽"

    await bot.edit_message_text(
        text,
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id
    )

    await bot.answer_callback_query(callback_query.id)

# ----------- ДОБАВЛЕНИЕ РАСХОДА ------------

@dp.message_handler()
async def add_expense(message: types.Message):

    pattern = r"(\d+)\s*(\d{2}\.\d{2}\.\d{4})?"
    match = re.match(pattern, message.text)

    if not match:
        await message.answer("Пример: 1500 или 1500 25.02.2026", reply_markup=main_keyboard)
        return

    amount = float(match.group(1))
    date_input = match.group(2)

    if date_input:
        try:
            date = datetime.strptime(date_input, "%d.%m.%Y").strftime("%Y-%m-%d")
        except:
            await message.answer("❌ Неверный формат даты")
            return
    else:
        date = datetime.now().strftime("%Y-%m-%d")

    pending_expenses[message.from_user.id] = {
        "amount": amount,
        "date": date
    }

    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(cat, callback_data=cat) for cat in CATEGORIES]
    keyboard.add(*buttons)

    await message.answer("Выбери категорию:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data in CATEGORIES)
async def process_category(callback_query: types.CallbackQuery):

    user_id = callback_query.from_user.id

    if user_id not in pending_expenses:
        await bot.answer_callback_query(callback_query.id)
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
