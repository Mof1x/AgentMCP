import datetime

WEEKDAYS_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье"
]

def get_current_datetime() -> dict:
    """
    Возвращает текущую дату, время, день недели и ISO-штамп.
    Необходим для разрешения относительных временных указаний (завтра, через 2 часа, в пятницу).
    """
    now = datetime.datetime.now()
    weekday_idx = now.weekday()
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M"),
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": WEEKDAYS_RU[weekday_idx],
        "weekday_index": weekday_idx + 1,  # 1 = Пн, 7 = Вс
        "iso": now.isoformat()
    }
