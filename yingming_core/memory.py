from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


MEMORY_CATEGORIES = (
    "identity",
    "preference",
    "learning",
    "habit",
    "project",
    "persona",
    "relationship",
    "manual",
)


@dataclass(frozen=True)
class MemoryItem:
    id: str
    category: str
    text: str
    source: str
    created_at: str


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps(default_memory(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> dict[str, Any]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        changed = self.ensure_shape(data)
        if changed:
            self.save(data)
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_shape(self, data: dict[str, Any]) -> bool:
        changed = False
        for key, default in (("long_term", []), ("pending", []), ("boundaries", [])):
            if key not in data or not isinstance(data.get(key), list):
                data[key] = default.copy()
                changed = True
        return changed

    def add(self, text: str, category: str = "manual", source: str = "chat") -> MemoryItem:
        text = text.strip()
        if not text:
            raise ValueError("记忆内容不能为空。")

        data = self.load()
        item = MemoryItem(
            id=f"mem_{uuid4().hex[:10]}",
            category=category,
            text=text,
            source=source,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        data.setdefault("long_term", []).append(item.__dict__)
        self.save(data)
        return item

    def add_pending(self, text: str, category: str = "manual", source: str = "auto_chat") -> MemoryItem:
        text = text.strip()
        if not text:
            raise ValueError("待确认记忆内容不能为空。")

        data = self.load()
        item = MemoryItem(
            id=f"pend_{uuid4().hex[:10]}",
            category=normalize_category(category),
            text=text,
            source=source,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        data.setdefault("pending", []).append(item.__dict__)
        self.save(data)
        return item

    def update(self, memory_id: str, text: str, category: str) -> dict[str, Any]:
        data = self.load()
        index = self.find_index(data.get("long_term", []), memory_id)
        if index == -1:
            raise ValueError("没有找到这条长期记忆。")

        text = text.strip()
        if not text:
            raise ValueError("记忆内容不能为空。")

        item = data["long_term"][index]
        item["text"] = text
        item["category"] = normalize_category(category)
        item["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.save(data)
        return item

    def delete(self, memory_id: str) -> dict[str, Any]:
        data = self.load()
        memories = data.get("long_term", [])
        index = self.find_index(memories, memory_id)
        if index == -1:
            raise ValueError("没有找到这条长期记忆。")
        item = memories.pop(index)
        self.save(data)
        return item

    def update_pending(self, pending_id: str, text: str, category: str) -> dict[str, Any]:
        data = self.load()
        index = self.find_index(data.get("pending", []), pending_id)
        if index == -1:
            raise ValueError("没有找到这条待确认记忆。")

        text = text.strip()
        if not text:
            raise ValueError("待确认记忆内容不能为空。")

        item = data["pending"][index]
        item["text"] = text
        item["category"] = normalize_category(category)
        item["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.save(data)
        return item

    def confirm_pending(self, pending_id: str, text: str | None = None, category: str | None = None) -> MemoryItem:
        data = self.load()
        pending = data.get("pending", [])
        index = self.find_index(pending, pending_id)
        if index == -1:
            raise ValueError("没有找到这条待确认记忆。")

        pending_item = pending.pop(index)
        final_text = (text if text is not None else str(pending_item.get("text", ""))).strip()
        if not final_text:
            raise ValueError("记忆内容不能为空。")

        item = MemoryItem(
            id=f"mem_{uuid4().hex[:10]}",
            category=normalize_category(category or str(pending_item.get("category", "manual"))),
            text=final_text,
            source="confirmed_" + str(pending_item.get("source", "pending")),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        item_data = item.__dict__.copy()
        item_data["suggested_at"] = pending_item.get("created_at", "")
        data.setdefault("long_term", []).append(item_data)
        self.save(data)
        return item

    def discard_pending(self, pending_id: str) -> dict[str, Any]:
        data = self.load()
        pending = data.get("pending", [])
        index = self.find_index(pending, pending_id)
        if index == -1:
            raise ValueError("没有找到这条待确认记忆。")
        item = pending.pop(index)
        self.save(data)
        return item

    def find_index(self, items: list[Any], item_id: str) -> int:
        for index, item in enumerate(items):
            if isinstance(item, dict) and item.get("id") == item_id:
                return index
        return -1

    def as_prompt_text(self) -> str:
        data = self.load()
        parts: list[str] = []

        owner = data.get("owner", {})
        if owner:
            parts.append("【使用者基础信息】")
            for key, value in owner.items():
                parts.append(f"- {key}: {value}")

        memories = data.get("long_term", [])
        if memories:
            parts.append("【长期记忆】")
            for item in memories:
                parts.append(f"- [{item.get('category', 'memory')}] {item.get('text', '')}")

        boundaries = data.get("boundaries", [])
        if boundaries:
            parts.append("【相处边界】")
            for boundary in boundaries:
                parts.append(f"- {boundary}")

        return "\n".join(parts).strip()

    def as_readable_text(self) -> str:
        data = self.load()
        memories = data.get("long_term", [])
        if not memories:
            return "现在还没有长期记忆。"

        lines = ["当前长期记忆："]
        for index, item in enumerate(memories, start=1):
            category = item.get("category", "memory")
            text = item.get("text", "")
            created_at = item.get("created_at", "")
            lines.append(f"{index}. [{category}] {text} ({created_at})")
        return "\n".join(lines)


def default_memory() -> dict[str, Any]:
    return {
        "owner": {
            "preferred_language": "中文为主",
            "current_project": "正在制作一个属于自己的 AI 伙伴，名字叫樱茗。",
        },
        "yingming": {
            "name": "樱茗",
            "temperament": "温柔体贴，有大和抚子般的安静气质，但带一点机灵和轻微打趣。",
        },
        "long_term": [
            {
                "id": "mem_initial_001",
                "category": "project",
                "text": "用户希望先制作文字版樱茗，之后再考虑接入 VTuber 模型、语音和直播互动。",
                "source": "initial_setup",
                "created_at": "2026-06-19T00:00:00",
            },
            {
                "id": "mem_initial_002",
                "category": "persona",
                "text": "樱茗应当中文为主，性格温柔体贴，像大和抚子，但不要木讷，要多一点机灵。",
                "source": "initial_setup",
                "created_at": "2026-06-19T00:00:00",
            },
            {
                "id": "mem_initial_003",
                "category": "personalization",
                "text": "用户希望之后导入自己和 ChatGPT 的记录，让樱茗分析并逐步变得更懂自己。",
                "source": "initial_setup",
                "created_at": "2026-06-19T00:00:00",
            },
        ],
        "pending": [],
        "boundaries": [
            "樱茗不能假装自己是人类；如果被问到身份，应坦诚自己是 AI。",
            "樱茗可以亲近、体贴和陪伴，但不要制造依赖或替用户做重大人生决定。",
            "未经用户确认，不要把导入记录里的敏感内容写入长期记忆。",
        ],
    }


def normalize_category(category: str) -> str:
    text = category.strip().lower()
    return text if text in MEMORY_CATEGORIES else "manual"
