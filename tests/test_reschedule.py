import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from mcp_server.tools.reschedule_tools import reschedule_event


class TestRescheduleEvent(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.db_path = Path(temporary_directory.name) / "test.db"

        with closing(self.connect()) as connection:
            connection.executescript("""
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    start_datetime TEXT NOT NULL,
                    end_datetime TEXT,
                    status TEXT DEFAULT 'planned',
                    chat_id INTEGER,
                    is_all_day INTEGER DEFAULT 0
                );

                CREATE TABLE reminders (
                    id INTEGER PRIMARY KEY,
                    event_id INTEGER,
                    remind_at TEXT NOT NULL,
                    is_sent INTEGER DEFAULT 0
                );

                INSERT INTO events (
                    id, title, start_datetime, end_datetime, chat_id
                )
                VALUES (
                    1, 'Встреча',
                    '2026-11-01 15:00:00',
                    '2026-11-01 16:00:00',
                    1
                );

                INSERT INTO reminders
                VALUES (1, 1, '2026-11-01 14:30:00', 0);

                INSERT INTO reminders
                VALUES (2, 1, '2026-11-01 13:00:00', 1);
            """)
            connection.commit()

        connection_patch = patch(
            "mcp_server.tools.reschedule_tools.get_connection",
            side_effect=self.connect
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def execute(self, query):
        with closing(self.connect()) as connection:
            connection.execute(query)
            connection.commit()

    def snapshot(self):
        with closing(self.connect()) as connection:
            events = connection.execute(
                "SELECT * FROM events ORDER BY id"
            ).fetchall()
            reminders = connection.execute(
                "SELECT * FROM reminders ORDER BY id"
            ).fetchall()

        return {
            "events": [dict(row) for row in events],
            "reminders": [dict(row) for row in reminders]
        }

    def move(self, chat_id=1, new_start="2026-11-01 17:00:00"):
        return reschedule_event(
            event_id=1,
            new_start=new_start,
            chat_id=chat_id
        )

    def test_move_with_pending_reminder(self):
        result = self.move()
        state = self.snapshot()

        self.assertTrue(result["success"])
        self.assertEqual(result["shifted_reminders_count"], 1)
        self.assertEqual(
            state["events"][0]["start_datetime"],
            "2026-11-01 17:00:00"
        )
        self.assertEqual(
            state["events"][0]["end_datetime"],
            "2026-11-01 18:00:00"
        )
        self.assertEqual(
            state["reminders"][0]["remind_at"],
            "2026-11-01 16:30:00"
        )
        self.assertEqual(
            state["reminders"][1]["remind_at"],
            "2026-11-01 13:00:00"
        )
        self.assertEqual(state["reminders"][1]["is_sent"], 1)

    def test_conflict_changes_nothing(self):
        self.execute("""
            INSERT INTO events (
                id, title, start_datetime, end_datetime, chat_id
            )
            VALUES (
                2, 'Другое дело',
                '2026-11-01 17:30:00',
                '2026-11-01 18:30:00',
                1
            )
        """)
        before = self.snapshot()

        result = self.move()

        self.assertFalse(result["success"])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(self.snapshot(), before)

    def test_wrong_user_changes_nothing(self):
        before = self.snapshot()

        result = self.move(chat_id=2)

        self.assertFalse(result["success"])
        self.assertEqual(self.snapshot(), before)

    def test_event_does_not_conflict_with_itself(self):
        before = self.snapshot()

        result = self.move(new_start="2026-11-01 15:30:00")

        self.assertTrue(result["success"])
        self.assertEqual(result["new_end"], "2026-11-01 16:30:00")
        self.assertEqual(
            self.snapshot()["reminders"][0]["remind_at"],
            "2026-11-01 15:00:00"
        )
        self.assertEqual(
            self.snapshot()["reminders"][1],
            before["reminders"][1]
        )

    def test_missing_end_means_one_hour(self):
        self.execute("UPDATE events SET end_datetime = NULL WHERE id = 1")

        result = self.move()

        self.assertTrue(result["success"])
        self.assertEqual(
            self.snapshot()["events"][0]["end_datetime"],
            "2026-11-01 18:00:00"
        )

    def test_all_day_event_is_not_changed(self):
        self.execute("UPDATE events SET is_all_day = 1 WHERE id = 1")
        before = self.snapshot()

        result = self.move()

        self.assertFalse(result["success"])
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()