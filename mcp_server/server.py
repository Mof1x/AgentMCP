import sys
from pathlib import Path
from typing import Optional


# Добавляем корневую директорию проекта в sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from mcp_server.tools.creation_tools import (
    ReminderInput,
    create_event_with_reminders as _create_event_with_reminders,
    get_creation_result as _get_creation_result,
)
from mcp_server.tools.free_slots_tools import find_free_slots as _find_free_slots
from mcp_server.tools.summary_tools import get_day_summary as _get_day_summary
from mcp_server.tools.recurring_tools import create_recurring_events as _create_recurring_events
from mcp_server.tools.reschedule_tools import reschedule_event as _reschedule_event
from mcp_server.tools.export_tools import export_schedule as _export_schedule
from mcp_server.tools.overdue_tools import get_overdue_events as _get_overdue_events

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


@server.tool()
def find_free_slots(
    date: str,
    chat_id: int,
    duration_minutes: int = 60,
    day_start: str = "09:00",
    day_end: str = "21:00",
    buffer_minutes: int = 0
) -> dict:
    """
    Ищет свободные промежутки в расписании пользователя.

    date: дата в формате YYYY-MM-DD.
    chat_id: идентификатор чата из метаданных сообщения пользователя.
    duration_minutes: необходимая длительность дела в минутах.
    day_start: начало периода поиска в формате HH:MM.
    day_end: конец периода поиска в формате HH:MM.
    buffer_minutes: минимальный перерыв между новым делом
    и каждым соседним событием, от 0 до 1440 минут.

    Например, buffer_minutes=15 оставляет по 15 минут
    перед существующими событиями и после них.
    Возвращает свободные интервалы не короче duration_minutes
    с уже учтёнными перерывами.
    Только предлагает время и не изменяет расписание.
    """
    return _find_free_slots(
        date=date,
        chat_id=chat_id,
        duration_minutes=duration_minutes,
        day_start=day_start,
        day_end=day_end,
        buffer_minutes=buffer_minutes
    )


@server.tool()
def get_day_summary(
    date: str,
    chat_id: int,
    day_start: str = "09:00",
    day_end: str = "21:00"
) -> dict:
    """
    Показывает загруженность расписания пользователя за выбранную дату
    в пределах указанного периода.

    date: дата в формате YYYY-MM-DD.
    chat_id: идентификатор чата из метаданных сообщения пользователя.
    day_start: начало периода в формате HH:MM.
    day_end: конец периода в формате HH:MM.

    Возвращает количество запланированных событий, занятые и свободные
    минуты, процент загруженности и самый длинный свободный промежуток.
    Пересекающиеся события не учитываются дважды в занятом времени.
    Не изменяет расписание.
    """
    return _get_day_summary(
        date=date,
        chat_id=chat_id,
        day_start=day_start,
        day_end=day_end
    )


@server.tool()
def create_recurring_events(
    title: str,
    first_start: str,
    chat_id: int,
    duration_minutes: int = 60,
    repeat_every_days: int = 7,
    occurrences: int = 4,
    priority: int = 2
) -> dict:
    """
    Создаёт конечную серию повторяющихся событий.

    title: название события.
    first_start: начало первого события в формате YYYY-MM-DD HH:MM:SS.
    chat_id: идентификатор чата из метаданных сообщения пользователя.
    duration_minutes: длительность каждого события, от 1 до 1440 минут.
    repeat_every_days: интервал между событиями, от 1 до 365 дней.
    occurrences: общее число событий, включая первое, от 1 до 52.
    priority: важность от 1 до 4.

    Например, repeat_every_days=7 и occurrences=4 создают четыре
    события с интервалом в неделю.

    Проверяет конфликты всех дат внутри одной транзакции.
    Если обнаружен хотя бы один конфликт, не создаёт ни одного события.
    Напоминания не создаются.
    """
    return _create_recurring_events(
        title=title,
        first_start=first_start,
        chat_id=chat_id,
        duration_minutes=duration_minutes,
        repeat_every_days=repeat_every_days,
        occurrences=occurrences,
        priority=priority
    )


@server.tool()
def reschedule_event(
    event_id: int,
    new_start: str,
    chat_id: int
) -> dict:
    """
    Переносит запланированное событие пользователя вместе
    с ещё не отправленными напоминаниями.

    event_id: идентификатор переносимого события.
    new_start: новое начало в формате YYYY-MM-DD HH:MM:SS.
    chat_id: идентификатор чата из метаданных сообщения пользователя.

    Сохраняет длительность события. Если конец не указан,
    использует длительность один час.
    Сдвигает неотправленные напоминания на разницу между новым
    и старым временем начала. Отправленные напоминания не изменяет.
    Проверяет конфликты, исключая само переносимое событие.
    При конфликте событие и напоминания остаются без изменений.
    События на весь день не поддерживаются.
    """
    return _reschedule_event(
        event_id=event_id,
        new_start=new_start,
        chat_id=chat_id
    )


@server.tool()
def export_schedule(
    start_date: str,
    end_date: str,
    chat_id: int
) -> dict:
    """
    Формирует содержимое календаря в формате ICS.

    start_date: первая дата периода в формате YYYY-MM-DD.
    end_date: последняя дата периода включительно, формат YYYY-MM-DD.
    chat_id: идентификатор чата из метаданных сообщения пользователя.

    Экспортирует запланированные события указанного пользователя,
    пересекающие период, включая события на весь день.
    Максимальный период — 366 дней.
    Возвращает filename, events_count и ics_content.
    Самостоятельно файл в Telegram не отправляет.
    """
    return _export_schedule(
        start_date=start_date,
        end_date=end_date,
        chat_id=chat_id
    )


@server.tool()
def get_overdue_events(
    chat_id: int,
    as_of: str,
    since: Optional[str] = None,
    limit: int = 50
) -> dict:
    """
    Показывает события, время окончания которых уже наступило,
    но выполнение ещё не отмечено: статус остаётся planned.

    chat_id: идентификатор чата из метаданных сообщения пользователя.
    as_of: момент проверки в формате YYYY-MM-DD HH:MM:SS.
    since: необязательная нижняя граница времени окончания событий,
    формат YYYY-MM-DD HH:MM:SS.
    limit: максимальное количество результатов, от 1 до 100.

    Актуальное время для as_of получай через get_current_datetime.
    Результаты сортируются по важности, затем по времени окончания.
    events_count — количество возвращённых событий.
    has_more=True означает, что найдены дополнительные события
    сверх указанного лимита.
    Не изменяет события и не отмечает их выполненными.
    """
    return _get_overdue_events(
        chat_id=chat_id,
        as_of=as_of,
        since=since,
        limit=limit
    )


@server.tool()
def create_event_with_reminders(
    title: str,
    start_datetime: str,
    chat_id: int,
    operation_id: str,
    end_datetime: Optional[str] = None,
    reminders: Optional[list[ReminderInput]] = None,
    description: Optional[str] = None,
    category_id: Optional[int] = None,
    priority: int = 2,
    is_all_day: bool = False,
) -> dict:
    """Создаёт одно событие и все его напоминания атомарно.

    Даты: YYYY-MM-DD HH:MM:SS. reminders: список {remind_at, custom_message}.
    Если конец не задан, длительность — час (для is_all_day — сутки).
    Для is_all_day обе границы должны быть в полночь.
    Проверяет конфликты пользователя внутри транзакции.
    status=saved: всё сохранено; not_saved: эта операция ничего не изменила;
    unknown: нельзя повторять запись до проверки результата.
    Используй для создания одиночного события, в том числе без напоминаний.
    """
    return _create_event_with_reminders(
        title=title, start_datetime=start_datetime, chat_id=chat_id,
        operation_id=operation_id, end_datetime=end_datetime, reminders=reminders,
        description=description, category_id=category_id, priority=priority,
        is_all_day=is_all_day,
    )


@server.tool()
def get_creation_result(operation_id: str, chat_id: int) -> dict:
    """Служебная проверка квитанции после потери ответа MCP."""
    return _get_creation_result(operation_id, chat_id)


if __name__ == "__main__":
    server.run(transport="stdio")
