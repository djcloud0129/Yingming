from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yingming_core.behavior_protocol import PetAction, pet_action_for_mood


@dataclass(frozen=True)
class BodyState:
    key: str
    label: str
    mood: str
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "mood": self.mood,
            "description": self.description,
        }

    def as_pet_action(
        self,
        *,
        text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PetAction:
        merged_metadata = {
            "body_state": self.key,
            "body_label": self.label,
        }
        if metadata:
            merged_metadata.update(metadata)
        return pet_action_for_mood(
            self.mood,
            kind="stage",
            text=text,
            metadata=merged_metadata,
        )


BODY_STATES = {
    "idle": BodyState("idle", "安静待机", "normal", "没有正在处理的输入，保持轻微呼吸。"),
    "listening": BodyState("listening", "在听你说", "typing", "用户正在输入或刚说完一句话。"),
    "thinking": BodyState("thinking", "认真思考", "thinking", "正在等待模型或本地逻辑生成回复。"),
    "speaking": BodyState("speaking", "轻声回应", "normal", "正在把回复交给用户。"),
    "waiting_user": BodyState("waiting_user", "等你回答", "waiting", "话题已经递给用户，保持等待。"),
    "comforting": BodyState("comforting", "温柔陪着", "caring", "用户需要情绪支持，动作放轻。"),
    "focused": BodyState("focused", "专注处理", "focused", "正在处理项目、代码或复杂问题。"),
    "remembering": BodyState("remembering", "整理记忆", "memory", "正在处理长期记忆或画像。"),
    "sleepy": BodyState("sleepy", "放轻声音", "sleepy", "深夜或收尾状态，动作更安静。"),
    "error": BodyState("error", "连接异常", "error", "连接或内部流程出现异常。"),
    "greeting": BodyState("greeting", "向你招呼", "welcome", "欢迎、恢复窗口或轻提醒。"),
}


def body_state_for_key(key: str) -> BodyState:
    return BODY_STATES.get(key, BODY_STATES["idle"])


def body_state_for_dialogue(
    dialogue_state: dict[str, Any] | None,
    topic_state: dict[str, Any] | None = None,
    *,
    mode: str = "",
) -> BodyState:
    if mode == "fallback":
        return BODY_STATES["error"]

    dialogue_state = dialogue_state if isinstance(dialogue_state, dict) else {}
    topic_state = topic_state if isinstance(topic_state, dict) else {}
    topic_status = str(topic_state.get("status") or "")
    if topic_status in {"waiting_user", "paused"}:
        return BODY_STATES["waiting_user"]

    mood = str(dialogue_state.get("mood") or "normal")
    if mood == "waiting":
        return BODY_STATES["waiting_user"]
    if mood == "caring":
        return BODY_STATES["comforting"]
    if mood == "focused":
        return BODY_STATES["focused"]
    if mood == "thinking":
        return BODY_STATES["thinking"]
    if mood == "memory":
        return BODY_STATES["remembering"]
    if mood == "sleepy":
        return BODY_STATES["sleepy"]
    if mood == "error":
        return BODY_STATES["error"]
    return BODY_STATES["speaking"]


def body_state_for_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    current: BodyState | None = None,
) -> BodyState:
    payload = payload if isinstance(payload, dict) else {}
    if event_type in {"user.message", "ui.input"}:
        return BODY_STATES["listening"]
    if event_type == "model.thinking":
        return BODY_STATES["thinking"]
    if event_type in {"assistant.reply", "proactive.nudge"}:
        return body_state_for_dialogue(
            payload.get("dialogue_state"),
            payload.get("topic_state"),
            mode=str(payload.get("mode") or ""),
        )
    if event_type in {"memory.suggested", "memory.updated", "profile.updated"}:
        return BODY_STATES["remembering"]
    if event_type in {"model.fallback", "system.error"}:
        return BODY_STATES["error"]
    if event_type in {"welcome.ready", "ui.restore"}:
        return BODY_STATES["greeting"]
    if event_type in {"ui.wait", "topic.paused"}:
        return BODY_STATES["waiting_user"]
    if event_type == "idle":
        return BODY_STATES["idle"]
    return current or BODY_STATES["idle"]


class BodyStateMachine:
    def __init__(self, initial: str = "idle") -> None:
        self.current = body_state_for_key(initial)

    def transition(self, event_type: str, payload: dict[str, Any] | None = None) -> BodyState:
        self.current = body_state_for_event(event_type, payload, current=self.current)
        return self.current

    def set_state(self, key: str) -> BodyState:
        self.current = body_state_for_key(key)
        return self.current
