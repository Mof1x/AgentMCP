from datetime import datetime

from database.db import get_connection


def get_day_summary(
    date: str,
    chat_id: int,
    day_start: str = "09:00",
    day_end: str = "21:00"
) -> dict:
    start = datetime.strptime(f"{date} {day_start}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{date} {day_end}", "%Y-%m-%d %H:%M")

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

    events_count = 0
    free_intervals = []
    current = start

    for event in events:
        busy_start = datetime.fromisoformat(event["busy_start"])
        busy_end = datetime.fromisoformat(event["busy_end"])

        if busy_end <= start or busy_start >= end:
            continue

        busy_start = max(busy_start, start)
        busy_end = min(busy_end, end)

        if busy_end <= busy_start:
            continue

        events_count += 1

        if busy_start > current:
            free_intervals.append((current, busy_start))

        current = max(current, busy_end)

    if current < end:
        free_intervals.append((current, end))

    total_seconds = (end - start).total_seconds()
    free_seconds = sum(
        (finish - begin).total_seconds()
        for begin, finish in free_intervals
    )
    busy_seconds = total_seconds - free_seconds

    longest_free_slot = None

    if free_intervals:
        longest_start, longest_end = max(
            free_intervals,
            key=lambda interval: interval[1] - interval[0]
        )

        longest_free_slot = {
            "start": longest_start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": longest_end.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_minutes": round(
                (longest_end - longest_start).total_seconds() / 60, 2
            )
        }

    return {
        "date": date,
        "day_start": day_start,
        "day_end": day_end,
        "events_count": events_count,
        "total_minutes": round(total_seconds / 60, 2),
        "busy_minutes": round(busy_seconds / 60, 2),
        "free_minutes": round(free_seconds / 60, 2),
        "load_percent": round(busy_seconds / total_seconds * 100, 1),
        "longest_free_slot": longest_free_slot
    }