from database.db import get_connection

def execute_read_query(query: str) -> list[dict]:
    """
    Выполняет безопасный SELECT-запрос к базе данных для чтения расписания, категорий и напоминаний.
    Запрещены любые модифицирующие и деструктивные операции (INSERT, UPDATE, DELETE, DROP и др.).
    
    :param query: SQL-запрос на чтение, начинающийся с SELECT или WITH.
    """
    cleaned = query.strip()
    upper = cleaned.upper()
    
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("Ошибка безопасности: execute_read_query предназначен ТОЛЬКО для запросов чтения (SELECT / WITH).")
    
    forbidden_tokens = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "REPLACE ", "CREATE "]
    for token in forbidden_tokens:
        if token in upper:
            raise ValueError(f"Ошибка безопасности: обнаружен запрещенный оператор '{token.strip()}' в запросе на чтение.")
            
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(cleaned)
        rows = [dict(row) for row in cursor.fetchall()]
        return rows
    except Exception as e:
        return [{"error": f"SQL Error: {str(e)}"}]
    finally:
        conn.close()


def execute_write_query(query: str) -> dict:
    """
    Выполняет SQL-запрос на создание, изменение или удаление записей в расписании и напоминаниях (INSERT, UPDATE, DELETE).
    Деструктивные операции со схемой (DROP, ALTER, TRUNCATE) строго запрещены.
    
    :param query: SQL-запрос (INSERT, UPDATE или DELETE).
    """
    cleaned = query.strip()
    upper = cleaned.upper()
    
    allowed_start = ("INSERT ", "UPDATE ", "DELETE ")
    if not any(upper.startswith(prefix) for prefix in allowed_start):
        raise ValueError("Ошибка безопасности: execute_write_query предназначен ТОЛЬКО для INSERT, UPDATE или DELETE.")
        
    forbidden_tokens = ["DROP ", "ALTER ", "TRUNCATE ", "ATTACH ", "DETACH "]
    for token in forbidden_tokens:
        if token in upper:
            raise ValueError(f"Ошибка безопасности: выполнение DDL-операции '{token.strip()}' запрещено.")
            
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(cleaned)
        conn.commit()
        return {
            "success": True,
            "rows_affected": cursor.rowcount,
            "last_insert_rowid": cursor.lastrowid
        }
    except Exception as e:
        conn.rollback()
        return {
            "success": False,
            "error": f"SQL Error: {str(e)}"
        }
    finally:
        conn.close()
