from __future__ import annotations

from datetime import datetime
import unittest

from yingming_core.chat import build_messages
from yingming_core.dialogue_state import (
    assistant_is_waiting_for_user,
    conversation_waiting_for_user,
    detect_dialogue_state,
    mood_for_state,
)


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

    def test_state_dict_includes_mood(self) -> None:
        state = detect_dialogue_state("我今天有点累").as_dict()
        self.assertEqual(state["mood"], "caring")

    def test_project_state_maps_to_focused_mood(self) -> None:
        self.assertEqual(mood_for_state("project"), "focused")

    def test_waiting_state_maps_to_waiting_mood(self) -> None:
        self.assertEqual(mood_for_state("waiting_reply"), "waiting")

    def test_detects_wait_command(self) -> None:
        state = detect_dialogue_state("等我一下，我想想")
        self.assertEqual(state.key, "waiting_reply")

    def test_detects_return_topic_command(self) -> None:
        state = detect_dialogue_state("回到刚才话题")
        self.assertEqual(state.key, "topic_return")

    def test_assistant_question_waits_for_user(self) -> None:
        self.assertTrue(assistant_is_waiting_for_user("看过吗？还是我说中你没看过？"))

    def test_assistant_waiting_sentence_waits_for_user(self) -> None:
        self.assertTrue(assistant_is_waiting_for_user("去吧，等你回来告诉我感受。"))

    def test_conversation_waiting_for_user(self) -> None:
        messages = [
            {"role": "user", "content": "我没看过哦"},
            {"role": "assistant", "content": "等你回来告诉我感受。"},
        ]
        self.assertTrue(conversation_waiting_for_user(messages))

    def test_conversation_not_waiting_after_user_replies(self) -> None:
        messages = [
            {"role": "assistant", "content": "你看过吗？"},
            {"role": "user", "content": "我没看过"},
        ]
        self.assertFalse(conversation_waiting_for_user(messages))


if __name__ == "__main__":
    unittest.main()
