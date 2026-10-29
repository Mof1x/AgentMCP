from datetime import datetime, timedelta

from database.db import get_connection


def find_free_slots(
    date: str,
    chat_id: int,
    duration_minutes: int = 60,
    day_start: str = "09:00",
    day_end: str = "21:00",
    buffer_minutes: int = 0
) -> dict:
    start = datetime.strptime(f"{date} {day_start}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{date} {day_end}", "%Y-%m-%d %H:%M")

    if duration_minutes <= 0:
        raise ValueError("Продолжительность должна быть больше нуля.")
    if not 0 <= buffer_minutes <= 1440:
        raise ValueError("Перерыв должен быть от 0 до 1440 минут.")

    buffer = timedelta(minutes=buffer_minutes)

    if start >= end:
        raise ValueError("Конец периода должен быть позже начала.")

    connection = get_connection()

    try:
        events = connection.execute(
            """
            SELECT
                datetime(
                    CASE WHEN is_all_day = 1
                         THEN date(start_datetime)
                         ELSE start_datetime
                    END
                ) AS busy_start,
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
                ) AS busy_end
            FROM events
            WHERE status = 'planned'
              AND chat_id = ?
            ORDER BY busy_start
            """,
            (chat_id,)
        ).fetchall()
    finally:
        connection.close()

    free_slots = []
    current = start
    required_duration = timedelta(minutes=duration_minutes)

    for event in events:
        busy_start = (
            datetime.fromisoformat(event["busy_start"]) - buffer
        )
        busy_end = (
            datetime.fromisoformat(event["busy_end"]) + buffer
        )

        if busy_end <= start or busy_start >= end:
            continue

        busy_start = max(busy_start, start)
        busy_end = min(busy_end, end)

        if busy_start - current >= required_duration:
            free_slots.append({
                "start": current.strftime("%Y-%m-%d %H:%M:%S"),
                "end": busy_start.strftime("%Y-%m-%d %H:%M:%S")
            })

        current = max(current, busy_end)

    if end - current >= required_duration:
        free_slots.append({
            "start": current.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "date": date,
        "duration_minutes": duration_minutes,
        "slots_count": len(free_slots),
        "free_slots": free_slots
    }