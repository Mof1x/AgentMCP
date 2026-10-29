import sqlite3
import unittest
from unittest.mock import patch

from mcp_server.tools.free_slots_tools import find_free_slots


class TestFreeSlots(unittest.TestCase):
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

        self.mock_connection = patch(
            "mcp_server.tools.free_slots_tools.get_connection",
            return_value=self.connection
        )
        self.mock_connection.start()
        self.addCleanup(self.mock_connection.stop)

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

    def search(self):
        return find_free_slots(
            date="2026-11-01",
            chat_id=1,
            duration_minutes=60,
            day_start="09:00",
            day_end="13:00"
        )

    def test_empty_schedule(self):
        result = self.search()
        self.assertEqual(result["free_slots"], [
            {"start": "2026-11-01 09:00:00",
             "end": "2026-11-01 13:00:00"}
        ])

    def test_overlapping_events(self):
        self.add_event("2026-11-01 10:00:00", "2026-11-01 11:00:00")
        self.add_event("2026-11-01 10:30:00", "2026-11-01 12:30:00")

        result = self.search()

        self.assertEqual(result["free_slots"], [
            {"start": "2026-11-01 09:00:00",
             "end": "2026-11-01 10:00:00"}
        ])

    def test_other_user_and_cancelled_events(self):
        self.add_event(
            "2026-11-01 09:00:00", "2026-11-01 13:00:00",
            chat_id=2
        )
        self.add_event(
            "2026-11-01 09:00:00", "2026-11-01 13:00:00",
            status="cancelled"
        )

        result = self.search()
        self.assertEqual(result["free_slots"], [
            {"start": "2026-11-01 09:00:00",
             "end": "2026-11-01 13:00:00"}
        ])

    def test_all_day_event(self):
        self.add_event("2026-11-01 00:00:00", None, is_all_day=1)

        result = self.search()

        self.assertEqual(result["slots_count"], 0)
        self.assertEqual(result["free_slots"], [])


    def test_buffer_between_events(self):
        self.add_event("2026-11-01 11:00:00", "2026-11-01 12:00:00")

        result = find_free_slots(
            date="2026-11-01",
            chat_id=1,
            duration_minutes=30,
            day_start="09:00",
            day_end="13:00",
            buffer_minutes=15
        )

        self.assertEqual(result["free_slots"], [
            {"start": "2026-11-01 09:00:00",
             "end": "2026-11-01 10:45:00"},
            {"start": "2026-11-01 12:15:00",
             "end": "2026-11-01 13:00:00"}
        ])

    def test_buffer_from_event_outside_period(self):
        self.add_event("2026-11-01 08:00:00", "2026-11-01 09:00:00")

        result = find_free_slots(
            date="2026-11-01",
            chat_id=1,
            duration_minutes=60,
            day_start="09:00",
            day_end="13:00",
            buffer_minutes=15
        )

        self.assertEqual(result["free_slots"], [
            {"start": "2026-11-01 09:15:00",
             "end": "2026-11-01 13:00:00"}
        ])


if __name__ == "__main__":
    unittest.main()