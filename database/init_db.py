import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database.db import get_connection

INIT_SQL = """
-- Категории дел
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color_code TEXT DEFAULT '#808080'
);

-- События / Записи в расписании
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    start_datetime DATETIME NOT NULL,
    end_datetime DATETIME,
    is_all_day BOOLEAN DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 4),
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned', 'completed', 'cancelled')),
    chat_id INTEGER -- Telegram Chat ID для персональных уведомлений
);

-- Напоминания
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    remind_at DATETIME NOT NULL,
    remind_before_minutes INTEGER,
    custom_message TEXT,
    is_sent BOOLEAN DEFAULT 0
);

-- Квитанция сохраняется вместе с событием и напоминаниями.
CREATE TABLE IF NOT EXISTS creation_receipts (
    operation_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_datetime);
CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority);
CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(is_sent, remind_at);
"""

def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executescript(INIT_SQL)
        conn.commit()
        print("База данных успешно инициализирована.")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
