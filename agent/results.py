"""Deterministic user-facing receipts when the agent cannot finish its reply."""
import json

WRITE_TOOLS = {
    "create_event_with_reminders", "execute_write_query",
    "create_recurring_events", "reschedule_event",
}


def parse_result(raw: str) -> dict:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def result_status(result: dict) -> str:
    if result.get("status") == "unknown":
        return "unknown"
    if result.get("success") is True:
        return "saved"
    if result.get("success") is False or result.get("status") == "not_saved":
        return "not_saved"
    return "unknown"


class TurnResults:
    def __init__(self):
        self.operations = {}

    def record(self, key: str, name: str, result: dict):
        if name in WRITE_TOOLS:
            self.operations[key] = (name, result)

    def fallback(self, reason: str) -> str:
        lines = [reason]
        saved = []
        failed = False
        unknown = False
        for name, result in self.operations.values():
            status = result_status(result)
            if status == "unknown":
                unknown = True
            elif status == "not_saved":
                failed = True
            elif name == "create_event_with_reminders":
                title = str(result.get("title", "Событие")).replace("\n", " ")[:120]
                text = f"Создано «{title}» на {result.get('start', 'указанное время')} (№{result.get('event_id', '?')})."
                reminders = result.get("reminders", [])
                if reminders:
                    times = ", ".join(str(r.get("remind_at", "")) for r in reminders[:5])
                    text += f" Напоминания: {times}."
                    if len(reminders) > 5:
                        text += f" Всего: {len(reminders)}."
                else:
                    text += " Без напоминаний."
                saved.append(text)
            elif name == "reschedule_event":
                saved.append(f"Событие №{result.get('event_id', '?')} перенесено на {result.get('new_start', 'новое время')}. Перенесено напоминаний: {result.get('shifted_reminders_count', 0)}.")
            elif name == "create_recurring_events":
                saved.append(f"Создана серия из {result.get('created_count', '?')} событий.")
            else:
                saved.append(f"SQL-операция выполнена; затронуто записей: {result.get('rows_affected', '?')}. Состав изменений проверь в расписании.")
        if saved:
            lines.append("Подтверждённые действия этого запроса:")
            lines.extend("• " + item for item in saved[:6])
            if len(saved) > 6:
                lines.append(f"Ещё подтверждённых операций: {len(saved) - 6}. Проверь расписание.")
        if failed:
            lines.append("Одна или несколько операций не выполнены; их изменения не сохранены.")
        if unknown:
            lines.append("Результат одной или нескольких операций подтвердить не удалось. Они могли сохраниться. Проверь расписание перед повтором; автоматически запись не повторялась.")
        elif not saved:
            lines.append("Изменения не внесены.")
        return "\n".join(lines)
