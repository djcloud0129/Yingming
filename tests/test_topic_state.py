from __future__ import annotations

import unittest

from yingming_core.chat import build_messages
from yingming_core.topic_state import detect_topic_state, topic_blocks_proactive


class TopicStateTests(unittest.TestCase):
    def test_detects_movie_topic_from_history(self) -> None:
        messages = [
            {"role": "user", "content": "聊聊电影吧"},
            {"role": "assistant", "content": "我推荐《降临》，你看过吗？"},
        ]
        topic = detect_topic_state(messages)

        self.assertEqual(topic.kind, "movie")
        self.assertIn("降临", topic.title)
        self.assertEqual(topic.status, "waiting_user")

    def test_return_to_topic_keeps_previous_movie_topic(self) -> None:
        messages = [
            {"role": "user", "content": "我没看过《降临》"},
            {"role": "assistant", "content": "那我先不剧透，等你看完告诉我感受。"},
        ]
        topic = detect_topic_state(messages, "回到刚才话题")

        self.assertEqual(topic.kind, "movie")
        self.assertEqual(topic.status, "open")

    def test_wait_command_pauses_previous_topic(self) -> None:
        messages = [
            {"role": "user", "content": "聊聊银翼杀手2049"},
            {"role": "assistant", "content": "你最喜欢哪个场景？"},
        ]
        topic = detect_topic_state(messages, "等我一下")

        self.assertEqual(topic.kind, "movie")
        self.assertEqual(topic.status, "paused")

    def test_open_topic_blocks_proactive_nudge(self) -> None:
        topic = detect_topic_state(
            [
                {"role": "user", "content": "我们聊聊电影"},
                {"role": "assistant", "content": "《降临》和《银翼杀手2049》的气质都很安静。"},
            ]
        )

        self.assertTrue(topic_blocks_proactive(topic))

    def test_no_recent_topic_is_closed(self) -> None:
        topic = detect_topic_state([])

        self.assertEqual(topic.status, "closed")
        self.assertFalse(topic_blocks_proactive(topic))

    def test_build_messages_includes_topic_state_prompt(self) -> None:
        topic_prompt = detect_topic_state([], "聊聊电影吧").as_prompt_text()
        messages = build_messages("", "", "", [], "聊聊电影吧", topic_state_text=topic_prompt)

        self.assertIn("当前短期话题", messages[0]["content"])
        self.assertIn("不要写入长期记忆", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
