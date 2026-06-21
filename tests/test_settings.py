from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yingming_core.settings import ModelSettings, load_model_settings, save_model_settings


class SettingsTests(unittest.TestCase):
    def test_default_proactive_mode_is_normal(self) -> None:
        with patch.dict(os.environ, {"YINGMING_PROACTIVE_MODE": ""}, clear=False):
            self.assertEqual(load_model_settings().proactive_mode, "normal")

    def test_proactive_mode_is_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save_model_settings(root, ModelSettings(proactive_mode="warm"))
            self.assertEqual(load_model_settings(root).proactive_mode, "warm")

    def test_proactive_mode_aliases_are_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save_model_settings(root, ModelSettings(proactive_mode="chatty"))
            self.assertEqual(load_model_settings(root).proactive_mode, "warm")


if __name__ == "__main__":
    unittest.main()
