from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PetAction:
    kind: str
    mood: str
    expression: str
    action: str
    motion: str
    text: str = ""
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mood": self.mood,
            "expression": self.expression,
            "action": self.action,
            "motion": self.motion,
            "text": self.text,
            "priority": self.priority,
            "metadata": self.metadata,
        }


MOOD_ACTIONS = {
    "normal": ("微笑", "轻轻呼吸", "breath"),
    "focused": ("认真", "靠近看", "focus"),
    "caring": ("温柔", "轻轻点头", "nod"),
    "thinking": ("在想", "整理思路", "think"),
    "sleepy": ("困困", "声音放轻", "sleep"),
    "memory": ("记下", "翻看记忆", "memory"),
    "waiting": ("安静", "等你回答", "wait"),
    "error": ("抱歉", "有点慌张", "shake"),
    "typing": ("在听", "看着你打字", "wait"),
    "welcome": ("回来啦", "向你招呼", "nod"),
}

MOTION_FRAMES = {
    "breath": ((0, 0), (0, -1), (0, 0), (0, 1)),
    "focus": ((0, 0), (0, -1), (0, -1), (0, 0)),
    "nod": ((0, 0), (0, 2), (0, 0), (0, -1)),
    "think": ((-1, 0), (0, -1), (1, 0), (0, 1)),
    "sleep": ((0, 0), (0, 0), (0, 1), (0, 1)),
    "memory": ((-1, 0), (0, 0), (1, 0), (0, 0)),
    "wait": ((0, 0), (0, 0), (0, -1), (0, 0)),
    "shake": ((-2, 0), (2, 0), (-1, 0), (1, 0), (0, 0)),
}


def pet_action_for_mood(
    mood: str,
    *,
    kind: str = "stage",
    text: str = "",
    priority: int = 0,
    metadata: dict[str, Any] | None = None,
) -> PetAction:
    normalized = mood if mood in MOOD_ACTIONS else "normal"
    expression, action, motion = MOOD_ACTIONS[normalized]
    return PetAction(
        kind=kind,
        mood=normalized,
        expression=expression,
        action=action,
        motion=motion,
        text=text,
        priority=priority,
        metadata=metadata or {},
    )


def pet_action_for_dialogue_state(
    state: dict[str, Any] | None,
    *,
    text: str = "",
    metadata: dict[str, Any] | None = None,
) -> PetAction:
    if not isinstance(state, dict):
        state = {}
    mood = str(state.get("mood") or "normal")
    label = str(state.get("label") or "")
    merged_metadata = {"dialogue_label": label}
    if metadata:
        merged_metadata.update(metadata)
    return pet_action_for_mood(mood, text=text, metadata=merged_metadata)


def motion_offset(motion: str, step: int) -> tuple[int, int]:
    frames = MOTION_FRAMES.get(motion, MOTION_FRAMES["breath"])
    return frames[step % len(frames)]
