import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kie_media.cli import _apply_media, _resolve_media_params, build_parser, main, parse_key_values
from kie_media.client import KieApiError
from kie_media.agent import build_plan, save_manifest
from kie_media.models import FieldSpec, ModelSpec, ModelValidationError


class CliTests(unittest.TestCase):
    def test_refresh_does_not_return_stale_cached_schema_without_fetch(self):
        from kie_media.cli import _resolve_model
        from kie_media.models import get_model
        spec = get_model("image-fast")
        with patch("kie_media.cli.DocsCatalog") as catalog:
            catalog.return_value.resolve.return_value = spec
            _resolve_model("image-fast", refresh=True)
            catalog.return_value.resolve.assert_called_once()

    def test_parse_key_values_parses_json_scalars_and_arrays(self):
        parsed = parse_key_values(["duration=5", "generate_audio=false", 'image_urls=["https://x/a.png"]'])
        self.assertEqual(parsed, {"duration": 5, "generate_audio": False, "image_urls": ["https://x/a.png"]})

    def test_version_flag(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), "kie-media 0.5.0")

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

    def test_agent_plan_parser_exposes_workflow_controls(self):
        args = build_parser().parse_args([
            "agent", "plan", "Pinterest pin for my candle", "--media", "candle.jpg",
            "--workflow", "product-photoshoot", "--count", "3", "--json",
        ])
        self.assertEqual(args.command, "agent")
        self.assertEqual(args.agent_command, "plan")
        self.assertEqual(args.count, 3)
        self.assertEqual(args.media, ["candle.jpg"])
        video = build_parser().parse_args([
            "agent", "plan", "Video", "--workflow", "video",
            "--reference-video", "motion.mp4", "--reference-audio", "beat.wav",
        ])
        self.assertEqual(video.reference_video, ["motion.mp4"])
        self.assertEqual(video.reference_audio, ["beat.wav"])
        run = build_parser().parse_args([
            "agent", "run", "campaign", "--manifest", "run.json", "--selected-file", "winner.jpg",
        ])
        self.assertEqual(run.selected_file, "winner.jpg")
        self.assertIsNone(run.max_jobs)
        tailored = build_parser().parse_args([
            "agent", "plan", "premium launch", "--tier", "premium",
            "--image-model", "Seedream 5 Pro", "--video-model", "Seedance 2 Mini",
        ])
        self.assertEqual(tailored.tier, "premium")
        self.assertEqual(tailored.image_model, "Seedream 5 Pro")
        self.assertEqual(tailored.video_model, "Seedance 2 Mini")

    def test_live_models_and_preferences_commands_exist(self):
        live = build_parser().parse_args(["models", "--live", "--search", "Seedream", "--refresh", "--json"])
        self.assertTrue(live.live)
        self.assertEqual(live.search, "Seedream")
        preferences = build_parser().parse_args([
            "preferences", "set", "--tier", "budget", "--image-model", "Seedream 5 Pro", "--max-jobs", "3",
        ])
        self.assertEqual(preferences.preferences_command, "set")
        self.assertEqual(preferences.tier, "budget")
        self.assertEqual(preferences.max_jobs, 3)

    @patch("kie_media.cli.execute_plan")
    def test_agent_run_blocks_plans_above_default_job_budget(self, execute_plan):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main([
                "agent", "run", "Complete marketplace listing set",
                "--workflow", "marketplace-cards", "--scope", "full-set",
                "--media", "product.jpg", "--json",
            ])
        self.assertEqual(code, 1)
        self.assertIn("13 jobs", stderr.getvalue())
        self.assertIn("--max-jobs", stderr.getvalue())
        execute_plan.assert_not_called()

    @patch("kie_media.cli.execute_plan", return_value={"state": "completed", "results": []})
    def test_agent_run_accepts_explicit_job_budget(self, execute_plan):
        with tempfile.TemporaryDirectory() as td:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main([
                    "agent", "run", "Complete marketplace listing set",
                    "--workflow", "marketplace-cards", "--scope", "full-set",
                    "--media", "product.jpg", "--output-dir", td,
                    "--manifest", str(Path(td) / "run.json"), "--max-jobs", "13", "--json",
                ])
        self.assertEqual(code, 0)
        execute_plan.assert_called_once()

    @patch("kie_media.cli.KieClient")
    def test_agent_plan_needs_no_api_key_or_client(self, client_class):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["agent", "plan", "Quick image of a fox", "--budget", "fast", "--json"]), 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["workflow"], "image")
        self.assertEqual(payload["stages"][0]["model"], "image-fast")
        client_class.assert_not_called()

    def test_preferences_feed_agent_plan_without_paid_client(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"KIE_MEDIA_HOME": td}):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([
                    "preferences", "set", "--tier", "premium",
                    "--image-model", "image-default", "--max-jobs", "3", "--json",
                ]), 0)
            saved = json.loads(out.getvalue())
            self.assertEqual(saved["image_model"], "gpt-image-2-text-to-image")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["agent", "plan", "Premium image from preferences", "--workflow", "image", "--json"]), 0)
            plan = json.loads(out.getvalue())
            self.assertEqual(plan["tier"], "premium")
            self.assertEqual(plan["stages"][0]["model"], "gpt-image-2-text-to-image")
            self.assertIn('resolution="2K"', plan["stages"][0]["command"])

    @patch("kie_media.cli.DocsCatalog")
    def test_model_command_resolves_a_natural_live_name(self, catalog_type):
        catalog_type.return_value.resolve.return_value = ModelSpec(
            "vendor/new-image", "Newest Image", "image", "documented", aliases=("Newest Image",),
            fields={"prompt": FieldSpec(str, required=True)}, docs="https://docs.kie.ai/market/vendor/new-image",
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["model", "Newest Image", "--json"]), 0)
        detail = json.loads(out.getvalue())
        self.assertEqual(detail["id"], "vendor/new-image")
        self.assertEqual(detail["source"], "dynamic-docs")

    @patch("kie_media.cli.KieClient")
    def test_completed_manifest_is_rejoined_without_paid_client(self, client_class):
        plan = build_plan("One icon", workflow="image")
        execution = {
            "state": "completed", "running_stage": None,
            "results": [{"stage_id": "image-1", "state": "success", "task_id": "done"}],
        }
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "run.json"
            save_manifest(manifest, plan, execution)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["agent", "run", "One icon", "--workflow", "image", "--manifest", str(manifest), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["state"], "completed")
        client_class.assert_not_called()

    def test_mismatched_manifest_is_rejected_before_execution(self):
        first = build_plan("First icon", workflow="image")
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "run.json"
            save_manifest(manifest, first, {"state": "planned", "running_stage": None, "results": []})
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["agent", "run", "Different icon", "--workflow", "image", "--manifest", str(manifest), "--json"])
        self.assertEqual(code, 1)
        self.assertIn("does not match", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
