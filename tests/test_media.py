import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from kie_media.media import assemble_timeline, probe


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe required")
class MediaIntegrationTests(unittest.TestCase):
    def test_real_assembly_with_narration_music_and_captions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video, voice, music = root / "clip.mp4", root / "voice.wav", root / "music.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", str(video)], check=True)
            for target, frequency in [(voice, 440), (music, 220)]:
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=1.4", str(target)], check=True)
            from kie_media.projects import create_project, import_asset, project_plan, render_project
            project = root / "project.json"
            create_project(project, "Fixture", shots=1)
            with self.assertRaises(ValueError):
                import_asset(project, "scene-1.image", video)
            import_asset(project, "scene-1.video", video)
            plan = project_plan(project)
            self.assertEqual(plan["stages"][0]["state"], "not_required_imported_video")
            self.assertEqual(plan["pending_jobs"], 0)
            with self.assertRaisesRegex(ValueError, "Review required"):
                render_project(project)
            result = assemble_timeline([
                {"video": str(video), "voice": str(voice), "duration": 1, "narration": "First scene."},
                {"video": str(video), "duration": 1, "narration": "Second scene."},
            ], root / "result.mp4", aspect_ratio="9:16", music=str(music), captions=True)
            data = probe(Path(result["file"]))
            self.assertGreater(data["duration"], 2.3)
            self.assertEqual((data["width"], data["height"]), (720, 1280))
            self.assertTrue(data["audio"])
            self.assertTrue(Path(result["subtitles"]).is_file())
