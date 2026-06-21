from __future__ import annotations

from datetime import datetime
import unittest

from yingming_core.chat import build_messages
from yingming_core.dialogue_state import detect_dialogue_state


class DialogueStateTests(unittest.TestCase):
    def test_detects_project_mode(self) -> None:
        state = detect_dialogue_state("下一步我们做状态感知系统")
        self.assertEqual(state.key, "project")

    def test_detects_emotional_mode(self) -> None:
        state = detect_dialogue_state("我今天有点累，不太想动")
        self.assertEqual(state.key, "emotional")

    def test_detects_memory_mode(self) -> None:
        state = detect_dialogue_state("记住我喜欢先看结论")
        self.assertEqual(state.key, "memory")

    def test_detects_late_night_mode(self) -> None:
        state = detect_dialogue_state("随便聊聊", now=datetime(2026, 6, 21, 23, 40))
        self.assertEqual(state.key, "late_night")

    def test_detects_pending_memory_without_user_text(self) -> None:
        state = detect_dialogue_state("", memory_data={"pending": [{"text": "待确认"}]})
        self.assertEqual(state.key, "pending_memory")

    def test_detects_concise_mode(self) -> None:
        state = detect_dialogue_state("简单说，别长篇")
        self.assertEqual(state.key, "concise")

    def test_build_messages_includes_dialogue_state_prompt(self) -> None:
        prompt = detect_dialogue_state("我有点累").as_prompt_text()
        messages = build_messages("", "", "", [], "我有点累", dialogue_state_text=prompt)
        self.assertIn("当前临时对话状态", messages[0]["content"])
        self.assertIn("陪伴模式", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
