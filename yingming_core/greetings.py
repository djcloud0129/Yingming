from __future__ import annotations

from datetime import datetime
from typing import Any


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


def contextual_welcome_text(
    memory_data: dict[str, Any] | None = None,
    recent_messages: list[dict[str, str]] | None = None,
    now: datetime | None = None,
) -> str:
    memory_data = memory_data or {}
    recent_messages = recent_messages or []
    greeting = current_greeting(now)
    pending = memory_data.get("pending", [])
    pending_count = len(pending) if isinstance(pending, list) else 0

    parts = [f"{greeting}。我在这里。"]
    if pending_count:
        parts.append(f"我这里有 {pending_count} 条待确认记忆，等你方便，我们一起看一眼，别让我记偏。")
        return "".join(parts)

    last_user = latest_user_message(recent_messages)
    if last_user:
        if is_project_like(last_user):
            parts.append(f"上次我们聊到“{compact_text(last_user, 34)}”。")
        else:
            parts.append("上次的话题我还留着。")
        parts.append("要继续往前推一点，还是先换个轻一点的话题？")
        return "".join(parts)

    project_hint = latest_project_hint(memory_data)
    if project_hint:
        parts.append(f"我还记得：{compact_text(project_hint, 42)}。")
        parts.append("今天也可以只往前挪一小步。")
        return "".join(parts)

    parts.append("你可以慢慢说。")
    return "".join(parts)


def proactive_text(
    memory_data: dict[str, Any] | None = None,
    recent_messages: list[dict[str, str]] | None = None,
    mode: str = "normal",
    now: datetime | None = None,
    sequence: int = 0,
) -> str:
    if mode == "quiet":
        return ""

    memory_data = memory_data or {}
    recent_messages = recent_messages or []
    current = now if now is not None else datetime.now().astimezone()
    pending = memory_data.get("pending", [])
    pending_count = len(pending) if isinstance(pending, list) else 0

    if pending_count:
        return f"我这里还有 {pending_count} 条记忆没确认。等你方便，我们看一眼就好，别让我记错你。"

    if current.hour >= 23 or current.hour < 5:
        return "夜深了。今天不用把所有事都做完，我们留一个很小的收尾就好。"

    last_user = latest_user_message(recent_messages)
    if last_user and is_project_like(last_user):
        topic = compact_text(last_user, 30)
        variants = [
            f"我还在想刚才的“{topic}”。要不要把下一步落到一个很小的清单里？",
            f"关于“{topic}”，我觉得可以先抓一个最小动作。你想让我帮你拆一下吗？",
        ]
        return variants[sequence % len(variants)]

    project_hint = latest_project_hint(memory_data)
    if project_hint:
        return f"我还记得我们在推进：{compact_text(project_hint, 34)}。今天往前挪一小步也算数。"

    if mode == "warm":
        return "我还在旁边。你不用急着说话；想继续的时候，我会接住。"
    return "我还在。你想继续做樱茗，还是先安静一会儿？"


def latest_user_message(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", "")).strip()
    return ""


def latest_project_hint(memory_data: dict[str, Any]) -> str:
    memories = memory_data.get("long_term", [])
    if not isinstance(memories, list):
        return ""
    for item in reversed(memories):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        text = str(item.get("text", "")).strip()
        if text and category in {"project", "learning", "preference", "persona"}:
            return text
    return ""


def is_project_like(text: str) -> bool:
    keywords = (
        "樱茗",
        "桌宠",
        "记忆",
        "画像",
        "deepseek",
        "api",
        "模型",
        "代码",
        "ui",
        "界面",
        "时间",
        "问候",
        "主动",
        "中枢",
        "vtuber",
        "live2d",
        "项目",
    )
    lower = text.lower()
    return any(keyword in lower for keyword in keywords)


def compact_text(text: str, limit: int) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: max(0, limit - 1)].rstrip() + "..."
