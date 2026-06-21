from __future__ import annotations

import unittest

from yingming_core.pet_app import motion_offset, stage_visual_for_mood


class StageVisualTests(unittest.TestCase):
    def test_focused_mood_looks_attentive(self) -> None:
        visual = stage_visual_for_mood("focused")

        self.assertEqual(visual.expression, "认真")
        self.assertEqual(visual.motion, "focus")

    def test_typing_stage_listens_to_user(self) -> None:
        visual = stage_visual_for_mood("typing")

        self.assertEqual(visual.expression, "在听")
        self.assertIn("打字", visual.action)

    def test_unknown_mood_falls_back_to_normal(self) -> None:
        visual = stage_visual_for_mood("unknown")

        self.assertEqual(visual.expression, "微笑")
        self.assertEqual(visual.motion, "breath")

    def test_shake_motion_moves_sideways(self) -> None:
        offsets = [motion_offset("shake", index) for index in range(4)]

        self.assertIn((-2, 0), offsets)
        self.assertIn((2, 0), offsets)


if __name__ == "__main__":
    unittest.main()
