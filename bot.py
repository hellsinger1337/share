import os
import asyncio
import csv
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI

client = OpenAI(api_key="sk-9_bWgBwTT5WQ1rigH9YaAhZCfre4_eoXiEzjcvseQiT3BlbkFJtpwp_eRRJYI_yCevtLVUm49m-dULML5LASYM7tCOUA")
bot = Bot(token="7691922270:AAEax1BvZDKyZ_AbRFVIglW9s1Vp51EXbJ0")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# Пути к файлам для хранения данных
DAILY_MESSAGES_FILE = 'daily_messages.csv'
WEEKLY_MESSAGES_FILE = 'weekly_messages.csv'
MONTHLY_MESSAGES_FILE = 'monthly_messages.csv'
PLANS_FILE = 'plans.csv'

# Идентификаторы приватных каналов
QUICK_NOTES_CHANNEL_ID = -1002325662898
DAILY_NOTES_CHANNEL_ID = -1002477975778
WEEKLY_NOTES_CHANNEL_ID = -1002258226293
MONTHLY_NOTES_CHANNEL_ID = -1002295966789
PLANS_CHANNEL_ID = -1002466940147

# Настройка планировщика
scheduler = AsyncIOScheduler()

# Состояния для FSM
class Form(StatesGroup):
    quick_note = State()
    detailed_note = State()
    confirm_quick_note = State()
    confirm_detailed_note = State()

# Функция для редактуры текста
async def edit_text(text):
    completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "ты редактируешь текст, исправляя пунктуацию и орфографию, но сохраняя стиль и основныу мысль. В ответ присылаешь толкьо отредактированный текст. Ты не меняешь сами слова и оставляешь все так, как писал автор"},
        {
            "role": "user",
            "content": text
        }
    ]
)
    return completion.choices[0].message.content

async def make_text(text):
    completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "Ты исполнительный помошник, кратко но полностью выполняешь запрос пользователя, но не более"},
        {
            "role": "user",
            "content": text
        }
    ]
)
    return completion.choices[0].message.content

# Функция для записи сообщения в CSV-файл
def save_message_to_csv(file_path, text, date):
    print(123)
    with open(file_path, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([text, date.isoformat()])

# Функция для чтения сообщений из CSV-файла за определенный период
def read_messages_from_csv(file_path, period):
    messages = []
    now = datetime.now(timezone.utc)
    try:
        with open(file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                text, date_str = row
                date = datetime.fromisoformat(date_str)
                real_date = str(date + timedelta(hours=3))
                if date >= now - period:
                    messages.append(text+"от"+real_date)

    except FileNotFoundError:
        pass  
    return messages

# Функция для сохранения плана в CSV-файл
def save_plan_to_csv(plan_time, plan_text, user_id):
    with open(PLANS_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([plan_time, plan_text, user_id])

# Функция для чтения планов из CSV-файла
def read_plans_from_csv():
    plans = []
    try:
        with open(PLANS_FILE, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                plan_time_str, plan_text, user_id = row
                plans.append((plan_time_str, plan_text, user_id))
    except FileNotFoundError:
        pass  # Файл еще не создан, возвращаем пустой список
    return plans

# Обработчик для сбора сообщений из каналов
@router.channel_post()
async def collect_channel_messages(message: types.Message):
    # Проверяем, из какого канала пришло сообщение, и сохраняем его
    if message.chat.id == QUICK_NOTES_CHANNEL_ID:
        save_message_to_csv(DAILY_MESSAGES_FILE, message.text, message.date)
    elif message.chat.id == DAILY_NOTES_CHANNEL_ID:
        save_message_to_csv(WEEKLY_MESSAGES_FILE, message.text, message.date)
    elif message.chat.id == WEEKLY_NOTES_CHANNEL_ID:
        save_message_to_csv(MONTHLY_MESSAGES_FILE, message.text, message.date)

# Быстрая заметка
@router.message(Command("quick_note"))
async def quick_note_handler(message: types.Message, state: FSMContext):
    await message.answer("Введите текст для быстрой заметки:")
    await state.set_state(Form.quick_note)

@router.message(Form.quick_note)
async def process_quick_note(message: types.Message, state: FSMContext):
    edited_text = await edit_text(message.text)
    await state.update_data(edited_text=edited_text)
    await message.answer(f"Вот отредактированный текст:\n\n{edited_text}\n\nОтправить? (да/нет)")
    await state.set_state(Form.confirm_quick_note)

@router.message(Form.confirm_quick_note, F.text.lower().in_(["да", "нет"]))
async def confirm_quick_note_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    edited_text = data.get('edited_text')
    if message.text.lower() == "да":
        await bot.send_message(QUICK_NOTES_CHANNEL_ID, edited_text)
        save_message_to_csv(DAILY_MESSAGES_FILE,edited_text,datetime.now(timezone.utc))
        await message.answer("Заметка отправлена в канал быстрых заметок!")
        await state.clear()
    elif message.text.lower() == "нет":
        await message.answer("Вы можете изменить текст и отправить заново.")
        await state.set_state(Form.quick_note)

# Дневная, недельная и месячная заметки
@router.message(Command(commands=["daily_note", "weekly_note", "monthly_note"]))
async def detailed_note_handler(message: types.Message, state: FSMContext):
    command = message.text.split()[0].lstrip('/')
    note_type = command.replace('_note', '')
    note_period = {"daily": "день", "weekly": "неделя", "monthly": "месяц"}.get(note_type, "период")
    events = await fetch_events_from_storage(note_type)
    prompt = f"Составь отчет по событиям из личного дневника за {note_period}:\n\n{events}! Твой ответ должен выглядеть как краткая запись в дневник, которая бы была сформирована на основе этих событий"
    summary = await make_text(prompt)
    await state.update_data(summary=summary, note_type=note_type)
    await message.answer(f"Сформированная заметка:\n\n{summary}\n\nВведите текст заметки:")
    await state.set_state(Form.detailed_note)

@router.message(Form.detailed_note)
async def confirm_detailed_note_handler(message: types.Message, state: FSMContext):
    edited_text = await edit_text(message.text)
    await state.update_data(edited_text=edited_text)
    await message.answer(f"Вот отредактированный текст:\n\n{edited_text}\n\nОтправить? (да/нет)")
    await state.set_state(Form.confirm_detailed_note)

@router.message(Form.confirm_detailed_note, F.text.lower().in_(["да", "нет"]))
async def send_detailed_note_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    edited_text = data.get('edited_text')
    note_type = data.get('note_type')
    channel_id = {
        "daily": DAILY_NOTES_CHANNEL_ID,
        "weekly": WEEKLY_NOTES_CHANNEL_ID,
        "monthly": MONTHLY_NOTES_CHANNEL_ID,
    }.get(note_type, DAILY_NOTES_CHANNEL_ID)
    file_to_save_id = {
        "daily": WEEKLY_MESSAGES_FILE,
        "weekly": MONTHLY_MESSAGES_FILE,
    }.get(note_type, DAILY_NOTES_CHANNEL_ID)
    if message.text.lower() == "да":
        await bot.send_message(channel_id, edited_text)
        save_message_to_csv(file_to_save_id,edited_text,datetime.now(timezone.utc))
        await message.answer("Заметка отправлена!")
        await state.clear()
    elif message.text.lower() == "нет":
        await message.answer("Вы можете изменить текст и отправить заново.")
        await state.set_state(Form.detailed_note)

# Функция для получения событий из файлов
async def fetch_events_from_storage(note_type):
    period_map = {
        'daily': timedelta(days=1),
        'weekly': timedelta(weeks=1),
        'monthly': timedelta(days=30),
    }
    period = period_map.get(note_type, timedelta(days=1))
    now = datetime.now()
    file_path_map = {
        'daily': DAILY_MESSAGES_FILE,
        'weekly': WEEKLY_MESSAGES_FILE,
        'monthly': MONTHLY_MESSAGES_FILE,
    }
    file_path = file_path_map.get(note_type)
    messages = read_messages_from_csv(file_path, period)
    return "\n".join(messages)

# Добавление планов
@router.message(Command("add_plan"))
async def add_plan_handler(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Формат: /add_plan <время> <план>")
        return
    plan_args = args[1].split(maxsplit=1)
    if len(plan_args) < 2:
        await message.answer("Формат: /add_plan <время> <план>")
        return
    plan_time = plan_args[0]
    plan_text = plan_args[1]
    user_id = message.from_user.id
    # Сохраняем план в файл
    save_plan_to_csv(plan_time, plan_text, user_id)
    await message.answer(f"План добавлен: {plan_time} - {plan_text}")

# Проверка планов с уведомлениями
async def check_plans():
    now = datetime.now()
    plans = read_plans_from_csv()
    updated_plans = []
    for plan_time_str, plan_text, user_id in plans:
        plan_datetime = datetime.strptime(plan_time_str, "%H:%M")
        plan_datetime = plan_datetime.replace(year=now.year, month=now.month, day=now.day)
        if now >= plan_datetime and now - timedelta(minutes=15) <= plan_datetime:
            try:
                await bot.send_message(int(user_id), f"Напоминание: {plan_text}")
            except Exception as e:
                print(f"Ошибка при отправке напоминания: {e}")
        else:
            # Сохраняем план обратно, если его время еще не пришло
            updated_plans.append((plan_time_str, plan_text, user_id))
    # Перезаписываем файл с оставшимися планами
    with open(PLANS_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(updated_plans)

# Задача для проверки планов каждые 15 минут
scheduler.add_job(check_plans, "interval", minutes=15)

# Запуск бота
async def main():
    dp.include_router(router)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())