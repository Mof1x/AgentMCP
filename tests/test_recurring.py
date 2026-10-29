import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from mcp_server.tools.recurring_tools import create_recurring_events


class TestRecurringEvents(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.db_path = Path(temporary_directory.name) / "test.db"

        with closing(self.connect()) as connection:
            connection.execute("""
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_datetime TEXT NOT NULL,
                    end_datetime TEXT,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'planned',
                    chat_id INTEGER,
                    is_all_day INTEGER DEFAULT 0
                )
            """)
            connection.commit()

        connection_patch = patch(
            "mcp_server.tools.recurring_tools.get_connection",
            side_effect=self.connect
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def add_event(self, start, end, chat_id=1, status="planned",
                  is_all_day=0):
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO events (
                    title, start_datetime, end_datetime,
                    chat_id, status, is_all_day
                )
                VALUES ('Существующее дело', ?, ?, ?, ?, ?)
                """,
                (start, end, chat_id, status, is_all_day)
            )
            connection.commit()

    def event_count(self):
        with closing(self.connect()) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]

    def create_series(self, occurrences=3):
        return create_recurring_events(
            title="Тренировка",
            first_start="2026-11-01 10:00:00",
            chat_id=1,
            duration_minutes=60,
            repeat_every_days=7,
            occurrences=occurrences,
            priority=2
        )

    def test_weekly_series(self):
        result = self.create_series()

        self.assertTrue(result["success"])
        self.assertEqual(result["created_count"], 3)
        self.assertEqual(self.event_count(), 3)

        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM events ORDER BY start_datetime"
            ).fetchall()

        self.assertEqual(
            [row["start_datetime"] for row in rows],
            [
                "2026-11-01 10:00:00",
                "2026-11-08 10:00:00",
                "2026-11-15 10:00:00"
            ]
        )
        self.assertEqual(rows[0]["end_datetime"], "2026-11-01 11:00:00")
        self.assertEqual(rows[0]["chat_id"], 1)

    def test_conflict_prevents_entire_series(self):
        self.add_event(
            "2026-11-08 10:30:00",
            "2026-11-08 11:30:00"
        )

        result = self.create_series()

        self.assertFalse(result["success"])
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(
            result["conflicts"][0]["requested_start"],
            "2026-11-08 10:00:00"
        )
        self.assertEqual(self.event_count(), 1)

    def test_other_user_and_cancelled_events(self):
        self.add_event(
            "2026-11-01 10:00:00", "2026-11-01 11:00:00",
            chat_id=2
        )
        self.add_event(
            "2026-11-08 10:00:00", "2026-11-08 11:00:00",
            status="cancelled"
        )

        result = self.create_series()

        self.assertTrue(result["success"])
        self.assertEqual(result["created_count"], 3)
        self.assertEqual(self.event_count(), 5)

    def test_all_day_conflict(self):
        self.add_event("2026-11-15 00:00:00", None, is_all_day=1)

        result = self.create_series()

        self.assertFalse(result["success"])
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(self.event_count(), 1)

    def test_invalid_occurrences(self):
        with self.assertRaises(ValueError):
            self.create_series(occurrences=0)

        self.assertEqual(self.event_count(), 0)


if __name__ == "__main__":
    unittest.main()