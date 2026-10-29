import sqlite3
import unittest
from datetime import date, datetime
from unittest.mock import patch

from icalendar import Calendar

from mcp_server.tools.export_tools import export_schedule


class TestExportSchedule(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)

        self.connection.execute("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT,
                priority INTEGER DEFAULT 2,
                status TEXT DEFAULT 'planned',
                chat_id INTEGER,
                is_all_day INTEGER DEFAULT 0
            )
        """)

        connection_patch = patch(
            "mcp_server.tools.export_tools.get_connection",
            return_value=self.connection
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def add_event(self, start, end, chat_id=1, status="planned",
                  is_all_day=0, title="Встреча", description=None):
        self.connection.execute(
            """
            INSERT INTO events (
                title, description, start_datetime, end_datetime,
                chat_id, status, is_all_day
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, description, start, end, chat_id, status, is_all_day)
        )

    def export(self):
        return export_schedule(
            start_date="2026-11-01",
            end_date="2026-11-07",
            chat_id=1
        )

    def calendar_events(self, result):
        calendar = Calendar.from_ical(
            result["ics_content"].encode("utf-8")
        )
        return list(calendar.walk("VEVENT"))

    def test_timed_event_and_text(self):
        title = "Встреча, учёба; планы"
        description = "Первая строка\nВторая строка"

        self.add_event(
            "2026-11-01 15:00:00",
            "2026-11-01 16:00:00",
            title=title,
            description=description
        )

        result = self.export()
        events = self.calendar_events(result)

        self.assertEqual(result["events_count"], 1)
        self.assertEqual(
            result["filename"],
            "schedule_2026-11-01_2026-11-07.ics"
        )
        self.assertEqual(str(events[0]["SUMMARY"]), title)
        self.assertEqual(str(events[0]["DESCRIPTION"]), description)
        self.assertEqual(
            events[0].decoded("DTSTART"),
            datetime(2026, 11, 1, 15, 0)
        )
        self.assertEqual(
            events[0].decoded("DTEND"),
            datetime(2026, 11, 1, 16, 0)
        )
        self.assertIn("UID", events[0])
        self.assertIn("DTSTAMP", events[0])

    def test_all_day_event(self):
        self.add_event("2026-11-03 00:00:00", None, is_all_day=1)

        events = self.calendar_events(self.export())

        self.assertEqual(events[0].decoded("DTSTART"), date(2026, 11, 3))
        self.assertEqual(events[0].decoded("DTEND"), date(2026, 11, 4))

    def test_user_status_and_period_filter(self):
        self.add_event(
            "2026-11-07 23:00:00", "2026-11-08 01:00:00",
            title="В последний день"
        )
        self.add_event(
            "2026-10-31 23:00:00", "2026-11-01 01:00:00",
            title="Пересекает начало периода"
        )
        self.add_event(
            "2026-11-02 10:00:00", "2026-11-02 11:00:00",
            chat_id=2
        )
        self.add_event(
            "2026-11-03 10:00:00", "2026-11-03 11:00:00",
            status="cancelled"
        )
        self.add_event(
            "2026-11-08 00:00:00", "2026-11-08 01:00:00"
        )

        result = self.export()
        events = self.calendar_events(result)

        self.assertEqual(result["events_count"], 2)
        self.assertEqual(
            {str(event["SUMMARY"]) for event in events},
            {"В последний день", "Пересекает начало периода"}
        )
        self.assertEqual(
            events[0].decoded("DTSTART"),
            datetime(2026, 10, 31, 23, 0)
        )

    def test_empty_calendar(self):
        result = self.export()

        self.assertTrue(result["success"])
        self.assertEqual(result["events_count"], 0)
        self.assertEqual(self.calendar_events(result), [])

    def test_invalid_period(self):
        with self.assertRaises(ValueError):
            export_schedule(
                start_date="2026-11-07",
                end_date="2026-11-01",
                chat_id=1
            )


if __name__ == "__main__":
    unittest.main()