from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yingming_core.dialogue_state import (
    assistant_is_waiting_for_user,
    conversation_waiting_for_user,
    is_return_to_topic_command,
    is_wait_command,
)


@dataclass(frozen=True)
class TopicState:
    kind: str
    title: str
    status: str
    anchor: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "anchor": self.anchor,
        }

    def as_prompt_text(self) -> str:
        if self.status == "closed" or not self.title:
            return ""
        return "\n".join(
            [
                "当前短期话题：",
                f"- 话题：{self.title}",
                f"- 状态：{TOPIC_STATUS_LABELS.get(self.status, self.status)}",
                f"- 线索：{self.anchor or '无'}",
                "- 这只是短期会话节奏，不要写入长期记忆。",
                "- 如果用户说“回到刚才/继续刚才/别换话题”，优先接回这个话题。",
                "- 如果状态是 waiting_user 或 paused，保持等待，不主动开启新话题。",
            ]
        )

    def with_status(self, status: str) -> TopicState:
        return TopicState(self.kind, self.title, status, self.anchor)


TOPIC_STATUS_LABELS = {
    "open": "进行中",
    "waiting_user": "等用户回答",
    "paused": "用户让樱茗等一下",
    "closed": "已收束",
}

TOPIC_KIND_LABELS = {
    "movie": "电影",
    "project": "项目",
    "emotional": "情绪",
    "memory": "记忆",
    "casual": "闲聊",
}

MOVIE_TITLES = (
    "银翼杀手2049",
    "银翼杀手",
    "blade runner 2049",
    "blade runner",
    "降临",
    "arrival",
)

MOVIE_WORDS = (
    "电影",
    "片子",
    "科幻",
    "导演",
    "镜头",
    "画面",
    "结局",
    "片尾",
    "看过",
    "重温",
    "维伦纽瓦",
)

PROJECT_WORDS = (
    "樱茗",
    "桌宠",
    "代码",
    "项目",
    "功能",
    "github",
    "deepseek",
    "api",
    "记忆体",
    "画像",
    "状态感知",
    "主动陪伴",
    "mood",
    "live2d",
)

EMOTIONAL_WORDS = (
    "累",
    "焦虑",
    "难受",
    "不开心",
    "压力",
    "孤独",
    "没动力",
)

MEMORY_WORDS = (
    "记住",
    "记忆",
    "长期记忆",
    "待确认",
    "忘掉",
    "画像",
)

CLOSING_WORDS = (
    "先这样",
    "不聊这个",
    "换个话题",
    "这个话题先放下",
    "结束这个话题",
    "聊点别的",
)


def detect_topic_state(
    recent_messages: list[dict[str, str]] | None = None,
    user_text: str = "",
) -> TopicState:
    recent_messages = recent_messages or []
    text = normalize_text(user_text)

    if is_wait_command(text):
        previous = infer_topic_from_messages(recent_messages)
        return previous.with_status("paused") if previous.status != "closed" else TopicState("casual", "刚才的话题", "paused")

    previous = infer_topic_from_messages(recent_messages)
    if is_return_to_topic_command(text):
        return previous.with_status("open") if previous.status != "closed" else TopicState("casual", "刚才的话题", "open")

    if text and contains_any(text, CLOSING_WORDS):
        return previous.with_status("closed") if previous.status != "closed" else previous

    current = infer_topic_from_text(text) if text else TopicState("", "", "closed")
    if current.status != "closed":
        return current

    if conversation_waiting_for_user(recent_messages):
        return previous.with_status("waiting_user") if previous.status != "closed" else TopicState("casual", "刚才的话题", "waiting_user")

    return previous


def infer_topic_from_messages(messages: list[dict[str, str]]) -> TopicState:
    if not messages:
        return TopicState("", "", "closed")

    last_assistant = ""
    last_user = ""
    for message in reversed(messages):
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role == "assistant" and not last_assistant:
            last_assistant = content
        if role == "user" and not last_user:
            last_user = content
        if last_assistant and last_user:
            break

    combined_parts: list[str] = []
    for message in messages[-8:]:
        content = str(message.get("content", "")).strip()
        if content:
            combined_parts.append(content)
    combined = "\n".join(combined_parts)

    topic = infer_topic_from_text(combined)
    if topic.status == "closed":
        return topic
    if last_user and contains_any(normalize_text(last_user), CLOSING_WORDS):
        return topic.with_status("closed")
    if last_assistant and assistant_is_waiting_for_user(last_assistant):
        return topic.with_status("waiting_user")
    return topic.with_status("open")


def infer_topic_from_text(text: str) -> TopicState:
    normalized = normalize_text(text)
    if not normalized:
        return TopicState("", "", "closed")

    if contains_any(normalized, MOVIE_TITLES) or contains_any(normalized, MOVIE_WORDS):
        title = detect_movie_title(normalized)
        return TopicState("movie", f"电影：{title}", "open", anchor_from_text(text))
    if contains_any(normalized, PROJECT_WORDS):
        return TopicState("project", "项目：樱茗桌宠", "open", anchor_from_text(text))
    if contains_any(normalized, MEMORY_WORDS):
        return TopicState("memory", "记忆整理", "open", anchor_from_text(text))
    if contains_any(normalized, EMOTIONAL_WORDS):
        return TopicState("emotional", "情绪陪伴", "open", anchor_from_text(text))
    return TopicState("casual", "闲聊", "open", anchor_from_text(text)) if len(normalized) >= 8 else TopicState("", "", "closed")


def detect_movie_title(text: str) -> str:
    if "降临" in text or "arrival" in text:
        return "《降临》"
    if "2049" in text or "银翼杀手" in text or "blade runner" in text:
        return "《银翼杀手2049》"
    return "电影"


def topic_blocks_proactive(topic: TopicState) -> bool:
    return topic.status in {"open", "waiting_user", "paused"} and bool(topic.title)


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def normalize_text(text: str) -> str:
    return " ".join(str(text).strip().split()).lower()


def anchor_from_text(text: str, limit: int = 80) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."
