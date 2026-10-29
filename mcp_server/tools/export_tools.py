from datetime import datetime, timedelta, timezone

from icalendar import Calendar, Event

from database.db import get_connection


def export_schedule(
    start_date: str,
    end_date: str,
    chat_id: int
) -> dict:
    first_day = datetime.strptime(start_date, "%Y-%m-%d").date()
    last_day = datetime.strptime(end_date, "%Y-%m-%d").date()

    if last_day < first_day:
        raise ValueError("Конечная дата не должна быть раньше начальной.")

    if (last_day - first_day).days >= 366:
        raise ValueError("Можно экспортировать не больше 366 дней.")

    period_start = datetime.combine(first_day, datetime.min.time())
    period_end = datetime.combine(
        last_day + timedelta(days=1),
        datetime.min.time()
    )

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            WITH schedule AS (
                SELECT
                    *,
                    datetime(
                        CASE WHEN is_all_day = 1
                             THEN date(start_datetime)
                             ELSE start_datetime
                        END
                    ) AS effective_start,
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
            WHERE effective_start < datetime(?)
              AND effective_end > datetime(?)
            ORDER BY effective_start, id
            """,
            (
                chat_id,
                period_end.strftime("%Y-%m-%d %H:%M:%S"),
                period_start.strftime("%Y-%m-%d %H:%M:%S")
            )
        ).fetchall()
    finally:
        connection.close()

    calendar = Calendar()
    calendar.add("prodid", "-//AgentMCP//Personal Schedule//RU")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")

    priority_values = {1: 9, 2: 5, 3: 3, 4: 1}
    exported_count = 0

    for row in rows:
        start = datetime.fromisoformat(row["effective_start"])
        end = datetime.fromisoformat(row["effective_end"])

        if end <= start:
            raise ValueError(
                f"У события #{row['id']} неверная длительность."
            )

        event = Event()
        event.add("uid", f"event-{chat_id}-{row['id']}@agentmcp.local")
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("summary", row["title"])
        event.add("status", "CONFIRMED")
        event.add("priority", priority_values.get(row["priority"], 5))

        if row["description"]:
            event.add("description", row["description"])

        if row["is_all_day"]:
            if end.date() <= start.date():
                raise ValueError(
                    f"У события на весь день #{row['id']} "
                    "конец должен приходиться на следующий день или позже."
                )

            event.add("dtstart", start.date())
            event.add("dtend", end.date())
        else:
            event.add("dtstart", start)
            event.add("dtend", end)

        calendar.add_component(event)
        exported_count += 1

    return {
        "success": True,
        "filename": f"schedule_{start_date}_{end_date}.ics",
        "events_count": exported_count,
        "ics_content": calendar.to_ical().decode("utf-8")
    }