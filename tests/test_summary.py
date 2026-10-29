import sqlite3
import unittest
from unittest.mock import patch

from mcp_server.tools.summary_tools import get_day_summary


class TestDaySummary(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)

        self.connection.execute("""
            CREATE TABLE events (
                start_datetime TEXT,
                end_datetime TEXT,
                is_all_day INTEGER DEFAULT 0,
                status TEXT DEFAULT 'planned',
                chat_id INTEGER
            )
        """)

        connection_patch = patch(
            "mcp_server.tools.summary_tools.get_connection",
            return_value=self.connection
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def add_event(self, start, end, chat_id=1, status="planned",
                  is_all_day=0):
        self.connection.execute(
            """
            INSERT INTO events
            (start_datetime, end_datetime, chat_id, status, is_all_day)
            VALUES (?, ?, ?, ?, ?)
            """,
            (start, end, chat_id, status, is_all_day)
        )

    def summary(self):
        return get_day_summary(
            date="2026-11-01",
            chat_id=1,
            day_start="09:00",
            day_end="13:00"
        )

    def test_empty_day(self):
        result = self.summary()

        self.assertEqual(result["events_count"], 0)
        self.assertEqual(result["busy_minutes"], 0)
        self.assertEqual(result["free_minutes"], 240)
        self.assertEqual(result["load_percent"], 0)
        self.assertEqual(result["longest_free_slot"], {
            "start": "2026-11-01 09:00:00",
            "end": "2026-11-01 13:00:00",
            "duration_minutes": 240
        })

    def test_overlapping_events(self):
        self.add_event("2026-11-01 10:00:00", "2026-11-01 11:00:00")
        self.add_event("2026-11-01 10:30:00", "2026-11-01 12:00:00")

        result = self.summary()

        self.assertEqual(result["events_count"], 2)
        self.assertEqual(result["busy_minutes"], 120)
        self.assertEqual(result["free_minutes"], 120)
        self.assertEqual(result["load_percent"], 50)
        self.assertEqual(result["longest_free_slot"], {
            "start": "2026-11-01 09:00:00",
            "end": "2026-11-01 10:00:00",
            "duration_minutes": 60
        })

    def test_event_crossing_period_boundary(self):
        self.add_event("2026-11-01 08:00:00", "2026-11-01 10:00:00")

        result = self.summary()

        self.assertEqual(result["events_count"], 1)
        self.assertEqual(result["busy_minutes"], 60)
        self.assertEqual(result["free_minutes"], 180)
        self.assertEqual(result["load_percent"], 25)
        self.assertEqual(result["longest_free_slot"], {
            "start": "2026-11-01 10:00:00",
            "end": "2026-11-01 13:00:00",
            "duration_minutes": 180
        })

    def test_other_user_and_cancelled_events(self):
        self.add_event(
            "2026-11-01 09:00:00", "2026-11-01 13:00:00",
            chat_id=2
        )
        self.add_event(
            "2026-11-01 09:00:00", "2026-11-01 13:00:00",
            status="cancelled"
        )

        result = self.summary()

        self.assertEqual(result["events_count"], 0)
        self.assertEqual(result["busy_minutes"], 0)
        self.assertEqual(result["free_minutes"], 240)

    def test_all_day_event(self):
        self.add_event("2026-11-01 00:00:00", None, is_all_day=1)

        result = self.summary()

        self.assertEqual(result["events_count"], 1)
        self.assertEqual(result["busy_minutes"], 240)
        self.assertEqual(result["free_minutes"], 0)
        self.assertEqual(result["load_percent"], 100)
        self.assertIsNone(result["longest_free_slot"])


if __name__ == "__main__":
    unittest.main()