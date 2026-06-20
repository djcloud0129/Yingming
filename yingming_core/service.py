from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yingming_core.chat import append_history, build_messages, load_recent_history
from yingming_core.llm import LLMError, OfflineYingming, OpenAICompatibleClient
from yingming_core.memory import MemoryStore
from yingming_core.settings import (
    ModelSettings,
    deepseek_default_settings,
    redacted_model_settings,
    save_model_settings,
)


MAX_AUTO_MEMORIES_PER_TURN = 3


class YingmingService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.persona_path = project_root / "personas" / "yingming.md"
        self.profile_path = project_root / "data" / "profile.md"
        self.history_path = project_root / "data" / "chat_history.jsonl"
        self.memory = MemoryStore(project_root / "data" / "memory.json")
        self.client = OpenAICompatibleClient(project_root)
        self.offline = OfflineYingming()
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def state(self) -> dict[str, Any]:
        return {
            "model": {
                "available": self.client.available,
                "name": self.client.settings.display_name if self.client.available else "离线模式",
                "base_url": self.client.base_url if self.client.available else "",
                "settings": redacted_model_settings(self.client.settings),
            },
            "persona": self.read_persona(),
            "profile": self.read_profile(),
            "memory": self.memory.load(),
            "memory_text": self.memory.as_readable_text(),
            "history": load_recent_history(self.history_path, limit=80),
        }

    def reply(self, user_text: str) -> dict[str, Any]:
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("消息不能为空。")

        recent_messages = load_recent_history(self.history_path, limit=12)
        messages = build_messages(
            self.read_persona(),
            self.read_profile(),
            self.memory.as_prompt_text(),
            recent_messages,
            user_text,
        )

        mode = "online" if self.client.available else "offline"
        try:
            assistant_text = self.client.complete(messages) if self.client.available else self.offline.complete(messages)
        except LLMError as exc:
            mode = "fallback"
            assistant_text = (
                "模型那边暂时没有接上，我先用自己的小纸条回答你。\n"
                f"接口信息：{exc}\n\n"
                f"{self.offline.complete(messages)}"
            )

        append_history(self.history_path, "user", user_text)
        append_history(self.history_path, "assistant", assistant_text)
        added_memories = self.extract_memories_from_turn(user_text, assistant_text) if mode == "online" else []

        return {
            "reply": assistant_text,
            "mode": mode,
            "memories_added": [item.__dict__ for item in added_memories],
            "history": load_recent_history(self.history_path, limit=80),
        }

    def remember(self, text: str, category: str = "manual") -> dict[str, Any]:
        item = self.memory.add(text, category=category or "manual", source="web")
        return {"item": item.__dict__, "memory": self.memory.load(), "memory_text": self.memory.as_readable_text()}

    def save_profile(self, text: str) -> dict[str, str]:
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(text, encoding="utf-8")
        return {"profile": text}

    def save_model_settings(self, settings: ModelSettings) -> dict[str, Any]:
        save_model_settings(self.project_root, settings)
        self.client = OpenAICompatibleClient(self.project_root)
        return {"model": redacted_model_settings(self.client.settings)}

    def deepseek_defaults(self, api_key: str = "") -> ModelSettings:
        return deepseek_default_settings(api_key=api_key)

    def clear_history(self) -> dict[str, list[Any]]:
        if self.history_path.exists():
            self.history_path.unlink()
        return {"history": []}

    def read_persona(self) -> str:
        return self.persona_path.read_text(encoding="utf-8") if self.persona_path.exists() else ""

    def read_profile(self) -> str:
        return self.profile_path.read_text(encoding="utf-8") if self.profile_path.exists() else ""

    def extract_memories_from_turn(self, user_text: str, assistant_text: str) -> list[Any]:
        if not self.client.available or not self.client.settings.auto_memory:
            return []

        messages = [
            {
                "role": "system",
                "content": (
                    "你是樱茗的长期记忆整理器。只从用户明确表达的内容中提取稳定、可长期使用的信息。"
                    "可以保存：称呼、学习目标、项目目标、偏好、希望被怎样帮助、反复出现的习惯。"
                    "不要保存：身份证/住址/电话/账号密钥、未经确认的敏感健康或财务信息、短暂情绪、"
                    "你自己的推测、助手说过但用户没有确认的内容。"
                    "如果没有值得长期记住的新信息，返回空数组。只输出 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "现有记忆：\n"
                    f"{self.memory.as_prompt_text() or '无'}\n\n"
                    "本轮用户消息：\n"
                    f"{user_text}\n\n"
                    "本轮樱茗回复：\n"
                    f"{assistant_text}\n\n"
                    "输出格式："
                    "{\"memories\":[{\"category\":\"preference|project|habit|learning|identity|manual\","
                    "\"text\":\"一句完整中文记忆\"}]}"
                ),
            },
        ]

        try:
            raw = self.client.complete(
                messages,
                response_format="json_object",
                max_tokens=600,
                temperature=0.2,
            )
            data = json.loads(extract_json_object(raw))
        except Exception:
            return []

        memories = data.get("memories", [])
        if not isinstance(memories, list):
            return []

        added = []
        existing_texts = {
            str(item.get("text", "")).strip()
            for item in self.memory.load().get("long_term", [])
            if str(item.get("text", "")).strip()
        }
        for memory in memories[:MAX_AUTO_MEMORIES_PER_TURN]:
            if not isinstance(memory, dict):
                continue
            text = str(memory.get("text", "")).strip()
            if not text or text in existing_texts or len(text) > 240:
                continue
            category = str(memory.get("category", "manual")).strip() or "manual"
            added.append(self.memory.add(text, category=category, source="auto_chat"))
            existing_texts.add(text)

        return added


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("没有找到 JSON 对象。")
    return stripped[start : end + 1]
