import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from agent.orchestrator import AgentOrchestrator


def tool(name, arguments, call_id="call-1"):
    return NS(id=call_id, function=NS(name=name, arguments=json.dumps(arguments)))


def response(*calls, content=None):
    return NS(choices=[NS(message=NS(tool_calls=list(calls), content=content))])


SAVED = {
    "success": True, "status": "saved", "event_id": 42,
    "title": "Встреча", "start": "2026-11-01 15:00:00",
    "reminders": [{"remind_at": "2026-11-01 14:00:00"}],
}
CREATE_ARGS = {"title": "Встреча", "start_datetime": "2026-11-01 15:00:00"}


class TestAgentFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = AsyncMock()
        with patch("agent.orchestrator.AsyncOpenAI", return_value=NS(chat=NS(completions=NS(create=self.api)))):
            self.agent = AgentOrchestrator()
        self.session = NS(get_openai_tools=AsyncMock(return_value=[]), call_tool=AsyncMock())

        @asynccontextmanager
        async def session_context():
            yield self.session

        self.agent.mcp_client = NS(session_context=session_context)
        patcher = patch("agent.orchestrator.logger")
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_history_complete(self):
        history = self.agent.sessions[1]
        calls = [tc["id"] for msg in history for tc in msg.get("tool_calls", [])]
        replies = [msg["tool_call_id"] for msg in history if msg["role"] == "tool"]
        self.assertEqual(calls, replies)
        self.assertEqual(history[-1]["role"], "assistant")

    async def test_api_failure_after_save_uses_receipt_without_extra_api_call(self):
        self.api.side_effect = [response(tool("create_event_with_reminders", CREATE_ARGS)), RuntimeError("secret-in-error")]
        self.session.call_tool.return_value = json.dumps(SAVED)
        text = await self.agent.process_user_message(1, "Создай встречу")
        self.assertIn("Встреча", text)
        self.assertIn("2026-11-01 15:00:00", text)
        self.assertIn("2026-11-01 14:00:00", text)
        self.assertNotIn("secret-in-error", text)
        self.assertNotIn("Изменения не внесены", text)
        self.assertEqual(self.api.await_count, 2)
        self.assert_history_complete()

    async def test_api_failure_before_tools_says_no_changes(self):
        self.api.side_effect = RuntimeError("secret")
        text = await self.agent.process_user_message(1, "Создай встречу")
        self.assertIn("Изменения не внесены", text)
        self.session.call_tool.assert_not_awaited()
        self.assertEqual(self.api.await_count, 1)

    async def test_rejected_creation_then_api_failure(self):
        self.api.side_effect = [response(tool("create_event_with_reminders", CREATE_ARGS)), RuntimeError()]
        self.session.call_tool.return_value = json.dumps({"success": False, "status": "not_saved"})
        text = await self.agent.process_user_message(1, "Создай встречу")
        self.assertIn("Изменения не внесены", text)
        self.assertNotIn("Создано", text)

    async def test_lost_mcp_reply_recovers_saved_receipt(self):
        self.api.side_effect = [response(tool("create_event_with_reminders", CREATE_ARGS)), RuntimeError()]
        self.session.call_tool.side_effect = [ConnectionError(), json.dumps(SAVED)]
        text = await self.agent.process_user_message(1, "Создай встречу")
        self.assertIn("Создано", text)
        calls = self.session.call_tool.call_args_list
        self.assertEqual(calls[1].args[0], "get_creation_result")
        self.assertEqual(calls[0].args[1]["operation_id"], calls[1].args[1]["operation_id"])
        self.assertEqual(self.api.await_count, 2)

    async def test_unknown_write_stops_batch_and_does_not_claim_rollback(self):
        self.api.return_value = response(
            tool("create_event_with_reminders", CREATE_ARGS),
            tool("execute_write_query", {"query": "DELETE FROM events"}, "call-2"),
        )
        self.session.call_tool.side_effect = [json.dumps({"status": "unknown"}), json.dumps({"status": "unknown"})]
        text = await self.agent.process_user_message(1, "Создай встречу")
        self.assertIn("могли сохраниться", text)
        self.assertNotIn("Изменения не внесены", text)
        self.assertEqual(self.session.call_tool.await_count, 2)
        self.assertEqual(self.api.await_count, 1)
        self.assert_history_complete()

    async def test_recovery_failure_stays_unknown(self):
        self.api.return_value = response(tool("create_event_with_reminders", CREATE_ARGS))
        self.session.call_tool.side_effect = [ConnectionError(), ConnectionError()]
        text = await self.agent.process_user_message(1, "Создай встречу")
        self.assertIn("могли сохраниться", text)
        self.assertNotIn("Изменения не внесены", text)

    async def test_same_creation_uses_same_id_and_overrides_model_identity(self):
        calls = [tool("create_event_with_reminders", {**CREATE_ARGS, "chat_id": 999, "operation_id": "forged"}, "a"),
                 tool("create_event_with_reminders", CREATE_ARGS, "b")]
        self.api.side_effect = [response(*calls), RuntimeError()]
        self.session.call_tool.return_value = json.dumps(SAVED)
        text = await self.agent.process_user_message(1, "Создай встречу")
        first, second = [call.args[1] for call in self.session.call_tool.call_args_list]
        self.assertEqual(first["chat_id"], 1)
        self.assertEqual(first["operation_id"], second["operation_id"])
        self.assertNotEqual(first["operation_id"], "forged")
        self.assertEqual(text.count("Создано «Встреча»"), 1)

    async def test_partial_legacy_writes_are_reported_honestly(self):
        self.api.side_effect = [response(
            tool("execute_write_query", {"query": "INSERT ..."}, "a"),
            tool("execute_write_query", {"query": "INSERT ..."}, "b")), RuntimeError()]
        self.session.call_tool.side_effect = [json.dumps({"success": True, "rows_affected": 1}),
                                            json.dumps({"success": False, "error": "SQL failure"})]
        text = await self.agent.process_user_message(1, "Запиши")
        self.assertIn("затронуто записей: 1", text)
        self.assertIn("не выполнены", text)
        self.assertNotIn("Изменения не внесены", text)

    async def test_empty_final_reply_uses_saved_results(self):
        self.api.side_effect = [response(tool("create_event_with_reminders", CREATE_ARGS)), response()]
        self.session.call_tool.return_value = json.dumps(SAVED)
        text = await self.agent.process_user_message(1, "Запиши")
        self.assertIn("Создано", text)
        self.assertNotEqual(text, "Действие выполнено.")

    async def test_step_limit_reports_saved_operations(self):
        self.api.return_value = response(tool("create_event_with_reminders", CREATE_ARGS))
        self.session.call_tool.return_value = json.dumps(SAVED)
        text = await self.agent.process_user_message(1, "Запиши")
        self.assertIn("лимит", text)
        self.assertIn("Создано", text)
        self.assertEqual(self.api.await_count, 10)
        self.assertEqual(text.count("Создано «Встреча»"), 1)

    async def test_normal_reply_is_unchanged(self):
        self.api.return_value = response(content="Какое время выбрать?")
        self.assertEqual(await self.agent.process_user_message(1, "Запиши"), "Какое время выбрать?")
        self.session.call_tool.assert_not_awaited()

    async def test_results_do_not_leak_into_next_turn(self):
        self.api.side_effect = [response(tool("create_event_with_reminders", CREATE_ARGS)), response(content="Готово"), RuntimeError()]
        self.session.call_tool.return_value = json.dumps(SAVED)
        await self.agent.process_user_message(1, "Запиши")
        text = await self.agent.process_user_message(1, "Что завтра?")
        self.assertNotIn("Создано", text)
        self.assertIn("Изменения не внесены", text)
