from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DialogueState:
    key: str
    label: str
    strategy: str

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "strategy": self.strategy,
        }

    def as_prompt_text(self) -> str:
        return "\n".join(
            [
                "当前临时对话状态：",
                f"- 状态：{self.label}",
                f"- 回复策略：{self.strategy}",
                "- 这只是当下状态，不要自动写入长期记忆。",
            ]
        )


STATES: dict[str, DialogueState] = {
    "project": DialogueState(
        "project",
        "项目模式",
        "优先帮用户把模糊目标变成下一步行动；少铺垫，多给可执行的小步骤。",
    ),
    "emotional": DialogueState(
        "emotional",
        "陪伴模式",
        "先接住情绪和身体感受，再给很小的选择；不要急着讲道理或催行动。",
    ),
    "memory": DialogueState(
        "memory",
        "记忆整理",
        "关注用户想让樱茗记住、修改或确认的信息；提醒用户确认后再进入长期记忆。",
    ),
    "late_night": DialogueState(
        "late_night",
        "深夜收尾",
        "语气放轻，提醒收尾和休息；如果继续工作，只保留一个最小下一步。",
    ),
    "clarify": DialogueState(
        "clarify",
        "轻声追问",
        "用户信息不足时只问一个具体小问题，帮助他把想法说清楚。",
    ),
    "concise": DialogueState(
        "concise",
        "少说一点",
        "回答要短，直接给重点；不要展开长段解释。",
    ),
    "pending_memory": DialogueState(
        "pending_memory",
        "记忆待确认",
        "温柔提醒有待确认记忆；不要把待确认内容当作事实使用。",
    ),
    "casual": DialogueState(
        "casual",
        "自然闲聊",
        "像日常相处一样自然回应，可以轻轻打趣；不必强行推进项目。",
    ),
}


PROJECT_WORDS = (
    "下一步",
    "项目",
    "代码",
    "实现",
    "修",
    "bug",
    "ui",
    "界面",
    "功能",
    "测试",
    "提交",
    "推送",
    "github",
    "api",
    "deepseek",
    "模型",
    "记忆体",
    "画像",
    "桌宠",
    "樱茗",
    "vtuber",
    "live2d",
    "语音",
)

EMOTIONAL_WORDS = (
    "累",
    "困",
    "焦虑",
    "难受",
    "崩溃",
    "害怕",
    "迷茫",
    "烦",
    "不开心",
    "撑不住",
    "压力",
    "没动力",
    "不想动",
    "孤独",
)

MEMORY_WORDS = (
    "记住",
    "记忆",
    "长期记忆",
    "待确认",
    "确认",
    "忘掉",
    "删掉",
    "改一下记忆",
    "画像",
)

CONCISE_WORDS = (
    "简短",
    "简单说",
    "短一点",
    "少说",
    "直接说",
    "别长篇",
    "一句话",
)

CLARIFY_PATTERNS = (
    "怎么办",
    "怎么弄",
    "怎么做",
    "怎么搞",
    "然后呢",
    "下一步呢",
    "呢？",
    "呢?",
)


def detect_dialogue_state(
    user_text: str = "",
    recent_messages: list[dict[str, str]] | None = None,
    memory_data: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> DialogueState:
    text = " ".join(user_text.strip().split())
    lower = text.lower()
    current = now if now is not None else datetime.now().astimezone()
    memory_data = memory_data or {}
    pending = memory_data.get("pending", [])
    pending_count = len(pending) if isinstance(pending, list) else 0

    if any(word in lower or word in text for word in CONCISE_WORDS):
        return STATES["concise"]
    if any(word in lower or word in text for word in MEMORY_WORDS):
        return STATES["memory"]
    if any(word in lower or word in text for word in EMOTIONAL_WORDS):
        return STATES["emotional"]
    if current.hour >= 23 or current.hour < 5:
        return STATES["late_night"]
    if any(word in lower or word in text for word in PROJECT_WORDS):
        return STATES["project"]
    if pending_count and not text:
        return STATES["pending_memory"]
    if is_under_specified(text, recent_messages or []):
        return STATES["clarify"]
    return STATES["casual"]


def is_under_specified(text: str, recent_messages: list[dict[str, str]]) -> bool:
    if not text:
        return False
    compact = text.strip()
    if len(compact) <= 4:
        return True
    if compact in {"可以", "行", "好", "继续", "下一步", "随便", "都行"}:
        return True
    if any(compact.endswith(pattern) for pattern in CLARIFY_PATTERNS):
        return not any(word in compact.lower() or word in compact for word in PROJECT_WORDS)
    return False
