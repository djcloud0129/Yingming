from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from yingming_core.llm import Message


DEFAULT_RETRIEVAL_LIMIT = 6

RECALL_QUERY_HINTS = (
    "你记得我",
    "记得我什么",
    "你了解我",
    "关于我",
    "我的长期记忆",
    "长期记忆",
    "回忆一下",
    "你知道我",
)

STOPWORDS = {
    "我",
    "你",
    "她",
    "他",
    "的",
    "了",
    "是",
    "在",
    "有",
    "和",
    "跟",
    "就",
    "都",
    "也",
    "还",
    "吗",
    "呢",
    "啊",
    "吧",
    "想",
    "说",
    "这个",
    "那个",
    "一下",
    "现在",
    "今天",
    "我们",
    "可以",
    "一个",
    "怎么",
    "什么",
    "聊聊",
}

CATEGORY_HINTS = {
    "identity": ("身份", "名字", "叫", "专业", "学校", "身高", "体重"),
    "preference": ("喜欢", "偏好", "爱好", "游戏", "电影", "讨厌", "更喜欢"),
    "learning": ("学习", "代码", "编程", "单片机", "嵌入式", "通信", "信号", "专业"),
    "habit": ("习惯", "早睡", "健身", "读书", "作息"),
    "project": ("项目", "樱茗", "桌宠", "ai", "模型", "记忆体", "vtuber"),
    "persona": ("樱茗", "性格", "温柔", "人设", "语气", "陪伴"),
    "relationship": ("相处", "陪伴", "距离", "分寸", "关系"),
    "manual": ("记住", "记忆", "备注"),
}


@dataclass(frozen=True)
class RetrievedMemory:
    id: str
    category: str
    text: str
    source: str
    score: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "text": self.text,
            "source": self.source,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
        }


def retrieve_relevant_memories(
    memory_data: dict[str, Any],
    query_text: str,
    *,
    recent_messages: list[Message] | None = None,
    profile_text: str = "",
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
    min_score: float = 2.5,
) -> list[RetrievedMemory]:
    memories = confirmed_memories(memory_data)
    if not memories or limit <= 0:
        return []

    query = build_retrieval_query(query_text, recent_messages, profile_text)
    if is_recall_query(query_text):
        return recall_memories(memories, limit)

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scored: list[RetrievedMemory] = []
    for item in memories:
        result = score_memory(item, query, query_tokens)
        if result.score >= min_score:
            scored.append(result)

    scored.sort(key=lambda item: (-item.score, item.category, item.id))
    return scored[:limit]


def format_memory_context(
    memory_data: dict[str, Any],
    retrieved: list[RetrievedMemory],
    *,
    include_empty_note: bool = True,
) -> str:
    parts: list[str] = []

    owner = memory_data.get("owner", {})
    if isinstance(owner, dict) and owner:
        parts.append("【使用者基础信息（常驻）】")
        for key, value in owner.items():
            if value:
                parts.append(f"- {key}: {value}")

    parts.append("【当前相关长期记忆】")
    if retrieved:
        for item in retrieved:
            parts.append(f"- [{item.category}] {item.text}")
    elif include_empty_note:
        parts.append("- 暂未找到和当前消息明显相关的长期记忆；不要牵强提起不相关记忆。")

    boundaries = memory_data.get("boundaries", [])
    if isinstance(boundaries, list) and boundaries:
        parts.append("【相处边界（常驻）】")
        for boundary in boundaries:
            if boundary:
                parts.append(f"- {boundary}")

    parts.append("【记忆使用规则】")
    parts.append("- 只把上面列出的长期记忆当作当前对话的相关依据；未列出的记忆仍保存在本地，不要自行编造。")
    parts.append("- 待确认记忆没有出现在这里，不能当作事实使用。")
    return "\n".join(parts).strip()


def format_retrieved_memories(retrieved: list[RetrievedMemory]) -> str:
    if not retrieved:
        return "当前没有检索到明显相关的长期记忆。"
    lines = ["当前相关长期记忆："]
    for index, item in enumerate(retrieved, start=1):
        lines.append(f"{index}. [{item.category}] {item.text}")
    return "\n".join(lines)


def confirmed_memories(memory_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = memory_data.get("long_term", [])
    if not isinstance(raw_items, list):
        return []
    memories: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if text:
            memories.append(item)
    return memories


def build_retrieval_query(
    query_text: str,
    recent_messages: list[Message] | None = None,
    profile_text: str = "",
) -> str:
    parts = [query_text.strip()]
    if recent_messages:
        recent_parts = [
            str(message.get("content", "")).strip()
            for message in recent_messages[-4:]
            if str(message.get("content", "")).strip()
        ]
        parts.extend(recent_parts)
    return "\n".join(part for part in parts if part)


def is_recall_query(text: str) -> bool:
    normalized = text.strip().lower()
    return any(hint in normalized for hint in RECALL_QUERY_HINTS)


def recall_memories(memories: list[dict[str, Any]], limit: int) -> list[RetrievedMemory]:
    priority = {
        "identity": 0,
        "learning": 1,
        "preference": 2,
        "habit": 3,
        "project": 4,
        "persona": 5,
        "relationship": 6,
        "manual": 7,
    }
    ordered = sorted(
        memories,
        key=lambda item: (
            priority.get(str(item.get("category", "manual")), 20),
            str(item.get("created_at", "")),
        ),
    )
    results: list[RetrievedMemory] = []
    for index, item in enumerate(ordered[:limit]):
        results.append(
            RetrievedMemory(
                id=str(item.get("id", f"memory_{index}")),
                category=str(item.get("category", "memory")),
                text=str(item.get("text", "")).strip(),
                source=str(item.get("source", "")),
                score=100.0 - index,
                reasons=("用户询问樱茗记得什么",),
            )
        )
    return results


def score_memory(item: dict[str, Any], query: str, query_tokens: set[str]) -> RetrievedMemory:
    text = str(item.get("text", "")).strip()
    category = str(item.get("category", "memory")).strip() or "memory"
    source = str(item.get("source", "")).strip()
    item_id = str(item.get("id", ""))
    haystack = f"{category}\n{text}".lower()
    memory_tokens = tokenize(haystack)

    score = 0.0
    reasons: list[str] = []

    overlap = sorted((query_tokens & memory_tokens) - STOPWORDS, key=lambda token: (-len(token), token))
    if overlap:
        useful_overlap = overlap[:6]
        score += sum(2.0 + min(len(token), 6) * 0.35 for token in useful_overlap)
        reasons.append("关键词重合：" + "、".join(useful_overlap[:4]))

    for token in query_tokens:
        if len(token) >= 2 and token not in STOPWORDS and token in haystack:
            score += 1.2

    if category_boost(category, query):
        score += 1.8
        reasons.append(f"类别匹配：{category}")

    if text and text in query:
        score += 8.0
        reasons.append("整句匹配")

    return RetrievedMemory(
        id=item_id,
        category=category,
        text=text,
        source=source,
        score=score,
        reasons=tuple(reasons),
    )


def category_boost(category: str, query: str) -> bool:
    hints = CATEGORY_HINTS.get(category, ())
    lowered = query.lower()
    return any(hint in lowered for hint in hints)


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens: set[str] = set()
    tokens.update(match.group(0) for match in re.finditer(r"[a-z0-9_+#.-]{2,}", lowered))

    for chunk in re.findall(r"[\u4e00-\u9fff]+", lowered):
        if len(chunk) == 1:
            if chunk not in STOPWORDS:
                tokens.add(chunk)
            continue
        for size in (2, 3, 4):
            if len(chunk) < size:
                continue
            for index in range(0, len(chunk) - size + 1):
                token = chunk[index : index + size]
                if token not in STOPWORDS:
                    tokens.add(token)
        for char in chunk:
            if char not in STOPWORDS:
                tokens.add(char)

    return {token for token in tokens if token and token not in STOPWORDS}
