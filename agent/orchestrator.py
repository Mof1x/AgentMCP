import sys
import json
import logging
from typing import Dict, List, Optional
from openai import AsyncOpenAI

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import settings
from agent.prompts import SYSTEM_PROMPT
from agent.mcp_client import MCPClient

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Оркестратор агента: управляет контекстом диалога и реализует цикл ReAct (Tool Calling)
    с подключением к базе данных через протокол MCP.
    """

    def __init__(self):
        self.mcp_client = MCPClient(settings.MCP_SERVER_SCRIPT)
        
        # Инициализируем клиента OpenAI (поддерживает OpenAI, OpenRouter, DeepSeek и др.)
        client_kwargs = {"api_key": settings.OPENAI_API_KEY or "dummy-key"}
        if settings.OPENAI_BASE_URL:
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL
        self.llm_client = AsyncOpenAI(**client_kwargs)
        
        # Хранилище сессий: chat_id -> list of messages
        self.sessions: Dict[int, List[Dict[str, any]]] = {}

    def get_or_create_history(self, chat_id: int) -> List[Dict[str, any]]:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
        return self.sessions[chat_id]

    def reset_session(self, chat_id: int):
        """Очищает историю диалога пользователя."""
        self.sessions[chat_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    async def process_user_message(self, chat_id: int, user_text: str) -> str:
        """
        Главный цикл обработки сообщения пользователя:
        1. Подключается к MCP серверу по stdio.
        2. Запрашивает актуальный список инструментов.
        3. Запускает цикл Tool Calling с LLM до получения финального ответа.
        """
        history = self.get_or_create_history(chat_id)
        
        # Добавляем в контекст метаданные пользователя (например chat_id для персональных напоминаний)
        user_message_content = f"[User Chat ID: {chat_id}]\n{user_text}"
        history.append({"role": "user", "content": user_message_content})

        async with self.mcp_client.session_context() as mcp_session:
            # 1. Получаем инструменты от MCP-сервера
            tools = await mcp_session.get_openai_tools()

            max_steps = 10
            step = 0

            while step < max_steps:
                step += 1
                
                try:
                    response = await self.llm_client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=history,
                        tools=tools,
                        tool_choice="auto"
                    )
                except Exception as e:
                    logger.error(f"Ошибка вызова LLM API: {e}", exc_info=True)
                    return f"❌ Ошибка вызова LLM: {str(e)}\nПроверьте настройки API ключа в файле .env."

                message = response.choices[0].message
                
                # Если модель хочет вызвать инструменты:
                if message.tool_calls:
                    # Сохраняем запрос модели в историю строго по спецификации OpenAI
                    assistant_msg = {"role": "assistant"}
                    if message.content:
                        assistant_msg["content"] = message.content
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                    history.append(assistant_msg)

                    for tool_call in message.tool_calls:
                        func_name = tool_call.function.name
                        try:
                            func_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            func_args = {}

                        if settings.DEBUG_TOOL_CALLS:
                            print(f"\n[TOOL CALL #{step}] Tool: {func_name}")
                            print(f"  Args: {json.dumps(func_args, ensure_ascii=False)}")

                        # Вызываем инструмент через MCP
                        tool_result = await mcp_session.call_tool(func_name, func_args)

                        if settings.DEBUG_TOOL_CALLS:
                            preview = tool_result[:250] + "..." if len(tool_result) > 250 else tool_result
                            print(f"  Result: {preview}")

                        # Добавляем результат выполнения инструмента в историю
                        history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": tool_result
                        })

                    # Продолжаем цикл — отправляем результаты обратно в LLM
                    continue

                # Если модель сформировала финальный ответ:
                final_text = message.content or "Действие выполнено."
                history.append({"role": "assistant", "content": final_text})
                return final_text

            return "⚠️ Достигнут лимит итераций вызова инструментов. Попробуйте сформулировать запрос иначе."
