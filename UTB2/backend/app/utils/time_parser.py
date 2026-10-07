import re

def parse_start_minutes(time_str: str) -> int:
    """
    Преобразует строку с временем пары в количество минут от начала дня.
    Используется исключительно как ключ для хронологической сортировки.

    Примеры:
      "08:30-09:50" -> 510 (08:30)
      "9:10-1000"   -> 550 (09:10)
      "12-13"       -> 720 (12:00)
    """
    if not time_str or not time_str.strip():
        return 9999  # Записи без времени уходят в конец списка

    # 1. Извлекаем левую часть до дефиса/тире (время начала)
    start_part = re.split(r'[-–—]', time_str)[0].strip()

    # 2. Формат с разделителем (08:30, 9.10)
    if ':' in start_part or '.' in start_part:
        parts = re.split(r'[:.]', start_part)
        try:
            hours = int(parts[0]) if parts[0] else 0
            minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            return hours * 60 + minutes
        except ValueError:
            return 9999

    # 3. Формат без разделителей (12, 910, 0830)
    digits = re.sub(r'\D', '', start_part)
    if not digits:
        return 9999

    if len(digits) <= 2:
        # "9" -> 9:00, "12" -> 12:00
        hours, minutes = int(digits), 0
    elif len(digits) == 3:
        # "910" -> 9:10
        hours, minutes = int(digits[0]), int(digits[1:])
    else:
        # "0830" -> 08:30, "1000" -> 10:00
        hours, minutes = int(digits[:2]), int(digits[2:])

    return hours * 60 + minutes


def sort_schedules_by_time(schedules: list) -> list:
    """Сортирует список объектов расписания по хронологическому времени начала."""
    return sorted(schedules, key=lambda s: parse_start_minutes(s.time))
