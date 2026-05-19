from datetime import datetime


def is_time_in_range(current_hour: int, start_hour: int, end_hour: int) -> bool:
    if start_hour <= end_hour:
        return start_hour <= current_hour < end_hour
    return current_hour >= start_hour or current_hour < end_hour


def get_current_weekday_frontend_format() -> int:
    current_weekday = datetime.now().weekday()
    weekday_mapping = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}
    return weekday_mapping[current_weekday]


def get_current_hour() -> int:
    return datetime.now().hour
