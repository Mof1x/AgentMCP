import asyncio
import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import settings
from database.seed_data import seed
from mcp_server.tools.datetime_tools import get_current_datetime
from mcp_server.tools.schema_tools import get_db_schema
from mcp_server.tools.conflict_tools import check_time_conflict
from mcp_server.tools.query_tools import execute_read_query, execute_write_query
from agent.mcp_client import MCPClient

class TestScheduleMCPTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        db_patch = patch.object(settings, "DB_PATH", str(Path(directory.name) / "tools.db"))
        db_patch.start()
        cls.addClassCleanup(db_patch.stop)
        seed()

    def test_01_get_current_datetime(self):
        dt = get_current_datetime()
        self.assertIn("current_date", dt)
        self.assertIn("current_time", dt)
        self.assertIn("weekday", dt)
        self.assertTrue(len(dt["current_date"]) == 10)

    def test_02_get_db_schema(self):
        schema = get_db_schema()
        self.assertIn("tables", schema)
        self.assertIn("events", schema["tables"])
        self.assertIn("reminders", schema["tables"])
        self.assertIn("categories", schema["tables"])
        self.assertIn("priority_levels", schema)

    def test_03_execute_read_query_safe(self):
        rows = execute_read_query("SELECT id, title, priority FROM events WHERE status = 'planned'")
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)

    def test_04_execute_read_query_blocks_destructive(self):
        with self.assertRaises(ValueError):
            execute_read_query("DROP TABLE events")
            
        with self.assertRaises(ValueError):
            execute_read_query("SELECT * FROM events; DELETE FROM events;")

    def test_05_check_time_conflict(self):
        # В seed_data запланирован созвон сегодня в 15:00:00
        now_dt = get_current_datetime()["current_date"]
        conflict_res = check_time_conflict(f"{now_dt} 15:30:00", f"{now_dt} 16:30:00")
        self.assertTrue(conflict_res["has_conflict"])
        self.assertGreater(conflict_res["conflicts_count"], 0)
        self.assertEqual(conflict_res["conflicts"][0]["priority_label"], "HIGH")

    def test_06_execute_write_query(self):
        now_dt = get_current_datetime()["current_date"]
        insert_res = execute_write_query(
            f"INSERT INTO events (title, start_datetime, priority, status) "
            f"VALUES ('Тестовое дело', '{now_dt} 22:00:00', 1, 'planned')"
        )
        self.assertTrue(insert_res["success"])
        self.assertEqual(insert_res["rows_affected"], 1)

    def test_07_mcp_client_stdio_connection(self):
        async def run_mcp_check():
            client = MCPClient()
            async with client.session_context() as session:
                tools = await session.get_openai_tools()
                tool_names = [t["function"]["name"] for t in tools]
                self.assertIn("get_current_datetime", tool_names)
                self.assertIn("get_db_schema", tool_names)
                self.assertIn("check_time_conflict", tool_names)
                self.assertIn("execute_read_query", tool_names)
                self.assertIn("execute_write_query", tool_names)
                self.assertIn("find_free_slots", tool_names)
                self.assertIn("get_day_summary", tool_names)
                self.assertIn("create_recurring_events", tool_names)
                self.assertIn("reschedule_event", tool_names)
                self.assertIn("export_schedule", tool_names)
                self.assertIn("get_overdue_events", tool_names)

                # Вызов инструмента через протокол MCP
                res_str = await session.call_tool("get_current_datetime", {})
                self.assertIn("current_date", res_str)

        asyncio.run(run_mcp_check())


if __name__ == "__main__":
    unittest.main()
