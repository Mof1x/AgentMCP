import copy
import sys
import json
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from config import settings

logger = logging.getLogger(__name__)

class MCPClient:
    """Обертка над клиентом Model Context Protocol (MCP) для вызова инструментов сервера."""

    def __init__(self, script_path: Optional[str] = None):
        self.script_path = script_path or settings.MCP_SERVER_SCRIPT

    @asynccontextmanager
    async def session_context(self):
        """Асинхронный контекстный менеджер для соединения с MCP-сервером через stdio."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.script_path],
            env={"DB_PATH": settings.DB_PATH}
        )
        
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield MCPClientSessionWrapper(session)


class MCPClientSessionWrapper:
    """Удобный интерфейс для взаимодействия с инициализированной сессией MCP."""

    def __init__(self, session: ClientSession):
        self.session = session

    async def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Получает список инструментов от MCP-сервера и преобразует их в формат OpenAI Function Calling."""
        tool_list = await self.session.list_tools()
        openai_tools = []
        for t in tool_list.tools:
            if t.name == "get_creation_result":
                continue  # Recovery is controlled by the orchestrator, not the model.
            parameters = copy.deepcopy(getattr(t, "input_schema", getattr(t, "inputSchema", {})))
            if t.name == "create_event_with_reminders":
                for field in ("operation_id", "chat_id"):
                    parameters.get("properties", {}).pop(field, None)
                    if field in parameters.get("required", []):
                        parameters["required"].remove(field)
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": parameters
                }
            })
        return openai_tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Вызывает инструмент на MCP-сервере и возвращает результат в виде строкового JSON.
        """
        try:
            result = await self.session.call_tool(name, arguments)
            
            # Извлекаем текстовый контент из результата
            text_parts = []
            if result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        text_parts.append(item.text)
                    else:
                        text_parts.append(str(item))
            
            output = "\n".join(text_parts) if text_parts else "{}"
            
            if getattr(result, "isError", getattr(result, "is_error", False)):
                return json.dumps({"error": output, "status": "unknown"}, ensure_ascii=False)
                
            return output
        except Exception as e:
            logger.error(f"Ошибка при вызове MCP инструмента '{name}': {e}", exc_info=True)
            return json.dumps({"error": "Не удалось получить результат инструмента.", "status": "unknown"}, ensure_ascii=False)
