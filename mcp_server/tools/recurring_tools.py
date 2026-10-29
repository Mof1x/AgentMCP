from datetime import datetime, timedelta

from database.db import get_connection


def create_recurring_events(
    title: str,
    first_start: str,
    chat_id: int,
    duration_minutes: int = 60,
    repeat_every_days: int = 7,
    occurrences: int = 4,
    priority: int = 2
) -> dict:
    title = title.strip()

    if not title:
        raise ValueError("Название события не должно быть пустым.")

    if not 1 <= duration_minutes <= 1440:
        raise ValueError("Длительность должна быть от 1 до 1440 минут.")

    if not 1 <= repeat_every_days <= 365:
        raise ValueError("Интервал повторения должен быть от 1 до 365 дней.")

    if not 1 <= occurrences <= 52:
        raise ValueError("Количество повторов должно быть от 1 до 52.")

    if not 1 <= priority <= 4:
        raise ValueError("Важность должна быть от 1 до 4.")

    first = datetime.strptime(first_start, "%Y-%m-%d %H:%M:%S")
    duration = timedelta(minutes=duration_minutes)
    planned_events = []

    for number in range(occurrences):
        start = first + timedelta(days=number * repeat_every_days)
        end = start + duration

        planned_events.append({
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S")
        })

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        conflicts = []

        for event in planned_events:
            rows = connection.execute(
                """
                WITH schedule AS (
                    SELECT
                        id,
                        title,
                        priority,
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
                )
                SELECT *
                FROM schedule
                WHERE busy_start < datetime(?)
                  AND busy_end > datetime(?)
                ORDER BY busy_start
                """,
                (chat_id, event["end"], event["start"])
            ).fetchall()

            for row in rows:
                conflicts.append({
                    "requested_start": event["start"],
                    "requested_end": event["end"],
                    "existing_event_id": row["id"],
                    "existing_title": row["title"],
                    "existing_start": row["busy_start"],
                    "existing_end": row["busy_end"],
                    "existing_priority": row["priority"]
                })

        if conflicts:
            connection.rollback()

            return {
                "success": False,
                "created_count": 0,
                "conflicts": conflicts,
                "message": "Обнаружены конфликты. Серия не создана."
            }

        created_events = []

        for event in planned_events:
            cursor = connection.execute(
                """
                INSERT INTO events (
                    title,
                    start_datetime,
                    end_datetime,
                    priority,
                    status,
                    chat_id
                )
                VALUES (?, ?, ?, ?, 'planned', ?)
                """,
                (
                    title,
                    event["start"],
                    event["end"],
                    priority,
                    chat_id
                )
            )

            created_events.append({
                "id": cursor.lastrowid,
                "title": title,
                "start": event["start"],
                "end": event["end"]
            })

        connection.commit()

        return {
            "success": True,
            "created_count": len(created_events),
            "events": created_events,
            "conflicts": []
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()