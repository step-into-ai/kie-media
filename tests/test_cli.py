import argparse
import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from kie_media.cli import _apply_media, _resolve_media_params, build_parser, main, parse_key_values
from kie_media.client import KieApiError
from kie_media.models import ModelValidationError


class CliTests(unittest.TestCase):
    def test_parse_key_values_parses_json_scalars_and_arrays(self):
        parsed = parse_key_values(["duration=5", "generate_audio=false", 'image_urls=["https://x/a.png"]'])
        self.assertEqual(parsed, {"duration": 5, "generate_audio": False, "image_urls": ["https://x/a.png"]})

    def test_generate_command_matches_agent_friendly_shape(self):
        args = build_parser().parse_args(["generate", "image-fast", "--prompt", "hello", "--wait"])
        self.assertEqual(args.command, "generate")
        self.assertEqual(args.model, "image-fast")
        self.assertTrue(args.wait)

    def test_image_and_video_shortcuts_exist(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["image", "hello"]).command, "image")
        self.assertEqual(parser.parse_args(["video", "move"]).command, "video")

    def test_model_inspection_and_upload_commands_exist(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["model", "video-default"]).command, "model")
        upload = parser.parse_args(["upload", "./frame.png", "--json"])
        self.assertEqual(upload.path, "./frame.png")
        self.assertTrue(upload.json)

    def test_wait_supports_no_download_and_video_default_is_model_specific(self):
        parser = build_parser()
        wait = parser.parse_args(["wait", "task", "--no-download"])
        self.assertTrue(wait.no_download)
        video = parser.parse_args(["video", "move", "--model", "video-bold"])
        self.assertIsNone(video.duration)
        self.assertIsNone(video.aspect_ratio)
        self.assertIsNone(video.resolution)

    def test_seedance_rejects_mixed_frame_and_reference_modes_before_upload(self):
        args = argparse.Namespace(
            image=[], start_image="first.png", end_image=None,
            reference_image=["ref.png"], reference_video=[], reference_audio=[],
        )
        client = Mock()
        with self.assertRaises(ModelValidationError):
            _apply_media(client, "bytedance/seedance-2", {}, args)
        client.resolve_media.assert_not_called()

    def test_unsupported_reference_flag_is_rejected_before_upload(self):
        args = argparse.Namespace(
            image=[], start_image=None, end_image=None,
            reference_image=["ref.png"], reference_video=[], reference_audio=[],
        )
        client = Mock()
        with self.assertRaises(ModelValidationError):
            _apply_media(client, "gpt-image-2-text-to-image", {}, args)
        client.resolve_media.assert_not_called()

    def test_param_media_fields_use_the_same_type_resolver(self):
        client = Mock()
        client.resolve_media.side_effect = lambda value, kind: f"https://resolved/{kind}"
        values = {"image_urls": ["local.jpg"], "reference_audio_urls": ["voice.mp3"]}
        _resolve_media_params(client, values)
        self.assertEqual(values["image_urls"], ["https://resolved/image"])
        self.assertEqual(values["reference_audio_urls"], ["https://resolved/audio"])

    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_param_media_and_media_flags_cannot_silently_overwrite(self, client_class, _key):
        result = main(["generate", "image-fast", "--prompt", "x", "--param", 'image_urls=["https://x/a.jpg"]', "--image", "b.jpg"])
        self.assertEqual(result, 1)
        client_class.return_value.create_task.assert_not_called()

    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_shortcut_rejects_wrong_model_kind_before_task_creation(self, client_class, _key):
        self.assertEqual(main(["image", "test", "--model", "video-default", "--json"]), 1)
        client_class.return_value.create_task.assert_not_called()

    @patch("kie_media.cli.HistoryStore")
    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_history_failure_never_hides_created_paid_task(self, client_class, _key, history_class):
        client_class.return_value.create_task.return_value = ("paid-task", {})
        history_class.return_value.append.side_effect = OSError("read-only filesystem")
        self.assertEqual(main(["generate", "image-fast", "--prompt", "x", "--no-wait", "--json"]), 0)
        client_class.return_value.create_task.assert_called_once()

    @patch("kie_media.cli.HistoryStore")
    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_downstream_failure_always_reports_paid_task_id(self, client_class, _key, history_class):
        client_class.return_value.create_task.return_value = ("paid-task", {})
        client_class.return_value.wait.side_effect = KieApiError("poll failed")
        history_class.return_value.append.side_effect = OSError("read-only")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["generate", "image-fast", "--prompt", "x", "--json"]), 1)
        self.assertIn("paid-task", stderr.getvalue())

    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_explicit_unsupported_shortcut_option_is_rejected(self, client_class, _key):
        self.assertEqual(main(["image", "x", "--model", "image-fast", "--resolution", "4K"]), 1)
        client_class.return_value.create_task.assert_not_called()

    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_static_schema_and_wait_validation_happen_before_upload_or_paid_task(self, client_class, _key):
        client = client_class.return_value
        self.assertEqual(main(["generate", "video-default", "--prompt", "x", "--param", "duration=99", "--image", "first.jpg"]), 1)
        self.assertEqual(main(["generate", "image-fast", "--prompt", "x", "--wait-timeout", "0"]), 1)
        client.resolve_media.assert_not_called()
        client.create_task.assert_not_called()

    @patch("kie_media.cli._load_env_key", return_value="key")
    @patch("kie_media.cli.KieClient")
    def test_direct_task_command_errors_include_task_id(self, client_class, _key):
        client_class.return_value.get_task.side_effect = KieApiError("network down")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["status", "task-123"]), 1)
        self.assertIn("task-123", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
