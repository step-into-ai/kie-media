import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kie_media.agent import (
    PlanError, build_plan, execute_plan, load_manifest, manifest_lock, new_manifest_path,
    plan_fingerprint, production_lock, save_manifest,
)


class AgentPlanningTests(unittest.TestCase):
    def test_quick_image_routes_to_fast_image_model(self):
        plan = build_plan("Make me a quick photorealistic image of a fox in snow", budget="fast")
        self.assertEqual(plan.workflow, "image")
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.stages[0].model, "image-fast")

    def test_image_to_video_uses_reference_aware_model_and_motion_prompt(self):
        plan = build_plan(
            "Animate this photo into a five second clip with the camera slowly pulling back",
            media=["still.jpg"],
            duration=5,
        )
        self.assertEqual(plan.workflow, "image-to-video")
        self.assertEqual(plan.stages[0].model, "video-kling-image")
        self.assertIn("--image", plan.stages[0].command)
        self.assertIn("pull", plan.stages[0].prompt.lower())

    def test_image_to_video_without_frame_is_a_real_blocker(self):
        plan = build_plan("Animate this photo with a slow push in")
        self.assertEqual(plan.status, "needs_input")
        self.assertIn("reference_image", plan.missing_inputs)
        self.assertEqual(plan.estimated_jobs, 0)

    def test_product_video_routes_to_video_and_keeps_reference_media(self):
        plan = build_plan(
            "Create a cinematic product video for my serum", media=["product.png"],
            reference_videos=["motion.mp4"], reference_audio=["beat.wav"],
        )
        self.assertEqual(plan.workflow, "video")
        self.assertEqual(plan.stages[0].model, "video-default")
        self.assertIn("--reference-image", plan.stages[0].command)
        self.assertIn("product.png", plan.stages[0].command)
        self.assertIn("--reference-video", plan.stages[0].command)
        self.assertIn("motion.mp4", plan.stages[0].command)
        self.assertIn("--reference-audio", plan.stages[0].command)
        self.assertIn("beat.wav", plan.stages[0].command)

    def test_typed_video_references_are_not_silently_ignored_by_image_workflows(self):
        with self.assertRaises(PlanError):
            build_plan("Create a poster", workflow="image", reference_videos=["clip.mp4"])

    def test_pinterest_and_hero_tie_breakers_match_public_agent_rules(self):
        pin = build_plan("Pinterest pin of my candle on a kitchen counter", media=["candle.jpg"])
        hero = build_plan("Hero banner showing my serum being applied", media=["serum.jpg"])
        self.assertEqual(pin.workflow, "product-photoshoot")
        self.assertEqual(pin.mode, "moodboard_pin")
        self.assertEqual(pin.aspect_ratio, "2:3")
        self.assertEqual(hero.mode, "hero_banner")
        self.assertEqual(hero.aspect_ratio, "16:9")

    def test_product_workflow_requires_reference_for_identity_fidelity(self):
        plan = build_plan("Make a product photoshoot for my bottle")
        self.assertEqual(plan.status, "needs_input")
        self.assertIn("product_image", plan.missing_inputs)

    def test_marketplace_full_set_expands_to_declared_assets(self):
        plan = build_plan(
            "Create a complete marketplace listing set and A+ cards for this serum",
            media=["serum.jpg"],
            scope="full-set",
        )
        self.assertEqual(plan.workflow, "marketplace-cards")
        self.assertEqual(plan.scope, "full-set")
        self.assertEqual(plan.estimated_jobs, 13)
        self.assertEqual(plan.stages[0].asset, "main_image")
        self.assertTrue(all(stage.model == "image-fast" for stage in plan.stages))

    def test_marketplace_negative_adjectives_do_not_expand_to_full_set(self):
        for brief in [
            "Create one replacement image for my incomplete marketplace listing",
            "Create one replacement image for my unvollständige marketplace listing",
        ]:
            plan = build_plan(brief, media=["product.jpg"])
            self.assertEqual(plan.scope, "main")
            self.assertEqual(plan.estimated_jobs, 1)

    def test_explainer_is_honest_hybrid_plan_not_fake_native_parity(self):
        plan = build_plan("Turn this report into a one minute narrated explainer")
        self.assertEqual(plan.workflow, "video-explainer")
        self.assertEqual(plan.status, "hybrid")
        self.assertIn("audio_generation", plan.capability_gaps)
        self.assertIn("timeline_assembly", plan.capability_gaps)
        self.assertFalse(plan.executable)

    def test_campaign_has_visual_review_gate_before_animation(self):
        plan = build_plan("Create a three-image campaign and animate the best one", count=3)
        self.assertEqual(plan.workflow, "campaign")
        self.assertEqual(plan.estimated_jobs, 4)
        self.assertEqual(plan.stages[-2].action, "review")
        self.assertTrue(plan.stages[-2].blocking)
        self.assertEqual(plan.stages[-1].action, "generate-selected")

    def test_promotional_campaign_does_not_imply_animation(self):
        plan = build_plan("Create a promotional campaign for my serum", media=["product.jpg"])
        self.assertEqual(plan.workflow, "campaign")
        self.assertEqual(plan.estimated_jobs, 1)
        self.assertNotIn("generate-selected", [stage.action for stage in plan.stages])

    def test_campaign_animation_intent_handles_negation_and_plurals(self):
        for brief in [
            "Create a promotional campaign without animation",
            "Create a promotional campaign, no video or motion",
            "Create a campaign, do not create an animation",
            "Create a campaign but don't animate the winner",
            "Create a campaign and never produce videos",
        ]:
            plan = build_plan(brief, media=["product.jpg"])
            self.assertNotIn("generate-selected", [stage.action for stage in plan.stages])
        for brief in [
            "Create a campaign and turn the winner into videos",
            "Create a campaign with animations of the best image",
            "Create a campaign with no video but animate the winner",
        ]:
            plan = build_plan(brief, media=["product.jpg"])
            self.assertIn("generate-selected", [stage.action for stage in plan.stages])

    def test_video_count_produces_the_declared_number_of_jobs(self):
        plan = build_plan("Create three cinematic clips", workflow="video", count=3)
        self.assertEqual(plan.count, 3)
        self.assertEqual(plan.estimated_jobs, 3)
        self.assertEqual(len(plan.stages), 3)

    def test_pink_product_does_not_trigger_pin_mode(self):
        plan = build_plan("Studio catalog photo of my pink candle", media=["candle.jpg"])
        self.assertEqual(plan.mode, "product_shot")

    def test_product_terms_do_not_match_video_or_ads_inside_other_words(self):
        cases = [
            "Create a promotional product photo of my serum",
            "Create a clean product photo of a paperclip",
            "Create a clean product photo of glass beads",
        ]
        for brief in cases:
            plan = build_plan(brief, media=["product.jpg"])
            self.assertEqual(plan.workflow, "product-photoshoot")
            self.assertNotEqual(plan.mode, "ad_creative_pack")

    def test_explicit_unknown_workflow_is_rejected(self):
        with self.assertRaises(PlanError):
            build_plan("x", workflow="invented-super-agent")

    def test_duration_is_validated_for_selected_video_backend(self):
        with self.assertRaises(PlanError):
            build_plan("make a cinematic video", duration=2)
        with self.assertRaises(PlanError):
            build_plan("animate this photo", media=["still.jpg"], duration=20)

    def test_plan_commands_are_argv_not_shell_strings(self):
        plan = build_plan('Poster with "quoted text" and $HOME', workflow="image")
        self.assertIsInstance(plan.stages[0].command, list)
        self.assertEqual(plan.stages[0].command[0], "kie-media")
        self.assertIn('$HOME', plan.stages[0].prompt)


class AgentExecutionTests(unittest.TestCase):
    def test_execute_runs_generation_stages_then_stops_at_review_gate(self):
        plan = build_plan("Create two campaign images and animate the best", count=2)
        calls = []

        def runner(command):
            calls.append(command)
            return {"task_id": f"task-{len(calls)}", "state": "success", "files": [f"image-{len(calls)}.jpg"]}

        result = execute_plan(plan, runner=runner)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["state"], "awaiting_review")
        self.assertEqual(len(result["results"]), 2)

    def test_resume_skips_completed_paid_stages(self):
        plan = build_plan("Two icon variants", workflow="image", count=2)
        first_calls = []
        first = execute_plan(plan, runner=lambda command: first_calls.append(command) or {"task_id": f"t-{len(first_calls)}", "state": "success"})
        resumed_calls = []
        resumed = execute_plan(plan, runner=lambda command: resumed_calls.append(command) or {}, prior_execution=first)
        self.assertEqual(first["state"], "completed")
        self.assertEqual(resumed["state"], "completed")
        self.assertEqual(resumed_calls, [])

    def test_interrupted_running_stage_requires_recovery_not_duplicate_job(self):
        plan = build_plan("One icon", workflow="image")
        calls = []
        prior = {"state": "running", "running_stage": "image-1", "results": []}
        result = execute_plan(plan, runner=lambda command: calls.append(command) or {}, prior_execution=prior)
        self.assertEqual(result["state"], "needs_recovery")
        self.assertEqual(result["running_stage"], "image-1")
        self.assertEqual(calls, [])

    def test_checkpoint_is_written_before_paid_stage_and_after_result(self):
        plan = build_plan("One icon", workflow="image")
        events = []

        def checkpoint(state):
            events.append(("checkpoint", state.get("running_stage"), len(state["results"])))

        def runner(_command):
            events.append(("runner", "image-1", 0))
            return {"task_id": "t-1", "state": "success"}

        result = execute_plan(plan, runner=runner, checkpoint=checkpoint)
        self.assertEqual(result["state"], "completed")
        self.assertLess(events.index(("checkpoint", "image-1", 0)), events.index(("runner", "image-1", 0)))
        self.assertIn(("checkpoint", None, 1), events)

    def test_checkpoint_failure_before_stage_prevents_paid_call(self):
        plan = build_plan("One icon", workflow="image")
        calls = []
        result = execute_plan(
            plan,
            runner=lambda command: calls.append(command) or {"state": "success"},
            checkpoint=lambda _state: (_ for _ in ()).throw(OSError("disk full")),
        )
        self.assertEqual(result["state"], "checkpoint_failed")
        self.assertFalse(result["checkpoint_after_paid"])
        self.assertEqual(calls, [])

    def test_campaign_resume_animates_only_selected_winner(self):
        plan = build_plan("Create two campaign images and animate the best", count=2)
        calls = []
        first = execute_plan(plan, runner=lambda command: calls.append(command) or {"task_id": f"t-{len(calls)}", "state": "success", "files": [f"image-{len(calls)}.jpg"]})
        self.assertEqual(first["state"], "awaiting_review")
        self.assertEqual(len(calls), 2)
        continued_calls = []
        continued = execute_plan(
            plan,
            runner=lambda command: continued_calls.append(command) or {"task_id": "video", "state": "success", "files": ["video.mp4"]},
            prior_execution=first,
            selected_file="image-1.jpg",
        )
        self.assertEqual(continued["state"], "completed")
        self.assertEqual(len(continued_calls), 1)
        self.assertIn("image-1.jpg", continued_calls[0])

    def test_execute_refuses_missing_input_or_hybrid_plan(self):
        for plan in [
            build_plan("animate this image"),
            build_plan("make a narrated explainer"),
        ]:
            with self.assertRaises(PlanError):
                execute_plan(plan, runner=lambda _: {})

    def test_later_stage_failure_preserves_earlier_results(self):
        plan = build_plan("Create three campaign visuals", count=3)
        calls = 0

        def runner(_command):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PlanError("simulated stage failure")
            return {"task_id": "task-1", "state": "success", "files": ["one.jpg"]}

        result = execute_plan(plan, runner=runner)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["failed_stage"], "campaign-image-2")
        self.assertEqual(len(result["results"]), 1)

    def test_manifest_is_private_and_contains_reproducible_plan(self):
        plan = build_plan("A square icon for an AI studio", workflow="image", aspect_ratio="1:1")
        with tempfile.TemporaryDirectory() as td:
            path = save_manifest(Path(td) / "run.json", plan, {"state": "planned", "results": []})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn('"workflow": "image"', path.read_text())

    def test_manifest_temp_file_is_private_during_write(self):
        plan = build_plan("A square icon", workflow="image")
        modes = []
        original_dump = json.dump

        def observe_dump(value, handle, **kwargs):
            modes.append(os.stat(handle.name).st_mode & 0o777)
            return original_dump(value, handle, **kwargs)

        with tempfile.TemporaryDirectory() as td, patch("kie_media.agent.json.dump", side_effect=observe_dump):
            save_manifest(Path(td) / "run.json", plan, {"state": "planned", "results": []})
        self.assertEqual(modes, [0o600])

    def test_manifest_roundtrip_has_plan_fingerprint_and_unique_default_names(self):
        plan = build_plan("A square icon", workflow="image")
        with tempfile.TemporaryDirectory() as td:
            plan.output_dir = td
            first = new_manifest_path(plan)
            second = new_manifest_path(plan)
            self.assertNotEqual(first, second)
            save_manifest(first, plan, {"state": "planned", "results": []})
            payload = load_manifest(first)
            self.assertEqual(payload["plan_fingerprint"], plan_fingerprint(plan))

    def test_manifest_lock_rejects_concurrent_paid_run(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "run.json"
            with manifest_lock(path):
                with self.assertRaises(PlanError):
                    with manifest_lock(path):
                        self.fail("second lock must not be acquired")
            self.assertEqual((Path(str(path) + ".lock").stat().st_mode & 0o777), 0o600)

    def test_manifest_lock_canonicalizes_symlink_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "run.json"
            alias = Path(td) / "alias.json"
            real.write_text("{}")
            alias.symlink_to(real)
            with manifest_lock(real):
                with self.assertRaises(PlanError):
                    with manifest_lock(alias):
                        self.fail("symlink alias must share the real manifest lock")

    def test_production_lock_blocks_same_plan_across_unique_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            plan = build_plan("One icon", workflow="image", output_dir=td)
            self.assertNotEqual(new_manifest_path(plan), new_manifest_path(plan))
            with production_lock(plan):
                with self.assertRaises(PlanError):
                    with production_lock(plan):
                        self.fail("same production plan must have one active paid runner")

    def test_selected_file_must_come_from_awaiting_review_manifest(self):
        plan = build_plan("Create two campaign images and animate the best", count=2)
        prior = {
            "state": "awaiting_review",
            "results": [{"stage_id": "campaign-image-1", "state": "success", "files": ["winner.jpg"]}],
        }
        with self.assertRaises(PlanError):
            execute_plan(plan, prior_execution=prior, selected_file="foreign.jpg", runner=lambda _: {})


if __name__ == "__main__":
    unittest.main()
