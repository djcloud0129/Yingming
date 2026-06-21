from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from yingming_core.behavior_protocol import pet_action_for_dialogue_state
from yingming_core.chat import append_history, build_messages, current_time_context, load_recent_history
from yingming_core.dialogue_state import (
    DialogueState,
    assistant_is_waiting_for_user,
    conversation_waiting_for_user,
    detect_dialogue_state,
    is_wait_command,
    STATES,
)
from yingming_core.events import EventBus
from yingming_core.greetings import contextual_welcome_text, proactive_text
from yingming_core.llm import LLMError, OfflineYingming, OpenAICompatibleClient, friendly_llm_error
from yingming_core.memory import MemoryStore
from yingming_core.topic_state import TopicState, detect_topic_state, topic_blocks_proactive
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
        self.events = EventBus()
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def emit_event(self, event_type: str, payload: dict[str, Any] | None = None, source: str = "service") -> dict[str, Any]:
        return self.events.emit(event_type, payload=payload, source=source).as_dict()

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
            "welcome": self.welcome(use_model=False)["welcome"],
            "dialogue_state": self.current_dialogue_state().as_dict(),
            "topic_state": self.current_topic_state().as_dict(),
            "events": self.events.recent(),
        }

    def current_dialogue_state(self) -> DialogueState:
        memory_data = self.memory.load()
        recent_messages = load_recent_history(
            self.history_path,
            limit=8,
            drop_offline_placeholders=self.client.available,
        )
        last_user = ""
        for message in reversed(recent_messages):
            if message.get("role") == "user":
                last_user = str(message.get("content", ""))
                break
        if conversation_waiting_for_user(recent_messages):
            return STATES["waiting_reply"]
        return detect_dialogue_state(last_user, recent_messages, memory_data)

    def current_topic_state(self) -> TopicState:
        recent_messages = load_recent_history(
            self.history_path,
            limit=12,
            drop_offline_placeholders=self.client.available,
        )
        return detect_topic_state(recent_messages)

    def welcome(self, use_model: bool = False) -> dict[str, Any]:
        memory_data = self.memory.load()
        recent_messages = load_recent_history(
            self.history_path,
            limit=8,
            drop_offline_placeholders=self.client.available,
        )
        fallback = contextual_welcome_text(memory_data, recent_messages)
        if not use_model or not self.client.available:
            return {"welcome": fallback, "mode": "local"}

        try:
            welcome = self.build_online_welcome(fallback, memory_data, recent_messages)
        except LLMError as exc:
            return {"welcome": fallback, "mode": "fallback", "error": str(exc)}

        return {"welcome": welcome or fallback, "mode": "online"}

    def proactive_nudge(self, sequence: int = 0) -> dict[str, Any]:
        mode = self.client.settings.proactive_mode
        if mode == "quiet":
            return {"message": "", "mode": mode}

        recent_messages = load_recent_history(
            self.history_path,
            limit=8,
            drop_offline_placeholders=self.client.available,
        )
        if conversation_waiting_for_user(recent_messages):
            return {"message": "", "mode": mode, "waiting_for_user": True}
        topic_state = detect_topic_state(recent_messages)
        if topic_blocks_proactive(topic_state):
            return {
                "message": "",
                "mode": mode,
                "topic_state": topic_state.as_dict(),
                "topic_open": True,
            }
        dialogue_state = self.current_dialogue_state()
        message = proactive_text(
            self.memory.load(),
            recent_messages,
            mode=mode,
            sequence=sequence,
        )
        dialogue_dict = dialogue_state.as_dict()
        topic_dict = topic_state.as_dict()
        pet_action = pet_action_for_dialogue_state(
            dialogue_dict,
            text=message,
            metadata={"trigger": "proactive", "mode": mode},
        ).as_dict()
        events = [
            self.emit_event("proactive.nudge", {"message": message, "mode": mode}, source="service"),
            self.emit_event("mood.changed", dialogue_dict, source="service"),
            self.emit_event("topic.updated", topic_dict, source="service"),
            self.emit_event("pet.action", pet_action, source="service"),
        ]
        return {
            "message": message,
            "mode": mode,
            "dialogue_state": dialogue_dict,
            "topic_state": topic_dict,
            "pet_action": pet_action,
            "events": events,
        }

    def build_online_welcome(
        self,
        fallback: str,
        memory_data: dict[str, Any],
        recent_messages: list[dict[str, str]],
    ) -> str:
        pending = memory_data.get("pending", [])
        pending_items = pending if isinstance(pending, list) else []
        pending_text = format_memory_items(pending_items[:3])
        recent_text = format_recent_messages(recent_messages[-6:])
        memory_text = self.memory.as_prompt_text()
        messages = [
            {
                "role": "system",
                "content": (
                    "你是樱茗的启动欢迎语生成器。请写一段樱茗打开窗口时对用户说的话。"
                    "要求：中文，1 到 3 句，120 字以内，像真实相处中的温柔 AI 伙伴。"
                    "要主动接上最近状态；如果有待确认记忆，轻轻提醒。"
                    "不要说自己在读取系统提示、后台、接口或 API。不要假装成人类或现实女友。"
                    "不要输出引号、项目符号或“樱茗：”前缀。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{current_time_context()}\n\n"
                    f"本地欢迎语参考：{fallback}\n\n"
                    "用户画像：\n"
                    f"{clip_text(self.read_profile() or '无', 1000)}\n\n"
                    "长期记忆与边界：\n"
                    f"{clip_text(memory_text or '无', 1600)}\n\n"
                    f"待确认记忆数量：{len(pending_items)}\n"
                    f"待确认记忆示例：\n{pending_text or '无'}\n\n"
                    f"最近对话：\n{recent_text or '无'}\n\n"
                    "请直接输出欢迎语。"
                ),
            },
        ]
        raw = self.client.complete(messages, max_tokens=220, temperature=0.6)
        return clean_welcome_text(raw)

    def reply(self, user_text: str) -> dict[str, Any]:
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("消息不能为空。")
        turn_events: list[dict[str, Any]] = []

        def record(event_type: str, payload: dict[str, Any], source: str = "service") -> None:
            turn_events.append(self.emit_event(event_type, payload, source=source))

        recent_messages = load_recent_history(
            self.history_path,
            limit=12,
            drop_offline_placeholders=self.client.available,
        )
        record("user.message", {"text": user_text}, source="user")
        if is_wait_command(user_text):
            dialogue_state = STATES["waiting_reply"]
            topic_state = detect_topic_state(recent_messages, user_text)
            assistant_text = "好，我等你。你慢慢想，我不会自己把话题岔开。"
            append_history(self.history_path, "user", user_text)
            append_history(self.history_path, "assistant", assistant_text)
            dialogue_dict = dialogue_state.as_dict()
            topic_dict = topic_state.as_dict()
            pet_action = pet_action_for_dialogue_state(
                dialogue_dict,
                text=assistant_text,
                metadata={"mode": "local", "topic_status": topic_state.status},
            ).as_dict()
            record("assistant.reply", {"text": assistant_text, "mode": "local"}, source="assistant")
            record("mood.changed", dialogue_dict)
            record("topic.updated", topic_dict)
            record("pet.action", pet_action)
            return {
                "reply": assistant_text,
                "mode": "local",
                "memories_added": [],
                "memory_suggestions": [],
                "history": load_recent_history(self.history_path, limit=80),
                "dialogue_state": dialogue_dict,
                "topic_state": topic_dict,
                "pet_action": pet_action,
                "events": turn_events,
            }

        memory_data = self.memory.load()
        dialogue_state = detect_dialogue_state(user_text, recent_messages, memory_data)
        topic_state = detect_topic_state(recent_messages, user_text)
        messages = build_messages(
            self.read_persona(),
            self.read_profile(),
            self.memory.as_prompt_text(),
            recent_messages,
            user_text,
            active_model=self.client.settings.display_name if self.client.available else "",
            dialogue_state_text=dialogue_state.as_prompt_text(),
            topic_state_text=topic_state.as_prompt_text(),
        )

        mode = "online" if self.client.available else "offline"
        try:
            assistant_text = self.client.complete(messages) if self.client.available else self.offline.complete(messages)
        except LLMError as exc:
            mode = "fallback"
            readable_error = friendly_llm_error(exc)
            assistant_text = (
                "DeepSeek 刚刚断了一下，我先接住这一句。\n"
                f"{readable_error}\n\n"
                f"{self.offline.complete(messages)}"
            )
            record("model.fallback", {"reason": readable_error, "model": self.client.settings.display_name})

        append_history(self.history_path, "user", user_text)
        append_history(self.history_path, "assistant", assistant_text)
        memory_suggestions = self.suggest_memories_from_turn(user_text, assistant_text) if mode == "online" else []
        display_state = STATES["waiting_reply"] if assistant_is_waiting_for_user(assistant_text) else dialogue_state
        display_topic = topic_state.with_status("waiting_user") if assistant_is_waiting_for_user(assistant_text) else topic_state
        dialogue_dict = display_state.as_dict()
        topic_dict = display_topic.as_dict()
        suggestion_dicts = [item.__dict__ for item in memory_suggestions]
        pet_action = pet_action_for_dialogue_state(
            dialogue_dict,
            text=assistant_text,
            metadata={"mode": mode, "topic_status": display_topic.status},
        ).as_dict()
        record("assistant.reply", {"text": assistant_text, "mode": mode}, source="assistant")
        record("mood.changed", dialogue_dict)
        record("topic.updated", topic_dict)
        if suggestion_dicts:
            record("memory.suggested", {"count": len(suggestion_dicts), "items": suggestion_dicts})
        record("pet.action", pet_action)

        return {
            "reply": assistant_text,
            "mode": mode,
            "memories_added": [],
            "memory_suggestions": suggestion_dicts,
            "history": load_recent_history(self.history_path, limit=80),
            "dialogue_state": dialogue_dict,
            "topic_state": topic_dict,
            "pet_action": pet_action,
            "events": turn_events,
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

    def test_model_connection(self, settings: ModelSettings | None = None) -> dict[str, Any]:
        client = OpenAICompatibleClient(self.project_root, settings=settings) if settings else self.client
        if not client.available:
            return {"ok": False, "message": friendly_llm_error("未配置 DeepSeek/OpenAI API key。")}
        messages = [
            {"role": "system", "content": "请用中文简短回复。"},
            {"role": "user", "content": "请只回复：樱茗连接正常。"},
        ]
        try:
            reply = client.complete(messages, max_tokens=40, temperature=0.2)
        except LLMError as exc:
            return {"ok": False, "message": friendly_llm_error(exc)}
        return {"ok": True, "message": f"连接成功：{clip_text(reply, 40)}"}

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


def format_memory_items(items: list[Any]) -> str:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "manual")).strip() or "manual"
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(f"{index}. [{category}] {clip_text(text, 120)}")
    return "\n".join(lines)


def format_recent_messages(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = "用户" if message.get("role") == "user" else "樱茗"
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {clip_text(content, 180)}")
    return "\n".join(lines)


def clean_welcome_text(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    cleaned = "\n".join(lines[:3]).strip()
    for prefix in ("樱茗：", "樱茗:", "助手：", "助手:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    return clip_text(cleaned, 260)


def clip_text(text: str, limit: int) -> str:
    compacted = " ".join(str(text).split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: max(0, limit - 1)].rstrip() + "..."


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
