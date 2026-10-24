import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kie_media.client import TaskResult
from kie_media.recast import (
    build_recast_plan,
    recover_recast,
    review_recast,
    run_recast,
)
from kie_media.storage import atomic_json


class RecastAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"source" * 16)
        self.reference = self.root / "subject.png"
        self.reference.write_bytes(b"\x89PNG\r\n\x1a\n" + b"subject" * 16)
        self.output = self.root / "result.mp4"
        self.output.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"output" * 16)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def metadata(path):
        path = Path(path)
        return {
            "duration": 6 if path.suffix == ".mp4" else 0,
            "width": 720,
            "height": 720,
            "video": path.suffix == ".mp4",
            "image": path.suffix == ".png",
            "audio": False,
            "fps": 30,
            "pixel_format": "yuv420p",
            "has_alpha": False,
        }

    def build_plan(self):
        with patch("kie_media.recast.probe", side_effect=self.metadata):
            return build_recast_plan(
                self.source,
                "Replace the performer while preserving source timing and camera motion.",
                references=[self.reference],
            )

    def client_with_success(self):
        client = Mock()
        client.resolve_media.side_effect = lambda value, kind: "https://example.test/" + Path(value).name
        client.create_task.return_value = ("task-known", {})
        client.wait.return_value = TaskResult(
            task_id="task-known", state="success", urls=["https://example.test/result.mp4"],
        )
        client.download_urls.return_value = [str(self.output)]
        return client

    def test_invalid_source_duration_fails_in_free_plan_before_any_provider_client_exists(self):
        bad_metadata = dict(self.metadata(self.source), duration=31)
        with patch("kie_media.recast.probe", return_value=bad_metadata):
            with self.assertRaisesRegex(ValueError, "source duration"):
                build_recast_plan(
                    self.source, "Recast this clip.", references=[self.reference],
                )

    def test_mode_specific_source_duration_limits_are_enforced(self):
        too_long_for_edit = dict(self.metadata(self.source), duration=11)
        with patch("kie_media.recast.probe", return_value=too_long_for_edit):
            with self.assertRaisesRegex(ValueError, "2–10"):
                build_recast_plan(
                    self.source, "Replace only the jacket with the reference product.",
                    references=[self.reference], mode="object-swap", resolution="1080p",
                )
        too_long_for_restyle = dict(self.metadata(self.source), duration=16)
        with patch("kie_media.recast.probe", return_value=too_long_for_restyle):
            with self.assertRaisesRegex(ValueError, "3–15.5"):
                build_recast_plan(
                    self.source, "Turn the clip into a hand-painted film.", mode="restyle",
                )

    def test_restyle_accepts_a_video_inside_its_documented_technical_bounds(self):
        with patch("kie_media.recast.probe", side_effect=self.metadata):
            plan = build_recast_plan(
                self.source, "Turn the clip into a hand-painted film.", mode="restyle",
            )
        self.assertEqual(plan["model"], "kling-3.0-omni/transformation")

    def test_changed_source_blocks_upload_and_paid_task_creation(self):
        plan = self.build_plan()
        self.source.write_bytes(self.source.read_bytes() + b"changed")
        client = self.client_with_success()
        with self.assertRaisesRegex(ValueError, "Input changed after planning"):
            run_recast(plan, self.root / "run.json", client=client)
        client.resolve_media.assert_not_called()
        client.create_task.assert_not_called()

    def test_ambiguous_create_never_retries_without_explicit_recovery(self):
        plan = self.build_plan()
        client = self.client_with_success()
        client.create_task.side_effect = TimeoutError("provider response lost")
        manifest = self.root / "run.json"
        first = run_recast(plan, manifest, client=client)
        second = run_recast(plan, manifest, client=client)
        self.assertEqual(first["state"], "needs_recovery")
        self.assertEqual(second["state"], "needs_recovery")
        client.create_task.assert_called_once()

    def test_alternate_manifest_cannot_submit_the_same_take_twice(self):
        plan = self.build_plan()
        client = self.client_with_success()
        first_manifest, alternate_manifest = self.root / "first.json", self.root / "alternate.json"
        with patch("kie_media.recast.probe", side_effect=self.metadata):
            run_recast(plan, first_manifest, client=client)
            with self.assertRaisesRegex(ValueError, "belongs to"):
                run_recast(plan, alternate_manifest, client=client)
        client.create_task.assert_called_once()

    def test_checkpoint_failure_before_create_prevents_the_paid_request(self):
        plan = self.build_plan()
        client = self.client_with_success()
        manifest = self.root / "run.json"

        def fail_submitting_checkpoint(path, value):
            if Path(path) == manifest.resolve() and value.get("execution", {}).get("state") == "submitting":
                raise OSError("disk full")
            return atomic_json(path, value)

        with patch("kie_media.recast.atomic_json", side_effect=fail_submitting_checkpoint):
            with self.assertRaisesRegex(OSError, "disk full"):
                run_recast(plan, manifest, client=client)
        client.create_task.assert_not_called()

    def test_mutated_plan_is_rejected_before_any_client_operation(self):
        plan = self.build_plan()
        mutated = copy.deepcopy(plan)
        mutated["prompt"] = "A different request that must never reuse this plan."
        client = self.client_with_success()
        with self.assertRaisesRegex(ValueError, "plan changed"):
            run_recast(mutated, self.root / "run.json", client=client)
        client.resolve_media.assert_not_called()
        client.create_task.assert_not_called()

    def test_active_receipt_without_task_id_needs_recovery_and_can_be_attached(self):
        plan = self.build_plan()
        client = self.client_with_success()
        manifest = self.root / "run.json"
        atomic_json(manifest, {
            "version": 1,
            "plan": plan,
            "execution": {"state": "submitted", "created_at": "2026-10-24T00:00:00Z"},
        })
        result = run_recast(plan, manifest, client=client)
        self.assertEqual(result["state"], "needs_recovery")
        client.create_task.assert_not_called()
        attached = recover_recast(manifest, "task-verified-out-of-band")
        self.assertEqual(attached["state"], "submitted")
        self.assertEqual(attached["task_id"], "task-verified-out-of-band")

    def test_malformed_manifest_is_rejected_without_provider_calls(self):
        plan = self.build_plan()
        client = self.client_with_success()
        manifest = self.root / "run.json"
        manifest.write_text(json.dumps({"version": 1, "execution": {"state": "submitted"}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid recast (?:manifest|plan)"):
            run_recast(plan, manifest, client=client)
        client.resolve_media.assert_not_called()
        client.create_task.assert_not_called()

    def test_recovered_task_is_polled_without_creating_a_second_task(self):
        plan = self.build_plan()
        client = self.client_with_success()
        client.create_task.side_effect = TimeoutError("provider response lost")
        manifest = self.root / "run.json"
        self.assertEqual(run_recast(plan, manifest, client=client)["state"], "needs_recovery")
        recovered = recover_recast(manifest, "task-confirmed-elsewhere")
        self.assertEqual(recovered["state"], "submitted")
        client.wait.return_value = TaskResult(
            task_id="task-confirmed-elsewhere", state="success", urls=["https://example.test/result.mp4"],
        )
        with patch("kie_media.recast.probe", side_effect=self.metadata):
            result = run_recast(plan, manifest, client=client)
        self.assertEqual(result["state"], "awaiting_review")
        client.create_task.assert_called_once()
        client.wait.assert_called_once_with("task-confirmed-elsewhere")

    def test_review_requires_an_unchanged_downloaded_video(self):
        plan = self.build_plan()
        client = self.client_with_success()
        manifest = self.root / "run.json"
        with patch("kie_media.recast.probe", side_effect=self.metadata):
            result = run_recast(plan, manifest, client=client)
        self.assertEqual(result["state"], "awaiting_review")
        self.output.write_bytes(self.output.read_bytes() + b"mutated")
        with self.assertRaisesRegex(ValueError, "unchanged downloaded output"):
            review_recast(manifest, "accepted", "Identity and timing look correct.")

    def test_accepted_review_completes_only_after_successful_download(self):
        plan = self.build_plan()
        client = self.client_with_success()
        manifest = self.root / "run.json"
        with patch("kie_media.recast.probe", side_effect=self.metadata):
            run_recast(plan, manifest, client=client)
        approved = review_recast(manifest, "accepted", "Identity, timing, and unaffected details were checked.")
        self.assertEqual(approved["state"], "completed")
        self.assertEqual(approved["visual_review"]["decision"], "accepted")


if __name__ == "__main__":
    unittest.main()
