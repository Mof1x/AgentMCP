from datetime import datetime, timedelta

from database.db import get_connection


def reschedule_event(
    event_id: int,
    new_start: str,
    chat_id: int
) -> dict:
    new_start_dt = datetime.strptime(new_start, "%Y-%m-%d %H:%M:%S")
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        event = connection.execute(
            """
            SELECT *
            FROM events
            WHERE id = ?
              AND chat_id = ?
              AND status = 'planned'
            """,
            (event_id, chat_id)
        ).fetchone()

        if event is None:
            connection.rollback()
            return {
                "success": False,
                "message": "Запланированное событие пользователя не найдено."
            }

        if event["is_all_day"]:
            connection.rollback()
            return {
                "success": False,
                "message": "Эта функция переносит только события со временем."
            }

        old_start = datetime.fromisoformat(event["start_datetime"])

        if event["end_datetime"]:
            old_end = datetime.fromisoformat(event["end_datetime"])
        else:
            old_end = old_start + timedelta(hours=1)

        duration = old_end - old_start

        if duration.total_seconds() <= 0:
            raise ValueError("У исходного события неверная длительность.")

        shift = new_start_dt - old_start
        new_end_dt = new_start_dt + duration
        new_end = new_end_dt.strftime("%Y-%m-%d %H:%M:%S")

        rows = connection.execute(
            """
            WITH schedule AS (
                SELECT
                    id,
                    title,
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
                  AND id != ?
            )
            SELECT *
            FROM schedule
            WHERE busy_start < datetime(?)
              AND busy_end > datetime(?)
            ORDER BY busy_start
            """,
            (chat_id, event_id, new_end, new_start)
        ).fetchall()

        if rows:
            connection.rollback()
            return {
                "success": False,
                "message": "Найден конфликт. Событие и напоминания не изменены.",
                "conflicts": [dict(row) for row in rows]
            }

        reminders = connection.execute(
            """
            SELECT id, remind_at
            FROM reminders
            WHERE event_id = ?
              AND is_sent = 0
            """,
            (event_id,)
        ).fetchall()

        shifted_reminders = []

        for reminder in reminders:
            old_remind_at = datetime.fromisoformat(reminder["remind_at"])
            new_remind_at = (old_remind_at + shift).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            shifted_reminders.append({
                "id": reminder["id"],
                "remind_at": new_remind_at
            })

        connection.execute(
            """
            UPDATE events
            SET start_datetime = ?, end_datetime = ?
            WHERE id = ? AND chat_id = ?
            """,
            (new_start, new_end, event_id, chat_id)
        )

        for reminder in shifted_reminders:
            connection.execute(
                """
                UPDATE reminders
                SET remind_at = ?
                WHERE id = ? AND event_id = ? AND is_sent = 0
                """,
                (reminder["remind_at"], reminder["id"], event_id)
            )

        connection.commit()

        return {
            "success": True,
            "event_id": event_id,
            "title": event["title"],
            "old_start": event["start_datetime"],
            "new_start": new_start,
            "new_end": new_end,
            "shifted_reminders_count": len(shifted_reminders),
            "shifted_reminders": shifted_reminders
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()