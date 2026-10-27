from database.db import get_connection

def get_db_schema() -> dict:
    """
    Возвращает структуру реляционной базы данных: таблицы, колонки, типы данных, ограничения и внешние ключи.
    Позволяет агенту динамически изучать схему БД без хардкода в промпте.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Получаем список пользовательских таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row["name"] for row in cursor.fetchall()]
        
        schema = {}
        for table in tables:
            # Колонки
            cursor.execute(f"PRAGMA table_info({table});")
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col["name"],
                    "type": col["type"],
                    "not_null": bool(col["notnull"]),
                    "default_value": col["dflt_value"],
                    "primary_key": bool(col["pk"])
                })
            
            # Внешние ключи
            cursor.execute(f"PRAGMA foreign_key_list({table});")
            foreign_keys = []
            for fk in cursor.fetchall():
                foreign_keys.append({
                    "from_column": fk["from"],
                    "to_table": fk["table"],
                    "to_column": fk["to"]
                })
                
            schema[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys
            }
            
        return {
            "tables": schema,
            "priority_levels": {
                1: "LOW (Бытовые мелочи, покупка продуктов, дела без жесткого дедлайна)",
                2: "MEDIUM (Обычные дела, тренировка, хобби, уборка)",
                3: "HIGH (Важные дела, рабочие встречи, созвоны, дедлайны)",
                4: "CRITICAL (Критически важные: врачи, экзамены, вылеты, поезда — нельзя двигать!)"
            },
            "status_values": ["planned", "completed", "cancelled"]
        }
    finally:
        conn.close()
