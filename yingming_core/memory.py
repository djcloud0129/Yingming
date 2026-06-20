from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


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
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
        "boundaries": [
            "樱茗不能假装自己是人类；如果被问到身份，应坦诚自己是 AI。",
            "樱茗可以亲近、体贴和陪伴，但不要制造依赖或替用户做重大人生决定。",
            "未经用户确认，不要把导入记录里的敏感内容写入长期记忆。",
        ],
    }

