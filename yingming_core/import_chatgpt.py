from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImportResult:
    user_message_count: int
    profile_draft_path: Path
    corpus_path: Path


def import_chatgpt_export(path: Path, project_root: Path, limit: int | None = None) -> ImportResult:
    conversations = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(conversations, list):
        raise ValueError("ChatGPT 导出的 conversations.json 应该是一个列表。")

    return import_chatgpt_conversations(conversations, project_root, limit=limit)


def import_chatgpt_conversations(
    conversations: list[dict[str, Any]],
    project_root: Path,
    limit: int | None = None,
) -> ImportResult:
    if limit is not None:
        conversations = conversations[:limit]

    user_messages: list[dict[str, str]] = []
    for conversation in conversations:
        title = str(conversation.get("title") or "未命名对话")
        for message in iter_messages(conversation):
            if message.get("role") != "user":
                continue
            text = message.get("text", "").strip()
            if not text:
                continue
            user_messages.append({"title": title, "text": text})

    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = data_dir / "user_corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as handle:
        for item in user_messages:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    profile_draft_path = data_dir / "profile_draft.md"
    profile_draft_path.write_text(build_profile_draft(user_messages), encoding="utf-8")

    return ImportResult(
        user_message_count=len(user_messages),
        profile_draft_path=profile_draft_path,
        corpus_path=corpus_path,
    )


def iter_messages(conversation: dict[str, Any]) -> list[dict[str, str]]:
    mapping = conversation.get("mapping", {})
    if not isinstance(mapping, dict):
        return []

    messages: list[dict[str, str]] = []
    for node in mapping.values():
        message = node.get("message") if isinstance(node, dict) else None
        if not isinstance(message, dict):
            continue
        author = message.get("author", {})
        role = author.get("role")
        content = message.get("content", {})
        parts = content.get("parts", [])
        text_parts = [part for part in parts if isinstance(part, str)]
        text = "\n".join(text_parts).strip()
        if role and text:
            messages.append({"role": str(role), "text": text})

    return messages


def build_profile_draft(user_messages: list[dict[str, str]]) -> str:
    total = len(user_messages)
    samples = user_messages[:20]
    topics = score_topics(user_messages)

    lines = [
        "# 用户画像草稿",
        "",
        "这份文件由导入工具根据 ChatGPT 导出的用户消息生成，只适合作为人工确认前的草稿。",
        "请先删除不想让樱茗记住的内容，再把确认后的信息移动到 `data/profile.md` 或长期记忆。",
        "",
        "## 导入概况",
        "",
        f"- 用户消息数量：{total}",
        "",
        "## 高频线索",
        "",
    ]

    if topics:
        for topic, count in topics:
            lines.append(f"- {topic}: {count}")
    else:
        lines.append("- 暂无足够线索。")

    lines.extend(
        [
            "",
            "## 待人工确认的问题",
            "",
            "- 用户希望樱茗怎样称呼自己？",
            "- 用户在压力大时，希望樱茗先安慰、先分析，还是先给行动清单？",
            "- 哪些话题适合进入长期记忆？哪些只适合当次对话使用？",
            "- 用户不喜欢怎样的语气？",
            "",
            "## 消息样本",
            "",
        ]
    )

    for index, item in enumerate(samples, start=1):
        title = item["title"].replace("\n", " ")
        text = trim(item["text"].replace("\n", " "), 240)
        lines.append(f"{index}. 《{title}》 {text}")

    lines.append("")
    return "\n".join(lines)


def score_topics(user_messages: list[dict[str, str]]) -> list[tuple[str, int]]:
    topic_keywords = {
        "AI/模型/自动化": ("ai", "AI", "模型", "agent", "GPT", "prompt", "自动化"),
        "代码/工程": ("代码", "项目", "Python", "前端", "后端", "bug", "开发", "repo"),
        "创作/角色": ("角色", "设定", "世界观", "故事", "人设", "写作", "画风"),
        "情绪/陪伴": ("焦虑", "难受", "压力", "喜欢", "陪", "孤独", "安慰"),
        "学习/规划": ("学习", "计划", "目标", "复习", "考试", "课程", "路线"),
        "游戏/直播": ("游戏", "直播", "VTuber", "弹幕", "obs", "OBS", "主播"),
    }

    joined = "\n".join(item["text"] for item in user_messages)
    scores: list[tuple[str, int]] = []
    for topic, keywords in topic_keywords.items():
        count = sum(joined.count(keyword) for keyword in keywords)
        if count:
            scores.append((topic, count))

    return sorted(scores, key=lambda item: item[1], reverse=True)


def trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
