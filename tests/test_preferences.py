import stat
import tempfile
import unittest
from pathlib import Path

from kie_media.history import HistoryStore
from kie_media.preferences import Preferences, PreferencesError, PreferencesStore


class PreferencesTests(unittest.TestCase):
    def test_defaults_are_balanced_and_safe(self):
        with tempfile.TemporaryDirectory() as td:
            prefs = PreferencesStore(Path(td) / "preferences.json").load()
        self.assertEqual(prefs.default_tier, "balanced")
        self.assertEqual(prefs.max_jobs, 5)
        self.assertIsNone(prefs.image_model)
        self.assertIsNone(prefs.video_model)

    def test_preferences_round_trip_privately(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "preferences.json"
            store = PreferencesStore(path)
            expected = Preferences(
                default_tier="premium",
                image_model="seedream/5-pro-text-to-image",
                video_model="bytedance/seedance-2-mini",
                excluded_models=("legacy/model",),
                max_jobs=7,
            )
            store.save(expected)
            actual = store.load()
            mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(actual, expected)
        self.assertEqual(mode, 0o600)

    def test_invalid_preferences_are_rejected(self):
        with self.assertRaises(PreferencesError):
            Preferences(default_tier="luxury").validate()
        with self.assertRaises(PreferencesError):
            Preferences(max_jobs=0).validate()
        with self.assertRaises(PreferencesError):
            Preferences(image_model="\ninvalid").validate()


class ObservedCostsTests(unittest.TestCase):
    def test_history_builds_idempotent_model_cost_profile(self):
        with tempfile.TemporaryDirectory() as td:
            store = HistoryStore(Path(td) / "history.jsonl")
            store.append({"task_id": "a", "model": "image/fast", "state": "success", "credits_consumed": 2.0})
            store.append({"task_id": "b", "model": "image/fast", "state": "success", "credits_consumed": 4.0})
            store.append({"task_id": "b", "model": "image/fast", "state": "success", "credits_consumed": 4.0})
            store.append({"task_id": "c", "model": "image/top", "state": "failed", "credits_consumed": 99.0})
            profile = store.cost_profile()
        self.assertEqual(profile["image/fast"]["samples"], 2)
        self.assertEqual(profile["image/fast"]["median_credits"], 3.0)
        self.assertNotIn("image/top", profile)


if __name__ == "__main__":
    unittest.main()
