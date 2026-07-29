import unittest

from kie_media.models import ModelValidationError, get_model, list_models, prepare_input


class ModelCatalogTests(unittest.TestCase):
    def test_aliases_resolve_to_documented_kie_ids(self):
        self.assertEqual(get_model("image-default").id, "gpt-image-2-text-to-image")
        self.assertEqual(get_model("video-default").id, "bytedance/seedance-2")
        self.assertEqual(get_model("video-fast").id, "bytedance/seedance-2-fast")

    def test_catalog_contains_image_and_video_models(self):
        kinds = {item.kind for item in list_models()}
        self.assertEqual(kinds, {"image", "video"})

    def test_prepare_input_applies_documented_defaults(self):
        payload = prepare_input("gpt-image-2-text-to-image", {"prompt": "hello"})
        self.assertEqual(payload["aspect_ratio"], "auto")
        self.assertEqual(payload["resolution"], "1K")

    def test_prepare_input_coerces_cli_scalars(self):
        payload = prepare_input(
            "bytedance/seedance-2-fast",
            {"prompt": "move", "duration": "5", "generate_audio": "false"},
        )
        self.assertEqual(payload["duration"], 5)
        self.assertIs(payload["generate_audio"], False)

    def test_prepare_input_rejects_unknown_or_invalid_declared_param(self):
        with self.assertRaises(ModelValidationError):
            prepare_input("gpt-image-2-text-to-image", {"prompt": "x", "resolution": "8K"})
        with self.assertRaises(ModelValidationError):
            prepare_input("gpt-image-2-text-to-image", {"prompt": "x", "made_up": 1})

    def test_generic_model_allows_passthrough_input(self):
        payload = prepare_input("future/model", {"prompt": "x", "future_flag": 3})
        self.assertEqual(payload["future_flag"], 3)

    def test_cross_field_and_range_rules_are_enforced(self):
        with self.assertRaises(ModelValidationError):
            prepare_input("gpt-image-2-text-to-image", {"prompt": "x", "aspect_ratio": "1:1", "resolution": "4K"})
        with self.assertRaises(ModelValidationError):
            prepare_input("kling/v3-turbo-text-to-video", {"prompt": "x", "duration": "999"})
        with self.assertRaises(ModelValidationError):
            prepare_input("kling/v3-turbo-image-to-video", {"prompt": "x", "image_urls": []})

    def test_documented_nsfw_checker_is_accepted(self):
        payload = prepare_input("grok-imagine/text-to-video", {"prompt": "x", "nsfw_checker": False})
        self.assertIs(payload["nsfw_checker"], False)

    def test_empty_prompt_and_mixed_seedance_modes_are_rejected(self):
        with self.assertRaises(ModelValidationError):
            prepare_input("image-default", {"prompt": "   "})
        with self.assertRaises(ModelValidationError):
            prepare_input("future/model", {"prompt": ""})
        with self.assertRaises(ModelValidationError):
            prepare_input("video-default", {
                "prompt": "x", "first_frame_url": "https://x/first.jpg",
                "reference_image_urls": ["https://x/ref.jpg"],
            })
        with self.assertRaises(ModelValidationError):
            prepare_input("video-default", {"prompt": "x", "first_frame_url": ["https://x/a.jpg"]})


if __name__ == "__main__":
    unittest.main()
