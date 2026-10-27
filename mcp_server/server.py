import sys
from pathlib import Path
from typing import Optional

# Добавляем корневую директорию проекта в sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from mcp_server.tools.datetime_tools import get_current_datetime as _get_current_datetime
from mcp_server.tools.schema_tools import get_db_schema as _get_db_schema
from mcp_server.tools.conflict_tools import check_time_conflict as _check_time_conflict
from mcp_server.tools.query_tools import (
    execute_read_query as _execute_read_query,
    execute_write_query as _execute_write_query
)

# Инициализируем MCP-сервер
server = MCPServer("PersonalScheduleDB")


@server.tool()
def get_current_datetime() -> dict:
    """
    Возвращает текущую дату, время, день недели и ISO штамп.
    Используй ВСЕГДА при обработке относительных дат пользователя ('сегодня', 'завтра', 'в эту пятницу', 'через 2 часа').
    """
    return _get_current_datetime()


@server.tool()
def get_db_schema() -> dict:
    """
    Возвращает структуру реляционной базы данных (таблицы, колонки, типы, внешние ключи, уровни важности).
    Используй для понимания структуры таблиц events, reminders, categories перед выполнением запросов.
    """
    return _get_db_schema()


@server.tool()
def check_time_conflict(
    start_datetime: str,
    end_datetime: Optional[str] = None,
    exclude_event_id: Optional[int] = None
) -> dict:
    """
    Проверяет, пересекается ли интервал времени с уже существующими запланированными делами.
    Возвращает информацию о конфликтах и их уровнях важности (1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL).
    Используй перед созданием или переносом событий.
    
    :param start_datetime: Дата и время начала события ('YYYY-MM-DD HH:MM:SS').
    :param end_datetime: Дата и время окончания события (если не указано, берется +1 час).
    :param exclude_event_id: ID события для исключения (например, при редактировании/переносе того же дела).
    """
    return _check_time_conflict(start_datetime, end_datetime, exclude_event_id)


@server.tool()
def execute_read_query(query: str) -> list[dict]:
    """
    Выполняет безопасный SELECT-запрос к базе данных (events, reminders, categories).
    Любые модифицирующие операции (INSERT/UPDATE/DELETE/DROP) запрещены.
    
    :param query: SQL-запрос на чтение, начинающийся с SELECT или WITH.
    """
    return _execute_read_query(query)


@server.tool()
def execute_write_query(query: str) -> dict:
    """
    Выполняет SQL-запрос на изменение данных (INSERT, UPDATE или DELETE) в таблицах events и reminders.
    Возвращает success=True/False, rows_affected и last_insert_rowid.
    
    :param query: SQL-запрос на модификацию данных.
    """
    return _execute_write_query(query)


if __name__ == "__main__":
    server.run(transport="stdio")
