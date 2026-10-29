"""Atomic creation and durable receipts for uncertain MCP responses."""
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, ConfigDict
from database.db import get_connection

logger = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ReminderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remind_at: str
    custom_message: Optional[str] = None


def get_creation_result(operation_id: str, chat_id: int) -> dict:
    """Absence of a receipt does not prove that a pending call failed."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT result_json FROM creation_receipts WHERE operation_id = ? AND chat_id = ?",
            (operation_id, chat_id),
        ).fetchone()
        return json.loads(row["result_json"]) if row else {"status": "unknown"}
    finally:
        connection.close()


def create_event_with_reminders(
    title: str,
    start_datetime: str,
    chat_id: int,
    operation_id: str,
    end_datetime: Optional[str] = None,
    reminders: Optional[list[ReminderInput]] = None,
    description: Optional[str] = None,
    category_id: Optional[int] = None,
    priority: int = 2,
    is_all_day: bool = False,
) -> dict:
    """Save the event, every reminder and a replayable receipt together."""
    try:
        title = title.strip()
        if not title or not operation_id or len(operation_id) > 200:
            raise ValueError("Нужны название события и идентификатор операции.")
        if not 1 <= priority <= 4:
            raise ValueError("Важность должна быть от 1 до 4.")
        start = datetime.strptime(start_datetime, DATE_FORMAT)
        end = (datetime.strptime(end_datetime, DATE_FORMAT) if end_datetime
               else start + (timedelta(days=1) if is_all_day else timedelta(hours=1)))
        if end <= start:
            raise ValueError("Конец события должен быть позже начала.")
        if is_all_day and (start.time() != datetime.min.time() or end.time() != datetime.min.time()):
            raise ValueError("Границы события на весь день должны быть в 00:00:00.")
        normalized_reminders = []
        for item in reminders or []:
            reminder = ReminderInput.model_validate(item)
            remind_at = datetime.strptime(reminder.remind_at, DATE_FORMAT)
            normalized_reminders.append({
                "remind_at": remind_at.strftime(DATE_FORMAT),
                "custom_message": reminder.custom_message,
            })
        request = {
            "title": title, "start_datetime": start.strftime(DATE_FORMAT),
            "end_datetime": end.strftime(DATE_FORMAT), "chat_id": chat_id,
            "description": description, "category_id": category_id,
            "priority": priority, "is_all_day": is_all_day,
            "reminders": normalized_reminders,
        }
        request_json = json.dumps(request, ensure_ascii=False, sort_keys=True)
    except (ValueError, TypeError) as error:
        return {"success": False, "status": "not_saved", "message": str(error)}

    connection = None
    committing = False
    try:
        connection = get_connection()
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT * FROM creation_receipts WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if previous:
            connection.rollback()
            if previous["chat_id"] != chat_id or previous["request_json"] != request_json:
                return {"success": False, "status": "not_saved",
                        "message": "Идентификатор операции уже использован. Новые изменения не внесены."}
            return json.loads(previous["result_json"])

        conflicts = connection.execute(
            """
            WITH schedule AS (
                SELECT id, title,
                    datetime(CASE WHEN is_all_day = 1 THEN date(start_datetime)
                                  ELSE start_datetime END) AS busy_start,
                    datetime(CASE WHEN is_all_day = 1
                        THEN COALESCE(end_datetime, datetime(date(start_datetime), '+1 day'))
                        ELSE COALESCE(end_datetime, datetime(start_datetime, '+1 hour'))
                    END) AS busy_end
                FROM events WHERE chat_id = ? AND status = 'planned'
            )
            SELECT * FROM schedule
            WHERE busy_start < datetime(?) AND busy_end > datetime(?)
            ORDER BY busy_start
            """, (chat_id, request["end_datetime"], request["start_datetime"])
        ).fetchall()
        if conflicts:
            connection.rollback()
            return {"success": False, "status": "not_saved",
                    "message": "Есть пересечения. Событие и напоминания не сохранены.",
                    "conflicts": [dict(row) for row in conflicts]}

        cursor = connection.execute(
            """INSERT INTO events
               (title, description, category_id, start_datetime, end_datetime,
                is_all_day, priority, status, chat_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?)""",
            (title, description, category_id, request["start_datetime"],
             request["end_datetime"], is_all_day, priority, chat_id),
        )
        event_id = cursor.lastrowid
        saved_reminders = []
        for reminder in normalized_reminders:
            minutes = int((start - datetime.strptime(reminder["remind_at"], DATE_FORMAT)).total_seconds() / 60)
            cursor = connection.execute(
                """INSERT INTO reminders (event_id, remind_at, remind_before_minutes, custom_message)
                   VALUES (?, ?, ?, ?)""",
                (event_id, reminder["remind_at"], minutes, reminder["custom_message"]),
            )
            saved_reminders.append({"id": cursor.lastrowid, **reminder})
        result = {
            "success": True, "status": "saved", "operation_id": operation_id,
            "event_id": event_id, "title": title, "start": request["start_datetime"],
            "end": request["end_datetime"], "reminders": saved_reminders,
        }
        connection.execute(
            "INSERT INTO creation_receipts VALUES (?, ?, ?, ?)",
            (operation_id, chat_id, request_json, json.dumps(result, ensure_ascii=False)),
        )
        committing = True
        connection.commit()
        return result
    except sqlite3.Error:
        logger.exception("Ошибка атомарного создания события")
        try:
            if connection is not None:
                connection.rollback()
        except sqlite3.Error:
            committing = True
        if committing:
            # A failed acknowledgement of COMMIT must be reconciled via the receipt.
            return {"success": False, "status": "unknown",
                    "message": "Результат сохранения требует проверки."}
        return {"success": False, "status": "not_saved",
                "message": "Не удалось сохранить событие и напоминания. Изменения этой операции отменены."}
    finally:
        if connection is not None:
            connection.close()
