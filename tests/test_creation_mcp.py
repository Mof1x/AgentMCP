import json
import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager, closing
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from agent.mcp_client import MCPClient, MCPClientSessionWrapper
from agent.orchestrator import AgentOrchestrator
from config import settings
from database.init_db import INIT_SQL


class TestCreationMCP(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "integration.db"
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript(INIT_SQL)
        db_patch = patch.object(settings, "DB_PATH", str(self.path))
        db_patch.start()
        self.addCleanup(db_patch.stop)

    async def test_real_stdio_creation_replay_and_schema(self):
        client = MCPClient()
        async with client.session_context() as session:
            tools = await session.get_openai_tools()
            names = [tool["function"]["name"] for tool in tools]
            self.assertNotIn("get_creation_result", names)
            schema = next(tool["function"]["parameters"] for tool in tools
                          if tool["function"]["name"] == "create_event_with_reminders")
            for hidden in ("chat_id", "operation_id"):
                self.assertNotIn(hidden, schema["properties"])
                self.assertNotIn(hidden, schema.get("required", []))
            args = {"title": "Встреча", "start_datetime": "2026-11-01 15:00:00",
                    "chat_id": 1, "operation_id": "integration",
                    "reminders": [{"remind_at": "2026-11-01 14:00:00"}]}
            saved = json.loads(await session.call_tool("create_event_with_reminders", args))
            self.assertEqual(saved["status"], "saved")
            replay = json.loads(await session.call_tool("create_event_with_reminders", args))
            self.assertEqual(saved, replay)
            recovered = json.loads(await session.call_tool("get_creation_result", {
                "operation_id": "integration", "chat_id": 1}))
            self.assertEqual(saved, recovered)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reminders").fetchone()[0], 1)

    async def test_real_save_lost_reply_recovery_and_api_failure(self):
        args = {"title": "Встреча", "start_datetime": "2026-11-01 15:00:00",
                "reminders": [{"remind_at": "2026-11-01 14:00:00"}]}
        call = NS(id="first", function=NS(name="create_event_with_reminders", arguments=json.dumps(args)))
        api = AsyncMock(side_effect=[NS(choices=[NS(message=NS(tool_calls=[call], content=None))]), RuntimeError("simulated API outage")])
        with patch("agent.orchestrator.AsyncOpenAI", return_value=NS(chat=NS(completions=NS(create=api)))):
            agent = AgentOrchestrator()
        real_client = MCPClient()
        calls = []

        @asynccontextmanager
        async def session_context():
            async with real_client.session_context() as session:
                async def call_tool(name, arguments):
                    calls.append(name)
                    result = await session.call_tool(name, arguments)
                    if name == "create_event_with_reminders":
                        self.assertEqual(json.loads(result)["status"], "saved")
                        raise ConnectionError("lost response after actual commit")
                    return result
                yield NS(get_openai_tools=session.get_openai_tools, call_tool=call_tool)

        agent.mcp_client = NS(session_context=session_context)
        with self.assertLogs("agent.orchestrator", level="ERROR"):
            text = await agent.process_user_message(1, "Создай встречу и напомни за час")
        self.assertIn("Создано «Встреча»", text)
        self.assertIn("2026-11-01 14:00:00", text)
        self.assertEqual(calls, ["create_event_with_reminders", "get_creation_result"])
        self.assertEqual(api.await_count, 2)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    async def test_mcp_error_flag_is_preserved_as_uncertain(self):
        session = NS(call_tool=AsyncMock(return_value=NS(
            content=[NS(text="tool failed")], isError=True)))
        result = json.loads(await MCPClientSessionWrapper(session).call_tool("create_event_with_reminders", {}))
        self.assertEqual(result["status"], "unknown")
        self.assertIn("error", result)
