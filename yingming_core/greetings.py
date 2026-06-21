from __future__ import annotations

from datetime import datetime


def greeting_for_hour(hour: int) -> str:
    if not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23.")

    if 5 <= hour < 9:
        return "早上好"
    if 9 <= hour < 11:
        return "上午好"
    if 11 <= hour < 14:
        return "中午好"
    if 14 <= hour < 18:
        return "下午好"
    if 18 <= hour < 23:
        return "晚上好"
    return "夜深了"


def current_greeting(now: datetime | None = None) -> str:
    current = now if now is not None else datetime.now().astimezone()
    return greeting_for_hour(current.hour)


def welcome_text(now: datetime | None = None) -> str:
    return f"{current_greeting(now)}。我在这里。你可以慢慢说。"
