import asyncio
import logging
from aiogram import Bot
from database.db import get_connection
from config import settings

logger = logging.getLogger(__name__)

PRIORITY_ICONS = {
    1: "⚪ [Низкий]",
    2: "🟢 [Обычный]",
    3: "🟡 [Высокий]",
    4: "🔴 [КРИТИЧЕСКИЙ]"
}

async def check_and_send_reminders(bot: Bot):
    """
    Фоновая задача: периодически проверяет базу данных на наличие наступивших напоминаний
    и отправляет их пользователю в Telegram.
    """
    logger.info("Запущен фоновый воркер напоминаний.")
    
    while True:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Ищем неотправленные напоминания, время которых уже наступило
            query = """
                SELECT 
                    r.id AS reminder_id,
                    r.custom_message,
                    r.remind_before_minutes,
                    e.id AS event_id,
                    e.title,
                    e.description,
                    e.start_datetime,
                    e.priority,
                    e.chat_id,
                    c.name AS category_name
                FROM reminders r
                JOIN events e ON r.event_id = e.id
                LEFT JOIN categories c ON e.category_id = c.id
                WHERE r.is_sent = 0 
                  AND datetime(r.remind_at) <= datetime('now', 'localtime')
            """
            cursor.execute(query)
            pending = cursor.fetchall()
            
            for row in pending:
                reminder_id = row["reminder_id"]
                chat_id = row["chat_id"]
                title = row["title"]
                start_dt = row["start_datetime"]
                priority = row["priority"]
                custom_msg = row["custom_message"]
                category = row["category_name"] or "Общее"
                p_icon = PRIORITY_ICONS.get(priority, "📌")
                
                # Текст уведомления
                lines = [
                    f"⏰ <b>НАПОМИНАНИЕ О СОБЫТИИ!</b>",
                    f"{p_icon} <b>{title}</b>",
                    f"📁 Категория: {category}",
                    f"📅 Время начала: {start_dt}"
                ]
                if row["description"]:
                    lines.append(f"📝 Описание: {row['description']}")
                if custom_msg:
                    lines.append(f"\n💡 <i>{custom_msg}</i>")
                    
                message_text = "\n".join(lines)
                
                # Если chat_id известен — отправляем в Telegram
                if chat_id:
                    try:
                        await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="HTML")
                        logger.info(f"Напоминание #{reminder_id} отправлено в чат {chat_id}")
                    except Exception as send_err:
                        logger.error(f"Не удалось отправить напоминание #{reminder_id} в чат {chat_id}: {send_err}")
                else:
                    logger.warning(f"Напоминание #{reminder_id} готово к отправке, но chat_id не указан (событие создано вне бота).")
                
                # Помечаем напоминание как отправленное
                cursor.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))
                conn.commit()
                
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка в воркере напоминаний: {e}", exc_info=True)
            
        await asyncio.sleep(settings.REMINDER_CHECK_INTERVAL_SECONDS)
