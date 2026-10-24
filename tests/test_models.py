import unittest

from kie_media.models import ModelValidationError, get_model, list_models, prepare_input


class ModelCatalogTests(unittest.TestCase):
    def test_aliases_resolve_to_documented_kie_ids(self):
        self.assertEqual(get_model("image-default").id, "gpt-image-2-text-to-image")
        self.assertEqual(get_model("video-default").id, "bytedance/seedance-2")
        self.assertEqual(get_model("video-fast").id, "bytedance/seedance-2-fast")
        self.assertEqual(get_model("grok-imagine-1-5").id, "grok-imagine-video-1-5-preview")

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

    def test_grok_imagine_1_5_accepts_documented_pinned_frames_without_prompt(self):
        payload = prepare_input("grok-imagine-1-5", {
            "first_frame_url": "https://x/first.png",
            "last_frame_url": "https://x/last.png",
            "keyframes": [
                {"url": "https://x/mid.png", "timestamp_s": 3},
                {"url": "https://x/end-mid.png", "timestamp_s": 6},
            ],
            "duration": 8,
        })
        self.assertEqual(payload["keyframes"][1]["timestamp_s"], 6)
        self.assertNotIn("prompt", payload)

    def test_grok_imagine_1_5_rejects_invalid_or_too_close_keyframes_before_upload(self):
        with self.assertRaisesRegex(ModelValidationError, "timestamp_s"):
            prepare_input("grok-imagine-1-5", {
                "first_frame_url": "https://x/first.png", "duration": 5,
                "keyframes": [{"url": "https://x/mid.png", "timestamp_s": 5}],
            })
        with self.assertRaisesRegex(ModelValidationError, "not of type 'integer'"):
            prepare_input("grok-imagine-1-5", {
                "first_frame_url": "https://x/first.png", "duration": 5,
                "keyframes": [
                    {"url": "https://x/mid-a.png", "timestamp_s": 1},
                    {"url": "https://x/mid-b.png", "timestamp_s": 1.2},
                ],
            })

    def test_kling_4_reference_validates_nested_materials_and_combined_limits(self):
        payload = prepare_input("kling-4-reference", {
            "prompt": "@Hero walks into @video_1 and speaks as @Narrator",
            "duration": 10,
            "image_urls": ["https://x/product.png"],
            "video_urls": ["https://x/room.mp4"],
            "elements": [{
                "name": "Hero", "image_urls": ["https://x/hero-a.png", "https://x/hero-b.png"],
                "tag": "character", "description": "A presenter",
            }],
            "voices": [{"name": "Narrator", "audio_url": "https://x/narrator.mp3"}],
        })
        self.assertEqual(payload["elements"][0]["name"], "Hero")
        with self.assertRaisesRegex(ModelValidationError, "15 materials"):
            prepare_input("kling-4-reference", {
                "prompt": "x", "image_urls": [f"https://x/{index}.png" for index in range(10)],
                "video_urls": [f"https://x/{index}.mp4" for index in range(5)], "elements": [{
                    "name": "Hero", "image_urls": ["https://x/a.png", "https://x/b.png"],
                }],
            })

    def test_kling_4_reference_rejects_invalid_nested_element_and_reserved_name(self):
        with self.assertRaisesRegex(ModelValidationError, "too short"):
            prepare_input("kling-4-reference", {
                "prompt": "x", "elements": [{"name": "Hero", "image_urls": ["https://x/a.png"]}],
            })
        with self.assertRaisesRegex(ModelValidationError, "reserved"):
            prepare_input("kling-4-reference", {
                "prompt": "x", "voices": [{"name": "image_1", "audio_url": "https://x/voice.mp3"}],
            })

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
