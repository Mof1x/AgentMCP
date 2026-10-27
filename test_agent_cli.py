import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import settings
from database.seed_data import seed
from agent.orchestrator import AgentOrchestrator


async def cli_mode():
    print("=" * 65)
    print("🤖 КОНСОЛЬНЫЙ ТЕСТОВЫЙ РЕЖИМ АГЕНТА С MCP")
    print("=" * 65)
    print(f"Модель: {settings.LLM_MODEL}")
    print(f"База данных: {settings.DB_PATH}")
    print(f"MCP Сервер: {settings.MCP_SERVER_SCRIPT}")
    print("-" * 65)
    
    # Засеем тестовые данные для наглядности
    seed()
    
    orchestrator = AgentOrchestrator()
    test_chat_id = 99999
    
    print("\nПримеры запросов для проверки:")
    print(" 1. Что у меня запланировано на сегодня?")
    print(" 2. Запиши завтра к стоматологу на 16:00, это критически важно. Напомни за 2 часа.")
    print(" 3. Перенеси тренировку в зале на завтра на 12:30.")
    print(" 4. Какие дела с высоким или критическим приоритетом у меня есть?")
    print("Введите 'exit' или 'quit' для выхода.\n")
    
    while True:
        try:
            user_input = input("\n👤 Вы: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Выход из тестового режима.")
                break
                
            print("\n⏳ Агент думает и выполняет инструменты MCP...")
            reply = await orchestrator.process_user_message(
                chat_id=test_chat_id,
                user_text=user_input
            )
            print(f"\n🤖 Ответ Агента:\n{reply}\n")
            print("-" * 65)
        except (KeyboardInterrupt, EOFError):
            print("\nСессия завершена.")
            break


if __name__ == "__main__":
    asyncio.run(cli_mode())
