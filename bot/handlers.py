import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ChatAction
from agent.orchestrator import AgentOrchestrator
from asyncio import to_thread
from aiogram.filters.command import CommandObject
from aiogram.types import BufferedInputFile

from mcp_server.tools.export_tools import export_schedule

logger = logging.getLogger(__name__)
router = Router()
orchestrator = AgentOrchestrator()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 <b>Привет! Я твой персональный AI-ассистент по расписанию и делам.</b>\n\n"
        "Я управляю базой данных твоего персонального календаря через протокол <b>MCP (Model Context Protocol)</b>. "
        "Ты можешь общаться со мной простым человеческим языком, а я сам сформирую нужные SQL-запросы, проверю конфликты по времени и установлю напоминания!\n\n"
        "<b>Что я умею:</b>\n"
        "• 📅 <i>«Что у меня запланировано на сегодня?»</i>\n"
        "• 🩺 <i>«Запиши завтра к стоматологу на 15:00, это критически важно. Напомни за 2 часа»</i>\n"
        "• 🏃 <i>«Перенеси тренировку в спортзале на пятницу в 19:00»</i>\n"
        "• 🔴 <i>«Покажи все критические и важные дела на этой неделе»</i>\n"
        "• ⏰ <i>«Какие напоминания у меня активны?»</i>\n\n"
        "Команды:\n"
        "/start — Справка и приветствие\n"
        "/reset — Сбросить контекст диалога\n"
        "/today — Быстрый просмотр планов на сегодня"
    )
    await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "<b>Справка по уровням важности (Priority):</b>\n"
        "🔴 <b>4 = CRITICAL</b> — Врачи, авиарейсы, экзамены (нельзя пропускать/двигать!)\n"
        "🟡 <b>3 = HIGH</b> — Важные созвоны, рабочие встречи, дедлайны\n"
        "🟢 <b>2 = MEDIUM</b> — Стандартные дела, тренировки, хобби\n"
        "⚪ <b>1 = LOW</b> — Бытовые мелочи, покупка продуктов\n\n"
        "<b>Как работает агент:</b>\n"
        "При каждом запросе агент сам исследует базу данных, определяет дату и проверяет наложения дел друг на друга. "
        "Если новое дело пересекается со старым, агент предупредит тебя и предложит решение!"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("reset"))
async def cmd_reset(message: types.Message):
    orchestrator.reset_session(message.chat.id)
    await message.answer("🔄 Контекст диалога очищен. О чем вы хотите узнать?")


@router.message(Command("today"))
async def cmd_today(message: types.Message):
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    response = await orchestrator.process_user_message(
        chat_id=message.chat.id,
        user_text="Покажи все мои дела и события, запланированные на сегодня."
    )
    await message.answer(response)


@router.message(Command("export"))
async def cmd_export(message: types.Message, command: CommandObject):
    arguments = (command.args or "").split()

    if len(arguments) != 2:
        await message.answer(
            "Укажи начальную и конечную даты:\n"
            "/export 2026-11-01 2026-11-07\n\n"
            "Обе даты входят в период экспорта."
        )
        return

    start_date, end_date = arguments

    try:
        result = await to_thread(
            export_schedule,
            start_date=start_date,
            end_date=end_date,
            chat_id=message.chat.id
        )
    except ValueError as error:
        await message.answer(
            f"Не удалось сформировать календарь: {error}\n"
            "Даты нужно писать в формате ГГГГ-ММ-ДД."
        )
        return
    except Exception:
        logger.exception("Ошибка формирования календаря")
        await message.answer(
            "Не удалось сформировать календарь. Попробуй позже."
        )
        return

    document = BufferedInputFile(
        file=result["ics_content"].encode("utf-8"),
        filename=result["filename"]
    )

    await message.answer_document(
        document=document,
        caption=(
            f"Расписание с {start_date} по {end_date}.\n"
            f"Событий: {result['events_count']}.\n"
            "Время встреч указано как местное время календаря."
        )
    )


@router.message()
async def handle_user_text(message: types.Message):
    if not message.text:
        return
        
    # Показываем статус "печатает..." в Telegram пока агент выполняет ReAct цикл
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    
    try:
        reply = await orchestrator.process_user_message(
            chat_id=message.chat.id,
            user_text=message.text
        )
        await message.answer(reply)
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения пользователя: {e}", exc_info=True)
        await message.answer(f"Произошла ошибка при обработке запроса: {e}")
