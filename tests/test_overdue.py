import sqlite3
import unittest
from unittest.mock import patch

from mcp_server.tools.overdue_tools import get_overdue_events


class TestOverdueEvents(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)

        self.connection.execute("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                priority INTEGER DEFAULT 2,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT,
                is_all_day INTEGER DEFAULT 0,
                status TEXT DEFAULT 'planned',
                chat_id INTEGER
            )
        """)

        connection_patch = patch(
            "mcp_server.tools.overdue_tools.get_connection",
            return_value=self.connection
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def add_event(self, title, start, end, priority=2, chat_id=1,
                  status="planned", is_all_day=0):
        self.connection.execute(
            """
            INSERT INTO events (
                title, start_datetime, end_datetime,
                priority, chat_id, status, is_all_day
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, start, end, priority, chat_id, status, is_all_day)
        )

    def search(self, since=None, limit=50):
        return get_overdue_events(
            chat_id=1,
            as_of="2026-11-08 12:00:00",
            since=since,
            limit=limit
        )

    def test_empty_schedule(self):
        result = self.search()

        self.assertEqual(result["events_count"], 0)
        self.assertEqual(result["events"], [])
        self.assertFalse(result["has_more"])

    def test_only_finished_planned_events_of_user(self):
        self.add_event(
            "Прошедшее дело",
            "2026-11-08 10:00:00", "2026-11-08 11:00:00"
        )
        self.add_event(
            "Ещё идёт",
            "2026-11-08 11:30:00", "2026-11-08 12:30:00"
        )
        self.add_event(
            "Будущее дело",
            "2026-11-08 13:00:00", "2026-11-08 14:00:00"
        )
        self.add_event(
            "Чужое дело",
            "2026-11-08 09:00:00", "2026-11-08 10:00:00",
            chat_id=2
        )
        self.add_event(
            "Выполнено",
            "2026-11-08 09:00:00", "2026-11-08 10:00:00",
            status="completed"
        )
        self.add_event(
            "Отменено",
            "2026-11-08 09:00:00", "2026-11-08 10:00:00",
            status="cancelled"
        )

        result = self.search()

        self.assertEqual(result["events_count"], 1)
        self.assertEqual(result["events"][0]["title"], "Прошедшее дело")
        self.assertEqual(result["events"][0]["overdue_minutes"], 60)

    def test_period_filters_by_end(self):
        self.add_event(
            "Старое дело",
            "2026-10-30 10:00:00", "2026-10-30 11:00:00"
        )
        self.add_event(
            "Пересекает границу",
            "2026-10-31 23:00:00", "2026-11-01 01:00:00"
        )

        result = self.search(since="2026-11-01 00:00:00")

        self.assertEqual(result["events_count"], 1)
        self.assertEqual(
            result["events"][0]["title"],
            "Пересекает границу"
        )

    def test_priority_and_limit(self):
        self.add_event(
            "Обычное дело",
            "2026-11-07 09:00:00", "2026-11-07 10:00:00",
            priority=2
        )
        self.add_event(
            "Критическое дело",
            "2026-11-07 11:00:00", "2026-11-07 12:00:00",
            priority=4
        )

        result = self.search(limit=1)

        self.assertEqual(result["events_count"], 1)
        self.assertTrue(result["has_more"])
        self.assertEqual(
            result["events"][0]["title"],
            "Критическое дело"
        )

    def test_default_end_and_all_day(self):
        self.add_event(
            "Без окончания",
            "2026-11-08 10:00:00", None
        )
        self.add_event(
            "Вчера весь день",
            "2026-11-07 00:00:00", None,
            is_all_day=1
        )
        self.add_event(
            "Сегодня весь день",
            "2026-11-08 00:00:00", None,
            is_all_day=1
        )

        result = self.search()
        events = {event["title"]: event for event in result["events"]}

        self.assertEqual(result["events_count"], 2)
        self.assertEqual(
            events["Без окончания"]["effective_end"],
            "2026-11-08 11:00:00"
        )
        self.assertEqual(
            events["Вчера весь день"]["effective_end"],
            "2026-11-08 00:00:00"
        )
        self.assertNotIn("Сегодня весь день", events)

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            self.search(limit=0)

        with self.assertRaises(ValueError):
            self.search(since="2026-11-09 00:00:00")


if __name__ == "__main__":
    unittest.main()