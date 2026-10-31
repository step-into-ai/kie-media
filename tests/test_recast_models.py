import unittest

from kie_media.models import ModelValidationError
from kie_media.recast_models import prepare_recast_request, recast_capabilities


class RecastModelTests(unittest.TestCase):
    def test_motion_transfer_uses_kling_motion_control_contract(self):
        model, payload = prepare_recast_request(
            "motion-transfer", "Make the supplied character perform the source motion.",
            video="motion.mp4", references=["character.png"], duration=5,
            resolution="720p", keep_original_sound=False,
        )
        self.assertEqual(model.id, "kling-3.0/motion-control")
        self.assertEqual(payload["input_urls"], ["character.png"])
        self.assertEqual(payload["video_urls"], ["motion.mp4"])
        self.assertEqual(payload["mode"], "720p")
        self.assertEqual(payload["character_orientation"], "video")

    def test_motion_transfer_accepts_1080p(self):
        _, payload = prepare_recast_request(
            "motion-transfer", "Transfer the source performance.",
            video="motion.mp4", references=["character.png"], duration=5,
            resolution="1080p", keep_original_sound=False,
        )
        self.assertEqual(payload["mode"], "1080p")

    def test_object_swap_uses_documented_wan_edit_reference_shape(self):
        model, payload = prepare_recast_request(
            "object-swap", "Replace the jacket with the supplied product.",
            video="source.mp4", references=["jacket.png"], duration=6,
            resolution="1080p", keep_original_sound=False,
        )
        self.assertEqual(model.id, "wan/2-7-videoedit")
        self.assertEqual(payload["video_url"], "source.mp4")
        self.assertEqual(payload["reference_image"], "jacket.png")
        self.assertEqual(payload["duration"], 0)
        self.assertEqual(payload["audio_setting"], "auto")
        self.assertNotIn("aspect_ratio", payload)

    def test_object_swap_preserves_audio_when_requested(self):
        _, payload = prepare_recast_request(
            "object-swap", "Replace the jacket.", video="source.mp4",
            references=["jacket.png"], duration=6, resolution="720p",
            keep_original_sound=True,
        )
        self.assertEqual(payload["audio_setting"], "origin")

    def test_unsupported_audio_preservation_is_rejected_before_upload(self):
        with self.assertRaises(ModelValidationError):
            prepare_recast_request(
                "motion-transfer", "Transfer this motion.", video="motion.mp4",
                references=["character.png"], duration=5, resolution="720p",
                keep_original_sound=True,
            )

    def test_capabilities_expose_known_limits_without_inventing_guarantees(self):
        capabilities = recast_capabilities("motion-transfer")
        self.assertEqual(capabilities["source_min_seconds"], 3)
        self.assertEqual(capabilities["source_max_seconds"], 30)
        self.assertEqual(capabilities["max_reference_images"], 1)
        self.assertEqual(capabilities["audio_preservation"], "unsupported")
        self.assertEqual(capabilities["character_orientation"], "video")
        self.assertEqual(capabilities["resolutions"], ["720p", "1080p"])


if __name__ == "__main__":
    unittest.main()
