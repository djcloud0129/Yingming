from __future__ import annotations

from datetime import datetime
import unittest

from yingming_core.greetings import greeting_for_hour, welcome_text


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


if __name__ == "__main__":
    unittest.main()
