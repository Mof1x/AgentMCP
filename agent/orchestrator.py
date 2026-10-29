import hashlib
import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

from openai import AsyncOpenAI

from config import settings
from agent.prompts import SYSTEM_PROMPT
from agent.mcp_client import MCPClient
from agent.results import TurnResults, WRITE_TOOLS, parse_result, result_status

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Conversation/tool loop with deterministic fallback for confirmed writes."""

    def __init__(self):
        self.mcp_client = MCPClient(settings.MCP_SERVER_SCRIPT)
        client_kwargs = {"api_key": settings.OPENAI_API_KEY or "dummy-key"}
        if settings.OPENAI_BASE_URL:
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL
        self.llm_client = AsyncOpenAI(**client_kwargs)
        self.sessions: Dict[int, List[Dict[str, Any]]] = {}

    def get_or_create_history(self, chat_id: int) -> List[Dict[str, Any]]:
        if chat_id not in self.sessions:
            self.reset_session(chat_id)
        return self.sessions[chat_id]

    def reset_session(self, chat_id: int):
        self.sessions[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    async def _recover_creation(self, operation_id: str, chat_id: int) -> dict:
        try:
            # A fresh connection also works when the original MCP process died.
            async with self.mcp_client.session_context() as session:
                raw = await session.call_tool("get_creation_result", {
                    "operation_id": operation_id, "chat_id": chat_id,
                })
                result = parse_result(raw)
                if result_status(result) == "saved":
                    return result
        except Exception:
            logger.exception("Не удалось прочитать квитанцию создания")
        return {"status": "unknown"}

    async def process_user_message(self, chat_id: int, user_text: str) -> str:
        history = self.get_or_create_history(chat_id)
        history.append({"role": "user", "content": f"[User Chat ID: {chat_id}]\n{user_text}"})
        results = TurnResults()
        turn_id = uuid4().hex
        pending = []

        def finish(text):
            history.append({"role": "assistant", "content": text})
            return text

        try:
            async with self.mcp_client.session_context() as session:
                tools = await session.get_openai_tools()
                for step in range(1, 11):
                    try:
                        response = await self.llm_client.chat.completions.create(
                            model=settings.LLM_MODEL, messages=history,
                            tools=tools, tool_choice="auto",
                        )
                        message = response.choices[0].message
                    except Exception:
                        logger.exception("Ошибка вызова LLM API")
                        return finish(results.fallback("Не удалось получить ответ модели."))

                    if not message.tool_calls:
                        return finish(message.content or results.fallback("Модель не сформировала ответ."))

                    pending = list(message.tool_calls)
                    assistant_msg = {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": tc.id, "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        } for tc in pending],
                    }
                    if message.content:
                        assistant_msg["content"] = message.content
                    history.append(assistant_msg)
                    stop_writes = False
                    for tool_call in list(pending):
                        name = tool_call.function.name
                        key = tool_call.id
                        try:
                            args = json.loads(tool_call.function.arguments)
                            if not isinstance(args, dict):
                                raise ValueError("Arguments must be an object")
                        except (ValueError, TypeError):
                            raw = json.dumps({"success": False, "status": "not_saved",
                                              "message": "Некорректные аргументы: нужен JSON-объект."}, ensure_ascii=False)
                        else:
                            if stop_writes:
                                raw = json.dumps({"success": False, "status": "not_saved",
                                                  "message": "Вызов не выполнен: результат предыдущей записи неизвестен."}, ensure_ascii=False)
                            else:
                                if name == "create_event_with_reminders":
                                    # Model-supplied identity fields are never trusted.
                                    args.pop("operation_id", None)
                                    args["chat_id"] = chat_id
                                    fingerprint = hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                                    key = f"{turn_id}:{fingerprint}"
                                    args["operation_id"] = key
                                results.record(key, name, {"status": "unknown"})
                                try:
                                    raw = await session.call_tool(name, args)
                                except Exception:
                                    logger.exception("Сбой вызова инструмента %s", name)
                                    raw = json.dumps({"status": "unknown"})
                                result = parse_result(raw)
                                if name == "create_event_with_reminders" and result_status(result) == "unknown":
                                    result = await self._recover_creation(key, chat_id)
                                    raw = json.dumps(result, ensure_ascii=False)
                                if name in WRITE_TOOLS and result_status(result) == "unknown":
                                    stop_writes = True
                                if settings.DEBUG_TOOL_CALLS:
                                    logger.info("Tool call #%s: %s; status=%s", step, name, result_status(result))
                        results.record(key, name, parse_result(raw))
                        history.append({"role": "tool", "tool_call_id": tool_call.id,
                                        "name": name, "content": raw})
                        pending.pop(0)
                    if stop_writes:
                        return finish(results.fallback("Обработка остановлена для проверки сохранения."))
                return finish(results.fallback("Достигнут лимит шагов обработки запроса."))
        except Exception:
            logger.exception("Ошибка сессии MCP")
            # Keep the protocol history valid if a batch was interrupted.
            for tool_call in pending:
                history.append({"role": "tool", "tool_call_id": tool_call.id,
                                "name": tool_call.function.name,
                                "content": json.dumps({"status": "unknown", "message": "Обработка прервана."})})
            return finish(results.fallback("Не удалось завершить обработку запроса."))
