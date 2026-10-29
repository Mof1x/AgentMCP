import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from database.init_db import INIT_SQL
from mcp_server.tools.creation_tools import create_event_with_reminders, get_creation_result


class TestAtomicCreation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        with closing(self.connect()) as connection:
            connection.executescript(INIT_SQL)
        patcher = patch("mcp_server.tools.creation_tools.get_connection", side_effect=self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create(self, **changes):
        args = dict(title="Встреча", start_datetime="2026-11-01 15:00:00",
                    chat_id=1, operation_id="test-operation",
                    reminders=[{"remind_at": "2026-11-01 14:00:00"},
                               {"remind_at": "2026-11-01 14:30:00", "custom_message": "Пора"}])
        args.update(changes)
        return create_event_with_reminders(**args)

    def counts(self):
        with closing(self.connect()) as connection:
            return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("events", "reminders", "creation_receipts"))

    def test_creates_event_reminders_and_receipt(self):
        result = self.create()
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["end"], "2026-11-01 16:00:00")
        self.assertEqual(self.counts(), (1, 2, 1))
        self.assertEqual(get_creation_result("test-operation", 1), result)
        with closing(self.connect()) as connection:
            self.assertEqual([row[0] for row in connection.execute(
                "SELECT remind_before_minutes FROM reminders ORDER BY id")], [60, 30])

    def test_second_reminder_failure_rolls_back_everything(self):
        with closing(self.connect()) as connection:
            connection.executescript("""
                CREATE TRIGGER reject_second BEFORE INSERT ON reminders
                WHEN NEW.remind_at = '2026-11-01 14:30:00'
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END;
            """)
        with self.assertLogs("mcp_server.tools.creation_tools", level="ERROR"):
            result = self.create()
        self.assertEqual(result["status"], "not_saved")
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_receipt_failure_rolls_back_event_and_reminders(self):
        with closing(self.connect()) as connection:
            connection.executescript("""
                CREATE TRIGGER reject_receipt BEFORE INSERT ON creation_receipts
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END;
            """)
        with self.assertLogs("mcp_server.tools.creation_tools", level="ERROR"):
            result = self.create()
        self.assertEqual(result["status"], "not_saved")
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_retry_returns_receipt_without_duplicate(self):
        first = self.create()
        self.assertEqual(self.create(), first)
        self.assertEqual(self.counts(), (1, 2, 1))

    def test_concurrent_retry_creates_once(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.create(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["status"], "saved")
        self.assertEqual(self.counts(), (1, 2, 1))

    def test_operation_id_cannot_be_reused_for_changed_payload_or_user(self):
        self.create()
        self.assertEqual(self.create(title="Другое")["status"], "not_saved")
        result = self.create(chat_id=2)
        self.assertEqual(result["status"], "not_saved")
        self.assertNotIn("event_id", result)
        self.assertEqual(get_creation_result("test-operation", 2), {"status": "unknown"})
        self.assertEqual(self.counts(), (1, 2, 1))

    def test_missing_receipt_is_unknown(self):
        self.assertEqual(get_creation_result("missing", 1), {"status": "unknown"})

    def test_conflict_does_not_create_reminders_or_receipt(self):
        self.create()
        result = self.create(operation_id="second")
        self.assertEqual(result["status"], "not_saved")
        self.assertTrue(result["conflicts"])
        self.assertEqual(self.counts(), (1, 2, 1))

    def test_other_chat_does_not_conflict(self):
        self.create()
        self.assertEqual(self.create(chat_id=2, operation_id="other")["status"], "saved")
        self.assertEqual(self.counts(), (2, 4, 2))

    def test_all_day_and_without_reminders(self):
        result = self.create(start_datetime="2026-11-01 00:00:00", is_all_day=True, reminders=[])
        self.assertEqual(result["end"], "2026-11-02 00:00:00")
        self.assertEqual(self.counts(), (1, 0, 1))
        self.assertEqual(self.create(operation_id="overlap")["status"], "not_saved")

    def test_invalid_input_does_not_write(self):
        for changes in ({"title": " "}, {"priority": 0},
                        {"end_datetime": "2026-11-01 14:00:00"},
                        {"reminders": [{"remind_at": "bad-date"}]},
                        {"is_all_day": True}):
            with self.subTest(changes=changes):
                self.assertEqual(self.create(**changes)["status"], "not_saved")
                self.assertEqual(self.counts(), (0, 0, 0))

    def test_commit_acknowledgement_failure_is_recoverable(self):
        connection = self.connect()

        class LostCommitReply:
            def __getattr__(self, name):
                return getattr(connection, name)

            def commit(self):
                connection.commit()
                raise sqlite3.OperationalError("commit response lost")

        with patch("mcp_server.tools.creation_tools.get_connection", return_value=LostCommitReply()):
            with self.assertLogs("mcp_server.tools.creation_tools", level="ERROR"):
                self.assertEqual(self.create()["status"], "unknown")
        recovered = get_creation_result("test-operation", 1)
        self.assertEqual(recovered["status"], "saved")
        self.assertEqual(self.create(), recovered)
        self.assertEqual(self.counts(), (1, 2, 1))
