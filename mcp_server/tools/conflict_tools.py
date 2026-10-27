from typing import Optional
from database.db import get_connection

PRIORITY_NAMES = {
    1: "LOW",
    2: "MEDIUM",
    3: "HIGH",
    4: "CRITICAL"
}

def check_time_conflict(
    start_datetime: str,
    end_datetime: Optional[str] = None,
    exclude_event_id: Optional[int] = None
) -> dict:
    """
    Проверяет, пересекается ли указанный интервал времени с уже запланированными делами.
    Учитывает уровни важности конфликтующих событий, помогая агенту принять решение о переносе или предупреждении.
    
    :param start_datetime: Дата и время начала в формате 'YYYY-MM-DD HH:MM:SS'
    :param end_datetime: Дата и время окончания (если не указано, считается +1 час от начала)
    :param exclude_event_id: ID события, которое нужно исключить из проверки (актуально при переносе существующего дела)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Если конечное время не передано, берем по умолчанию 1 час интервала
        query = """
            SELECT 
                e.id, 
                e.title, 
                e.description, 
                e.start_datetime, 
                COALESCE(e.end_datetime, datetime(e.start_datetime, '+1 hour')) AS effective_end,
                e.priority, 
                e.status,
                c.name AS category_name
            FROM events e
            LEFT JOIN categories c ON e.category_id = c.id
            WHERE e.status = 'planned'
              AND (
                  datetime(e.start_datetime) < datetime(COALESCE(?, datetime(?, '+1 hour')))
                  AND datetime(COALESCE(e.end_datetime, datetime(e.start_datetime, '+1 hour'))) > datetime(?)
              )
        """
        params = [end_datetime, start_datetime, start_datetime]
        
        if exclude_event_id is not None:
            query += " AND e.id != ?"
            params.append(exclude_event_id)
            
        cursor.execute(query, params)
        conflicts = []
        for row in cursor.fetchall():
            conflicts.append({
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "start_datetime": row["start_datetime"],
                "end_datetime": row["effective_end"],
                "priority": row["priority"],
                "priority_label": PRIORITY_NAMES.get(row["priority"], "UNKNOWN"),
                "category": row["category_name"]
            })
            
        return {
            "has_conflict": len(conflicts) > 0,
            "conflicts_count": len(conflicts),
            "conflicts": conflicts
        }
    finally:
        conn.close()
