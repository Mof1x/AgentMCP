import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import datetime
from database.db import get_connection
from database.init_db import init_db

def seed():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    # Базовые категории
    categories = [
        (1, "Здоровье", "#E74C3C"),
        (2, "Работа", "#3498DB"),
        (3, "Личное", "#9B59B6"),
        (4, "Спорт", "#2ECC71"),
        (5, "Быт", "#F39C12"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO categories (id, name, color_code) VALUES (?, ?, ?)",
        categories
    )

    # Очистим старые тестовые события перед повторным сидом
    cursor.execute("DELETE FROM reminders")
    cursor.execute("DELETE FROM events")

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tomorrow = now + datetime.timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")

    events = [
        # (title, description, category_id, start_dt, end_dt, is_all_day, priority, status)
        (
            "Созвон по архитектуре проекта",
            "Обсудить интеграцию MCP и LLM с командой",
            2,
            f"{today_str} 15:00:00",
            f"{today_str} 16:00:00",
            0,
            3, # HIGH
            "planned"
        ),
        (
            "Тренировка в спортзале",
            "Кардио + базовые упражнения",
            4,
            f"{today_str} 19:00:00",
            f"{today_str} 20:30:00",
            0,
            2, # MEDIUM
            "planned"
        ),
        (
            "Прием у стоматолога",
            "Плановый осмотр и чистка в клинике Дента",
            1,
            f"{tomorrow_str} 12:00:00",
            f"{tomorrow_str} 13:00:00",
            0,
            4, # CRITICAL
            "planned"
        ),
        (
            "Купить продукты и бытовую химию",
            "Молоко, кофе, стиральный порошок",
            5,
            f"{tomorrow_str} 18:00:00",
            f"{tomorrow_str} 19:00:00",
            0,
            1, # LOW
            "planned"
        ),
    ]

    for ev in events:
        cursor.execute(
            """
            INSERT INTO events (title, description, category_id, start_datetime, end_datetime, is_all_day, priority, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ev
        )
        event_id = cursor.lastrowid

        # Добавим напоминание к приему у стоматолога (за 2 часа)
        if "стоматолог" in ev[0].lower():
            remind_dt = (tomorrow.replace(hour=10, minute=0, second=0)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO reminders (event_id, remind_at, remind_before_minutes, custom_message, is_sent)
                VALUES (?, ?, ?, ?, 0)
                """,
                (event_id, remind_dt, 120, "Напоминание: через 2 часа прием у стоматолога!")
            )

    conn.commit()
    conn.close()
    print("Тестовые данные успешно созданы!")

if __name__ == "__main__":
    seed()
