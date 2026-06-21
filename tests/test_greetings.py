from __future__ import annotations

from datetime import datetime
import unittest

from yingming_core.greetings import contextual_welcome_text, greeting_for_hour, welcome_text


class GreetingTests(unittest.TestCase):
    def test_greeting_boundaries(self) -> None:
        cases = {
            4: "夜深了",
            5: "早上好",
            9: "上午好",
            11: "中午好",
            14: "下午好",
            18: "晚上好",
            23: "夜深了",
        }
        for hour, expected in cases.items():
            with self.subTest(hour=hour):
                self.assertEqual(greeting_for_hour(hour), expected)

    def test_1154_is_noon(self) -> None:
        now = datetime(2026, 6, 21, 11, 54)
        self.assertEqual(welcome_text(now), "中午好。我在这里。你可以慢慢说。")

    def test_contextual_welcome_mentions_pending_memories(self) -> None:
        memory = {"pending": [{"text": "用户喜欢简洁回答。"}, {"text": "用户正在做樱茗。"}]}
        text = contextual_welcome_text(memory, [], datetime(2026, 6, 21, 11, 54))
        self.assertIn("中午好", text)
        self.assertIn("2 条待确认记忆", text)

    def test_contextual_welcome_continues_recent_topic(self) -> None:
        recent = [{"role": "user", "content": "我们刚刚修好了启动问候和当前时间。"}]
        text = contextual_welcome_text({}, recent, datetime(2026, 6, 21, 15, 0))
        self.assertIn("下午好", text)
        self.assertIn("上次我们聊到", text)
        self.assertIn("启动问候", text)

    def test_contextual_welcome_does_not_quote_private_chat(self) -> None:
        recent = [{"role": "user", "content": "我女朋友叫什么"}]
        text = contextual_welcome_text({}, recent, datetime(2026, 6, 21, 15, 0))
        self.assertIn("上次的话题我还留着", text)
        self.assertNotIn("我女朋友叫什么", text)


if __name__ == "__main__":
    unittest.main()
