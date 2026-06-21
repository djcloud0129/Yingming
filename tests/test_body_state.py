from __future__ import annotations

import unittest

from yingming_core.body_state import BodyStateMachine, body_state_for_dialogue, body_state_for_event


class BodyStateTests(unittest.TestCase):
    def test_user_message_moves_to_listening(self) -> None:
        state = body_state_for_event("user.message", {"text": "你好"})

        self.assertEqual(state.key, "listening")
        self.assertEqual(state.mood, "typing")

    def test_model_thinking_moves_to_thinking(self) -> None:
        state = body_state_for_event("model.thinking", {"model": "local"})

        self.assertEqual(state.key, "thinking")

    def test_waiting_topic_overrides_dialogue_mood(self) -> None:
        state = body_state_for_dialogue(
            {"label": "自然闲聊", "mood": "normal"},
            {"title": "电影：《降临》", "status": "waiting_user"},
        )

        self.assertEqual(state.key, "waiting_user")

    def test_caring_dialogue_moves_to_comforting(self) -> None:
        state = body_state_for_dialogue({"label": "陪伴模式", "mood": "caring"})

        self.assertEqual(state.key, "comforting")
        self.assertEqual(state.mood, "caring")

    def test_fallback_reply_moves_to_error(self) -> None:
        state = body_state_for_event(
            "assistant.reply",
            {"mode": "fallback", "dialogue_state": {"mood": "normal"}},
        )

        self.assertEqual(state.key, "error")

    def test_state_machine_keeps_current_for_unknown_event(self) -> None:
        machine = BodyStateMachine()
        machine.transition("model.thinking")
        state = machine.transition("unknown.event")

        self.assertEqual(state.key, "thinking")

    def test_body_state_builds_pet_action_metadata(self) -> None:
        state = body_state_for_event("user.message")
        action = state.as_pet_action(text="我在听")

        self.assertEqual(action.metadata["body_state"], "listening")
        self.assertEqual(action.text, "我在听")


if __name__ == "__main__":
    unittest.main()
