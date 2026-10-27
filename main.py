import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в путь поиска
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from config import settings
from database.init_db import init_db
from bot.handlers import router
from bot.reminders_worker import check_and_send_reminders

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # 1. Проверяем и инициализируем базу данных
    init_db()

    # 2. Проверяем токен бота
    if not settings.TELEGRAM_BOT_TOKEN or "your_telegram_bot_token" in settings.TELEGRAM_BOT_TOKEN:
        logger.error(
            "\n" + "=" * 60 + "\n"
            "⚠️ ВНИМАНИЕ: Не указан TELEGRAM_BOT_TOKEN в файле .env!\n"
            "Пожалуйста, добавьте ваш токен от @BotFather в файл .env.\n"
            "Для тестирования агента без Telegram запустите:\n"
            "    python test_agent_cli.py\n"
            + "=" * 60
        )
        return

    # 3. Создаем бота и диспетчер
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # 4. Запускаем фоновый воркер напоминаний
    asyncio.create_task(check_and_send_reminders(bot))

    logger.info("🤖 Telegram-бот запущен и готов принимать сообщения...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
