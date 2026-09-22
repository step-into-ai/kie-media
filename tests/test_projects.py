import json
import tempfile
import unittest
from pathlib import Path

from kie_media.projects import create_project, project_plan, revise_shot, run_project, review_stage, add_entity


class ProjectTests(unittest.TestCase):
    def test_known_task_rejoins_after_poll_failure_without_create(self):
        from unittest.mock import Mock
        from kie_media.client import TaskResult
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A bottle", shots=1)
            asset = Path(td) / "asset.png"
            asset.write_bytes(b"persistent asset")
            client = Mock()
            client.create_task.return_value = ("paid-once", {})
            client.wait.side_effect = [TimeoutError("poll interrupted"), TaskResult(task_id="paid-once", state="success", urls=["https://example.test/asset.png"])]
            client.download_urls.return_value = [str(asset)]
            first = run_project(path, phase="images", max_jobs=1, client=client)
            self.assertEqual(first["state"], "pending")
            second = run_project(path, phase="images", max_jobs=1, client=client)
            self.assertEqual(second["state"], "awaiting_review")
            client.create_task.assert_called_once()
            self.assertEqual(client.wait.call_count, 2)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["jobs"][0]["validated_request"]["model"], "nano-banana-2-lite")

    def test_export_is_portable_and_verifies_assets(self):
        import zipfile
        from kie_media.projects import export_project
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "original" / "project.json"
            create_project(path, "A bottle", shots=1)
            output = path.parent / "image.png"
            def runner(stage, checkpoint):
                checkpoint("known-id")
                output.write_bytes(b"original asset")
                return {"state": "success", "files": [str(output)]}
            run_project(path, phase="images", max_jobs=1, runner=runner)
            bundle = root / "handoff.zip"
            export_project(path, bundle)
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(root / "received")
            plan = project_plan(root / "received" / "project.json")
            self.assertEqual(plan["stages"][0]["state"], "success")
            output.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                export_project(path, root / "bad.zip")

    def test_library_addition_does_not_change_unassigned_scenes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A bottle", shots=3)
            before = project_plan(path)
            image = Path(td) / "reference.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            add_entity(path, "bottle", image, "Blue bottle")
            self.assertEqual([s["fingerprint"] for s in before["stages"]], [s["fingerprint"] for s in project_plan(path)["stages"]])
            change = revise_shot(path, "scene-2", {"entities": ["bottle"]})
            self.assertEqual(change["affected_stages"], ["scene-2.image", "scene-2.video", "assembly"])

    def test_edit_changes_only_affected_scene_and_assembly(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A blue bottle", shots=3)
            before = project_plan(path)
            preview = revise_shot(path, "scene-2", {"motion": "slow orbit"}, dry_run=True)
            self.assertEqual(preview["affected_stages"], ["scene-2.video", "assembly"])
            self.assertEqual(before, project_plan(path))
            revise_shot(path, "scene-2", {"motion": "slow orbit"})
            after = project_plan(path)
            unchanged = {s["id"]: s["fingerprint"] for s in before["stages"]}
            for stage in after["stages"]:
                if stage["id"] != "scene-2.video":
                    self.assertEqual(stage["fingerprint"], unchanged[stage["id"]])

    def test_generation_resumes_and_does_not_duplicate_paid_stages(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A bottle", shots=3)
            calls = []
            def runner(stage, checkpoint):
                calls.append(stage["id"])
                checkpoint("job-" + stage["id"])
                output = Path(td) / (stage["id"] + ".png")
                output.write_bytes(b"test asset")
                return {"task_id": "job-" + stage["id"], "files": [str(output)], "state": "success"}
            result = run_project(path, phase="images", max_jobs=3, runner=runner)
            self.assertEqual(result["state"], "awaiting_review")
            run_project(path, phase="images", max_jobs=3, runner=runner)
            self.assertEqual(len(calls), 3)
            for number in range(1, 4):
                review_stage(path, f"scene-{number}.image", "accepted", "identity checked")
            self.assertEqual(project_plan(path)["pending_jobs"], 3)

    def test_unknown_submission_blocks_retries(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A bottle", shots=1)
            calls = []
            def runner(stage, checkpoint):
                calls.append(stage["id"])
                raise TimeoutError("response lost")
            first = run_project(path, phase="images", max_jobs=1, runner=runner)
            second = run_project(path, phase="images", max_jobs=1, runner=runner)
            self.assertEqual(first["state"], "needs_recovery")
            self.assertEqual(second["state"], "needs_recovery")
            self.assertEqual(len(calls), 1)

    def test_budget_checked_before_runner_and_invalid_edit_is_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A bottle", shots=3)
            with self.assertRaises(ValueError):
                run_project(path, phase="images", max_jobs=2, runner=lambda *_: self.fail("must not submit"))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                revise_shot(path, "scene-1", {"duration": -2})
            self.assertEqual(before, path.read_bytes())

    def test_modified_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            create_project(path, "A bottle", shots=1)
            output = Path(td) / "image.png"
            def runner(stage, checkpoint):
                checkpoint("id")
                output.write_bytes(b"original")
                return {"files": [str(output)], "state": "success"}
            run_project(path, phase="images", max_jobs=1, runner=runner)
            output.write_bytes(b"changed")
            result = run_project(path, phase="images", max_jobs=1, runner=lambda *_: self.fail("no silent regeneration"))
            self.assertEqual(result["state"], "asset_changed")
