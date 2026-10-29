from datetime import datetime
from typing import Optional

from database.db import get_connection


def get_overdue_events(
    chat_id: int,
    as_of: str,
    since: Optional[str] = None,
    limit: int = 50
) -> dict:
    current = datetime.strptime(as_of, "%Y-%m-%d %H:%M:%S")

    if not 1 <= limit <= 100:
        raise ValueError("Количество результатов должно быть от 1 до 100.")

    if since is not None:
        period_start = datetime.strptime(since, "%Y-%m-%d %H:%M:%S")

        if period_start > current:
            raise ValueError("Начало периода не должно быть позже проверки.")

    query = """
        WITH schedule AS (
            SELECT
                id,
                title,
                description,
                priority,
                start_datetime,
                end_datetime,
                is_all_day,
                datetime(
                    CASE WHEN is_all_day = 1
                         THEN COALESCE(
                             end_datetime,
                             datetime(date(start_datetime), '+1 day')
                         )
                         ELSE COALESCE(
                             end_datetime,
                             datetime(start_datetime, '+1 hour')
                         )
                    END
                ) AS effective_end
            FROM events
            WHERE chat_id = ?
              AND status = 'planned'
        )
        SELECT *
        FROM schedule
        WHERE effective_end <= datetime(?)
    """

    parameters = [chat_id, as_of]

    if since is not None:
        query += " AND effective_end >= datetime(?)"
        parameters.append(since)

    query += """
        ORDER BY priority DESC, effective_end, id
        LIMIT ?
    """
    parameters.append(limit + 1)

    connection = get_connection()

    try:
        rows = connection.execute(query, parameters).fetchall()
    finally:
        connection.close()

    has_more = len(rows) > limit
    events = []

    for row in rows[:limit]:
        event = dict(row)
        effective_end = datetime.fromisoformat(event["effective_end"])

        event["overdue_minutes"] = round(
            (current - effective_end).total_seconds() / 60,
            2
        )
        events.append(event)

    return {
        "as_of": as_of,
        "since": since,
        "events_count": len(events),
        "has_more": has_more,
        "events": events
    }