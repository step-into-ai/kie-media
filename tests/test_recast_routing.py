import unittest

from kie_media.agent import build_plan


class RecastRoutingTests(unittest.TestCase):
    def test_existing_clip_changes_require_the_recast_workflow(self):
        for brief in ("Use Genjutsu to put my character in this video",
                      "Transfer motion from this clip to my photo",
                      "Tausche die Person in diesem Video aus",
                      "Restyle this video as watercolor"):
            with self.subTest(brief=brief):
                plan = build_plan(brief)
                self.assertEqual(plan.workflow, "recast")
                self.assertEqual(plan.estimated_jobs, 0)
                self.assertFalse(plan.executable)
                self.assertIn("recast plan", plan.route_reason)

    def test_ordinary_video_and_still_restyle_keep_their_routes(self):
        self.assertEqual(build_plan("Create a cinematic video of a forest").workflow, "video")
        self.assertEqual(build_plan("Restyle my product photo", media=["photo.png"]).workflow, "product-photoshoot")
