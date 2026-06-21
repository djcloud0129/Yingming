from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yingming_core.chat import append_history
from yingming_core.service import YingmingService


class ServiceFlowTests(unittest.TestCase):
    def test_proactive_nudge_is_silent_when_assistant_waits_for_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = YingmingService(root)
            append_history(service.history_path, "user", "我没看过哦")
            append_history(service.history_path, "assistant", "去吧，等你回来告诉我感受。")

            result = service.proactive_nudge()

            self.assertEqual(result["message"], "")
            self.assertTrue(result["waiting_for_user"])

    def test_current_dialogue_state_waits_after_assistant_question(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = YingmingService(root)
            append_history(service.history_path, "user", "聊聊电影吧")
            append_history(service.history_path, "assistant", "你第一次看的时候是什么感觉？")

            self.assertEqual(service.current_dialogue_state().key, "waiting_reply")


if __name__ == "__main__":
    unittest.main()
