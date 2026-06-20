from __future__ import annotations

from datetime import datetime
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
        self.profile_draft_path = project_root / "data" / "profile_draft.md"
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

        recent_messages = load_recent_history(
            self.history_path,
            limit=12,
            drop_offline_placeholders=self.client.available,
        )
        messages = build_messages(
            self.read_persona(),
            self.read_profile(),
            self.memory.as_prompt_text(),
            recent_messages,
            user_text,
            active_model=self.client.settings.display_name if self.client.available else "",
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
        memory_suggestions = self.suggest_memories_from_turn(user_text, assistant_text) if mode == "online" else []

        return {
            "reply": assistant_text,
            "mode": mode,
            "memories_added": [],
            "memory_suggestions": [item.__dict__ for item in memory_suggestions],
            "history": load_recent_history(self.history_path, limit=80),
        }

    def remember(self, text: str, category: str = "manual", refresh_profile: bool = True) -> dict[str, Any]:
        item = self.memory.add(text, category=category or "manual", source="web")
        profile_result = self.auto_refresh_profile("新增长期记忆") if refresh_profile else {"updated": False}
        return {
            "item": item.__dict__,
            "memory": self.memory.load(),
            "memory_text": self.memory.as_readable_text(),
            "profile_updated": profile_result["updated"],
        }

    def suggest_memory(self, text: str, category: str = "manual") -> dict[str, Any]:
        item = self.memory.add_pending(text, category=category or "manual", source="manual_pending")
        return {"item": item.__dict__, "memory": self.memory.load(), "memory_text": self.memory.as_readable_text()}

    def update_memory(self, memory_id: str, text: str, category: str, refresh_profile: bool = True) -> dict[str, Any]:
        item = self.memory.update(memory_id, text, category)
        profile_result = self.auto_refresh_profile("修改长期记忆") if refresh_profile else {"updated": False}
        return {"item": item, "memory": self.memory.load(), "memory_text": self.memory.as_readable_text(), "profile_updated": profile_result["updated"]}

    def delete_memory(self, memory_id: str, refresh_profile: bool = True) -> dict[str, Any]:
        item = self.memory.delete(memory_id)
        profile_result = self.auto_refresh_profile("删除长期记忆") if refresh_profile else {"updated": False}
        return {"item": item, "memory": self.memory.load(), "memory_text": self.memory.as_readable_text(), "profile_updated": profile_result["updated"]}

    def update_pending_memory(self, pending_id: str, text: str, category: str) -> dict[str, Any]:
        item = self.memory.update_pending(pending_id, text, category)
        return {"item": item, "memory": self.memory.load(), "memory_text": self.memory.as_readable_text()}

    def confirm_pending_memory(
        self,
        pending_id: str,
        text: str | None = None,
        category: str | None = None,
        refresh_profile: bool = True,
    ) -> dict[str, Any]:
        item = self.memory.confirm_pending(pending_id, text=text, category=category)
        profile_result = self.auto_refresh_profile("确认待确认记忆") if refresh_profile else {"updated": False}
        return {
            "item": item.__dict__,
            "memory": self.memory.load(),
            "memory_text": self.memory.as_readable_text(),
            "profile_updated": profile_result["updated"],
        }

    def discard_pending_memory(self, pending_id: str) -> dict[str, Any]:
        item = self.memory.discard_pending(pending_id)
        return {"item": item, "memory": self.memory.load(), "memory_text": self.memory.as_readable_text()}

    def save_profile(self, text: str) -> dict[str, str]:
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(text, encoding="utf-8")
        return {"profile": text}

    def generate_profile_draft(self) -> dict[str, str]:
        current_profile = self.read_profile()
        memory_text = self.memory.as_prompt_text()
        if self.client.available:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是樱茗的用户画像整理器。请只根据用户已经确认的画像和长期记忆生成画像草稿，"
                        "不要编造，不要把待确认信息当作事实。"
                        "输出 Markdown，结构清晰，中文为主。"
                        "要把敏感或需要谨慎使用的信息单独放在“谨慎使用”部分，提醒樱茗不要主动频繁提起。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "当前画像：\n"
                        f"{current_profile or '无'}\n\n"
                        "长期记忆：\n"
                        f"{memory_text or '无'}\n\n"
                        "请生成一份可直接保存为 data/profile.md 的画像草稿。"
                        "建议包含：基本身份、学习方式、兴趣与目标、相处偏好、正在做的项目、谨慎使用。"
                    ),
                },
            ]
            try:
                draft = self.client.complete(messages, max_tokens=1800, temperature=0.3)
            except LLMError:
                draft = build_local_profile_draft(current_profile, memory_text)
        else:
            draft = build_local_profile_draft(current_profile, memory_text)

        self.profile_draft_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_draft_path.write_text(draft, encoding="utf-8")
        return {"profile_draft": draft, "profile_draft_path": str(self.profile_draft_path)}

    def auto_refresh_profile(self, reason: str = "") -> dict[str, Any]:
        if not self.client.settings.auto_profile:
            return {"updated": False, "reason": "自动画像已关闭"}
        if not self.client.available:
            return {"updated": False, "reason": "在线模型不可用"}

        current_profile = self.read_profile()
        memory_text = self.memory.as_prompt_text()
        if not memory_text:
            return {"updated": False, "reason": "没有长期记忆"}

        draft = self.build_profile_text(current_profile, memory_text, reason=reason)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        if current_profile.strip():
            backup_path = self.profile_path.with_name(
                "profile.before-auto-" + datetime.now().strftime("%Y%m%d%H%M%S") + ".md"
            )
            backup_path.write_text(current_profile, encoding="utf-8")
        self.profile_path.write_text(draft, encoding="utf-8")
        self.profile_draft_path.write_text(draft, encoding="utf-8")
        return {"updated": True, "profile": draft}

    def build_profile_text(self, current_profile: str, memory_text: str, reason: str = "") -> str:
        if self.client.available:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是樱茗的自动画像整理器。请根据已经确认的长期记忆更新正式用户画像。"
                        "必须保留当前画像中仍然合理的人工编辑内容，不要编造，不要把待确认信息写成事实。"
                        "输出 Markdown，可直接保存为 data/profile.md。"
                        "对感情、家庭、成长经历、健康等私人内容放在“谨慎使用”部分，并提醒樱茗不要主动频繁提起。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"触发原因：{reason or '长期记忆更新'}\n\n"
                        "当前画像：\n"
                        f"{current_profile or '无'}\n\n"
                        "已确认长期记忆：\n"
                        f"{memory_text or '无'}\n\n"
                        "请生成更新后的正式画像。建议包含：基本身份、学习方式、兴趣与目标、"
                        "相处偏好、正在做的项目、谨慎使用。"
                    ),
                },
            ]
            try:
                return self.client.complete(messages, max_tokens=1800, temperature=0.25)
            except LLMError:
                pass
        return build_local_profile_draft(current_profile, memory_text)

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

    def suggest_memories_from_turn(self, user_text: str, assistant_text: str) -> list[Any]:
        if not self.client.available or not self.client.settings.auto_memory:
            return []

        messages = [
            {
                "role": "system",
                "content": (
                    "你是樱茗的长期记忆整理器。只从用户明确表达的内容中提取稳定、可长期使用的信息，"
                    "这些信息会先进入待确认区，等待用户手动确认。"
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
            for item in [
                *self.memory.load().get("long_term", []),
                *self.memory.load().get("pending", []),
            ]
            if str(item.get("text", "")).strip()
        }
        for memory in memories[:MAX_AUTO_MEMORIES_PER_TURN]:
            if not isinstance(memory, dict):
                continue
            text = str(memory.get("text", "")).strip()
            if not text or text in existing_texts or len(text) > 240:
                continue
            category = str(memory.get("category", "manual")).strip() or "manual"
            added.append(self.memory.add_pending(text, category=category, source="auto_chat"))
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


def build_local_profile_draft(current_profile: str, memory_text: str) -> str:
    profile = current_profile.strip() or "暂无已保存画像。"
    memory = memory_text.strip() or "暂无长期记忆。"
    return "\n".join(
        [
            "# 使用者画像草稿",
            "",
            "这份草稿由本地模板根据当前画像和长期记忆整理。请检查、删改后再保存为正式画像。",
            "",
            "## 当前画像摘要",
            "",
            profile,
            "",
            "## 长期记忆依据",
            "",
            memory,
            "",
            "## 整理建议",
            "",
            "- 保留稳定身份、长期目标、学习偏好和相处偏好。",
            "- 对家庭、感情、成长经历等较私人的内容，放到“谨慎使用”部分。",
            "- 删除不想让樱茗长期使用的内容，再保存正式画像。",
            "",
            "## 谨慎使用",
            "",
            "- 涉及隐私、感情、家庭和成长经历的信息，只在用户主动提起或明显需要时使用。",
        ]
    )
