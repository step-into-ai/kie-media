import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from kie_media.projects import create_project, project_plan, review_stage, run_project, configure_project, revise_shot, production_report
from kie_media.directions import create_directions, compose_directions, compare_directions


class DirectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source" / "project.json"
        create_project(self.source, "Launch a blue bottle", shots=3)
        self.collection = self.root / "ideas" / "directions.json"

    def create(self):
        return create_directions(self.source, self.collection.parent)

    def member(self, name):
        return self.collection.parent / name / "project.json"

    def seed(self, name):
        path = self.member(name)
        def runner(stage, checkpoint):
            task = name + "-" + stage["id"]
            checkpoint(task)
            file = path.parent / (stage["id"] + ".png")
            file.write_bytes(task.encode())
            return {"state": "success", "task_id": task, "files": [str(file)], "credits_consumed": 2}
        for phase in ["images", "videos"]:
            result = run_project(path, phase=phase, max_jobs=3, runner=runner)
            for stage in result["review_stages"]:
                review_stage(path, stage, "accepted", "Test fixture inspected")

    def picks(self):
        return {"scene-1": "calm", "scene-2": "playful", "scene-3": "dramatic"}

    def test_directions_are_free_distinct_and_leave_original_unchanged(self):
        original = self.source.read_bytes()
        result = self.create()
        self.assertEqual(result["new_image_jobs"], 9)
        self.assertEqual(result["paid_requests"], 0)
        self.assertEqual(self.source.read_bytes(), original)
        prompts = []
        for name in self.picks().values():
            data = json.loads(self.member(name).read_text(encoding="utf-8"))
            prompts.append(data["shots"][0]["prompt"])
            self.assertEqual(data["shots"][0]["duration"], 5)
            self.assertEqual(data["shots"][0]["narration"], "")
        self.assertEqual(len(set(prompts)), 3)

    def test_dry_run_writes_no_output_and_reports_only_missing_jobs(self):
        self.create()
        output = self.root / "winner" / "project.json"
        result = compose_directions(self.collection, self.picks(), output, dry_run=True)
        self.assertEqual(result["new_jobs"], 6)
        self.assertFalse(output.parent.exists())

    def test_compose_preserves_paid_receipts_hashes_reviews_and_independent_assets(self):
        self.create()
        for name in self.picks().values():
            self.seed(name)
        output = self.root / "winner" / "project.json"
        result = compose_directions(self.collection, self.picks(), output)
        self.assertEqual(result["new_jobs"], 0)
        self.assertEqual(len(result["reused_stages"]), 6)
        data = json.loads(output.read_text(encoding="utf-8"))
        for job in data["jobs"]:
            name = self.picks()[job["stage_id"].split(".")[0]]
            self.assertEqual(job["task_id"], name + "-" + job["stage_id"])
            self.assertEqual(job["review"]["decision"], "accepted")
            self.assertFalse(Path(job["artifacts"][0]["path"]).is_absolute())
        (self.member("calm").parent / "scene-1.image.png").write_bytes(b"source changed later")
        self.assertEqual(project_plan(output)["pending_jobs"], 0)
        self.assertTrue(all(s["state"] == "success" for s in project_plan(output)["stages"]))

    def test_missing_picks_and_settings_conflicts_do_not_create_output(self):
        self.create()
        output = self.root / "winner" / "project.json"
        with self.assertRaisesRegex(ValueError, "every scene"):
            compose_directions(self.collection, {"scene-1": "calm"}, output)
        configure_project(self.member("dramatic"), voice="different-voice")
        with self.assertRaisesRegex(ValueError, "settings"):
            compose_directions(self.collection, self.picks(), output)
        self.assertFalse(output.exists())

    def test_rejects_active_jobs_and_tampered_selected_assets(self):
        data = json.loads(self.source.read_text(encoding="utf-8"))
        data["jobs"] = [{"id": "job", "stage_id": "scene-1.image", "fingerprint": "x", "state": "needs_recovery"}]
        self.source.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "active|ambiguous"):
            self.create()
        self.assertFalse(self.collection.exists())
        data["jobs"] = []
        self.source.write_text(json.dumps(data), encoding="utf-8")
        self.create()
        self.seed("calm")
        (self.member("calm").parent / "scene-1.image.png").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "changed|checksum"):
            compose_directions(self.collection, self.picks(), self.root / "winner" / "project.json")

    def test_comparison_has_scene_choices_and_escapes_prompts(self):
        self.create()
        from kie_media.projects import revise_shot
        revise_shot(self.member("calm"), "scene-1", {"prompt": "<script>alert('x')</script>"})
        result = compare_directions(self.collection)
        text = Path(result["file"]).read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>alert", text)
        self.assertIn("selection.json", text)
        self.assertIn('data-scene="scene-3"', text)

    def test_existing_target_is_not_overwritten(self):
        self.create()
        before = self.collection.read_bytes()
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(self.collection.read_bytes(), before)

    def test_soundtrack_with_different_timeline_length_is_not_reused(self):
        configure_project(self.source, music_prompt="Gentle piano")
        self.create()
        path = self.member("calm")
        def runner(stage, checkpoint):
            checkpoint("music-task")
            output = path.parent / "music.wav"
            output.write_bytes(b"music fixture")
            return {"state": "success", "task_id": "music-task", "files": [str(output)]}
        run_project(path, phase="audio", max_jobs=1, runner=runner)
        review_stage(path, "music", "accepted", "Music fixture")
        revise_shot(self.member("dramatic"), "scene-3", {"duration": 8})
        result = compose_directions(self.collection, self.picks(), self.root / "winner.json", dry_run=True)
        self.assertIn("music", result["pending_stages"])
        self.assertNotIn("music", [s["stage"] for s in result["reused_stages"]])

    def test_reuse_costs_are_not_reported_as_new_spend(self):
        self.create()
        for name in self.picks().values():
            self.seed(name)
        output = self.root / "winner" / "project.json"
        compose_directions(self.collection, self.picks(), output)
        report = production_report(output)
        self.assertEqual(report["new_credits_consumed"], 0)
        self.assertEqual(report["inherited_credits_consumed"], 12)

    def test_cli_selection_file_is_scoped_and_dry_run_is_read_only(self):
        from kie_media.cli import main
        self.create()
        collection = json.loads(self.collection.read_text(encoding="utf-8"))
        selection = self.root / "selection.json"
        selection.write_text(json.dumps({"collection_id": collection["id"], "picks": self.picks()}), encoding="utf-8")
        output = self.root / "folder with spaces" / "winner.json"
        args = ["project", "compose", str(self.collection), "--selection-file", str(selection), "--output", str(output), "--dry-run", "--json"]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(stream.getvalue())["new_jobs"], 6)
        self.assertFalse(output.parent.exists())
        selection.write_text(json.dumps({"collection_id": "unrelated", "picks": self.picks()}), encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 1)

    def test_rejected_selection_never_turns_into_accepted_receipt(self):
        self.create()
        self.seed("calm")
        review_stage(self.member("calm"), "scene-1.image", "rejected", "Wrong label")
        with self.assertRaisesRegex(ValueError, "rejected"):
            compose_directions(self.collection, self.picks(), self.root / "winner.json")

    def test_same_entity_name_with_different_reference_is_rejected(self):
        from kie_media.projects import add_entity
        self.create()
        for name in self.picks().values():
            image = self.member(name).parent / "ref.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + name.encode())
            add_entity(self.member(name), "bottle", image)
            scene = next(s for s, n in self.picks().items() if n == name)
            revise_shot(self.member(name), scene, {"entities": ["bottle"]})
        with self.assertRaisesRegex(ValueError, "Entity bottle differs"):
            compose_directions(self.collection, self.picks(), self.root / "winner.json")

    def test_accepted_narration_is_reused_after_visual_direction_changes(self):
        revise_shot(self.source, "scene-1", {"narration": "Meet the blue bottle."})
        def runner(stage, checkpoint):
            checkpoint("speech-once")
            output = self.source.parent / "voice.wav"
            output.write_bytes(b"voice fixture")
            return {"state": "success", "task_id": "speech-once", "files": [str(output)]}
        run_project(self.source, phase="audio", max_jobs=1, runner=runner)
        review_stage(self.source, "scene-1.voice", "accepted", "Narration checked")
        self.create()
        output = self.root / "winner" / "project.json"
        result = compose_directions(self.collection, self.picks(), output)
        self.assertEqual(result["new_jobs"], 6)
        reused = next(s for s in result["reused_stages"] if s["stage"] == "scene-1.voice")
        self.assertEqual(reused["task_id"], "speech-once")
        self.assertEqual(reused["review"]["decision"], "accepted")
