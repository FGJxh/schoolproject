from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import sys

# Инициализация
bot = Bot(token="7780127425:AAH0Ll3vO6xiljTdJPIT-epdh-P5VgvZ8vY")
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Хранение данных
user_tasks = {}  # {user_id: {"today": [], "tomorrow": [], "week": [], "deadlines": {}}}

# Состояния FSM
class TaskStates(StatesGroup):
    waiting_task_type = State()
    waiting_task_text = State()
    waiting_deadline_text = State()
    waiting_deadline_date = State()

# Клавиатуры
def get_main_keyboard():
    buttons = [
        [types.KeyboardButton(text="📝 Добавить задачу")],
        [types.KeyboardButton(text="🔄 Мои задачи")],
        [types.KeyboardButton(text="⏰ Добавить дедлайн")],
        [types.KeyboardButton(text="🧹 Очистить всё")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_task_type_keyboard():
    buttons = [
        [types.KeyboardButton(text="Сегодня")],
        [types.KeyboardButton(text="Завтра")],
        [types.KeyboardButton(text="Неделя")],
        [types.KeyboardButton(text="◀️ Назад")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="◀️ Отмена")]],
        resize_keyboard=True
    )

# Сопоставление русских названий с ключами
task_type_mapping = {
    "Сегодня": "today",
    "Завтра": "tomorrow",
    "Неделя": "week"
}

# Уведомление о дедлайне
async def send_deadline_reminder(user_id: int, task: str):
    await bot.send_message(user_id, f"⏰ Напоминание: завтра дедлайн по задаче '{task}'")

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_tasks:
        user_tasks[user_id] = {"today": [], "tomorrow": [], "week": [], "deadlines": {}}
    
    await message.answer(
        "📅 <b>Умный планировщик задач</b>\n\n"
        "Приветствую! Я помогу вам организовать ваши задачи.\n"
        "Выберите действие:",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# Обработчики кнопок
@dp.message(lambda message: message.text == "📝 Добавить задачу")
async def add_task_start(message: types.Message):
    await message.answer(
        "Выберите тип задачи:",
        reply_markup=get_task_type_keyboard()
    )

@dp.message(lambda message: message.text in task_type_mapping.keys())
async def add_task_type(message: types.Message, state: FSMContext):
    task_type_key = task_type_mapping[message.text]
    await state.update_data(task_type=task_type_key)
    await state.set_state(TaskStates.waiting_task_text)
    await message.answer(
        "📝 Введите текст задачи:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(TaskStates.waiting_task_text)
async def process_task_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    task_type = data["task_type"]
    
    if user_id not in user_tasks:
        user_tasks[user_id] = {"today": [], "tomorrow": [], "week": [], "deadlines": {}}
    
    user_tasks[user_id][task_type].append(message.text)
    
    await message.answer(
        f"✅ Задача добавлена ({task_type}):\n{message.text}",
        reply_markup=get_main_keyboard()
    )
    await state.clear()

@dp.message(lambda message: message.text == "⏰ Добавить дедлайн")
async def add_deadline_start(message: types.Message, state: FSMContext):
    await message.answer(
        "📝 Введите задачу с дедлайном:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TaskStates.waiting_deadline_text)

@dp.message(TaskStates.waiting_deadline_text)
async def process_deadline_text(message: types.Message, state: FSMContext):
    if message.text == "◀️ Отмена":
        await message.answer("Действие отменено", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    await state.update_data(task_text=message.text)
    await message.answer(
        "📅 Введите дату дедлайна (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TaskStates.waiting_deadline_date)

@dp.message(TaskStates.waiting_deadline_date)
async def process_deadline_date(message: types.Message, state: FSMContext):
    if message.text == "◀️ Отмена":
        await message.answer("Действие отменено", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        task_text = data["task_text"]
        deadline_date = datetime.strptime(message.text, "%d.%m.%Y").date()
        
        if user_id not in user_tasks:
            user_tasks[user_id] = {"today": [], "tomorrow": [], "week": [], "deadlines": {}}
        
        user_tasks[user_id]["deadlines"][task_text] = message.text
        
        # Напоминание за день до дедлайна
        reminder_time = datetime.combine(deadline_date - timedelta(days=1), datetime.min.time())
        scheduler.add_job(
            send_deadline_reminder,
            'date',
            run_date=reminder_time,
            args=(user_id, task_text)
        )
        
        await message.answer(
            f"⏰ Дедлайн добавлен:\n{task_text} — до {message.text}",
            reply_markup=get_main_keyboard()
        )
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
        return
    
    await state.clear()

@dp.message(lambda message: message.text == "🔄 Мои задачи")
async def show_all_tasks(message: types.Message):
    user_id = message.from_user.id
    tasks = user_tasks.get(user_id, {})
    
    response = []
    if tasks.get("today"):
        response.append("📝 <b>Сегодня:</b>\n" + "\n".join(f"• {task}" for task in tasks["today"]))
    if tasks.get("tomorrow"):
        response.append("\n📅 <b>Завтра:</b>\n" + "\n".join(f"• {task}" for task in tasks["tomorrow"]))
    if tasks.get("week"):
        response.append("\n🗓 <b>На неделю:</b>\n" + "\n".join(f"• {task}" for task in tasks["week"]))
    if tasks.get("deadlines"):
        response.append("\n⏰ <b>Дедлайны:</b>\n" + "\n".join(f"• {task} — до {date}" for task, date in tasks["deadlines"].items()))
    
    if response:
        await message.answer("\n".join(response), parse_mode="HTML")
    else:
        await message.answer("📭 У вас пока нет задач")

@dp.message(lambda message: message.text == "🧹 Очистить всё")
async def clear_all_tasks(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_tasks:
        user_tasks[user_id] = {"today": [], "tomorrow": [], "week": [], "deadlines": {}}
    await message.answer("🧹 Все задачи успешно очищены!", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text in ["◀️ Назад", "◀️ Отмена"])
async def back_to_main(message: types.Message):
    await message.answer(
        "Главное меню",
        reply_markup=get_main_keyboard()
    )

# Корректное завершение работы
async def shutdown():
    await bot.session.close()
    scheduler.shutdown()

# Запуск бота
async def main():
    scheduler.start()
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        await shutdown()
    except Exception as e:
        print(f"Ошибка: {e}")
        await shutdown()

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")