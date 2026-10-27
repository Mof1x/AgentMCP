import sqlite3
from pathlib import Path
from config import settings

def get_db_path() -> Path:
    path = Path(settings.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def get_connection() -> sqlite3.Connection:
    """Возвращает синхронное SQLite соединение со строковым доступом к колонкам."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
