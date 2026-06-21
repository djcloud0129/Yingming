from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yingming_core.behavior_protocol import pet_action_for_dialogue_state, pet_action_for_mood
from yingming_core.events import EventBus
from yingming_core.service import YingmingService


class EventBusTests(unittest.TestCase):
    def test_emit_records_and_notifies_subscribers(self) -> None:
        bus = EventBus(max_events=3)
        received: list[str] = []
        bus.subscribe("user.message", lambda event: received.append(str(event.payload["text"])))

        event = bus.emit("user.message", {"text": "你好"}, source="user")

        self.assertEqual(received, ["你好"])
        self.assertEqual(event.type, "user.message")
        self.assertEqual(bus.recent()[0]["payload"]["text"], "你好")

    def test_recent_keeps_bounded_history(self) -> None:
        bus = EventBus(max_events=2)
        bus.emit("one")
        bus.emit("two")
        bus.emit("three")

        self.assertEqual([event["type"] for event in bus.recent(10)], ["two", "three"])


class BehaviorProtocolTests(unittest.TestCase):
    def test_pet_action_for_mood_contains_stage_fields(self) -> None:
        action = pet_action_for_mood("focused")

        self.assertEqual(action.expression, "认真")
        self.assertEqual(action.motion, "focus")
        self.assertEqual(action.as_dict()["kind"], "stage")

    def test_pet_action_for_dialogue_state_uses_mood(self) -> None:
        action = pet_action_for_dialogue_state({"label": "等你回答", "mood": "waiting"}, text="慢慢来")

        self.assertEqual(action.mood, "waiting")
        self.assertEqual(action.expression, "安静")
        self.assertEqual(action.metadata["dialogue_label"], "等你回答")


class ServiceEventTests(unittest.TestCase):
    def test_reply_returns_turn_events_and_pet_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = YingmingService(Path(temp_dir))

            result = service.reply("你好，樱茗")

            event_types = [event["type"] for event in result["events"]]
            self.assertIn("user.message", event_types)
            self.assertIn("assistant.reply", event_types)
            self.assertIn("mood.changed", event_types)
            self.assertIn("topic.updated", event_types)
            self.assertIn("pet.action", event_types)
            self.assertEqual(result["pet_action"]["kind"], "stage")
            self.assertGreaterEqual(len(service.state()["events"]), len(result["events"]))


if __name__ == "__main__":
    unittest.main()
